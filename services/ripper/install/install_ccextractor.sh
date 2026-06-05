#!/usr/bin/env bash
# Build ccextractor from upstream and install at /usr/local/bin/ccextractor,
# with a /usr/local/bin/mmccextr symlink so MakeMKV can invoke it for closed-
# caption extraction (MSG:4041 goes away when this binary is on disk).
#
# ccextractor was removed from Debian (last shipped in buster), so the only
# reliable path is building from a pinned upstream tag. Built with -without-rust
# to skip the cargo crates.io index fetch + Rust compile (the slowest part of
# this stage); the C code has DISABLE_RUST fallbacks, so 608/708 CC -> SRT
# extraction — all MakeMKV asks for — is unaffected. OCR/tesseract is compiled
# in unconditionally by upstream, so libtesseract-dev/libleptonica-dev stay.
set -euxo pipefail

CCEXTRACTOR_VERSION="${CCEXTRACTOR_VERSION:-v0.94}"
echo "Building ccextractor ${CCEXTRACTOR_VERSION}"

work="$(mktemp -d)"
cd "$work"

curl -fsSL "https://github.com/CCExtractor/ccextractor/archive/refs/tags/${CCEXTRACTOR_VERSION}.tar.gz" \
    -o ccextractor.tar.gz
mkdir -p ccextractor
tar -xf ccextractor.tar.gz -C ccextractor --strip-components=1

# The upstream `build` script only ever inspects $1, and only to compare it
# against "-without-rust"; BLD_FLAGS is otherwise hardcoded. Any other args
# (e.g. the -DWITHOUT_HARDSUBX/-DNO_UPDATE_CHECK/-DWITHOUT_SHARING this used to
# pass) are silently ignored, so don't bother. "-without-rust" must be $1.
cd ccextractor/linux
./build -without-rust

install -m 0755 ccextractor /usr/local/bin/ccextractor
ln -sfn /usr/local/bin/ccextractor /usr/local/bin/mmccextr

cd /
rm -rf "$work"
