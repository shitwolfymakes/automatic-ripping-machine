# TODO(v3-release): pin by @sha256:<digest> — see docs/arch/06-deployment.md
FROM python:3.14-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# The backend no longer touches GPUs: GPU detection happens host-side at
# install time and arrives via the `ARM_GPUS` env (see arm_backend/gpu_probe.py),
# so no `nvidia-smi` / NVIDIA userspace is baked in here. The only container that
# needs GPU access is the ephemeral transcoder, which the dispatcher grants
# per-task.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tini \
        gosu \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy workspace root + packages + the backend service (context = repo root).
# Source must land before `uv sync` because hatchling validates each workspace
# package's force-include (e.g. arm_backend/py.typed) at install time.
COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock
COPY packages/arm_common /app/packages/arm_common
COPY services/ripper/pyproject.toml /app/services/ripper/pyproject.toml
COPY services/backend /app/services/backend

RUN uv sync --frozen --package arm_backend --no-dev

COPY services/_common/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Ship the project license in the image (placed late — it rarely changes, so
# it never busts the cache of the uv-sync layer above).
COPY LICENSE /LICENSE

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/app/services/backend"

WORKDIR /app/services/backend

EXPOSE 8443

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "arm_backend.main"]
