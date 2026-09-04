"""The single source of truth for "which node is my drive on right now".

Before this existed, the poll loop, heartbeat loop, JobController, boot
probe and eject each held their own copy of the device path, captured
once at startup. After a renumbering replug they disagreed: the poll loop
followed the drive while the heartbeat probed a stale node forever and a
manual rip could target another drive entirely. Every consumer now reads
this handle; only the poll loop writes it.
"""

from __future__ import annotations


class DriveHandle:
    __slots__ = ("_path",)

    def __init__(self, path: str | None = None) -> None:
        self._path = path

    @classmethod
    def fixed(cls, path: str) -> DriveHandle:
        """A handle for a source that never moves (an ISO file in
        manual-trigger mode, or a test)."""
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
