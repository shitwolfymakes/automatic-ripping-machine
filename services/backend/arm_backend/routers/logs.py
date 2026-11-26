"""Per-job log query + bug-report zip endpoints.

Two read-only endpoints scoped to a single `job_id`:

- `GET /api/logs/{job_id}` — NDJSON stream of every line tagged with
  the requested `job_id`. Sourced from `/logs/jobs/{job_id}.log`
  (written by `LogTailer`); falls back to scanning `/logs/*.log` when
  the per-job file is absent (legacy jobs predating the tailer's
  per-job append). `?limit=N` caps the line count.

- `GET /api/logs/{job_id}.zip` — in-memory zip. Single entry sourced
  from the per-job file when present; legacy fallback walks the
  service logs and writes one entry per service. Per-entry caps:
  `ARM_LOG_ZIP_PER_ENTRY_LINE_CAP` lines or `ARM_LOG_ZIP_PER_ENTRY_BYTE_CAP`
  bytes (env-tunable; defaults: 5000 lines / 5 MB), whichever hits first.

Both endpoints require a UI JWT — service-token callers are rejected.
The download URL the UI hardcodes is `/api/logs/{jobId}.zip`; there's
no global "give me the bug-report URL" diagnostics field, because the
URL is per-job and we don't want to thread `?job_id=` through the
diagnostics surface.
"""

from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse

from arm_backend.auth import require_jwt
from arm_backend.log_reader import effective_cap, job_log_files, job_log_lines, job_log_slices
from arm_backend.routers._params import JobIdParam
from arm_common import User
from arm_common.schemas import JobLogFileView

router = APIRouter(prefix="/api/logs", tags=["logs"])


# Plain `def`: the directory scan and per-file stat are blocking I/O, so
# FastAPI runs this in its threadpool instead of on the event loop.
@router.get("", response_model=list[JobLogFileView])
def list_job_logs(_: User = Depends(require_jwt)) -> list[JobLogFileView]:
    """Every per-job log file under `LOG_DIR/jobs`, newest first.

    Only `<job_id>.log` regular files whose stem is a valid job id are listed;
    anything else in the directory is ignored. A missing directory is `[]`.
    """
    return job_log_files()


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
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, lines in job_log_slices(job_id):
            zf.writestr(name, "".join(lines))

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
    limit: int | None = Query(default=None, ge=0),
    _: User = Depends(require_jwt),
) -> StreamingResponse:
    """NDJSON stream of every line tagged with `job_id`.

    Reads `/logs/jobs/{job_id}.log` directly when present; otherwise
    falls back to scanning `/logs/*.log` (alphabetical order; lines
    within a file in append order; no cross-file resort — the consumer
    can sort by `ts` if global ordering matters).
    """
    return StreamingResponse(job_log_lines(job_id, effective_cap(limit)), media_type="application/x-ndjson")
