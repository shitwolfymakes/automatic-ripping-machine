"""Origin allowlist gate. Doesn't exercise the full WS handshake — just
the predicate. Service-token clients (rippers, transcoders) skip via the
SERVICE_TOKEN_SUBPROTOCOL marker; browser clients must be on the
configured allowlist.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

from arm_backend.config import settings  # noqa: E402
from arm_backend.ws.router import (  # noqa: E402
    SERVICE_TOKEN_SUBPROTOCOL,
    _origin_allowed,
)


def test_service_subprotocol_skips_origin_check() -> None:
    settings.ARM_ALLOWED_ORIGINS = []
    assert _origin_allowed("https://malicious.example.com", [SERVICE_TOKEN_SUBPROTOCOL]) is True


def test_no_origin_header_allowed() -> None:
    """Sibling-container connections from compose network have no Origin."""
    settings.ARM_ALLOWED_ORIGINS = []
    assert _origin_allowed(None, []) is True


def test_browser_origin_not_in_allowlist_rejected() -> None:
    settings.ARM_ALLOWED_ORIGINS = ["https://arm.local:8081"]
    assert _origin_allowed("https://malicious.example.com", []) is False


def test_browser_origin_in_allowlist_accepted() -> None:
    settings.ARM_ALLOWED_ORIGINS = ["https://arm.local:8081", "https://arm.local"]
    assert _origin_allowed("https://arm.local:8081", []) is True


def test_browser_origin_with_empty_allowlist_rejected() -> None:
    """Phase 4 default: empty allowlist means service-token only."""
    settings.ARM_ALLOWED_ORIGINS = []
    assert _origin_allowed("https://arm.local:8081", []) is False
