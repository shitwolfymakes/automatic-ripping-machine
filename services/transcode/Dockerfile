# TODO(v3-release): pin base image by @sha256:<digest> — see docs/arch/06-deployment.md

# ---- HandBrake CLI builder ------------------------------------------------
# Debian's `handbrake-cli` package ships with NO hardware encoders (only x264/
# x265/SVT-AV1 software), so we compile HandBrakeCLI from source with the HW
# encoders enabled: --enable-nvenc (NVIDIA), --enable-qsv (Intel), --enable-vce
# (AMD VCN). The runtime stage below copies this binary over Debian's, reusing
# Debian's dependency closure. Bookworm builder so sonames match the runtime.
# Pinned to a release tag; bump HANDBRAKE_VERSION to upgrade.
FROM debian:bookworm AS handbrake-builder
ARG HANDBRAKE_VERSION=1.11.1
# nv-codec-headers pin. HandBrake 1.11.x defaults to 13.0.19.0, whose NVENC API
# (13.0) demands NVIDIA driver >= 570. Stable distros lag: Debian 13 (trixie)
# ships driver 550 from `nvidia-driver` and going off-package isn't advisable, so
# the 13.0 default makes every GPU encode die `rc=3` at `avcodec_open`
# ("Driver does not support the required nvenc API version"). We override the
# pin to 12.1.14.0, which (a) FFmpeg 8.0.1 — what HandBrake 1.11.1 bundles —
# accepts (its floor is `ffnvcodec >= 12.1.14.0`) and (b) requires only driver
# >= 530.41.03. NVENC is backward-compatible, so the binary still runs on 570+
# hosts; we just forgo 13.0-only features ARM doesn't use (h264/h265 only).
# Keep ARM_NVENC_MIN_DRIVER (install.sh / devtools/setup-dev.sh) in sync with the
# driver floor of whatever version is pinned here. Re-verify both the FFmpeg floor
# and the driver requirement when bumping HANDBRAKE_VERSION.
ARG NVCODEC_VERSION=12.1.14.0
ARG NVCODEC_SHA256=62b30ab37e4e9be0d0c5b37b8fee4b094e38e570984d56e1135a6b6c2c164c9f
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        autoconf automake build-essential ca-certificates cmake git \
        libass-dev libbz2-dev libfontconfig-dev libfreetype-dev libfribidi-dev \
        libharfbuzz-dev libjansson-dev liblzma-dev libmp3lame-dev libnuma-dev \
        libogg-dev libopus-dev libsamplerate0-dev libspeex-dev libtheora-dev \
        libtool libtool-bin libturbojpeg0-dev libvorbis-dev libx264-dev \
        libxml2-dev libvpx-dev m4 make meson nasm ninja-build patch pkg-config \
        tar zlib1g-dev curl libssl-dev clang \
        libva-dev libdrm-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --branch "${HANDBRAKE_VERSION}" --depth 1 https://github.com/HandBrake/HandBrake.git /HandBrake
WORKDIR /HandBrake
# Re-pin the contrib nv-codec-headers (see ARG comment above for the why). The
# version string appears in both the basename and the FFmpeg release path, so a
# global swap rewrites every URL; the HandBrake-contribs mirror won't host the
# older tarball, but HandBrake's fetcher falls through to the FFmpeg upstream URL
# on 404. The grep asserts the patch landed so a future HANDBRAKE_VERSION bump
# that changes module.defs fails the build loudly instead of silently shipping
# the 570-only default.
RUN set -eux; \
    sed -i \
      -e "s|13\.0\.19\.0|${NVCODEC_VERSION}|g" \
      -e "s|13da39edb3a40ed9713ae390ca89faa2f1202c9dda869ef306a8d4383e242bee|${NVCODEC_SHA256}|" \
      contrib/nvenc/module.defs; \
    grep -q "n${NVCODEC_VERSION}/nv-codec-headers-${NVCODEC_VERSION}.tar.gz" contrib/nvenc/module.defs; \
    grep -q "${NVCODEC_SHA256}" contrib/nvenc/module.defs
# `--launch` runs the build immediately; contrib libs (incl. nv-codec-headers
# and oneVPL) are fetched + built by HandBrake's own contrib system.
RUN ./configure --launch-jobs="$(nproc)" --launch --disable-gtk \
        --enable-qsv --enable-nvenc --enable-vce \
    && strip build/HandBrakeCLI

# ---- runtime image --------------------------------------------------------
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
