# TODO(v3-release): pin by @sha256:<digest> — see docs/arch/06-deployment.md
FROM python:3.14-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# TODO(v3): install MakeMKV + libdvdcss here when the real rip path lands.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tini \
        gosu \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock
COPY packages/arm_common /app/packages/arm_common
COPY services/backend/pyproject.toml /app/services/backend/pyproject.toml
COPY services/ripper/pyproject.toml /app/services/ripper/pyproject.toml

RUN uv sync --frozen --package arm_ripper --no-dev

COPY services/ripper /app/services/ripper
COPY services/_common/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/app/services/ripper"

WORKDIR /app/services/ripper

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "arm_ripper.main"]
