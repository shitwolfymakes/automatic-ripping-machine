"""Token-to-principal resolver."""

import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

from arm_backend.config import settings  # noqa: E402
from arm_backend.ws.principal import (  # noqa: E402
    AuthError,
    ServicePrincipal,
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


def test_empty_token_rejects() -> None:
    with pytest.raises(AuthError):
        resolve_principal("", hostname_hint="arm-ripper-sr0")
