"""Real asymmetric-token checks and fresh, server-owned membership decisions."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ceo_voice.api.authentication import (
    AccessError,
    Actor,
    Identity,
    TokenVerifier,
    WorkspaceAccess,
    require_role,
)
from ceo_voice.config.settings import WorkspaceSettings
from ceo_voice.workspace import SQLiteDatabase, WorkflowRepository, WorkspaceMember

ISSUER = "https://auth.example.test/neondb/auth"
AUDIENCE = "https://auth.example.test"


class Keys:
    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self.key = private_key.public_key()

    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
        if jwt.get_unverified_header(token)["kid"] != "known-key":
            raise jwt.PyJWKClientError("unknown key")
        return SimpleNamespace(key=self.key)


def signed_token(key: Ed25519PrivateKey, **overrides: Any) -> str:
    now = int(datetime.now(UTC).timestamp())
    claims = {"sub": "member-one", "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300}
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="EdDSA", headers={"kid": "known-key"})


def configuration(**values: Any) -> WorkspaceSettings:
    return WorkspaceSettings(
        auth_issuer=ISSUER,
        auth_audience=AUDIENCE,
        auth_jwks_url=ISSUER + "/.well-known/jwks.json",
        **values,
    )


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://attacker.example"},
        {"aud": "another-app"},
        {"exp": 1},
        {"iat": 9_999_999_999},
        {"sub": "anonymous"},
        {"sub": ""},
        {"sub": 17},
        {"exp": None},
    ],
)
def test_rejects_invalid_claims(claims: dict[str, Any]) -> None:
    key = Ed25519PrivateKey.generate()
    verifier = TokenVerifier(configuration(), jwks_client=Keys(key))
    with pytest.raises(AccessError):
        verifier.verify("Bearer " + signed_token(key, **claims))


def test_signature_algorithm_key_and_bearer_are_required() -> None:
    key = Ed25519PrivateKey.generate()
    verifier = TokenVerifier(configuration(), jwks_client=Keys(key))
    valid = signed_token(key)
    assert verifier.verify("Bearer " + valid) == "member-one"
    wrong_signature = signed_token(Ed25519PrivateKey.generate())
    hmac = jwt.encode({"sub": "member-one"}, "x" * 32, algorithm="HS256")
    missing_key = jwt.encode({"sub": "member-one"}, key, algorithm="EdDSA")
    unknown_key = jwt.encode({}, key, algorithm="EdDSA", headers={"kid": "other"})
    for value in (
        None,
        "",
        "Basic " + valid,
        "Bearer ",
        "Bearer a b",
        "Bearer " + "a" * 16_001,
        "Bearer " + wrong_signature,
        "Bearer " + hmac,
        "Bearer " + missing_key,
        "Bearer " + unknown_key,
        "Bearer malformed",
    ):
        with pytest.raises(AccessError):
            verifier.verify(value)


class Identities:
    def __init__(self) -> None:
        self.identity: Identity | None = Identity(
            id="member-one", name="Editorial owner", email="owner@example.test", email_verified=True
        )

    def get(self, subject: str) -> Identity | None:
        return self.identity if self.identity and self.identity.id == subject else None


def test_membership_is_current_and_bootstrap_does_not_restore_revoked_access(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "auth.sqlite", environment="test")
    database.migrate()
    repository = WorkflowRepository(database)
    identities = Identities()
    key = Ed25519PrivateKey.generate()
    settings = configuration(bootstrap_admin_emails=("OWNER@example.test",))
    access = WorkspaceAccess(
        settings, repository, identities, TokenVerifier(settings, jwks_client=Keys(key))
    )
    bearer = "Bearer " + signed_token(key, role="owner", email="attacker@example.test")
    actor = access.authorize(bearer)
    assert actor.role == "owner"
    assert actor.email == "owner@example.test"
    repository.upsert_member(
        WorkspaceMember(workspace_id=settings.workspace_id, user_id=actor.id, role="viewer")
    )
    assert access.authorize(bearer).role == "viewer"
    repository.upsert_member(
        WorkspaceMember(
            workspace_id=settings.workspace_id, user_id=actor.id, role="owner", active=False
        )
    )
    with pytest.raises(AccessError, match="awaiting"):
        access.authorize(bearer)


def test_sign_up_and_unverified_or_banned_accounts_do_not_grant_access(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "auth.sqlite", environment="test")
    database.migrate()
    repository = WorkflowRepository(database)
    identities = Identities()
    key = Ed25519PrivateKey.generate()
    settings = configuration()
    access = WorkspaceAccess(
        settings, repository, identities, TokenVerifier(settings, jwks_client=Keys(key))
    )
    bearer = "Bearer " + signed_token(key)
    with pytest.raises(AccessError, match="awaiting"):
        access.authorize(bearer)
    assert identities.identity is not None
    identities.identity.email_verified = False
    with pytest.raises(AccessError, match="Verify your email"):
        access.authorize(bearer)
    identities.identity.email_verified = True
    identities.identity.banned = True
    with pytest.raises(AccessError, match="cannot access"):
        access.authorize(bearer)
    identities.identity = None
    with pytest.raises(AccessError, match="cannot access"):
        access.authorize(bearer)


def test_role_gate_uses_server_actor() -> None:
    actor = Actor(
        id="user",
        name="Reviewer",
        email="reviewer@example.test",
        email_verified=True,
        workspace_id="narrative-company",
        role="reviewer",
    )
    require_role(actor, ("owner", "reviewer"))
    with pytest.raises(AccessError):
        require_role(actor, ("owner", "admin"))
