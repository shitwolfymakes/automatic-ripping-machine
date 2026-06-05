"""HS256 access-token issue/verify.

Tokens are signed with `config.session_signing_key` (32 random bytes,
seeded on first boot). 7-day TTL, no refresh per
[05-cross-cutting.md § Authentication model](../../../docs/arch/05-cross-cutting.md#authentication-model).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

ACCESS_TOKEN_TTL = timedelta(days=7)
ALGORITHM = "HS256"


def issue_access_token(user_id: str, username: str, signing_key: bytes) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    exp = now + ACCESS_TOKEN_TTL
    payload = {
        "sub": user_id,
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, signing_key, algorithm=ALGORITHM)
    return token, exp


def verify_access_token(token: str, signing_key: bytes) -> dict[str, Any]:
    """Returns the decoded payload. Raises `jwt.InvalidTokenError` (or subclass) on failure."""
    return jwt.decode(token, signing_key, algorithms=[ALGORITHM])
