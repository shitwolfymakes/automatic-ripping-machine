#!/usr/bin/env bash
# Build MakeMKV from upstream signed tarballs and install into /usr/local.
#
# Port of v2's temp_install_makemkv.sh, which itself is derived from
# https://github.com/tianon/dockerfiles/blob/master/makemkv/Dockerfile
# (Expat/MIT). Same recipe: scrape the current version, fetch oss + bin
# tarballs and the signed sha256 file, verify both, build oss, accept the
# bin EULA, install bin. No license is bundled — the runtime container
# acquires a working app_Key via update_key.sh on each boot.
set -euxo pipefail

MAKEMKV_VERSION="$(curl -fsSL https://www.makemkv.com/download/ | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)"
test -n "$MAKEMKV_VERSION"
echo "Building MakeMKV ${MAKEMKV_VERSION}"

work="$(mktemp -d)"
cd "$work"

curl -fsSLO "https://www.makemkv.com/download/makemkv-sha-${MAKEMKV_VERSION}.txt"
mv "makemkv-sha-${MAKEMKV_VERSION}.txt" sha256sums.txt.sig

GNUPGHOME="$(mktemp -d)" && export GNUPGHOME
gpg --batch --keyserver keyserver.ubuntu.com --recv-keys 2ECF23305F1FC0B32001673394E3083A18042697
gpg --batch --decrypt --output sha256sums.txt sha256sums.txt.sig
gpgconf --kill all
rm -rf "$GNUPGHOME" sha256sums.txt.sig

PREFIX="/usr/local"
for ball in makemkv-oss makemkv-bin; do
    curl -fsSLO "https://www.makemkv.com/download/${ball}-${MAKEMKV_VERSION}.tar.gz"
    expected="$(grep "  ${ball}-${MAKEMKV_VERSION}.tar.gz\$" sha256sums.txt | cut -d' ' -f1)"
    test -n "$expected"
    echo "$expected  ${ball}-${MAKEMKV_VERSION}.tar.gz" | sha256sum -c -

    mkdir -p "$ball"
    tar -xf "${ball}-${MAKEMKV_VERSION}.tar.gz" -C "$ball" --strip-components=1
    rm "${ball}-${MAKEMKV_VERSION}.tar.gz"

    pushd "$ball" >/dev/null
    if [[ -f configure ]]; then
        ./configure --prefix="$PREFIX"
    else
        mkdir -p tmp
        touch tmp/eula_accepted
    fi
    make -j "$(nproc)" PREFIX="$PREFIX"
    make install PREFIX="$PREFIX"
    popd >/dev/null
done

cd /
rm -rf "$work"
ldconfig
