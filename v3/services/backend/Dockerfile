# TODO(v3-release): pin by @sha256:<digest> — see docs/arch/06-deployment.md
FROM python:3.14-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# Phase 7b: install `nvidia-smi` (via `nvidia-utils-535`) so the GPU probe
# can enumerate NVENC devices without depending on the NVIDIA Container
# Toolkit's auto-mount path. `nvidia-utils-XXX` lives in Debian's `non-free`
# component and the 535 LTS branch is in `bookworm-backports`. Override the
# version with `--build-arg NVIDIA_UTILS_VERSION=...` if your host driver
# is on a different branch — `nvidia-smi` will refuse to talk to a driver
# whose major version doesn't match. The probe handles that gracefully
# (non-zero exit → empty NVENC list → CPU fallback).
ARG NVIDIA_UTILS_VERSION=535
RUN echo 'deb http://deb.debian.org/debian bookworm main contrib non-free non-free-firmware' \
        > /etc/apt/sources.list.d/non-free.list \
    && echo 'deb http://deb.debian.org/debian bookworm-backports main contrib non-free non-free-firmware' \
        > /etc/apt/sources.list.d/backports.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        tini \
        gosu \
        curl \
        ca-certificates \
    && apt-get install -y --no-install-recommends -t bookworm-backports \
        nvidia-utils-${NVIDIA_UTILS_VERSION} \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy workspace root + packages + the backend service (context = v3/).
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

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/app/services/backend"

WORKDIR /app/services/backend

EXPOSE 8443

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "arm_backend.main"]
