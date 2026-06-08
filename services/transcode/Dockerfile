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
# handbrake-cli + ffmpeg + flac are the encoder toolchain. util-linux pulls in
# `flock` for the atomic-rename safety net.
#
# Phase 7b — this is the fat, multi-vendor HW-transcode image (published to
# Docker Hub; the dispatcher spawns it ephemerally per task and injects the
# right device access). It bakes in the VAAPI/QSV *userspace*:
#   - libva2 / libva-drm2 / vainfo — the VAAPI loader + a probe tool.
#   - mesa-va-drivers           — AMD (VAAPI/VCN).
#   - intel-media-va-driver-non-free + i965-va-driver — Intel QSV (modern +
#     legacy iGPUs). The newer driver lives in Debian `non-free`.
#   - libvpl2                   — oneVPL runtime for Intel QSV.
# We apt-install `handbrake-cli` for its full runtime dependency closure, then
# (further down) overwrite the binary with our HW-enabled build from the builder
# stage. NVENC needs nothing baked here: `libnvidia-encode` is injected at
# runtime by the host's NVIDIA Container Toolkit. The kernel device nodes
# (/dev/dri/*, /dev/nvidia*) are passed in per-container by the dispatcher.
#
# `python:3.14-slim-bookworm` ships its base sources in deb822 format with an
# explicit `Signed-By:` directive; legacy lines we add must carry the matching
# `[signed-by=…]` option or apt errors with "Conflicting values ... Signed-By".
RUN echo 'deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] http://deb.debian.org/debian bookworm main contrib non-free non-free-firmware' \
        > /etc/apt/sources.list.d/non-free.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        tini \
        gosu \
        ca-certificates \
        curl \
        handbrake-cli \
        ffmpeg \
        flac \
        util-linux \
        libva2 \
        libva-drm2 \
        vainfo \
        mesa-va-drivers \
        intel-media-va-driver-non-free \
        i965-va-driver \
        libvpl2 \
    && rm -rf /var/lib/apt/lists/*

# Replace Debian's HW-less HandBrakeCLI with the HW-enabled build (NVENC/QSV/VCE).
COPY --from=handbrake-builder /HandBrake/build/HandBrakeCLI /usr/bin/HandBrakeCLI

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
