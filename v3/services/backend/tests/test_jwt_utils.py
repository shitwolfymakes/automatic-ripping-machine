"""HS256 issue/verify round-trip + tamper / expiry checks."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

from arm_backend.jwt_utils import (  # noqa: E402
    ACCESS_TOKEN_TTL,
    ALGORITHM,
    issue_access_token,
    verify_access_token,
)


def test_round_trip_returns_payload() -> None:
    key = secrets.token_bytes(32)
    token, exp = issue_access_token("usr_abc", "alice", key)
    payload = verify_access_token(token, key)
    assert payload["sub"] == "usr_abc"
    assert payload["username"] == "alice"
    assert exp - datetime.now(timezone.utc) <= ACCESS_TOKEN_TTL
    assert exp - datetime.now(timezone.utc) > ACCESS_TOKEN_TTL - timedelta(seconds=5)


def test_bad_signature_raises() -> None:
    k1 = secrets.token_bytes(32)
    k2 = secrets.token_bytes(32)
    token, _ = issue_access_token("usr_abc", "alice", k1)
    with pytest.raises(pyjwt.InvalidSignatureError):
        verify_access_token(token, k2)


def test_expired_token_raises() -> None:
    key = secrets.token_bytes(32)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {"sub": "usr_abc", "username": "alice", "iat": int(past.timestamp()), "exp": int(past.timestamp())}
    token = pyjwt.encode(payload, key, algorithm=ALGORITHM)
    with pytest.raises(pyjwt.ExpiredSignatureError):
        verify_access_token(token, key)
