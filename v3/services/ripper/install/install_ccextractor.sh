#!/usr/bin/env bash
# Build ccextractor from upstream and install at /usr/local/bin/ccextractor,
# with a /usr/local/bin/mmccextr symlink so MakeMKV can invoke it for closed-
# caption extraction (MSG:4041 goes away when this binary is on disk).
#
# ccextractor was removed from Debian (last shipped in buster), so the only
# reliable path is building from a pinned upstream tag. Built without OCR,
# hardsubx, sharing, or rust extras — those would pull in tesseract,
# leptonica, libcurl, rustc (+~300MB build deps) for features the MakeMKV
# CC-extraction call doesn't use.
set -euxo pipefail

CCEXTRACTOR_VERSION="${CCEXTRACTOR_VERSION:-v0.94}"
echo "Building ccextractor ${CCEXTRACTOR_VERSION}"

work="$(mktemp -d)"
cd "$work"

curl -fsSL "https://github.com/CCExtractor/ccextractor/archive/refs/tags/${CCEXTRACTOR_VERSION}.tar.gz" \
    -o ccextractor.tar.gz
mkdir -p ccextractor
tar -xf ccextractor.tar.gz -C ccextractor --strip-components=1

# Trim the build:
#   WITHOUT_HARDSUBX — skip hard-subtitle extraction (would pull in
#                      ffmpeg+libav-dev, ~200MB build deps we don't need)
#   NO_UPDATE_CHECK  — skip the version-check curl call at startup
#   WITHOUT_SHARING  — skip the optional submission/sharing telemetry
# Notes on what's NOT disabled:
#   * Rust — the build script runs a hard cargo check before parsing
#     flags, so we install cargo + libclang-dev and let it build.
#   * OCR — same story (the script requires libtesseract-dev regardless).
#     Keeping OCR is good for archival anyway: it lets ccextractor extract
#     burned-in hard subtitles when MakeMKV asks for SRT output.
cd ccextractor/linux
./build \
    -DWITHOUT_HARDSUBX=1 \
    -DNO_UPDATE_CHECK=1 \
    -DWITHOUT_SHARING=1

install -m 0755 ccextractor /usr/local/bin/ccextractor
ln -sfn /usr/local/bin/ccextractor /usr/local/bin/mmccextr

cd /
rm -rf "$work"
