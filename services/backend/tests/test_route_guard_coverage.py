"""Every mutating route must carry an authorization guard.

`test_guest_write_gating.py` proves the guards that exist behave correctly,
but its route table is hand-maintained: a new POST/PATCH/DELETE added without
`require_writer` is simply absent from the table and the sweep stays green.
This walks the real app's dependency tree instead, so an unguarded mutating
route fails CI until someone deliberately adds it to `_UNGUARDED_ALLOWLIST`
below.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi.dependencies.models import Dependant  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

from arm_backend.auth import (  # noqa: E402
    require_drive_owner_by_job,
    require_drive_owner_by_track,
    require_service_token,
    require_writer,
)
from arm_backend.main import app  # noqa: E402

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# A mutating route is considered guarded if any of these appears anywhere in
# its dependency tree. `require_jwt` is deliberately NOT here: since the
# anonymous->guest fallback landed it authenticates but no longer authorizes,
# so it can't gate a write on its own.
_WRITE_GUARDS = frozenset(
    {
        require_writer,
        require_service_token,
        require_drive_owner_by_job,
        require_drive_owner_by_track,
    }
)

# Mutating routes that intentionally carry no write guard. Each entry needs a
# reason — adding one should be a conscious decision, not a reflex to get CI
# green.
_UNGUARDED_ALLOWLIST: dict[tuple[str, str], str] = {
    ("POST", "/api/auth/login"): "issues the session; cannot require one",
    ("POST", "/api/auth/logout"): "client-side token drop, no server state in v3.0",
    ("POST", "/api/naming/validate"): "pure template compute, no persistence",
    ("POST", "/api/naming/preview"): "pure template compute, no persistence",
    ("POST", "/api/sessions/preview"): "pure template compute, no persistence",
    ("POST", "/api/notifications/services/{service_id}/compose-url"): "pure URL compute, no persistence",
    # Read-only today (recomputes online/stale counts). Its own docstring says a
    # follow-up will add ripper-side hardware re-enumeration behind this verb —
    # when that lands this entry must go and the route becomes require_writer.
    ("POST", "/api/drives/rescan"): "read-only recount; see drives.py rescan_drives docstring",
}


def _walk(dependant: Dependant) -> list[object]:
    """Every callable in a route's dependency tree, including sub-dependencies."""
    calls: list[object] = []
    if dependant.call is not None:
        calls.append(dependant.call)
    for sub in dependant.dependencies:
        calls.extend(_walk(sub))
    return calls


def _mutating_routes() -> list[tuple[str, str, APIRoute]]:
    out: list[tuple[str, str, APIRoute]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods or set()):
            if method in _MUTATING_METHODS:
                out.append((method, route.path, route))
    return out


def test_every_mutating_route_is_guarded() -> None:
    unguarded: list[str] = []
    for method, path, route in _mutating_routes():
        if (method, path) in _UNGUARDED_ALLOWLIST:
            continue
        if not _WRITE_GUARDS.intersection(_walk(route.dependant)):
            unguarded.append(f"{method} {path}")
    assert not unguarded, (
        "mutating routes with no write guard: "
        + ", ".join(sorted(unguarded))
        + " — add Depends(require_writer) (or a service-token guard), or an "
        "entry with a reason in _UNGUARDED_ALLOWLIST"
    )


def test_allowlist_has_no_stale_entries() -> None:
    """A route that gained a guard (or was deleted) must not linger in the
    allowlist — a stale entry would silently exempt a future route reusing
    that method+path."""
    live = {(m, p) for m, p, _ in _mutating_routes()}
    guarded_now = {(m, p) for m, p, r in _mutating_routes() if _WRITE_GUARDS.intersection(_walk(r.dependant))}
    stale = [f"{m} {p}" for (m, p) in _UNGUARDED_ALLOWLIST if (m, p) not in live or (m, p) in guarded_now]
    assert not stale, f"stale _UNGUARDED_ALLOWLIST entries (route gone or now guarded): {sorted(stale)}"
