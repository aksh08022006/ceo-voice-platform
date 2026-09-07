"""FastAPI application wiring for browser product workflows."""

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ceo_voice.config import Settings, get_settings
from ceo_voice.core.constants import Environment
from ceo_voice.core.exceptions import ApplicationError, ConfigurationError
from ceo_voice.core.logging import configure_logging, request_context
from ceo_voice.generation import HttpxJsonTransport
from ceo_voice.generation.fidelity import FidelityReviewer
from ceo_voice.generation.fidelity_contracts import FidelityPolicy
from ceo_voice.models.communication import CommentContext
from ceo_voice.services import create_model_provider, load_published_profile_catalog
from ceo_voice.services.retrieval_ranking import ConfiguredRetrievalRanking
from ceo_voice.showcase import ShowcaseWorkflowService
from ceo_voice.showcase.continuation import ContinuationError, WorkflowContinuation
from ceo_voice.showcase.service import WorkflowSession
from ceo_voice.workspace import PostgresDatabase, WorkflowRepository
from ceo_voice.workspace.schema import SCHEMA_VERSION

from .authentication import AccessError, NeonIdentityReader, TokenVerifier, WorkspaceAccess
from .profile_analytics import project_profile_analytics
from .schemas import (
    ContinueWorkflowRequest,
    DimensionResponse,
    EvidenceResponse,
    GenerateWorkflowRequest,
    HealthResponse,
    MetricResponse,
    ProfileAnalyticsResponse,
    ProfileResponse,
    ReVoiceWorkflowRequest,
    WalkthroughResponse,
    WorkflowResponse,
)

DISCLAIMER = (
    "Showcase mode uses synthetic corpora. Model-disabled runs use a deterministic local provider; "
    "model-enabled runs use the configured external provider. Named profiles demonstrate workflow "
    "behavior and are not verified identity simulations."
)
PUBLISHED_DISCLAIMER = (
    "Generated from a governed immutable profile release and its traceable evidence. "
    "Human review remains required before publication."
)
DEVELOPMENT_DISCLAIMER = (
    "Evaluation-only output derived from manually transcribed public posts. Source timestamps, "
    "engagement metadata, reuse authority, and independent fidelity review are incomplete. It is "
    "not endorsed by the named person; human review is required before publication."
)


def create_app(
    settings: Settings | None = None,
    service: ShowcaseWorkflowService | None = None,
    *,
    workspace_access: WorkspaceAccess | None = None,
    workspace_repository: WorkflowRepository | None = None,
    fidelity_reviewer: FidelityReviewer | None = None,
) -> FastAPI:
    """Create an isolated application with injected configuration and workflow service."""

    resolved = settings or get_settings()
    transport: HttpxJsonTransport | None = None
    reviewer = fidelity_reviewer
    repository: WorkflowRepository | None = workspace_repository
    if service is not None:
        workflows = service
    elif resolved.api.published_profile_catalog is not None and not resolved.model.enabled:
        raise ConfigurationError("published profile serving requires model access to be enabled")
    elif resolved.model.enabled:
        if resolved.model.generation_model is None:
            raise ConfigurationError("enabled model configuration has no generation model")
        transport = HttpxJsonTransport(
            timeout_seconds=resolved.model.request_timeout_seconds,
        )
        provider = create_model_provider(resolved.model, transport)
        if resolved.workspace.enabled and reviewer is None:
            reviewer = FidelityReviewer(
                provider,
                policy=FidelityPolicy(
                    enabled=True,
                    failure_behavior="return_for_review",
                    model=resolved.workspace.fidelity_model or resolved.model.generation_model,
                ),
            )
        published_bundles = (
            load_published_profile_catalog(resolved.api.published_profile_catalog)
            if resolved.api.published_profile_catalog is not None
            else ()
        )
        if resolved.application.environment is Environment.PRODUCTION and any(
            bundle.artifact_status == "development" for bundle in published_bundles
        ):
            raise ConfigurationError("development profile artifacts are forbidden in production")
        workflows = ShowcaseWorkflowService(
            artifact_storage=resolved.api.artifact_storage,
            provider=provider,
            model=resolved.model.generation_model,
            model_context_tokens=resolved.model.context_window_tokens,
            maximum_output_tokens=resolved.model.maximum_output_tokens,
            maximum_provider_retries=(
                0 if resolved.workspace.enabled else resolved.model.max_retries
            ),
            fidelity_reviewer=reviewer,
            published_bundles=published_bundles,
            retrieval_ranking=ConfiguredRetrievalRanking(
                resolved.retrieval, resolved.model, transport
            ),
        )
    else:
        workflows = ShowcaseWorkflowService(
            artifact_storage=resolved.api.artifact_storage,
            retrieval_ranking=ConfiguredRetrievalRanking(resolved.retrieval, resolved.model),
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(
            level=resolved.logging.level,
            output_format=resolved.logging.format,
            service_name=resolved.application.service_name,
        )
        if resolved.workspace.enabled and repository is not None:
            await run_in_threadpool(_verify_workspace_schema, repository)
        yield
        if transport is not None:
            await transport.aclose()

    application = FastAPI(
        title="CEO Voice Platform API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    application.state.workflows = workflows
    application.state.settings = resolved
    continuation = (
        WorkflowContinuation(
            resolved.api.continuation_key.get_secret_value(),
            workflows.published_bundles,
            ttl_seconds=resolved.api.continuation_ttl_seconds,
        )
        if resolved.api.continuation_key is not None and workflows.published_bundles
        else None
    )

    def project(session: WorkflowSession) -> WorkflowResponse:
        result = _project(session)
        if continuation is not None:
            result.continuation_token = continuation.seal(session)
            result.continuation_expires_in_seconds = resolved.api.continuation_ttl_seconds
        return result

    def resume(session_id: UUID, token: str | None) -> WorkflowSession:
        if continuation is None:
            return _session_or_404(workflows, session_id)
        if token is None:
            raise HTTPException(
                status_code=401,
                detail="This workflow requires its continuation token from the original browser tab.",
            )
        try:
            return workflows.resume(continuation.open(token, session_id))
        except ContinuationError as exc:
            raise HTTPException(status_code=410, detail=exc.message) from exc

    access = workspace_access
    if resolved.workspace.enabled:
        from .editor import create_editor_router

        if continuation is None or reviewer is None:
            raise ConfigurationError(
                "workspace requires published profiles, continuation and claim review"
            )
        assert resolved.workspace.database_url is not None
        assert resolved.workspace.encryption_key is not None
        repository = workspace_repository or WorkflowRepository(
            PostgresDatabase(resolved.workspace.database_url.get_secret_value())
        )
        access = access or WorkspaceAccess(
            resolved.workspace,
            repository,
            NeonIdentityReader(resolved.workspace.database_url.get_secret_value()),
            TokenVerifier(resolved.workspace),
        )
        application.state.workspace_repository = repository
        application.include_router(
            create_editor_router(
                repository=repository,
                service=workflows,
                continuation=continuation,
                reviewer=reviewer,
                encryption_key=resolved.workspace.encryption_key.get_secret_value(),
                workspace_id=resolved.workspace.workspace_id,
                allowed_profiles=resolved.workspace.allowed_profiles,
                maximum_runs_per_hour=resolved.workspace.maximum_runs_per_hour,
                run_lease_seconds=resolved.workspace.run_lease_seconds,
            )
        )

    @application.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied_identifier = request.headers.get("X-Request-ID", "")
        identifier = (
            supplied_identifier
            if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", supplied_identifier)
            else uuid4().hex
        )
        response: Response
        with request_context(identifier):
            try:
                protected = (
                    resolved.workspace.enabled
                    and request.url.path.startswith("/api/v1/")
                    and request.url.path != "/api/v1/health"
                )
                if protected and request.method != "OPTIONS":
                    assert access is not None
                    request.state.actor = await run_in_threadpool(
                        access.authorize, request.headers.get("Authorization")
                    )
                    if request.url.path.startswith("/api/v1/workflows"):
                        response = JSONResponse(
                            status_code=410,
                            content={
                                "detail": "Open the saved editor workspace to create or revise drafts."
                            },
                        )
                    else:
                        response = await call_next(request)
                else:
                    response = await call_next(request)
            except AccessError as exc:
                response = JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})
        response.headers["X-Request-ID"] = identifier
        if request.url.path.startswith("/api/v1/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(ApplicationError)
    async def application_error_handler(_: Request, error: ApplicationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=error.to_dict())

    @application.get("/api/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=resolved.application.service_name,
            showcase_enabled=resolved.api.showcase_enabled,
            model_enabled=resolved.model.enabled,
            model_provider=resolved.model.provider if resolved.model.enabled else None,
            mode=workflows.mode,
            profile_count=len(workflows.profiles),
        )

    @application.get("/api/v1/profiles", response_model=tuple[ProfileResponse, ...])
    async def profiles() -> tuple[ProfileResponse, ...]:
        return tuple(
            ProfileResponse(
                slug=item.slug,
                name=item.name,
                role=item.role,
                summary=item.summary,
                status=item.status,
            )
            for item in workflows.profiles
        )

    @application.get(
        "/api/v1/profiles/{profile_slug}/analytics",
        response_model=ProfileAnalyticsResponse,
    )
    async def profile_analytics(profile_slug: str) -> ProfileAnalyticsResponse:
        """Expose aggregate HVM evidence and governance without returning source content."""

        try:
            bundle = workflows.published_bundle(profile_slug)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail="published profile analytics not found",
            ) from exc
        return project_profile_analytics(bundle, workflows.published_bundles)

    @application.get("/api/v1/walkthroughs", response_model=tuple[WalkthroughResponse, ...])
    async def walkthroughs() -> tuple[WalkthroughResponse, ...]:
        return tuple(
            WalkthroughResponse(
                slug=item.slug,
                profile_slug=item.profile_slug,
                title=item.title,
                platform=item.platform,
                content_type=item.content_type,
                thread_post_count=item.thread_post_count,
                virality_influence=item.virality_influence,
                minimum_words=item.minimum_words,
                maximum_words=item.maximum_words,
                idea=item.idea,
                constraints=item.constraints,
                human_edit=item.human_edit,
                profile_name=next(
                    profile.name
                    for profile in workflows.profiles
                    if profile.slug == item.profile_slug
                ),
            )
            for item in workflows.walkthroughs
        )

    @application.post("/api/v1/workflows/generate", response_model=WorkflowResponse)
    async def generate(value: GenerateWorkflowRequest) -> WorkflowResponse:
        _ensure_available(resolved, workflows)
        try:
            session = await workflows.generate(
                profile_slug=value.profile_slug,
                platform=value.platform,
                content_type=value.content_type,
                comment_context=(
                    CommentContext(parent_post=value.parent_post, reply_intent=value.reply_intent)
                    if value.parent_post is not None and value.reply_intent is not None
                    else None
                ),
                idea=value.idea,
                expression=value.expression,
                constraints=(),
                thread_post_count=value.thread_post_count,
                virality_influence=value.virality_influence,
                minimum_words=value.minimum_words,
                maximum_words=value.maximum_words,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return project(session)

    @application.get("/api/v1/workflows/{session_id}", response_model=WorkflowResponse)
    async def get_workflow(session_id: UUID) -> WorkflowResponse:
        return project(resume(session_id, None))

    @application.post("/api/v1/workflows/{session_id}/resume", response_model=WorkflowResponse)
    async def resume_workflow(session_id: UUID, value: ContinueWorkflowRequest) -> WorkflowResponse:
        return project(resume(session_id, value.continuation_token))

    @application.post("/api/v1/workflows/{session_id}/revoice", response_model=WorkflowResponse)
    async def revoice(session_id: UUID, value: ReVoiceWorkflowRequest) -> WorkflowResponse:
        session = resume(session_id, value.continuation_token)
        if (
            value.expected_revision is not None
            and value.expected_revision != session.revision_count
        ):
            raise HTTPException(
                status_code=409,
                detail="A newer revision is available. Reload the current draft before re-voicing.",
            )
        return project(await workflows.revoice(session_id, value.content, value.editor_note))

    @application.post("/api/v1/workflows/{session_id}/evaluate", response_model=WorkflowResponse)
    async def evaluate(
        session_id: UUID, value: ContinueWorkflowRequest | None = None
    ) -> WorkflowResponse:
        resume(session_id, value.continuation_token if value else None)
        return project(await workflows.evaluate(session_id))

    # CORS must also wrap authentication failures so the separate frontend can read 401/403.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.api.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID", "Authorization", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],
    )
    return application


def _verify_workspace_schema(repository: WorkflowRepository) -> None:
    """Check the deployed dependency without migrating or creating records at startup."""
    with repository.database.transaction() as transaction:
        versions = transaction.all("SELECT version FROM cv_schema_migrations")
    if {row["version"] for row in versions} != {SCHEMA_VERSION}:
        raise ConfigurationError("workspace database requires its explicit schema migration")


def _ensure_available(settings: Settings, service: ShowcaseWorkflowService) -> None:
    if service.mode == "showcase" and not settings.api.showcase_enabled:
        raise HTTPException(status_code=404, detail="showcase mode is disabled")


def _session_or_404(service: ShowcaseWorkflowService, session_id: UUID) -> WorkflowSession:
    try:
        return service.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow session not found") from exc


def _project(session: WorkflowSession) -> WorkflowResponse:
    artifacts = session.outcome.artifacts
    if artifacts.draft is None or artifacts.retrieval is None:
        raise RuntimeError("successful workflow session has incomplete artifacts")
    draft, retrieval = artifacts.draft, artifacts.retrieval
    report = draft.report
    evaluation = session.evaluation
    revoice = session.revoiced
    comment = artifacts.context.intent.comment_context if artifacts.context else None
    revoice_attempts = revoice.report.attempts if revoice else ()
    last_revoice_validation = revoice_attempts[-1].validation if revoice_attempts else None
    voice = tuple(
        EvidenceResponse(
            id=item.evidence_id,
            label=(
                item.explanation.supporting_feature_ids[0]
                if item.explanation.supporting_feature_ids
                else "voice evidence"
            ),
            confidence=item.score.final_score,
            source=str(item.document_id),
            reason=item.explanation.reason,
        )
        for item in retrieval.evidence
        if item.explanation.supporting_feature_ids
    )
    structure = tuple(
        EvidenceResponse(
            id=item.evidence_id,
            label="structural pattern",
            confidence=item.score.final_score,
            source=str(item.document_id),
            reason=item.explanation.reason,
        )
        for item in retrieval.evidence
        if item.explanation.supporting_pattern_ids
    )
    return WorkflowResponse(
        session_id=session.id,
        expression=artifacts.context.intent.expression if artifacts.context else None,
        expression_profile=(
            artifacts.context.intent.expression_profile if artifacts.context else None
        ),
        revision_count=session.revision_count,
        current_candidate_id=revoice.id if revoice else draft.id,
        profile_slug=session.profile.slug,
        profile_name=session.profile.name,
        platform=artifacts.context.platform.platform.value if artifacts.context else "unknown",
        platform_maximum_characters=(
            artifacts.context.platform.maximum_characters if artifacts.context else 1
        ),
        content_type=artifacts.context.intent.content_type.value if artifacts.context else "post",
        virality_influence=artifacts.context.virality.influence if artifacts.context else 0.0,
        content_kind="comment" if comment else "original_post",
        parent_post=comment.parent_post if comment else None,
        reply_intent=comment.reply_intent if comment else None,
        thread=revoice.thread if revoice else draft.thread,
        content=draft.content,
        edited_content=session.edited.content if session.edited else None,
        revoiced_content=revoice.content if revoice else None,
        report=(
            MetricResponse(label="Model", value=report.model),
            MetricResponse(label="Latency", value=f"{report.total_latency_ms} ms"),
            MetricResponse(
                label="Tokens",
                value=str(report.total_usage.input_tokens + report.total_usage.output_tokens),
            ),
            MetricResponse(
                label="Mechanical checks",
                value="Passed" if report.final_validation.valid else "Failed",
            ),
        ),
        voice_features=voice,
        structural_features=structure,
        evidence_count=len(retrieval.evidence),
        timeline=tuple(
            MetricResponse(
                label=item.stage.value.replace("_", " ").title(), value=f"{item.duration_ms} ms"
            )
            for item in session.outcome.timeline
        ),
        changed_regions=revoice.report.changed_regions if revoice else (),
        preserved=tuple(item.subject for item in revoice.report.preserved) if revoice else (),
        revoice_confidence=revoice.report.confidence if revoice else None,
        revoice_applied=bool(revoice.report.changed_regions) if revoice else None,
        revoice_fallback_used=(
            bool(last_revoice_validation and not last_revoice_validation.valid) if revoice else None
        ),
        revoice_attempt_count=len(revoice_attempts) if revoice else None,
        evaluation_score=round(evaluation.overall_score * 100, 1) if evaluation else None,
        evaluation_status=evaluation.status.value if evaluation else None,
        dimensions=(
            tuple(
                DimensionResponse(
                    label=item.dimension.value.replace("_", " ").title(),
                    score=round(item.score * 100, 1),
                    passed=item.passed,
                    summary=item.summary,
                )
                for item in evaluation.dimensions
            )
            if evaluation
            else ()
        ),
        recommendations=evaluation.recommended_improvements if evaluation else (),
        disclaimer=(
            PUBLISHED_DISCLAIMER
            if session.profile.status == "published"
            else (DEVELOPMENT_DISCLAIMER if session.profile.status == "development" else DISCLAIMER)
        ),
    )


app = create_app()
