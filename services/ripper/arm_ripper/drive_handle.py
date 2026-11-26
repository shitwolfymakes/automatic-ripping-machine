"""The single source of truth for "which node is my drive on right now".

The poll loop, heartbeat loop, JobController, boot probe and eject all
read this handle; only the poll loop writes it. A private copy of the
device path captured once at startup would go stale after a renumbering
replug: the poll loop would follow the drive while the heartbeat probed a
stale node forever and a manual rip could target another drive entirely.
"""

from __future__ import annotations


class DriveHandle:
    __slots__ = ("_path",)

    def __init__(self, path: str | None = None) -> None:
        self._path = path

    @classmethod
    def fixed(cls, path: str) -> DriveHandle:
        """A handle for a source that never moves (an ISO source
        (ARM_SOURCE_PATH) or a test)."""
        return cls(path)

    @property
    def current(self) -> str | None:
        return self._path

    @property
    def absent(self) -> bool:
        return self._path is None

    def set(self, path: str | None) -> bool:
        """Update the current node. Returns True iff it changed, so the
        caller can log the transition exactly once."""
        if path == self._path:
            return False
        self._path = path
        return True

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"DriveHandle({self._path!r})"
