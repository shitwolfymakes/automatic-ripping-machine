"""Phase 12 — per-job log query + bug-report zip endpoints.

Two read-only endpoints scoped to a single `job_id`:

- `GET /api/logs/{job_id}` — line-by-line grep across `/logs/*.log`,
  streamed as `application/x-ndjson`. `?limit=N` is **per-file** (default
  1000, hard cap 10000) so one chatty service can't starve out the
  others.

- `GET /api/logs/{job_id}.zip` — in-memory zip with one entry per
  service that contributed any matching lines. Per-entry caps: 5000
  lines or 5 MB, whichever hits first. The user grabs the zip from
  the per-job UI page and drops it onto a github issue.

Both endpoints require a UI JWT — service-token callers are rejected.
The download URL the UI hardcodes is `/api/logs/{jobId}.zip`; there's
no global "give me the bug-report URL" diagnostics field, because the
URL is per-job and we don't want to thread `?job_id=` through the
diagnostics surface.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse

from arm_backend.auth import require_jwt
from arm_common import User

# Resolved at import time so tests can monkeypatch this module attribute.
LOG_DIR = Path("/logs")

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
    job_id: str,
    _: User = Depends(require_jwt),
) -> Response:
    """In-memory zip with one entry per service that has matching lines.

    Empty entries are omitted — a service whose log has zero lines for
    this job does not show up at all.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(LOG_DIR.glob("*.log")):
            slice_lines: list[str] = []
            byte_count = 0
            try:
                fh = path.open("r", encoding="utf-8", errors="replace")
            except OSError:
                continue
            with fh:
                for line in fh:
                    if not _line_matches_job(line, job_id):
                        continue
                    out = line if line.endswith("\n") else line + "\n"
                    slice_lines.append(out)
                    byte_count += len(out)
                    if len(slice_lines) >= ZIP_PER_ENTRY_LINE_CAP or byte_count >= ZIP_PER_ENTRY_BYTE_CAP:
                        break
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
    job_id: str,
    limit: int = PER_FILE_DEFAULT,
    _: User = Depends(require_jwt),
) -> StreamingResponse:
    """NDJSON stream of every `/logs/*.log` line whose `job_id` matches.

    Files are read in alphabetical order; within a file, lines are
    yielded in append order. No cross-file resort — the consumer can
    sort by `ts` if global ordering matters.
    """
    cap = max(0, min(limit, PER_FILE_HARD_CAP))

    def gen() -> Iterator[bytes]:
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


def _line_matches_job(line: str, job_id: str) -> bool:
    """True iff `line` is a JSON record whose `job_id` field equals `job_id`."""
    if not line.strip():
        return False
    try:
        record = json.loads(line)
    except ValueError:
        return False
    return bool(record.get("job_id") == job_id)
