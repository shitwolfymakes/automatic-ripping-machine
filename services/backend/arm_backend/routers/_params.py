"""Shared, validated FastAPI path-param types.

`JobIdParam` pins a `{job_id}` path param to the exact `job_<ULID>` shape, so
a malformed id is rejected with 422 before any handler runs. Several handlers
interpolate `job_id` into a filesystem path (per-job logs, `/raw/<job_id>/`);
constraining it here is the first line of the path-traversal defence, backed
up by `is_valid_id` re-checks at the sinks themselves.
"""

from typing import Annotated

from fastapi import Path as PathParam

from arm_common.ulid import id_pattern

JobIdParam = Annotated[str, PathParam(pattern=id_pattern("job"))]
