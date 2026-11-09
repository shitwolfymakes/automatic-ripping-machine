"""Finding and reading the log files under `LOG_DIR` (per-job, legacy
service, or any one file), capped by line and byte limits.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from arm_backend.config import settings
from arm_common.schemas import JobLogFileView
from arm_common.ulid import is_valid_id

# Resolved at import time so tests can monkeypatch this module attribute.
# `per_job_log_path` reads `LOG_DIR` at call time so a `monkeypatch.setattr`
# in a test flows through cleanly.
LOG_DIR = Path("/logs")


def per_job_log_path(job_id: str) -> Path:
    """The aggregated-log file written by `LogTailer` for `job_id`.

    `job_id` originates from a URL path param and is concatenated into a
    filesystem path, so it is validated against the `job_<ULID>` shape
    first — an unchecked `../…` would traverse out of `/logs`. Routes also
    pin the param with `pattern=`. The filename is then reduced to its
    `os.path.basename`, which strips any directory component outright — both
    a defence-in-depth barrier and the form static analysis recognises.
    """
    if not is_valid_id("job", job_id):
        raise ValueError(f"invalid job_id: {job_id!r}")
    return LOG_DIR / "jobs" / os.path.basename(f"{job_id}.log")


# Defaults / caps for the streaming grep + zip endpoints are env-tunable via
# the `ARM_LOG_*` settings (see config.py); resolved at call time so a
# `monkeypatch.setattr(settings, ...)` or env override flows through. Per-file
# (not global) — see the logs router's module docstring.


def effective_cap(limit: int | None) -> int:
    eff_limit = settings.ARM_LOG_PER_FILE_DEFAULT if limit is None else limit
    return max(0, min(eff_limit, settings.ARM_LOG_PER_FILE_HARD_CAP))


def _open_log(path: Path) -> TextIO | None:
    try:
        return path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return None


def _normalised_lines(lines: Iterable[str], predicate: Callable[[str], bool]) -> Iterator[str]:
    for line in lines:
        if not predicate(line):
            continue
        yield line if line.endswith("\n") else line + "\n"


def _iter_lines(path: Path, predicate: Callable[[str], bool], cap: int) -> Iterator[bytes]:
    fh = _open_log(path)
    if fh is None:
        return
    with fh:
        yielded = 0
        for normalised in _normalised_lines(fh, predicate):
            yield normalised.encode("utf-8")
            yielded += 1
            if yielded >= cap:
                break


def _iter_legacy(job_id: str, cap: int) -> Iterator[bytes]:
    for path in sorted(LOG_DIR.glob("*.log")):
        yield from _iter_lines(path, lambda line: _line_matches_job(line, job_id), cap)


def job_log_lines(job_id: str, cap: int) -> Iterator[bytes]:
    # `_iter_lines` checks the cap only after yielding, so a zero cap
    # would still emit one line (per file on the fallback path).
    if cap == 0:
        return
    per_job = per_job_log_path(job_id)
    if per_job.is_file():
        yield from file_log_lines(per_job, cap)
    else:
        yield from _iter_legacy(job_id, cap)


def file_log_lines(path: Path, cap: int) -> Iterator[bytes]:
    """Every line of the log file at `path`, newline-terminated, up to `cap`
    lines; nothing for a zero cap or a file that cannot be opened.
    """
    # `_iter_lines` checks the cap only after yielding, so a zero cap
    # would still emit one line.
    if cap == 0:
        return
    yield from _iter_lines(path, lambda _: True, cap)


def job_log_files() -> list[JobLogFileView]:
    jobs_dir = LOG_DIR / "jobs"
    out: list[JobLogFileView] = []
    try:
        entries = list(jobs_dir.iterdir())
    except OSError:
        return out
    for path in entries:
        if path.suffix != ".log" or not is_valid_id("job", path.stem):
            continue
        try:
            if not path.is_file():
                continue
            st = path.stat()
        except OSError:
            continue
        out.append(
            JobLogFileView(
                job_id=path.stem,
                size_bytes=st.st_size,
                modified_at=datetime.fromtimestamp(st.st_mtime, tz=UTC),
            )
        )
    out.sort(key=lambda v: v.modified_at, reverse=True)
    return out


def job_log_slices(job_id: str) -> Iterator[tuple[str, list[str]]]:
    per_job = per_job_log_path(job_id)
    if per_job.is_file():
        lines = file_log_slice(per_job)
        if lines:
            yield per_job.name, lines
        return
    for path in sorted(LOG_DIR.glob("*.log")):
        lines = _read_capped_lines(path, lambda line: _line_matches_job(line, job_id))
        if lines:
            yield path.name, lines


def file_log_slice(path: Path) -> list[str]:
    """The lines of the log file at `path` for a zip entry, newline-terminated
    and capped by the zip line and byte limits; empty when it cannot be
    opened.
    """
    return _read_capped_lines(path, lambda _: True)


def _read_capped_lines(path: Path, predicate: Callable[[str], bool]) -> list[str]:
    """Read lines from `path` matching `predicate`, capped by line+byte limits."""
    out: list[str] = []
    byte_count = 0
    fh = _open_log(path)
    if fh is None:
        return out
    with fh:
        for normalised in _normalised_lines(fh, predicate):
            out.append(normalised)
            byte_count += len(normalised)
            if (
                len(out) >= settings.ARM_LOG_ZIP_PER_ENTRY_LINE_CAP
                or byte_count >= settings.ARM_LOG_ZIP_PER_ENTRY_BYTE_CAP
            ):
                break
    return out


def _line_matches_job(line: str, job_id: str) -> bool:
    """True iff `line` is a JSON record whose `job_id` field equals `job_id`."""
    if not line.strip():
        return False
    try:
        record = json.loads(line)
    except ValueError:
        return False
    return bool(record.get("job_id") == job_id)
