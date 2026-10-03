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


# --- same-origin default (G-28) ----------------------------------------------


def test_same_origin_via_request_host_accepted() -> None:
    settings.ARM_ALLOWED_ORIGINS = []
    assert _origin_allowed("https://192.168.1.85:8082", [], request_host="192.168.1.85:8082") is True


def test_same_origin_via_forwarded_host_accepted() -> None:
    """ui-neu's nginx rewrites Host to arm-backend but forwards the real one."""
    settings.ARM_ALLOWED_ORIGINS = []
    assert (
        _origin_allowed(
            "https://nas.lan:8082",
            [],
            request_host="arm-backend",
            forwarded_host="nas.lan:8082",
            forwarded_proto="https",
        )
        is True
    )


def test_forwarded_host_wins_over_request_host() -> None:
    settings.ARM_ALLOWED_ORIGINS = []
    assert (
        _origin_allowed(
            "https://arm-backend",
            [],
            request_host="arm-backend",
            forwarded_host="nas.lan:8082",
        )
        is False
    )


def test_same_origin_scheme_mismatch_rejected() -> None:
    settings.ARM_ALLOWED_ORIGINS = []
    assert _origin_allowed("http://nas.lan:8082", [], request_host="nas.lan:8082", request_scheme="https") is False


def test_same_origin_forwarded_proto_http_accepted() -> None:
    """vite dev serves plain http and forwards proto accordingly."""
    settings.ARM_ALLOWED_ORIGINS = []
    assert (
        _origin_allowed(
            "http://localhost:5173",
            [],
            request_host="localhost:8443",
            forwarded_host="localhost:5173",
            forwarded_proto="http",
        )
        is True
    )


def test_same_origin_port_mismatch_rejected() -> None:
    settings.ARM_ALLOWED_ORIGINS = []
    assert _origin_allowed("https://nas.lan:9999", [], request_host="nas.lan:8082") is False


def test_same_origin_case_insensitive() -> None:
    settings.ARM_ALLOWED_ORIGINS = []
    assert _origin_allowed("https://NAS.lan:8082", [], request_host="nas.LAN:8082") is True


def test_forwarded_host_chain_uses_first_element() -> None:
    settings.ARM_ALLOWED_ORIGINS = []
    assert (
        _origin_allowed(
            "https://nas.lan:8082",
            [],
            forwarded_host="nas.lan:8082, arm-backend",
            forwarded_proto="https, https",
        )
        is True
    )


def test_allowlist_still_covers_split_origin() -> None:
    settings.ARM_ALLOWED_ORIGINS = ["https://arm.example.com"]
    assert _origin_allowed("https://arm.example.com", [], request_host="backend.internal:8443") is True
