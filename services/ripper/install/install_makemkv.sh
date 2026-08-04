#!/usr/bin/env bash
# Build MakeMKV from upstream signed tarballs and install into /usr/local.
#
# Derived from
# https://github.com/tianon/dockerfiles/blob/master/makemkv/Dockerfile
# (Expat/MIT). Same recipe: scrape the current version, fetch oss + bin
# tarballs and the signed sha256 file, verify both, build oss, accept the
# bin EULA, install bin. No license is bundled — the runtime container
# acquires a working app_Key via update_key.sh, which the ripper runs
# before every rip (arm_ripper/makemkv_key.py).
set -euxo pipefail

# Optional internal mirror (MAKEMKV_MIRROR_URL) — used instead of
# makemkv.com when set, e.g. to ride out makemkv.com outages or to get
# reproducible rebuilds after upstream deletes old tarballs. Expected layout:
#   $MAKEMKV_MIRROR_URL/LATEST                      -> current version string
#   $MAKEMKV_MIRROR_URL/<ver>/makemkv-sha-<ver>.txt -> original signed sha file
#   $MAKEMKV_MIRROR_URL/<ver>/makemkv-{oss,bin}-<ver>.tar.gz
# MAKEMKV_MIRROR_PASSWORD (optional) is sent as an X-SHARE-PASSWORD header
# (Filebrowser password-protected shares). The GPG + sha256 verification
# below is identical for both sources, so the mirror needs zero trust.
#
# xtrace is suspended around password handling so the secret never lands in
# build logs; it is passed to curl via --config for the same reason.
{ set +x; } 2>/dev/null
MAKEMKV_MIRROR_URL="${MAKEMKV_MIRROR_URL:-}"
MIRROR_CURL_CFG=""
if [[ -n "${MAKEMKV_MIRROR_PASSWORD:-}" ]]; then
    umask_prev="$(umask)"; umask 077
    MIRROR_CURL_CFG="$(mktemp)"
    printf 'header "X-SHARE-PASSWORD: %s"\n' "$MAKEMKV_MIRROR_PASSWORD" > "$MIRROR_CURL_CFG"
    umask "$umask_prev"
fi
set -x

fetch() { # fetch <curl-args...> — curl with the mirror auth header, if any
    if [[ -n "$MIRROR_CURL_CFG" ]]; then
        curl -fsSL --config "$MIRROR_CURL_CFG" "$@"
    else
        curl -fsSL "$@"
    fi
}

if [[ -n "$MAKEMKV_MIRROR_URL" ]]; then
    MAKEMKV_VERSION="$(fetch "$MAKEMKV_MIRROR_URL/LATEST" | tr -d '[:space:]')"
    test -n "$MAKEMKV_VERSION"
    DOWNLOAD_BASE="$MAKEMKV_MIRROR_URL/$MAKEMKV_VERSION"
    echo "Building MakeMKV ${MAKEMKV_VERSION} (source: mirror)"
else
    MAKEMKV_VERSION="$(curl -fsSL https://www.makemkv.com/download/ | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)"
    test -n "$MAKEMKV_VERSION"
    DOWNLOAD_BASE="https://www.makemkv.com/download"
    echo "Building MakeMKV ${MAKEMKV_VERSION}"
fi

work="$(mktemp -d)"
cd "$work"

fetch -O "$DOWNLOAD_BASE/makemkv-sha-${MAKEMKV_VERSION}.txt"
mv "makemkv-sha-${MAKEMKV_VERSION}.txt" sha256sums.txt.sig

GNUPGHOME="$(mktemp -d)" && export GNUPGHOME
# Fetch the MakeMKV signing key (DSA 2ECF23305F1FC0B32001673394E3083A18042697,
# owned by GuinpinSoft). `keys.openpgp.org` strips user IDs by policy which
# makes the key unusable for signature verification, so it's the LAST
# fallback after the keyservers that preserve UIDs. Each attempt retries
# 3× with 5s sleep to ride out transient DNS / connection blips.
KEY_FPR="2ECF23305F1FC0B32001673394E3083A18042697"
got_key=0
for ks in keyserver.ubuntu.com pgp.mit.edu; do
    for attempt in 1 2 3; do
        if gpg --batch --keyserver "hkps://$ks" --recv-keys "$KEY_FPR"; then
            # Confirm the key has at least one user ID — keys.openpgp.org's
            # UID-stripping behaviour would silently break verification below.
            if gpg --batch --list-keys "$KEY_FPR" | grep -q "^uid"; then
                got_key=1
                break 2
            fi
            echo "keyserver $ks returned key without UIDs; trying next"
            break
        fi
        echo "keyserver $ks attempt $attempt failed"
        sleep 5
    done
done
[[ $got_key -eq 1 ]] || { echo "all keyservers failed"; exit 1; }
gpg --batch --decrypt --output sha256sums.txt sha256sums.txt.sig
gpgconf --kill all
rm -rf "$GNUPGHOME" sha256sums.txt.sig

PREFIX="/usr/local"
for ball in makemkv-oss makemkv-bin; do
    fetch -O "$DOWNLOAD_BASE/${ball}-${MAKEMKV_VERSION}.tar.gz"
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
if [[ -n "$MIRROR_CURL_CFG" ]]; then rm -f "$MIRROR_CURL_CFG"; fi
ldconfig
