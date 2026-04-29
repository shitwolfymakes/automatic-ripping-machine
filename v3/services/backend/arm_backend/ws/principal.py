"""WS connection principal + token-to-principal resolver.

The principal is a per-connection identity stamped at auth time and
carried through every authz check. Service-token connections carry a
hostname (matched against `drives.hostname` for command-topic auth and
job→drive lookups for publish auth). UI-JWT connections carry the user
identity, populated by verifying the JWT against the cached
`config.session_signing_key`.
"""

from dataclasses import dataclass
from typing import Literal

import jwt

from arm_backend.auth import check_service_token, looks_like_jwt
from arm_backend.jwt_utils import verify_access_token

PrincipalKind = Literal["ripper", "transcoder"]


@dataclass(frozen=True)
class ServicePrincipal:
    kind: PrincipalKind
    hostname: str  # ripper: drive hostname; transcoder: container hostname
    task_id: str | None = None  # transcoder only (Phase 7)


@dataclass(frozen=True)
class UIPrincipal:
    user_id: str
    username: str


Principal = ServicePrincipal | UIPrincipal


class AuthError(Exception):
    """Raised when the auth message can't be turned into a principal."""


def resolve_principal(
    token: str,
    hostname_hint: str | None,
    *,
    signing_key: bytes | None = None,
) -> Principal:
    """Map an auth-message token to a Principal.

    Resolution order:
      1. Service token → ServicePrincipal(kind="ripper", hostname=hostname_hint)
      2. JWT-shaped + signing_key provided → UIPrincipal from verified payload
      3. Raise AuthError
    """
    if check_service_token(token):
        if not hostname_hint:
            raise AuthError("service-token connection requires hostname (X-ARM-Hostname header)")
        return ServicePrincipal(kind="ripper", hostname=hostname_hint)

    if signing_key is not None and looks_like_jwt(token):
        try:
            payload = verify_access_token(token, signing_key)
        except jwt.InvalidTokenError as exc:
            raise AuthError(f"invalid UI JWT: {exc}") from exc
        sub = payload.get("sub")
        username = payload.get("username")
        if not isinstance(sub, str) or not isinstance(username, str):
            raise AuthError("UI JWT missing sub/username")
        return UIPrincipal(user_id=sub, username=username)

    raise AuthError("unknown auth token")
