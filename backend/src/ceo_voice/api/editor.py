"""Authenticated durable editor; model work is fenced before external dispatch."""

import json
from collections.abc import Callable, Coroutine
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

from ceo_voice.api.authentication import Actor
from ceo_voice.api.editor_schemas import (
    EditorApprovalRequest,
    EditorCursor,
    EditorEditRequest,
    EditorGenerateRequest,
    EditorRestoreRequest,
    EditorState,
    ExpectedRevision,
    StoredApprovalNote,
)
from ceo_voice.api.editor_storage import EditorStateCodec, revision_id
from ceo_voice.core.exceptions import ApplicationError
from ceo_voice.generation.fidelity import FidelityReviewer
from ceo_voice.generation.fidelity_contracts import BriefSource
from ceo_voice.models.communication import CommentContext
from ceo_voice.models.enums import Platform
from ceo_voice.prompts import THREAD_SEPARATOR
from ceo_voice.retrieval.enums import EvidencePurpose
from ceo_voice.showcase.continuation import WorkflowContinuation
from ceo_voice.showcase.service import ShowcaseWorkflowService
from ceo_voice.utils import utc_now
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.workspace.contracts import (
    ReviewRecord,
    RevisionRecord,
    RunReservation,
    WorkspaceScope,
)
from ceo_voice.workspace.errors import (
    ApprovalConflict,
    RevisionConflict,
    WorkspaceNotFound,
    WorkspaceQuotaExceeded,
)
from ceo_voice.workspace.repository import WorkflowRepository

EDIT_ROLES = {"owner", "admin", "editor"}
APPROVE_ROLES = {"owner", "admin", "reviewer"}
MAX_REGENERATIONS = 3


def canonical_brief(request: EditorGenerateRequest) -> str:
    """Actual generator input contains complete supplied facts, not just their URLs."""
    parts = [request.idea]
    if request.constraints:
        parts.append("Explicit brief constraints:\n" + "\n".join(request.constraints))
    for index, source in enumerate(request.sources):
        parts.append(
            f"Factual source supplied by editor {index + 1}: {source.title}\n"
            + (f"Attribution: {source.attribution}\n" if source.attribution else "")
            + source.text
        )
    return "\n\n".join(parts).strip()


def brief_hash(request: EditorGenerateRequest) -> str:
    return sha256_text(
        json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    )


def request_sources(request: EditorGenerateRequest) -> tuple[BriefSource, ...]:
    sources = [
        BriefSource(source_id="request.topic", authority="brief", text=canonical_brief(request))
    ]
    sources.extend(
        BriefSource(source_id=f"request.constraint.{i}", authority="constraint", text=t)
        for i, t in enumerate(request.constraints)
    )
    sources.extend(
        BriefSource(source_id=f"editor.source.{i}", authority="factual_source", text=s.text)
        for i, s in enumerate(request.sources)
    )
    if request.parent_post:
        sources.append(
            BriefSource(
                source_id="comment.parent_post",
                authority="attributed_context",
                text=request.parent_post,
            )
        )
    return tuple(sources)


def format_valid(request: EditorGenerateRequest, content: str) -> bool:
    posts = content.split(THREAD_SEPARATOR)
    maximum = 280 if request.platform is Platform.X else 3000
    expected = request.thread_post_count or 1
    words = len(content.split())
    return (
        bool(content.strip())
        and "\x00" not in content
        and len(posts) == expected
        and all(p.strip() and len(p) <= maximum for p in posts)
        and (request.minimum_words is None or words >= request.minimum_words)
        and (request.maximum_words is None or words <= request.maximum_words)
    )


class EditorRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except WorkspaceNotFound as exc:
                raise HTTPException(404, "Draft not found in this workspace.") from exc
            except ApplicationError as exc:
                status = 429 if isinstance(exc, WorkspaceQuotaExceeded) else 409
                if exc.code in {"storage_error", "configuration_error"}:
                    status = 503
                raise HTTPException(status, str(exc)) from exc

        return handler


class EditorBackend:
    def __init__(
        self,
        *,
        repository: WorkflowRepository,
        service: ShowcaseWorkflowService,
        continuation: WorkflowContinuation,
        reviewer: FidelityReviewer,
        encryption_key: str,
        workspace_id: str,
        allowed_profiles: tuple[str, ...],
        maximum_runs_per_hour: int = 30,
        run_lease_seconds: int = 240,
    ) -> None:
        self.repository, self.service, self.continuation, self.reviewer = (
            repository,
            service,
            continuation,
            reviewer,
        )
        self.codec = EditorStateCodec(encryption_key)
        self.workspace_id, self.allowed_profiles = workspace_id, frozenset(allowed_profiles)
        self.maximum_runs_per_hour, self.run_lease_seconds = (
            maximum_runs_per_hour,
            run_lease_seconds,
        )
        if not reviewer.policy.enabled or reviewer.policy.failure_behavior != "return_for_review":
            raise ValueError("editor requires an enabled reviewer that retains blocked drafts")

    def actor(self, request: Request, action: Literal["read", "edit", "approve"] = "read") -> Actor:
        value = getattr(request.state, "actor", None)
        if not isinstance(value, Actor):
            raise HTTPException(401, "Sign in to access this workspace.")
        if value.workspace_id != self.workspace_id:
            raise HTTPException(403, "This account cannot access this workspace.")
        member = self.repository.get_member(self.workspace_id, value.id)
        if member is None or not member.active:
            raise HTTPException(403, "Workspace access is not active.")
        if (action == "edit" and member.role not in EDIT_ROLES) or (
            action == "approve" and member.role not in APPROVE_ROLES
        ):
            raise HTTPException(403, "Your workspace role does not allow this action.")
        return value.model_copy(update={"role": member.role})

    def profile(self, slug: str) -> None:
        if slug not in self.allowed_profiles or slug not in {p.slug for p in self.service.profiles}:
            raise HTTPException(403, "This profile is not authorized for the workspace.")

    @staticmethod
    def scope(actor: Actor) -> WorkspaceScope:
        return WorkspaceScope(workspace_id=actor.workspace_id, user_id=actor.id)

    def current(self, actor: Actor, workflow_id: UUID) -> tuple[RevisionRecord, EditorState]:
        workflow = self.repository.get_workflow(actor.workspace_id, workflow_id)
        self.profile(workflow.profile_slug)
        record = self.repository.get_revision(actor.workspace_id, workflow_id)
        state = self.codec.open(record)
        if state.profile_slug != workflow.profile_slug or state.brief_sha256 != brief_hash(
            state.request
        ):
            raise RevisionConflict("stored draft brief or profile binding is invalid")
        return record, state

    @staticmethod
    def expected(record: RevisionRecord, expected_id: UUID) -> None:
        if revision_id(record.workflow_id, record.revision) != expected_id:
            raise RevisionConflict(
                "A newer revision is available. Reload before changing this draft."
            )

    def approval(
        self, actor: Actor, record: RevisionRecord, state: EditorState
    ) -> dict[str, Any] | None:
        try:
            approved_record, review = self.repository.get_approved_revision(
                actor.workspace_id, record.workflow_id
            )
        except ApprovalConflict:
            return None
        return (
            self.approval_view(review, state)
            if approved_record.revision == record.revision
            else None
        )

    @staticmethod
    def approval_view(review: ReviewRecord, state: EditorState) -> dict[str, Any]:
        try:
            note = StoredApprovalNote.model_validate_json(review.note)
            display_name, text = note.display_name, note.note
            reviewed_claim_ids = note.reviewed_claim_ids
        except ValueError:
            display_name, text = review.reviewer_user_id, review.note
            reviewed_claim_ids = ()
        return {
            "id": str(review.id),
            "revision_id": str(revision_id(review.workflow_id, review.revision)),
            "content_sha256": review.candidate_sha256,
            "brief_sha256": state.brief_sha256,
            "review_run_id": str(review.review_run_id),
            "reviewer": {"id": review.reviewer_user_id, "display_name": display_name},
            "note": text,
            "approved_at": review.created_at.isoformat(),
            "reviewed_claim_ids": list(reviewed_claim_ids),
        }

    @staticmethod
    def revision_view(record: RevisionRecord, state: EditorState) -> dict[str, Any]:
        return {
            "id": str(revision_id(record.workflow_id, record.revision)),
            "number": record.revision + 1,
            "parent_revision_id": (
                str(revision_id(record.workflow_id, record.revision - 1))
                if record.revision
                else None
            ),
            "content": state.content,
            "content_sha256": record.candidate_sha256,
            "brief_sha256": state.brief_sha256,
            "created_at": record.created_at.isoformat(),
            "created_by": {"id": state.created_by_id, "display_name": state.created_by_name},
            "kind": state.kind,
        }

    def cursor_offset(
        self,
        actor: Actor,
        token: str | None,
        kind: Literal["drafts", "revisions"],
        workflow_id: UUID | None = None,
        head_revision: int | None = None,
    ) -> int:
        if token is None:
            return 0
        cursor = self.codec.open_cursor(token)
        if (cursor.workspace_id, cursor.kind, cursor.workflow_id, cursor.head_revision) != (
            actor.workspace_id,
            kind,
            workflow_id,
            head_revision,
        ):
            raise RevisionConflict(
                "Pagination belongs to a different list or older head. Reload it."
            )
        return cursor.offset

    def history(
        self,
        actor: Actor,
        record: RevisionRecord,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        offset = self.cursor_offset(actor, cursor, "revisions", record.workflow_id, record.revision)
        records = self.repository.list_revisions(
            actor.workspace_id, record.workflow_id, limit=limit + 1, offset=offset
        )
        return {
            "revisions": [self.revision_view(r, self.codec.open(r)) for r in records[:limit]],
            "next_cursor": (
                self.codec.seal_cursor(
                    EditorCursor(
                        kind="revisions",
                        workspace_id=actor.workspace_id,
                        workflow_id=record.workflow_id,
                        head_revision=record.revision,
                        offset=offset + limit,
                    )
                )
                if len(records) > limit
                else None
            ),
        }

    @staticmethod
    def source_view(source: BriefSource, state: EditorState) -> dict[str, Any]:
        originals = {f"editor.source.{i}": s for i, s in enumerate(state.request.sources)}
        original = originals.get(source.source_id)
        titles = {
            "attributed_context": "Attributed parent post",
            "brief": "Authoritative editor brief",
            "constraint": "Explicit brief constraint",
            "factual_source": "Supplied factual source",
        }
        return {
            "id": source.source_id,
            "title": original.title if original else titles[source.authority],
            "text": source.text,
            "url": original.url if original else None,
            "attribution": (
                original.attribution
                if original
                else (
                    "Parent author; underlying claim is unverified"
                    if source.authority == "attributed_context"
                    else None
                )
            ),
        }

    def view(
        self, actor: Actor, workflow_id: UUID, *, include_history: bool = True
    ) -> dict[str, Any]:
        record, state = self.current(actor, workflow_id)
        review = state.fidelity_review
        approval = self.approval(actor, record, state)
        gate = (
            "approved"
            if approval
            else (
                "review_pending"
                if review is None
                else (
                    "unavailable"
                    if review.status == "error"
                    else "blocked" if not record.review_eligible else "needs_review"
                )
            )
        )
        messages = {
            "approved": "This exact revision has named human approval.",
            "review_pending": "Run claim review after saving your changes.",
            "unavailable": "Claim review is unavailable. This draft remains editable and cannot be approved or exported.",
            "blocked": "Correct unsupported claims or format limits, then run claim review again.",
            "needs_review": "The model review found no blocking claims. A named reviewer must still approve this revision.",
        }
        claims = []
        if review and review.assessment:
            for unit in review.assessment.units:
                for index, claim in enumerate(unit.claims):
                    span = {**claim.span.model_dump(), "offset_unit": "unicode_code_points"}
                    claims.append(
                        {
                            "id": f"{state.review_run_id}:{unit.unit_id}:{index}",
                            "revision_id": str(revision_id(workflow_id, record.revision)),
                            "span": span,
                            "state": claim.verdict,
                            "reason": claim.reason,
                            "citations": [
                                {
                                    "source_id": c.source_id,
                                    "span": {
                                        "start": c.start,
                                        "end": c.end,
                                        "text": c.text,
                                        "offset_unit": "unicode_code_points",
                                    },
                                }
                                for c in claim.citations
                            ],
                            "human_resolution": None,
                        }
                    )
        history = (
            self.history(actor, record)
            if include_history
            else {"revisions": [], "next_cursor": None}
        )
        return {
            "id": str(workflow_id),
            "profile_slug": state.profile_slug,
            "profile_name": state.profile_name,
            "platform": state.request.platform.value,
            "content_type": state.request.content_type.value,
            "content_kind": state.request.content_kind,
            "thread_post_count": state.request.thread_post_count,
            "minimum_words": state.request.minimum_words,
            "maximum_words": state.request.maximum_words,
            "brief": {
                "id": str(state.brief_id),
                "content_sha256": state.brief_sha256,
                "idea": state.request.idea,
                "constraints": list(state.request.constraints),
                "sources": [self.source_view(source, state) for source in state.review_sources],
                "parent_post": state.request.parent_post,
                "reply_intent": (
                    state.request.reply_intent.value if state.request.reply_intent else None
                ),
            },
            "current_revision": self.revision_view(record, state),
            "revisions": history["revisions"],
            "revisions_cursor": history["next_cursor"],
            "review": {
                "state": gate,
                "review_run_id": str(state.review_run_id) if state.review_run_id else None,
                "revision_id": str(revision_id(workflow_id, record.revision)),
                "content_sha256": record.candidate_sha256,
                "brief_sha256": state.brief_sha256,
                "can_approve": bool(
                    record.review_eligible and not approval and actor.role in APPROVE_ROLES
                ),
                "message": messages[gate],
                "claims": claims,
                "regeneration_attempts_remaining": max(
                    0, MAX_REGENERATIONS - state.regeneration_count
                ),
                "approval": approval,
            },
        }

    def reserve(
        self,
        actor: Actor,
        *,
        key: str,
        body: dict[str, Any],
        operation: Literal["generate", "revoice", "review"],
        profile_slug: str | None = None,
        record: RevisionRecord | None = None,
    ) -> RunReservation:
        if not 1 <= len(key) <= 160 or any(c.isspace() for c in key):
            raise HTTPException(422, "A bounded Idempotency-Key is required.")
        reservation = self.repository.reserve_run(
            self.scope(actor),
            idempotency_key=key,
            operation=operation,
            request_sha256=sha256_text(json.dumps(body, sort_keys=True, separators=(",", ":"))),
            profile_slug=profile_slug,
            workflow_id=record.workflow_id if record else None,
            expected_revision=record.revision if record else None,
            lease_seconds=self.run_lease_seconds,
            maximum_runs_per_hour=self.maximum_runs_per_hour,
        )
        if reservation.disposition == "existing" and reservation.run.state != "completed":
            raise RevisionConflict(
                "This operation is already pending or has an unresolved outcome. It will not be dispatched twice."
            )
        return reservation

    def repeated(
        self, actor: Actor, workflow_id: UUID, key: str, body: dict[str, Any], operation: str
    ) -> dict[str, Any] | None:
        """A lost response can be retried after its original head has advanced."""
        try:
            run = self.repository.get_run(
                self.scope(actor),
                key,
                request_sha256=sha256_text(json.dumps(body, sort_keys=True, separators=(",", ":"))),
            )
        except WorkspaceNotFound:
            return None
        if run.workflow_id != workflow_id or run.operation != operation:
            raise RevisionConflict("Idempotency-Key belongs to a different operation.")
        if run.state == "reserved" and run.lease_expires_at <= utc_now():
            return None
        if run.state != "completed":
            raise RevisionConflict(
                "This operation is already pending or has an unresolved outcome. It will not be dispatched twice."
            )
        return self.view(actor, workflow_id)

    async def dispatch(
        self,
        actor: Actor,
        reservation: RunReservation,
        action: Callable[[], Coroutine[Any, Any, EditorState]],
    ) -> dict[str, Any]:
        if reservation.disposition == "existing":
            return await run_in_threadpool(self.view, actor, reservation.run.workflow_id)
        assert reservation.lease_token is not None
        scope = self.scope(actor)
        await run_in_threadpool(
            self.repository.mark_dispatched, scope, reservation.run.id, reservation.lease_token
        )
        try:
            state = await action()
            snapshot = await run_in_threadpool(self.codec.seal, state)
            await run_in_threadpool(
                self.repository.complete_run,
                scope,
                reservation.run.id,
                reservation.lease_token,
                snapshot,
            )
        except Exception:
            # A provider or persistence failure after dispatch can have unknown billing/result.
            await run_in_threadpool(
                self.repository.fail_run,
                scope,
                reservation.run.id,
                reservation.lease_token,
                error_code="editor_operation_unresolved",
                uncertain=True,
            )
            raise
        return await run_in_threadpool(self.view, actor, reservation.run.workflow_id)

    async def generated(
        self,
        actor: Actor,
        request: EditorGenerateRequest,
        reservation: RunReservation,
        previous: EditorState | None = None,
    ) -> EditorState:
        session = await self.service.generate(
            profile_slug=request.profile_slug,
            platform=request.platform,
            content_type=request.content_type.value,
            idea=canonical_brief(request),
            expression=request.expression,
            constraints=request.constraints,
            thread_post_count=request.thread_post_count,
            virality_influence=request.virality_influence,
            minimum_words=request.minimum_words,
            maximum_words=request.maximum_words,
            comment_context=(
                CommentContext(parent_post=request.parent_post, reply_intent=request.reply_intent)
                if request.parent_post and request.reply_intent
                else None
            ),
            reserved_session_id=reservation.run.workflow_id,
        )
        draft = session.outcome.artifacts.draft
        if draft is None:
            raise RevisionConflict("Generation produced no editable candidate.")
        review = draft.report.fidelity_review
        sources = list(request_sources(request))
        retrieval = session.outcome.artifacts.retrieval
        if retrieval:
            sources.extend(
                BriefSource(
                    source_id=f"factual:{item.evidence_id}",
                    authority="factual_source",
                    text=item.content,
                )
                for item in retrieval.evidence
                if EvidencePurpose.FACTUAL_SUPPORT in item.purposes
            )
        return EditorState(
            workspace_id=actor.workspace_id,
            workflow_id=session.id,
            revision_number=reservation.run.expected_revision + 1,
            profile_slug=request.profile_slug,
            profile_name=session.profile.name,
            brief_id=previous.brief_id if previous else uuid4(),
            brief_sha256=brief_hash(request),
            request=request,
            content=draft.content,
            continuation_token=self.continuation.seal(session),
            created_by_id=actor.id,
            created_by_name=actor.name,
            kind="generated",
            fidelity_review=review,
            review_run_id=reservation.run.id if review else None,
            regeneration_count=previous.regeneration_count + 1 if previous else 0,
            format_valid=draft.report.final_validation.valid
            and format_valid(request, draft.content),
            review_sources=tuple(sources),
        )

    async def reviewed(
        self, actor: Actor, state: EditorState, reservation: RunReservation
    ) -> EditorState:
        sources = request_sources(state.request)
        review = await self.reviewer.review_sources(
            state.content, request_id=reservation.run.id, sources=tuple(sources)
        )
        return state.model_copy(
            update={
                "revision_number": reservation.run.expected_revision + 1,
                "created_by_id": actor.id,
                "created_by_name": actor.name,
                "fidelity_review": review,
                "review_run_id": reservation.run.id,
                "format_valid": format_valid(state.request, state.content),
                "review_sources": sources,
            }
        )


def create_editor_router(
    *,
    repository: WorkflowRepository,
    service: ShowcaseWorkflowService,
    continuation: WorkflowContinuation,
    reviewer: FidelityReviewer,
    encryption_key: str,
    workspace_id: str,
    allowed_profiles: tuple[str, ...],
    maximum_runs_per_hour: int = 30,
    run_lease_seconds: int = 240,
) -> APIRouter:
    backend = EditorBackend(
        repository=repository,
        service=service,
        continuation=continuation,
        reviewer=reviewer,
        encryption_key=encryption_key,
        workspace_id=workspace_id,
        allowed_profiles=allowed_profiles,
        maximum_runs_per_hour=maximum_runs_per_hour,
        run_lease_seconds=run_lease_seconds,
    )
    router = APIRouter(prefix="/api/v1/workspace", route_class=EditorRoute)

    @router.get("/session")
    def session(request: Request) -> dict[str, Any]:
        actor = backend.actor(request)
        return {
            "id": actor.id,
            "display_name": actor.name,
            "email": actor.email,
            "can_edit": actor.role in EDIT_ROLES,
            "can_approve": actor.role in APPROVE_ROLES,
        }

    @router.get("/drafts")
    def drafts(
        request: Request,
        cursor: str | None = None,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        actor = backend.actor(request)
        offset = backend.cursor_offset(actor, cursor, "drafts")
        workflows = repository.list_workflows(actor.workspace_id, limit=limit + 1, offset=offset)
        result = []
        visible = backend.allowed_profiles & {p.slug for p in service.profiles}
        for workflow in workflows[:limit]:
            if workflow.head_revision < 0 or workflow.profile_slug not in visible:
                continue
            view = backend.view(actor, workflow.id, include_history=False)
            head = view["current_revision"]
            result.append(
                {
                    "id": str(workflow.id),
                    "title": view["brief"]["idea"][:100],
                    "profile_name": view["profile_name"],
                    "platform": view["platform"],
                    "content_kind": "comment" if view["brief"]["parent_post"] else "original_post",
                    "current_revision": head["number"],
                    "review_state": view["review"]["state"],
                    "updated_at": workflow.updated_at.isoformat(),
                    "updated_by": head["created_by"],
                }
            )
        return {
            "drafts": result,
            "next_cursor": (
                backend.codec.seal_cursor(
                    EditorCursor(
                        kind="drafts",
                        workspace_id=actor.workspace_id,
                        offset=offset + limit,
                    )
                )
                if len(workflows) > limit
                else None
            ),
        }

    @router.post("/drafts/generate")
    async def generate(
        request: Request, body: EditorGenerateRequest, idempotency_key: str = Header()
    ) -> dict[str, Any]:
        actor = await run_in_threadpool(backend.actor, request, "edit")
        backend.profile(body.profile_slug)
        if len(canonical_brief(body)) > 20_000:
            raise HTTPException(422, "The complete factual brief exceeds the review limit.")
        reservation = await run_in_threadpool(
            backend.reserve,
            actor,
            key=idempotency_key,
            body=body.model_dump(mode="json"),
            operation="generate",
            profile_slug=body.profile_slug,
        )
        return await backend.dispatch(
            actor, reservation, lambda: backend.generated(actor, body, reservation)
        )

    @router.get("/drafts/{workflow_id}")
    def current(request: Request, workflow_id: UUID) -> dict[str, Any]:
        return backend.view(backend.actor(request), workflow_id)

    @router.get("/drafts/{workflow_id}/revisions")
    def revisions(
        request: Request,
        workflow_id: UUID,
        cursor: str | None = None,
        limit: int = Query(default=100, ge=1, le=100),
    ) -> dict[str, Any]:
        actor = backend.actor(request)
        record, _ = backend.current(actor, workflow_id)
        return backend.history(actor, record, cursor=cursor, limit=limit)

    @router.post("/drafts/{workflow_id}/edit")
    def edit(request: Request, workflow_id: UUID, body: EditorEditRequest) -> dict[str, Any]:
        actor = backend.actor(request, "edit")
        record, state = backend.current(actor, workflow_id)
        backend.expected(record, body.expected_revision_id)
        next_state = state.model_copy(
            update={
                "revision_number": record.revision + 1,
                "content": body.content,
                "created_by_id": actor.id,
                "created_by_name": actor.name,
                "kind": "human_edit",
                "fidelity_review": None,
                "review_run_id": None,
                "format_valid": format_valid(state.request, body.content),
            }
        )
        repository.append_revision(
            backend.scope(actor),
            workflow_id,
            expected_revision=record.revision,
            snapshot=backend.codec.seal(next_state),
        )
        return backend.view(actor, workflow_id)

    @router.post("/drafts/{workflow_id}/restore")
    def restore(request: Request, workflow_id: UUID, body: EditorRestoreRequest) -> dict[str, Any]:
        actor = backend.actor(request, "edit")
        record, state = backend.current(actor, workflow_id)
        backend.expected(record, body.expected_revision_id)
        if revision_id(workflow_id, body.revision_number - 1) != body.revision_id:
            raise RevisionConflict("Restore must bind the exact revision number and ID.")
        prior = repository.get_revision(actor.workspace_id, workflow_id, body.revision_number - 1)
        original = backend.codec.open(prior)
        next_state = state.model_copy(
            update={
                "revision_number": record.revision + 1,
                "content": original.content,
                "created_by_id": actor.id,
                "created_by_name": actor.name,
                "kind": "restored",
                "fidelity_review": None,
                "review_run_id": None,
                "format_valid": format_valid(state.request, original.content),
            }
        )
        repository.append_revision(
            backend.scope(actor),
            workflow_id,
            expected_revision=record.revision,
            snapshot=backend.codec.seal(next_state),
        )
        return backend.view(actor, workflow_id)

    @router.post("/drafts/{workflow_id}/review")
    async def review(
        request: Request, workflow_id: UUID, body: ExpectedRevision, idempotency_key: str = Header()
    ) -> dict[str, Any]:
        actor = await run_in_threadpool(backend.actor, request, "edit")
        repeated = await run_in_threadpool(
            backend.repeated,
            actor,
            workflow_id,
            idempotency_key,
            body.model_dump(mode="json"),
            "review",
        )
        if repeated is not None:
            return repeated
        record, state = await run_in_threadpool(backend.current, actor, workflow_id)
        backend.expected(record, body.expected_revision_id)
        reservation = await run_in_threadpool(
            backend.reserve,
            actor,
            key=idempotency_key,
            body=body.model_dump(mode="json"),
            operation="review",
            record=record,
        )
        return await backend.dispatch(
            actor, reservation, lambda: backend.reviewed(actor, state, reservation)
        )

    @router.post("/drafts/{workflow_id}/regenerate")
    async def regenerate(
        request: Request, workflow_id: UUID, body: ExpectedRevision, idempotency_key: str = Header()
    ) -> dict[str, Any]:
        actor = await run_in_threadpool(backend.actor, request, "edit")
        repeated = await run_in_threadpool(
            backend.repeated,
            actor,
            workflow_id,
            idempotency_key,
            {"action": "regenerate", **body.model_dump(mode="json")},
            "revoice",
        )
        if repeated is not None:
            return repeated
        record, state = await run_in_threadpool(backend.current, actor, workflow_id)
        backend.expected(record, body.expected_revision_id)
        if state.regeneration_count >= MAX_REGENERATIONS:
            raise HTTPException(
                409, "This draft has reached its regeneration limit. Edit it directly."
            )
        if (
            state.fidelity_review is None
            or state.fidelity_review.status != "blocked"
            or state.fidelity_review.candidate_sha256 != record.candidate_sha256
        ):
            raise RevisionConflict(
                "Run a completed blocking claim review before revising flagged claims."
            )
        reservation = await run_in_threadpool(
            backend.reserve,
            actor,
            key=idempotency_key,
            body={"action": "regenerate", **body.model_dump(mode="json")},
            operation="revoice",
            record=record,
        )

        async def operation() -> EditorState:
            assert state.fidelity_review is not None
            proposal = await service.revise_editor(
                request_id=reservation.run.id,
                content=state.content,
                review=state.fidelity_review,
                sources=state.review_sources,
            )
            updated = state.model_copy(
                update={
                    "content": proposal.content,
                    "kind": "generated",
                    "revision_proposal": proposal,
                    "regeneration_count": state.regeneration_count + 1,
                }
            )
            return await backend.reviewed(actor, updated, reservation)

        return await backend.dispatch(actor, reservation, operation)

    @router.post("/drafts/{workflow_id}/revoice")
    async def revoice(
        request: Request, workflow_id: UUID, body: ExpectedRevision, idempotency_key: str = Header()
    ) -> dict[str, Any]:
        actor = await run_in_threadpool(backend.actor, request, "edit")
        repeated = await run_in_threadpool(
            backend.repeated,
            actor,
            workflow_id,
            idempotency_key,
            {"action": "revoice", **body.model_dump(mode="json")},
            "revoice",
        )
        if repeated is not None:
            return repeated
        record, state = await run_in_threadpool(backend.current, actor, workflow_id)
        backend.expected(record, body.expected_revision_id)
        reservation = await run_in_threadpool(
            backend.reserve,
            actor,
            key=idempotency_key,
            body={"action": "revoice", **body.model_dump(mode="json")},
            operation="revoice",
            record=record,
        )

        async def operation() -> EditorState:
            session = continuation.open_stored(state.continuation_token, workflow_id)
            service.resume(session)
            result = await service.revoice(workflow_id, state.content)
            if result.revoiced is None:
                raise RevisionConflict("Revoice produced no candidate.")
            candidate = result.revoiced.content
            updated = state.model_copy(
                update={
                    "content": candidate,
                    "continuation_token": continuation.seal(result),
                    "kind": "revoiced",
                }
            )
            return await backend.reviewed(actor, updated, reservation)

        return await backend.dispatch(actor, reservation, operation)

    @router.post("/drafts/{workflow_id}/approve")
    def approve(request: Request, workflow_id: UUID, body: EditorApprovalRequest) -> dict[str, Any]:
        actor = backend.actor(request, "approve")
        record, state = backend.current(actor, workflow_id)
        backend.expected(record, body.revision_id)
        if (
            state.brief_sha256 != body.brief_sha256
            or record.candidate_sha256 != body.content_sha256
            or record.review_run_id != body.review_run_id
            or not record.review_eligible
        ):
            raise ApprovalConflict(
                "Approval must match the current supported candidate, brief, and review run."
            )
        assessment = state.fidelity_review.assessment if state.fidelity_review else None
        claim_ids = (
            {
                f"{state.review_run_id}:{unit.unit_id}:{index}"
                for unit in assessment.units
                for index, _ in enumerate(unit.claims)
            }
            if assessment
            else set()
        )
        if not claim_ids or set(body.reviewed_claim_ids) != claim_ids:
            raise ApprovalConflict("Acknowledge every exact claim in this review before approval.")
        repository.record_review(
            backend.scope(actor),
            workflow_id,
            expected_revision=record.revision,
            candidate_sha256=body.content_sha256,
            review_run_id=body.review_run_id,
            decision="approved",
            note=StoredApprovalNote(
                display_name=actor.name,
                note=body.note,
                reviewed_claim_ids=body.reviewed_claim_ids,
            ).model_dump_json(),
        )
        return backend.view(actor, workflow_id)

    @router.get("/drafts/{workflow_id}/export")
    def export(request: Request, workflow_id: UUID) -> dict[str, str]:
        actor = backend.actor(request)
        backend.profile(repository.get_workflow(actor.workspace_id, workflow_id).profile_slug)
        record, _ = repository.get_approved_revision(actor.workspace_id, workflow_id)
        state = backend.codec.open(record)
        return {
            "content": state.content,
            "revision_id": str(revision_id(workflow_id, record.revision)),
        }

    return router
