"""WS connection principal + token-to-principal resolver.

The principal is a per-connection identity stamped at auth time and
carried through every authz check. Service-token connections carry a
hostname (matched against `drives.hostname` for command-topic auth and
job→drive lookups for publish auth). UI-JWT connections carry the user
identity; that branch is scaffolded but inert until Phase 5 wires the
JWT verifier.
"""

from dataclasses import dataclass
from typing import Literal

from arm_backend.auth import check_service_token

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


def resolve_principal(token: str, hostname_hint: str | None) -> Principal:
    """Map an auth-message token to a Principal.

    Phase 4 only resolves service tokens. UI JWTs raise AuthError until
    Phase 5 plugs in the `config.session_signing_key` verifier — that
    way Phase 5 is a one-line addition, not a control-flow change.
    """
    if check_service_token(token):
        if not hostname_hint:
            raise AuthError("service-token connection requires hostname (X-ARM-Hostname header)")
        return ServicePrincipal(kind="ripper", hostname=hostname_hint)
    raise AuthError("UI JWT auth not yet supported (Phase 5)")
