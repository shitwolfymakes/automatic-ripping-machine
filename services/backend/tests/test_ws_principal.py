"""Token-to-principal resolver."""

import pytest


from arm_backend.config import settings
from arm_backend.seeders import GUEST_USERNAME
from arm_backend.ws.principal import (
    AuthError,
    ServicePrincipal,
    UIPrincipal,
    resolve_principal,
)


def test_service_token_matches_with_hostname() -> None:
    p = resolve_principal(settings.ARM_SERVICE_TOKEN, hostname_hint="arm-ripper-sr0")
    assert isinstance(p, ServicePrincipal)
    assert p.kind == "ripper"
    assert p.hostname == "arm-ripper-sr0"


def test_service_token_without_hostname_rejects() -> None:
    with pytest.raises(AuthError, match="hostname"):
        resolve_principal(settings.ARM_SERVICE_TOKEN, hostname_hint=None)


def test_invalid_token_rejects() -> None:
    with pytest.raises(AuthError):
        resolve_principal("wrong-token-not-the-configured-one", hostname_hint="arm-ripper-sr0")


def test_resolve_principal_empty_token_anonymous() -> None:
    # Empty token → anonymous-guest UIPrincipal, resolved without touching the DB
    # (purity preserved; the router does the guest-enabled check separately).
    p = resolve_principal("", hostname_hint="arm-ripper-sr0")
    assert isinstance(p, UIPrincipal)
    assert p.username == GUEST_USERNAME
