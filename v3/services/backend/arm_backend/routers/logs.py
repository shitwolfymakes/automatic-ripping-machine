"""Phase 12 — per-job log query + bug-report zip endpoints.

Two read-only endpoints scoped to a single `job_id`:

- `GET /api/logs/{job_id}` — NDJSON stream of every line tagged with
  the requested `job_id`. Sourced from `/logs/jobs/{job_id}.log`
  (written by `LogTailer`); falls back to scanning `/logs/*.log` when
  the per-job file is absent (legacy jobs predating the tailer's
  per-job append). `?limit=N` caps the line count.

- `GET /api/logs/{job_id}.zip` — in-memory zip. Single entry sourced
  from the per-job file when present; legacy fallback walks the
  service logs and writes one entry per service. Per-entry caps:
  5000 lines or 5 MB, whichever hits first.

Both endpoints require a UI JWT — service-token callers are rejected.
The download URL the UI hardcodes is `/api/logs/{jobId}.zip`; there's
no global "give me the bug-report URL" diagnostics field, because the
URL is per-job and we don't want to thread `?job_id=` through the
diagnostics surface.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse

from arm_backend.auth import require_jwt
from arm_backend.routers._params import JobIdParam
from arm_common import User
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
    pin the param with `pattern=`. As a final barrier the resolved path is
    confirmed to stay within `LOG_DIR/jobs` (also closes symlink escapes).
    """
    if not is_valid_id("job", job_id):
        raise ValueError(f"invalid job_id: {job_id!r}")
    jobs_dir = LOG_DIR / "jobs"
    candidate = jobs_dir / f"{job_id}.log"
    base = os.path.realpath(jobs_dir)
    if os.path.commonpath([os.path.realpath(candidate), base]) != base:
        raise ValueError(f"job_id escapes log dir: {job_id!r}")
    return candidate


# Defaults / caps for the streaming grep endpoint. Per-file (not global)
# — see the module docstring.
PER_FILE_DEFAULT = 1000
PER_FILE_HARD_CAP = 10_000

# Caps for each zip entry. 5000 lines × 5 MB matches the homelab-scale
# expectation: a worst-case rip emits ~hundreds of lines, never 5k+.
ZIP_PER_ENTRY_LINE_CAP = 5000
ZIP_PER_ENTRY_BYTE_CAP = 5 * 1024 * 1024


router = APIRouter(prefix="/api/logs", tags=["logs"])


# Declared before `/{job_id}` so FastAPI matches the `.zip` suffix first;
# otherwise `/{job_id}` would consume `job_x.zip` as a job_id with `.zip`
# in it and the zip route would be unreachable.
@router.get("/{job_id}.zip")
async def download_job_logs_zip(
    job_id: JobIdParam,
    _: User = Depends(require_jwt),
) -> Response:
    """In-memory zip of every line tagged with `job_id`.

    Source preference:
      1. `/logs/jobs/{job_id}.log` — the per-job aggregated file written
         by `LogTailer`. Single zip entry, named `<job_id>.log`.
      2. Fallback (per-job file absent, e.g. jobs predating the tailer's
         per-job append): walk `/logs/*.log` and write one entry per
         service that contributed any matching lines.
    """
    buf = io.BytesIO()
    per_job = per_job_log_path(job_id)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if per_job.is_file():
            slice_lines = _read_capped_lines(per_job, lambda _: True)
            if slice_lines:
                zf.writestr(per_job.name, "".join(slice_lines))
        else:
            for path in sorted(LOG_DIR.glob("*.log")):
                slice_lines = _read_capped_lines(path, lambda line: _line_matches_job(line, job_id))
                if slice_lines:
                    zf.writestr(path.name, "".join(slice_lines))

    body = buf.getvalue()
    return Response(
        content=body,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="arm-logs-{job_id}.zip"',
            "Content-Length": str(len(body)),
        },
    )


@router.get("/{job_id}")
async def stream_job_logs(
    job_id: JobIdParam,
    limit: int = PER_FILE_DEFAULT,
    _: User = Depends(require_jwt),
) -> StreamingResponse:
    """NDJSON stream of every line tagged with `job_id`.

    Reads `/logs/jobs/{job_id}.log` directly when present; otherwise
    falls back to scanning `/logs/*.log` (alphabetical order; lines
    within a file in append order; no cross-file resort — the consumer
    can sort by `ts` if global ordering matters).
    """
    cap = max(0, min(limit, PER_FILE_HARD_CAP))

    def gen() -> Iterator[bytes]:
        per_job = per_job_log_path(job_id)
        if per_job.is_file():
            yielded = 0
            try:
                fh = per_job.open("r", encoding="utf-8", errors="replace")
            except OSError:
                return
            with fh:
                for line in fh:
                    out = line if line.endswith("\n") else line + "\n"
                    yield out.encode("utf-8")
                    yielded += 1
                    if yielded >= cap:
                        return
            return

        for path in sorted(LOG_DIR.glob("*.log")):
            yielded = 0
            try:
                fh = path.open("r", encoding="utf-8", errors="replace")
            except OSError:
                continue
            with fh:
                for line in fh:
                    if not _line_matches_job(line, job_id):
                        continue
                    out = line if line.endswith("\n") else line + "\n"
                    yield out.encode("utf-8")
                    yielded += 1
                    if yielded >= cap:
                        break

    return StreamingResponse(gen(), media_type="application/x-ndjson")


def _read_capped_lines(path: Path, predicate: Callable[[str], bool]) -> list[str]:
    """Read lines from `path` matching `predicate`, capped by line+byte limits."""
    out: list[str] = []
    byte_count = 0
    try:
        fh = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return out
    with fh:
        for line in fh:
            if not predicate(line):
                continue
            normalised = line if line.endswith("\n") else line + "\n"
            out.append(normalised)
            byte_count += len(normalised)
            if len(out) >= ZIP_PER_ENTRY_LINE_CAP or byte_count >= ZIP_PER_ENTRY_BYTE_CAP:
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
