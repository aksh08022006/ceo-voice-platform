"""The production app boundary closes legacy routes and preserves readable auth failures."""

from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pydantic import SecretStr
from tests.api.test_continuation import deployment as deployment
from tests.integration.test_full_workflow import NeverCalledProvider
from tests.unit.api.test_authentication import AUDIENCE, ISSUER, Identities, Keys, signed_token
from tests.unit.generation.test_fidelity import ReviewProvider

from ceo_voice.api import create_app
from ceo_voice.api.authentication import TokenVerifier, WorkspaceAccess
from ceo_voice.config import ApiSettings, Settings, WorkspaceSettings
from ceo_voice.generation.fidelity import FidelityReviewer
from ceo_voice.generation.fidelity_contracts import FidelityPolicy
from ceo_voice.services import PublishedProfileBundle
from ceo_voice.showcase import ShowcaseWorkflowService
from ceo_voice.workspace import SQLiteDatabase, WorkflowRepository, WorkspaceMember

ORIGIN = "https://editor.example.test"


def test_entire_workspace_requires_auth_and_legacy_routes_cannot_bypass_it(
    tmp_path: Path, deployment: PublishedProfileBundle
) -> None:
    database = SQLiteDatabase(tmp_path / "workspace.sqlite", environment="test")
    database.migrate()
    repository = WorkflowRepository(database)
    workspace = WorkspaceSettings(
        enabled=True,
        database_url=SecretStr("postgresql://unused.example.test/test"),
        encryption_key=SecretStr(Fernet.generate_key().decode()),
        auth_issuer=ISSUER,
        auth_audience=AUDIENCE,
        auth_jwks_url=ISSUER + "/.well-known/jwks.json",
        allowed_profiles=(deployment.slug,),
        fidelity_enabled=True,
    )
    settings = Settings(
        _env_file=None,
        workspace=workspace,
        api=ApiSettings(
            allowed_origins=(ORIGIN,),
            continuation_key=SecretStr(Fernet.generate_key().decode()),
        ),
    )
    key = Ed25519PrivateKey.generate()
    access = WorkspaceAccess(
        workspace, repository, Identities(), TokenVerifier(workspace, jwks_client=Keys(key))
    )
    provider = ReviewProvider()
    reviewer = FidelityReviewer(
        provider,
        policy=FidelityPolicy(enabled=True, model="fixture", failure_behavior="return_for_review"),
    )
    service = ShowcaseWorkflowService(
        output_directory=tmp_path / "artifacts",
        provider=NeverCalledProvider(),
        model="fixture",
        published_bundles=(deployment,),
        fidelity_reviewer=reviewer,
    )
    app = create_app(
        settings,
        service,
        workspace_access=access,
        workspace_repository=repository,
        fidelity_reviewer=reviewer,
    )
    with TestClient(app) as api:
        assert api.get("/api/v1/health").status_code == 200
        for method, path in [
            ("GET", "/api/v1/profiles"),
            ("GET", "/api/v1/walkthroughs"),
            ("GET", "/api/v1/workspace/session"),
            ("GET", "/api/v1/workspace/drafts"),
            ("POST", "/api/v1/workspace/drafts/generate"),
            ("POST", "/api/v1/workflows/generate"),
            ("POST", f"/api/v1/workflows/{uuid4()}/resume"),
        ]:
            response = api.request(method, path, headers={"Origin": ORIGIN})
            assert response.status_code == 401, (path, response.text)
            assert response.headers["access-control-allow-origin"] == ORIGIN
            assert response.headers["cache-control"] == "no-store"
        headers = {"Authorization": "Bearer " + signed_token(key)}
        assert api.get("/api/v1/workspace/session", headers=headers).status_code == 403
        member = WorkspaceMember(
            workspace_id=workspace.workspace_id, user_id="member-one", role="viewer"
        )
        repository.upsert_member(member)
        assert api.get("/api/v1/workspace/session", headers=headers).status_code == 200
        assert api.post("/api/v1/workflows/generate", headers=headers, json={}).status_code == 410
        response = api.post(
            "/api/v1/workspace/drafts/generate",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={
                "profile_slug": deployment.slug,
                "platform": "x",
                "idea": "Explain clear ownership.",
            },
        )
        assert response.status_code == 403, response.text
        repository.upsert_member(member.model_copy(update={"active": False}))
        assert api.get("/api/v1/workspace/session", headers=headers).status_code == 403
        preflight = api.options(
            "/api/v1/workspace/drafts/generate",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,idempotency-key,content-type",
            },
        )
        assert preflight.status_code == 200
        assert not provider.requests
