# TODO(v3-release): pin both stages by @sha256:<digest> — see docs/arch/06-deployment.md

# ---------- Stage 1: build MakeMKV from upstream signed tarballs ----------
FROM python:3.14-slim-bookworm AS mkv-build

ENV DEBIAN_FRONTEND=noninteractive

# Build deps for makemkv-oss + makemkv-bin (mirrors v2 temp_install_mkv_hb_deps.sh,
# minus HandBrake — that lands in Phase 7 with the transcode container).
# qtbase5-dev is needed because MakeMKV's OSS configure builds a GUI that we
# never ship; we only copy makemkvcon out into the runtime stage.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        dirmngr \
        g++ \
        gcc \
        gnupg \
        libavcodec-dev \
        libexpat-dev \
        libssl-dev \
        make \
        pkg-config \
        qtbase5-dev \
        wget \
        zlib1g-dev \
        openjdk-17-jre-headless \
        libtesseract-dev \
        libleptonica-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/ripper/install/install_makemkv.sh /install_makemkv.sh
RUN chmod +x /install_makemkv.sh && /install_makemkv.sh

# ccextractor is built in the same stage so MakeMKV can call it as
# /usr/local/bin/mmccextr at runtime for closed-caption SRT extraction.
# Skipped by Debian since buster — built from upstream v0.94 with -without-rust
# to avoid the cargo toolchain + crates.io fetch (the slowest part of this
# stage). OCR is compiled in unconditionally by upstream, hence the tesseract/
# leptonica -dev deps above; see install_ccextractor.sh for the details.
COPY services/ripper/install/install_ccextractor.sh /install_ccextractor.sh
RUN chmod +x /install_ccextractor.sh && /install_ccextractor.sh

# ---------- Stage 2: runtime image ----------
FROM python:3.14-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# Phase 2 runtime deps: MakeMKV handles its own DVD CSS, so we deliberately
# skip libdvd-pkg / libdvdcss here — Phase 3 (real rip pipeline) can re-add
# them if any rip-time tool turns out to need them. Keeps the image to
# main-repo packages only and avoids enabling contrib / non-free.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tini \
        gosu \
        ca-certificates \
        curl \
        abcde \
        cdparanoia \
        eject \
        flac \
        util-linux \
        libdiscid0 \
        libavcodec59 \
        libexpat1 \
        libssl3 \
        udftools \
        libtesseract5 \
        liblept5 \
    && rm -rf /var/lib/apt/lists/*

# Pull MakeMKV binaries + libs from the build stage. The bin tarball installs
# libmakemkv*, libdriveio*, and libmmbd* under /usr/local/lib/; nothing else
# in the build stage targets /usr/local/lib/, so copying the whole tree is safe.
# `mmgplsrv` is built by makemkv-oss and invoked by makemkvcon for libavcodec-
# backed decode paths — without it, some Blu-rays log MSG:4041 and degrade or
# fail, even though simpler discs scan/rip fine.
COPY --from=mkv-build /usr/local/bin/makemkvcon /usr/local/bin/makemkvcon
COPY --from=mkv-build /usr/local/bin/mmgplsrv /usr/local/bin/mmgplsrv
COPY --from=mkv-build /usr/local/bin/ccextractor /usr/local/bin/ccextractor
# mmccextr is the path MakeMKV calls; recreate as a symlink here rather than
# COPYing the symlink (BuildKit dereferences single-file symlink COPYs and
# would duplicate the binary).
RUN ln -sfn /usr/local/bin/ccextractor /usr/local/bin/mmccextr
COPY --from=mkv-build /usr/local/lib/ /usr/local/lib/
COPY --from=mkv-build /usr/local/share/MakeMKV /usr/local/share/MakeMKV
RUN ldconfig

# Pre-create the arm user's home so update_key.sh has somewhere to write.
# The shared entrypoint creates the arm user with --no-create-home; we own
# /home/arm at PUID=1000 (the entrypoint will usermod it on PUID changes).
RUN mkdir -p /home/arm/.MakeMKV \
    && chown -R 1000:1000 /home/arm

COPY services/ripper/install/update_key.sh /usr/local/bin/update_key.sh
RUN chmod +x /usr/local/bin/update_key.sh

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /usr/local/bin/

WORKDIR /app

# Source must land before `uv sync` because hatchling validates each workspace
# package's force-include (e.g. arm_ripper/py.typed) at install time.
COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock
COPY packages/arm_common /app/packages/arm_common
COPY services/backend/pyproject.toml /app/services/backend/pyproject.toml
COPY services/ripper /app/services/ripper

RUN uv sync --frozen --package arm_ripper --no-dev

COPY services/_common/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/app/services/ripper"

WORKDIR /app/services/ripper

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "arm_ripper.main"]
