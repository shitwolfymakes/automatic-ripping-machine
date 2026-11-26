"""HS256 issue/verify round-trip + tamper / expiry checks."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest


from arm_backend.jwt_utils import (
    ACCESS_TOKEN_TTL,
    ALGORITHM,
    CLOCK_SKEW_LEEWAY,
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


# ---- clock skew ---------------------------------------------------------------
# Tokens are minted with `iat`/`exp` at fixed offsets from now, a few seconds
# inside or a minute outside the leeway, so no test depends on timing.

_INSIDE = CLOCK_SKEW_LEEWAY - timedelta(seconds=3)
_OUTSIDE = CLOCK_SKEW_LEEWAY + timedelta(seconds=55)


def _token(key: bytes, *, iat: timedelta, exp: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "usr_abc",
        "username": "alice",
        "iat": int((now + iat).timestamp()),
        "exp": int((now + exp).timestamp()),
    }
    return pyjwt.encode(payload, key, algorithm=ALGORITHM)


def test_leeway_is_a_few_seconds() -> None:
    assert timedelta(seconds=1) <= CLOCK_SKEW_LEEWAY <= timedelta(seconds=30)


def test_token_issued_slightly_in_the_future_is_accepted() -> None:
    """The verifier's clock stepped back a moment after minting (or runs a
    little behind the issuer's): the token is still good."""
    key = secrets.token_bytes(32)
    token = _token(key, iat=_INSIDE, exp=ACCESS_TOKEN_TTL)

    assert verify_access_token(token, key)["sub"] == "usr_abc"


def test_token_issued_well_in_the_future_is_rejected() -> None:
    key = secrets.token_bytes(32)
    token = _token(key, iat=_OUTSIDE, exp=ACCESS_TOKEN_TTL)

    with pytest.raises(pyjwt.ImmatureSignatureError):
        verify_access_token(token, key)


def test_token_expired_moments_ago_is_accepted() -> None:
    key = secrets.token_bytes(32)
    token = _token(key, iat=-ACCESS_TOKEN_TTL, exp=-_INSIDE)

    assert verify_access_token(token, key)["sub"] == "usr_abc"


def test_token_expired_beyond_the_leeway_is_rejected() -> None:
    key = secrets.token_bytes(32)
    token = _token(key, iat=-ACCESS_TOKEN_TTL, exp=-_OUTSIDE)

    with pytest.raises(pyjwt.ExpiredSignatureError):
        verify_access_token(token, key)
