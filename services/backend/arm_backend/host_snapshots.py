"""In-memory per-host resource snapshots (live telemetry, not persisted).

Keyed by hostname; each entry is (snapshot, received_at). Lost on backend
restart and repopulated within one heartbeat (~30s) — resources are live
telemetry, so durability is neither needed nor wanted (no DB write per beat).
Held on app.state.host_snapshots.
"""

from datetime import datetime

from arm_common.schemas import HostResourcesSnapshot


class HostSnapshotStore:
    def __init__(self) -> None:
        self._map: dict[str, tuple[HostResourcesSnapshot, datetime]] = {}

    def put(self, hostname: str, snapshot: HostResourcesSnapshot, now: datetime) -> None:
        self._map[hostname] = (snapshot, now)

    def get(self, hostname: str) -> tuple[HostResourcesSnapshot, datetime] | None:
        return self._map.get(hostname)
