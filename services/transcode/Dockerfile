# TODO(v3-release): pin base image by @sha256:<digest> — see docs/arch/06-deployment.md

FROM python:3.14-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# tini reaps HandBrake / ffmpeg subprocesses; gosu drops privileges to PUID;
# handbrake-cli + ffmpeg + flac are the encoder toolchain (CPU-only Phase 7;
# GPU passthrough lands in Phase 7b). util-linux pulls in `flock` for the
# atomic-rename safety net.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tini \
        gosu \
        ca-certificates \
        curl \
        handbrake-cli \
        ffmpeg \
        flac \
        util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /usr/local/bin/

WORKDIR /app

# Same workspace install dance as the ripper image: source must land before
# `uv sync` so hatchling can validate every workspace package's force-include.
COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock
COPY packages/arm_common /app/packages/arm_common
COPY services/backend/pyproject.toml /app/services/backend/pyproject.toml
COPY services/ripper/pyproject.toml /app/services/ripper/pyproject.toml
COPY services/transcode /app/services/transcode

RUN uv sync --frozen --package arm_transcode --no-dev

COPY services/_common/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Ship the project license in the image (placed late — it rarely changes, so
# it never busts the cache of the uv-sync layer above).
COPY LICENSE /LICENSE

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/app/services/transcode"

WORKDIR /app/services/transcode

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "arm_transcode.main"]
