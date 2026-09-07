"""Managed identity verification and fresh, server-owned workspace authorization."""

from datetime import UTC, datetime
from typing import Any, Protocol

import certifi
import jwt
import psycopg
from jwt import PyJWKClient
from pydantic import BaseModel, Field

from ceo_voice.config.settings import WorkspaceSettings
from ceo_voice.workspace.contracts import MemberRole, WorkspaceMember, WorkspaceScope


class AccessError(Exception):
    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


class Identity(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=300)
    email: str = Field(min_length=3, max_length=320)
    email_verified: bool
    banned: bool = False


class Actor(Identity):
    workspace_id: str
    role: MemberRole


class IdentityReader(Protocol):
    def get(self, subject: str) -> Identity | None: ...


class MembershipReader(Protocol):
    def get_member(self, workspace_id: str, user_id: str) -> WorkspaceMember | None: ...

    def bootstrap_owner_if_empty(self, scope: WorkspaceScope) -> WorkspaceMember | None: ...


class TokenVerifier:
    """Validate only configured asymmetric keys, issuer, audience and token lifetime.

    Identity and roles are not accepted from token extras or browser headers. The managed
    user's current verified-email and ban state and our membership are read on every request.
    """

    def __init__(self, settings: WorkspaceSettings, *, jwks_client: Any = None) -> None:
        self._settings = settings
        self._keys = jwks_client or PyJWKClient(
            str(settings.auth_jwks_url), timeout=5, lifespan=300, max_cached_keys=16
        )

    def verify(self, authorization: str | None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise AccessError("Sign in to access this workspace.")
        token = authorization[7:]
        if not token or len(token) > 16_000 or any(char.isspace() for char in token):
            raise AccessError("Invalid sign-in token.")
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "EdDSA":
                raise ValueError("unsupported token algorithm")
            if not isinstance(header.get("kid"), str) or not 1 <= len(header["kid"]) <= 160:
                raise ValueError("missing signing key identity")
            key = self._keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["EdDSA"],
                issuer=self._settings.auth_issuer,
                audience=self._settings.auth_audience,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
                leeway=5,
            )
            subject = claims["sub"]
            if (
                not isinstance(subject, str)
                or not 1 <= len(subject) <= 160
                or subject == "anonymous"
            ):
                raise ValueError("invalid subject")
            return subject
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, OSError) as exc:
            raise AccessError("Your sign-in session could not be verified. Sign in again.") from exc


class NeonIdentityReader:
    """Read current identity from the managed provider's own schema, never from a client claim."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def get(self, subject: str) -> Identity | None:
        with psycopg.connect(
            self._dsn,
            connect_timeout=5,
            prepare_threshold=None,
            sslmode="verify-full",
            sslrootcert=certifi.where(),
        ) as conn:
            conn.execute("SET LOCAL statement_timeout = '5s'")
            row = conn.execute(
                'SELECT id, name, email, "emailVerified", banned, "banExpires" '
                'FROM neon_auth."user" WHERE id = %s',
                (subject,),
            ).fetchone()
        if row is None:
            return None
        active_ban = bool(row[4]) and (row[5] is None or row[5] > datetime.now(UTC))
        return Identity(
            id=row[0], name=row[1], email=row[2], email_verified=row[3], banned=active_ban
        )


class WorkspaceAccess:
    def __init__(
        self,
        settings: WorkspaceSettings,
        repository: MembershipReader,
        identities: IdentityReader,
        verifier: TokenVerifier,
    ) -> None:
        self.settings, self.repository = settings, repository
        self.identities, self.verifier = identities, verifier

    def authorize(self, authorization: str | None) -> Actor:
        subject = self.verifier.verify(authorization)
        identity = self.identities.get(subject)
        if identity is None or identity.banned:
            raise AccessError("This account cannot access the workspace.", 403)
        if not identity.email_verified:
            raise AccessError("Verify your email address before opening the workspace.", 403)
        member = self.repository.get_member(self.settings.workspace_id, subject)
        # Bootstrap only an explicitly named verified identity, once. Revoked memberships
        # never recreate themselves, and later signups cannot become another first owner.
        if member is None and identity.email.casefold() in {
            address.casefold() for address in self.settings.bootstrap_admin_emails
        }:
            member = self.repository.bootstrap_owner_if_empty(
                WorkspaceScope(workspace_id=self.settings.workspace_id, user_id=subject)
            )
        if member is None or not member.active:
            raise AccessError(
                "Your account is awaiting workspace access from an administrator.", 403
            )
        return Actor(**identity.model_dump(), workspace_id=member.workspace_id, role=member.role)


def require_role(actor: Actor, roles: tuple[MemberRole, ...]) -> None:
    if actor.role not in roles:
        raise AccessError("Your workspace role does not allow this action.", 403)
