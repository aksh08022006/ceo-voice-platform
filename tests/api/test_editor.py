"""Connected editor behavior with real SQL transactions and fake model responses."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from tests.api.test_continuation import deployment as deployment
from tests.unit.generation.test_engine import FakeProvider
from tests.unit.generation.test_fidelity import ReviewProvider

from ceo_voice.api.authentication import Actor
from ceo_voice.api.editor import create_editor_router
from ceo_voice.api.editor_storage import EditorStateCodec
from ceo_voice.generation.fidelity import FidelityReviewer
from ceo_voice.generation.fidelity_contracts import FidelityPolicy
from ceo_voice.services import PublishedProfileBundle
from ceo_voice.showcase.continuation import ContinuationError, WorkflowContinuation
from ceo_voice.showcase.service import ShowcaseWorkflowService
from ceo_voice.workspace.contracts import WorkspaceMember
from ceo_voice.workspace.database import SQLiteDatabase
from ceo_voice.workspace.errors import RevisionConflict
from ceo_voice.workspace.repository import WorkflowRepository

DRAFT = "Clear ownership improves execution by making decisions explicit."
INPUT = {
    "profile_slug": "integration-leader",
    "platform": "linkedin",
    "idea": "Explain how clear ownership improves execution.",
    "constraints": ["Do not invent personal memories."],
    "sources": [
        {
            "title": "Editorial fact sheet",
            "text": "Clear ownership makes decision responsibility explicit.",
            "url": "https://example.com/facts",
        }
    ],
}
OWNER = Actor(
    id="owner",
    name="Named Owner",
    email="owner@example.com",
    email_verified=True,
    workspace_id="workspace",
    role="owner",
)


@dataclass
class Harness:
    database: SQLiteDatabase
    bundle: PublishedProfileBundle
    key: str
    generator: FakeProvider
    review_provider: ReviewProvider
    quota: int = 30

    @property
    def repository(self) -> WorkflowRepository:
        return WorkflowRepository(self.database)

    def client(self, actor: Actor | None = OWNER) -> TestClient:
        reviewer = FidelityReviewer(
            self.review_provider,
            policy=FidelityPolicy(
                enabled=True, model="review-model", failure_behavior="return_for_review"
            ),
        )
        service = ShowcaseWorkflowService(
            provider=self.generator,
            model="test-model",
            published_bundles=(self.bundle,),
            artifact_storage="memory",
            maximum_provider_retries=0,
            fidelity_reviewer=reviewer,
        )
        app = FastAPI()

        @app.middleware("http")
        async def identity(request: Request, call_next: RequestResponseEndpoint) -> Response:
            if actor is not None:
                request.state.actor = actor
            return await call_next(request)

        app.include_router(
            create_editor_router(
                repository=self.repository,
                service=service,
                continuation=WorkflowContinuation(self.key, (self.bundle,)),
                reviewer=reviewer,
                encryption_key=self.key,
                workspace_id="workspace",
                allowed_profiles=(self.bundle.slug,),
                maximum_runs_per_hour=self.quota,
            )
        )
        return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def harness(tmp_path: Path, deployment: PublishedProfileBundle) -> Harness:
    database = SQLiteDatabase(tmp_path / "editor.sqlite", environment="test")
    database.migrate()
    item = Harness(
        database,
        deployment,
        Fernet.generate_key().decode(),
        FakeProvider((DRAFT,) * 30),
        ReviewProvider(("supported",) * 30),
    )
    item.repository.upsert_member(
        WorkspaceMember(workspace_id="workspace", user_id="owner", role="owner")
    )
    return item


def generate(
    client: TestClient, key: str = "generate-1", body: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/workspace/drafts/generate", json=body or INPUT, headers={"Idempotency-Key": key}
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def approval_body(draft: dict[str, Any]) -> dict[str, Any]:
    review = draft["review"]
    return {
        key: review[key]
        for key in ("revision_id", "content_sha256", "brief_sha256", "review_run_id")
    } | {
        "note": "Reviewed the exact draft and its evidence.",
        "reviewed_claim_ids": [claim["id"] for claim in review["claims"]],
    }


def test_cold_editor_generate_edit_review_approve_export_and_history(harness: Harness) -> None:
    first = generate(harness.client())
    identifier = first["id"]
    assert first["review"]["state"] == "needs_review" and first["review"]["can_approve"]
    assert (
        len(harness.generator.requests) == len(harness.review_provider.requests) == 1
    ), "generation reuses the engine review"
    assert "Editorial fact sheet" in harness.generator.requests[0].user
    material = {s["id"]: s["text"] for s in first["brief"]["sources"]}
    for claim in first["review"]["claims"]:
        for citation in claim["citations"]:
            span = citation["span"]
            assert material[citation["source_id"]][span["start"] : span["end"]] == span["text"]
    cold = harness.client()
    assert (
        cold.get(f"/api/v1/workspace/drafts/{identifier}").json()["current_revision"]
        == first["current_revision"]
    )
    assert cold.get(f"/api/v1/workspace/drafts/{identifier}/export").status_code == 409
    edit = cold.post(
        f"/api/v1/workspace/drafts/{identifier}/edit",
        json={
            "expected_revision_id": first["current_revision"]["id"],
            "content": DRAFT + " Teams can iterate.",
        },
    )
    assert edit.status_code == 200, edit.text
    edited = edit.json()
    assert edited["review"]["state"] == "review_pending" and not edited["review"]["can_approve"]
    assert len(harness.review_provider.requests) == 1
    review_request = {"expected_revision_id": edited["current_revision"]["id"]}
    response = harness.client().post(
        f"/api/v1/workspace/drafts/{identifier}/review",
        json=review_request,
        headers={"Idempotency-Key": "review-1"},
    )
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["current_revision"]["number"] == 3 and len(reviewed["revisions"]) == 3
    assert reviewed["current_revision"]["content"] == edited["current_revision"]["content"]
    assert reviewed["review"]["state"] == "needs_review"
    retry = harness.client().post(
        f"/api/v1/workspace/drafts/{identifier}/review",
        json=review_request,
        headers={"Idempotency-Key": "review-1"},
    )
    assert retry.status_code == 200 and len(harness.review_provider.requests) == 2
    approved = cold.post(
        f"/api/v1/workspace/drafts/{identifier}/approve", json=approval_body(reviewed)
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["review"]["approval"]["reviewer"] == {
        "id": "owner",
        "display_name": "Named Owner",
    }
    assert (
        approved.json()["review"]["approval"]["reviewed_claim_ids"]
        == approval_body(reviewed)["reviewed_claim_ids"]
    )
    exported = harness.client().get(f"/api/v1/workspace/drafts/{identifier}/export")
    assert (
        exported.status_code == 200
        and exported.json()["content"] == reviewed["current_revision"]["content"]
    )
    assert (
        DRAFT.encode() not in harness.database.path.read_bytes()
    ), "candidate content must be encrypted at rest"
    assert "continuation_token" not in json.dumps(reviewed)


def test_stale_edits_and_forged_approval_bindings_never_replace_current_head(
    harness: Harness,
) -> None:
    client = harness.client()
    draft = generate(client)
    path = f"/api/v1/workspace/drafts/{draft['id']}"
    for field in ("content_sha256", "brief_sha256", "review_run_id", "revision_id"):
        body = approval_body(draft)
        body[field] = "0" * 64 if field.endswith("sha256") else str(uuid4())
        assert client.post(path + "/approve", json=body).status_code == 409
    assert (
        client.post(
            path + "/approve", json={**approval_body(draft), "reviewer_user_id": "forged"}
        ).status_code
        == 422
    )
    updated = client.post(
        path + "/edit",
        json={
            "content": DRAFT + " Updated.",
            "expected_revision_id": draft["current_revision"]["id"],
        },
    ).json()
    assert client.post(path + "/approve", json=approval_body(draft)).status_code == 409
    assert (
        client.post(
            path + "/edit",
            json={"content": "stale", "expected_revision_id": draft["current_revision"]["id"]},
        ).status_code
        == 409
    )
    assert client.get(path).json()["current_revision"] == updated["current_revision"]


def test_approval_requires_specific_claim_acknowledgements_and_a_real_note(
    harness: Harness,
) -> None:
    client = harness.client()
    draft = generate(client)
    path = f"/api/v1/workspace/drafts/{draft['id']}/approve"
    valid = approval_body(draft)
    for claims in ([], ["forged-claim"]):
        assert client.post(path, json={**valid, "reviewed_claim_ids": claims}).status_code == 409
    assert (
        client.post(
            path, json={**valid, "reviewed_claim_ids": valid["reviewed_claim_ids"] * 2}
        ).status_code
        == 422
    )
    for note in ("", "ok", " " * 30):
        assert client.post(path, json={**valid, "note": note}).status_code == 422


def test_library_and_history_are_paginated_and_cursor_scope_is_verified(harness: Harness) -> None:
    client = harness.client()
    one = generate(client, key="one")
    two = generate(client, key="two")
    page = client.get("/api/v1/workspace/drafts", params={"limit": 1}).json()
    assert len(page["drafts"]) == 1 and page["next_cursor"]
    other = client.get(
        "/api/v1/workspace/drafts", params={"limit": 1, "cursor": page["next_cursor"]}
    ).json()
    assert {page["drafts"][0]["id"], other["drafts"][0]["id"]} == {one["id"], two["id"]}
    assert other["next_cursor"] is None
    path = f"/api/v1/workspace/drafts/{one['id']}"
    current = one
    for index in range(3):
        response = client.post(
            path + "/edit",
            json={
                "expected_revision_id": current["current_revision"]["id"],
                "content": DRAFT + f" Edit {index}.",
            },
        )
        assert response.status_code == 200
        current = response.json()
    history = client.get(path + "/revisions", params={"limit": 2}).json()
    older = client.get(
        path + "/revisions", params={"limit": 2, "cursor": history["next_cursor"]}
    ).json()
    assert [r["number"] for r in history["revisions"] + older["revisions"]] == [4, 3, 2, 1]
    assert older["next_cursor"] is None
    assert (
        client.get(path + "/revisions", params={"cursor": page["next_cursor"]}).status_code == 409
    )
    restored = client.post(
        path + "/restore",
        json={
            "expected_revision_id": current["current_revision"]["id"],
            "revision_number": 1,
            "revision_id": one["current_revision"]["id"],
        },
    )
    assert restored.status_code == 200 and restored.json()["current_revision"]["content"] == DRAFT
    assert (
        client.get(path + "/revisions", params={"cursor": history["next_cursor"]}).status_code
        == 409
    )
    assert client.get(path + "/revisions", params={"cursor": "tampered"}).status_code == 409


@pytest.mark.parametrize("verdict", ["unsupported", "uncertain", "contradicted"])
def test_blocked_candidates_remain_editable_and_cannot_approve_or_export(
    harness: Harness, verdict: str
) -> None:
    harness.review_provider.verdicts = [verdict] * 10
    client = harness.client()
    draft = generate(client)
    path = f"/api/v1/workspace/drafts/{draft['id']}"
    assert draft["current_revision"]["content"] == DRAFT and draft["review"]["state"] == "blocked"
    assert not draft["review"]["can_approve"]
    assert len(harness.generator.requests) == len(harness.review_provider.requests) == 2
    assert client.post(path + "/approve", json=approval_body(draft)).status_code == 409
    assert client.get(path + "/export").status_code == 409
    assert (
        client.post(
            path + "/edit",
            json={"content": DRAFT, "expected_revision_id": draft["current_revision"]["id"]},
        ).status_code
        == 200
    )


def test_review_unavailable_retains_candidate_without_repair_or_approval(harness: Harness) -> None:
    harness.review_provider.raw = "not a valid review"
    client = harness.client()
    draft = generate(client)
    assert (
        draft["review"]["state"] == "unavailable" and draft["current_revision"]["content"] == DRAFT
    )
    assert len(harness.generator.requests) == len(harness.review_provider.requests) == 1
    assert (
        client.post(
            f"/api/v1/workspace/drafts/{draft['id']}/approve", json=approval_body(draft)
        ).status_code
        == 409
    )


def test_duplicate_generation_key_and_quota_are_checked_before_any_model_call(
    harness: Harness,
) -> None:
    harness.quota = 1
    client = harness.client()
    first = generate(client)
    retry = generate(client)
    assert retry["id"] == first["id"] and len(harness.generator.requests) == 1
    response = client.post(
        "/api/v1/workspace/drafts/generate",
        json={**INPUT, "idea": "Changed brief about clear ownership and execution."},
        headers={"Idempotency-Key": "generate-1"},
    )
    assert response.status_code == 409
    response = client.post(
        "/api/v1/workspace/drafts/generate", json=INPUT, headers={"Idempotency-Key": "generate-2"}
    )
    assert response.status_code == 429 and len(harness.generator.requests) == 1


def test_identity_role_profile_and_workspace_are_server_authorized(harness: Harness) -> None:
    assert harness.client(None).get("/api/v1/workspace/session").status_code == 401
    stranger = OWNER.model_copy(update={"id": "unknown"})
    assert harness.client(stranger).get("/api/v1/workspace/session").status_code == 403
    assert (
        harness.client(OWNER.model_copy(update={"workspace_id": "other"}))
        .get("/api/v1/workspace/session")
        .status_code
        == 403
    )
    client = harness.client()
    assert (
        client.post(
            "/api/v1/workspace/drafts/generate",
            json={**INPUT, "profile_slug": "forbidden"},
            headers={"Idempotency-Key": "forbidden"},
        ).status_code
        == 403
    )
    draft = generate(client)
    harness.repository.upsert_member(
        WorkspaceMember(workspace_id="workspace", user_id="owner", role="viewer")
    )
    assert client.get("/api/v1/workspace/session").json()["can_edit"] is False
    assert (
        client.post(
            f"/api/v1/workspace/drafts/{draft['id']}/approve", json=approval_body(draft)
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/workspace/drafts/{draft['id']}/edit",
            json={"content": DRAFT, "expected_revision_id": draft["current_revision"]["id"]},
        ).status_code
        == 403
    )
    harness.repository.upsert_member(
        WorkspaceMember(workspace_id="workspace", user_id="owner", role="owner", active=False)
    )
    assert client.get(f"/api/v1/workspace/drafts/{draft['id']}").status_code == 403
    assert len(harness.generator.requests) == 1


def test_revoice_and_restore_are_durable_and_invalidate_old_approval(harness: Harness) -> None:
    client = harness.client()
    original = generate(client)
    path = f"/api/v1/workspace/drafts/{original['id']}"
    response = harness.client().post(
        path + "/revoice",
        json={"expected_revision_id": original["current_revision"]["id"]},
        headers={"Idempotency-Key": "revoice-1"},
    )
    assert response.status_code == 200, response.text
    revoiced = response.json()
    assert (
        revoiced["current_revision"]["kind"] == "revoiced"
        and revoiced["review"]["state"] == "needs_review"
    )
    approved = client.post(path + "/approve", json=approval_body(revoiced))
    assert approved.status_code == 200
    restored = client.post(
        path + "/restore",
        json={
            "expected_revision_id": revoiced["current_revision"]["id"],
            "revision_id": original["current_revision"]["id"],
            "revision_number": original["current_revision"]["number"],
        },
    )
    assert restored.status_code == 200
    assert (
        restored.json()["current_revision"]["kind"] == "restored"
        and restored.json()["review"]["state"] == "review_pending"
    )
    assert client.get(path + "/export").status_code == 409


def test_stale_concurrent_edits_have_one_authoritative_winner(harness: Harness) -> None:
    draft = generate(harness.client())
    path = f"/api/v1/workspace/drafts/{draft['id']}/edit"

    def edit(index: int) -> int:
        return int(
            harness.client()
            .post(
                path,
                json={
                    "expected_revision_id": draft["current_revision"]["id"],
                    "content": DRAFT + str(index),
                },
            )
            .status_code
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(edit, range(2)))
    assert sorted(statuses) == [200, 409]
    assert harness.repository.get_workflow("workspace", UUID(draft["id"])).head_revision == 1


def test_expired_browser_token_remains_authenticated_for_trusted_database_resume(
    harness: Harness,
) -> None:
    draft = generate(harness.client())
    record = harness.repository.get_revision("workspace", UUID(draft["id"]))
    state = EditorStateCodec(harness.key).open(record)
    cipher = Fernet(harness.key.encode())
    old = cipher.encrypt_at_time(
        cipher.decrypt(state.continuation_token), int(time.time()) - 100
    ).decode()
    continuation = WorkflowContinuation(harness.key, (harness.bundle,), ttl_seconds=1)
    with pytest.raises(ContinuationError):
        continuation.open(old, record.workflow_id)
    assert continuation.open_stored(old, record.workflow_id).id == record.workflow_id
    with pytest.raises(ContinuationError):
        continuation.open_stored(old, uuid4())
    with pytest.raises(ContinuationError):
        continuation.open_stored("invalid", record.workflow_id)


def test_encrypted_state_rejects_wrong_revision_hash_key_and_review_eligibility(
    harness: Harness,
) -> None:
    draft = generate(harness.client())
    record = harness.repository.get_revision("workspace", UUID(draft["id"]))
    codec = EditorStateCodec(harness.key)
    for invalid in (
        record.model_copy(update={"revision": 99}),
        record.model_copy(update={"candidate_sha256": "0" * 64}),
        record.model_copy(update={"review_eligible": False}),
    ):
        with pytest.raises(RevisionConflict):
            codec.open(invalid)
    with pytest.raises(RevisionConflict):
        EditorStateCodec(Fernet.generate_key().decode()).open(record)
