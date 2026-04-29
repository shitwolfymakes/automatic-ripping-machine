"""WS `resolve_principal` UI-JWT path."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

from arm_backend.jwt_utils import ALGORITHM, issue_access_token  # noqa: E402
from arm_backend.ws.principal import (  # noqa: E402
    AuthError,
    UIPrincipal,
    resolve_principal,
)


def test_signed_jwt_resolves_to_ui_principal() -> None:
    key = secrets.token_bytes(32)
    token, _ = issue_access_token("usr_abc", "alice", key)
    p = resolve_principal(token, hostname_hint=None, signing_key=key)
    assert isinstance(p, UIPrincipal)
    assert p.user_id == "usr_abc"
    assert p.username == "alice"


def test_jwt_without_signing_key_rejects() -> None:
    key = secrets.token_bytes(32)
    token, _ = issue_access_token("usr_abc", "alice", key)
    # signing_key=None means the WS endpoint never finished its lifespan; treat as auth failure.
    with pytest.raises(AuthError, match="unknown auth token"):
        resolve_principal(token, hostname_hint=None, signing_key=None)


def test_jwt_signed_with_other_key_rejects() -> None:
    k1 = secrets.token_bytes(32)
    k2 = secrets.token_bytes(32)
    token, _ = issue_access_token("usr_abc", "alice", k1)
    with pytest.raises(AuthError, match="invalid UI JWT"):
        resolve_principal(token, hostname_hint=None, signing_key=k2)


def test_expired_jwt_rejects() -> None:
    key = secrets.token_bytes(32)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {"sub": "usr_abc", "username": "alice", "iat": int(past.timestamp()), "exp": int(past.timestamp())}
    token = pyjwt.encode(payload, key, algorithm=ALGORITHM)
    with pytest.raises(AuthError, match="invalid UI JWT"):
        resolve_principal(token, hostname_hint=None, signing_key=key)


def test_jwt_missing_sub_rejects() -> None:
    key = secrets.token_bytes(32)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {"iat": int(datetime.now(timezone.utc).timestamp()), "exp": int(future.timestamp())}
    token = pyjwt.encode(payload, key, algorithm=ALGORITHM)
    with pytest.raises(AuthError, match="missing sub/username"):
        resolve_principal(token, hostname_hint=None, signing_key=key)
