#!/usr/bin/env bash
# ARM v3 installer.
#
# This file is only a bootstrap. It picks a release, downloads that release's
# installer bundle into <location>/arm/.armctl/releases/<tag>/, writes the
# `armctl` launcher, and hands over to `armctl install`, which does the rest.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/install.sh | bash
#   curl -fsSL <same url> | bash -s -- --version v3.1.0   # options through the pipe
#   bash install.sh                    # install into ~/arm
#   bash install.sh --prefix /srv        # install into /srv/arm
#   bash install.sh --version v3.1.0     # a specific release
#   bash install.sh --profile ripper-only --yes     # unattended; see below
#
# Run from a checkout of the repository, it packs a bundle from that checkout
# instead of downloading one (for development and for the install drill).
#
# Any option it does not list is passed on to `armctl install`
# (see deploy/install/flow.sh, or run `armctl install --help` afterwards).
# See docs/developers/architecture/06-deployment.md for the full design.

set -euo pipefail

# GitHub repo whose releases carry the installer bundle and name the image
# tags. Override for a fork with --release-repo or ARM_RELEASE_REPO.
ARM_RELEASE_REPO="${ARM_RELEASE_REPO:-automatic-ripping-machine/automatic-ripping-machine}"
# The latest stable release must be on this major line. Guards against picking
# up the repo's latest v2 stable, which has no v3 bundle or images.
ARM_EXPECTED_MAJOR="3"

bootstrap_usage() {
    cat <<'EOF'
ARM v3 installer.

Usage: install.sh [options] [armctl install options]

  --prefix <dir>      where the `arm` folder goes (default: your home folder,
                      giving ~/arm). The folder is always named `arm`.
  --version <tag>     install this release instead of the latest stable one
  --release-repo <owner/repo>
                      GitHub repo to take releases from (forks)
  --bundle <file>     use a local bundle file instead of downloading one
                      (needs --version; its .sha256 file must sit beside it)
  -h, --help          show this help

Everything else is passed to `armctl install`, for example:
  --profile <full|ripper-only|offload>   --raw-path <dir>   --media-path <dir>
  --yes   --no-host-changes   --no-start

When the installer is piped into bash, put the options after `bash -s --`:
  curl -fsSL <url> | bash -s -- --version <tag>
  curl -fsSL <url> | bash -s -- --prefix /srv --version <tag>
EOF
}

bootstrap_err() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
bootstrap_log() { printf '  %s\n' "$*"; }
bootstrap_uid() { id -u; }

# Print the latest stable (non-prerelease) release tag of ARM_RELEASE_REPO.
bootstrap_resolve_tag() {
    local url="https://api.github.com/repos/${ARM_RELEASE_REPO}/releases/latest" body tag
    # /releases/latest returns the newest non-prerelease, non-draft release.
    if ! body="$(curl -fsSL -H 'Accept: application/vnd.github+json' "${url}" 2>/dev/null)"; then
        bootstrap_err "could not find a stable release of '${ARM_RELEASE_REPO}' (GitHub unreachable, rate-limited, or no stable release yet). Name one with --version <tag>, or point at another repo with --release-repo."
    fi
    tag="$(printf '%s' "${body}" | grep -m1 '"tag_name"' | sed -E 's/.*"tag_name"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/')"
    [[ -n "${tag}" ]] || bootstrap_err "could not read a release tag from '${ARM_RELEASE_REPO}'. Name one with --version <tag>."
    if [[ ! "${tag}" =~ ^v?${ARM_EXPECTED_MAJOR}\. ]]; then
        bootstrap_err "the latest stable release of '${ARM_RELEASE_REPO}' is ${tag}, not a v${ARM_EXPECTED_MAJOR} release. Name a v${ARM_EXPECTED_MAJOR} release with --version <tag>, or point at a repo that has one with --release-repo."
    fi
    printf '%s' "${tag}"
}

# Refuse a tag that could name another folder (it becomes a folder name).
bootstrap_check_tag() {
    if [[ ! "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
        bootstrap_err "'$1' is not a valid release tag (letters, digits, '.', '_' and '-' only, not starting with a punctuation mark). Nothing was changed."
    fi
}

# bootstrap_fetch_bundle <tag> <dest dir> [local bundle path]
# Download (or copy) the bundle and its checksum, verify, and unpack into
# <dest>. On any failure <dest> is left exactly as it was: the bundle is
# unpacked beside it first and moved into place only when complete.
bootstrap_fetch_bundle() {
    local tag="$1" dest="$2" local_bundle="${3:-}" tmp archive base want got
    bootstrap_check_tag "${tag}"
    tmp="$(mktemp -d)"
    archive="${tmp}/bundle.tar.gz"
    if [[ -n "${local_bundle}" ]]; then
        if ! cp "${local_bundle}" "${archive}" 2>/dev/null || ! cp "${local_bundle}.sha256" "${archive}.sha256" 2>/dev/null; then
            rm -rf "${tmp}"
            bootstrap_err "cannot read ${local_bundle} and ${local_bundle}.sha256"
        fi
    else
        base="https://github.com/${ARM_RELEASE_REPO}/releases/download/${tag}/arm-installer-${tag}.tar.gz"
        if ! curl -fsSL -o "${archive}" "${base}" || ! curl -fsSL -o "${archive}.sha256" "${base}.sha256"; then
            rm -rf "${tmp}"
            bootstrap_err "could not download the installer bundle for ${tag} from '${ARM_RELEASE_REPO}'. Check the network and that the release exists. Nothing was changed."
        fi
    fi
    want="$(awk '{print $1; exit}' "${archive}.sha256")"
    got="$(sha256sum "${archive}" | awk '{print $1}')"
    if [[ -z "${want}" || "${want}" != "${got}" ]]; then
        rm -rf "${tmp}"
        bootstrap_err "the installer bundle for ${tag} failed its checksum (expected ${want:-nothing}, got ${got}). Nothing was changed."
    fi
    # Refuse an archive whose members could land outside the release folder.
    # The listing is captured first: with pipefail, `tar | grep -q` can report
    # failure when grep matches and exits early, which would let it through.
    local listing
    if ! listing="$(tar -tzf "${archive}")" || grep -qE '(^/|(^|/)\.\.(/|$))' <<<"${listing}"; then
        rm -rf "${tmp}"
        bootstrap_err "the installer bundle for ${tag} is unreadable or contains unsafe paths. Nothing was changed."
    fi
    rm -rf "${dest}.partial"
    mkdir -p "${dest}.partial"
    if ! tar -xzf "${archive}" --no-same-owner -C "${dest}.partial" \
        || [[ ! -f "${dest}.partial/armctl.sh" || ! -f "${dest}.partial/docker-compose.yml.example" ]]; then
        rm -rf "${tmp}" "${dest}.partial"
        bootstrap_err "the installer bundle for ${tag} is incomplete. Nothing was changed."
    fi
    rm -rf "${dest}"
    mv "${dest}.partial" "${dest}"
    rm -rf "${tmp}"
}

# The install folder is always named `arm` (the compose template writes its
# paths as ./arm/...). --prefix names the folder it goes in; a prefix that
# already ends in `arm` is taken to be the arm folder itself.
bootstrap_arm_dir() {
    local prefix="${1%/}"
    if [[ "$(basename "${prefix}")" == "arm" ]]; then
        printf '%s' "${prefix}"
    else
        printf '%s/arm' "${prefix}"
    fi
}

# Fresh installs only: refuse a folder that has content but is not an armctl
# install (an ARM v2 home, or the layout the old v3 installer produced).
bootstrap_check_target() {
    local dir="$1"
    if [[ ! -e "${dir}" ]]; then
        return 0
    fi
    [[ -d "${dir}" ]] || bootstrap_err "${dir} exists and is not a folder. Choose another location with --prefix."
    if [[ -d "${dir}/.armctl" ]]; then
        return 0
    fi
    if [[ -n "$(ls -A "${dir}" 2>/dev/null)" ]]; then
        bootstrap_err "${dir} already has files in it and was not created by this installer. ARM v3 installs into a new or empty folder; it does not convert an ARM v2 folder or an install made by the old v3 installer. Choose another location with --prefix, or move that folder aside first. Nothing was changed."
    fi
}

# The launcher resolves its own location (also through a PATH link), so the
# arm folder can be moved as a whole.
bootstrap_write_launcher() {
    local arm_dir="$1"
    cat > "${arm_dir}/armctl" <<'LAUNCHER'
#!/usr/bin/env bash
# Generated by the ARM installer. Runs the currently installed release's armctl.
ARM_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
export ARM_DIR
exec "${ARM_DIR}/.armctl/current/armctl.sh" "$@"
LAUNCHER
    chmod 755 "${arm_dir}/armctl"
}

# Its own function so tests can replace it: `exec` cannot be stubbed.
# Under `curl | bash`, stdin is the script, so prompts must read the terminal.
bootstrap_handover() {
    if [[ ! -t 0 ]] && { : </dev/tty; } 2>/dev/null; then
        exec "$@" </dev/tty
    fi
    exec "$@"
}

bootstrap_main() {
    local prefix="" prefix_given=0 version="" bundle="" pass=() arm_dir tag script_dir="" bin
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --prefix)         [[ $# -ge 2 ]] || bootstrap_err "--prefix needs a folder"; prefix="$2"; prefix_given=1; shift 2 ;;
            --prefix=*)       prefix="${1#*=}"; prefix_given=1; shift ;;
            --version)        [[ $# -ge 2 ]] || bootstrap_err "--version needs a release tag"; bootstrap_check_tag "$2"; version="$2"; shift 2 ;;
            --version=*)      bootstrap_check_tag "${1#*=}"; version="${1#*=}"; shift ;;
            --bundle)         [[ $# -ge 2 ]] || bootstrap_err "--bundle needs a file"; bundle="$2"; shift 2 ;;
            --bundle=*)       bundle="${1#*=}"; shift ;;
            --release-repo)   [[ $# -ge 2 ]] || bootstrap_err "--release-repo needs owner/repo"; ARM_RELEASE_REPO="$2"; pass+=(--release-repo "$2"); shift 2 ;;
            --release-repo=*) ARM_RELEASE_REPO="${1#*=}"; pass+=(--release-repo "${1#*=}"); shift ;;
            -h|--help)        bootstrap_usage; return 0 ;;
            *)                pass+=("$1"); shift ;;
        esac
    done

    if [[ "$(bootstrap_uid)" -eq 0 ]]; then
        bootstrap_err "do not run the ARM installer as root or with sudo. ARM records the user who installs it as the owner of your media files, and root is not accepted. Run it as your normal user; it asks for sudo only when a step needs it."
    fi
    for bin in curl tar sha256sum; do
        command -v "${bin}" >/dev/null 2>&1 || bootstrap_err "'${bin}' is needed to install ARM. Install it (on Debian or Ubuntu: sudo apt-get install -y curl tar coreutils) and run the installer again."
    done

    # Only an explicit --prefix may name the arm folder itself. The default
    # is always <home>/arm, even for a user whose home folder is called arm.
    if [[ "${prefix_given}" -eq 1 ]]; then
        [[ "${prefix}" == /* ]] || prefix="${PWD}/${prefix}"
        arm_dir="$(bootstrap_arm_dir "${prefix}")"
    else
        arm_dir="${HOME}/arm"
    fi
    bootstrap_check_target "${arm_dir}"

    # From a checkout, pack a bundle from the checkout itself.
    if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    fi
    if [[ -z "${bundle}" && -n "${script_dir}" && -f "${script_dir}/deploy/build-bundle.sh" ]]; then
        version="${version:-v$(cat "${script_dir}/VERSION")}"
        bootstrap_log "running from a checkout; packing a bundle for ${version}"
        bundle="$(bash "${script_dir}/deploy/build-bundle.sh" "${version}" "$(mktemp -d)")"
    fi
    if [[ -n "${bundle}" && -z "${version}" ]]; then
        bootstrap_err "--bundle needs --version <tag>, the release the bundle is for"
    fi
    tag="${version:-$(bootstrap_resolve_tag)}"
    bootstrap_log "installing ARM ${tag} into ${arm_dir}"

    # Fetch into a staging folder first: nothing under the arm folder is created
    # until the bundle is verified and unpacked, so a failure (bootstrap_err
    # exits) leaves the target exactly as it was. The trap removes the staging
    # folder; it is cleared before the handover.
    BOOTSTRAP_STAGE="$(mktemp -d)"
    trap 'rm -rf "${BOOTSTRAP_STAGE:-}"' EXIT
    bootstrap_fetch_bundle "${tag}" "${BOOTSTRAP_STAGE}/release" "${bundle}"
    mkdir -p "${arm_dir}/.armctl/releases"
    chmod 700 "${arm_dir}/.armctl"
    rm -rf "${arm_dir}/.armctl/releases/${tag}"
    mv "${BOOTSTRAP_STAGE}/release" "${arm_dir}/.armctl/releases/${tag}"
    rm -rf "${BOOTSTRAP_STAGE}"
    trap - EXIT
    ln -sfn "releases/${tag}" "${arm_dir}/.armctl/current"
    bootstrap_write_launcher "${arm_dir}"

    export ARM_DIR="${arm_dir}"
    bootstrap_handover "${arm_dir}/armctl" install "${pass[@]+"${pass[@]}"}"
}

# Test seam, and how `armctl upgrade` reuses the functions above: source with
# ARM_INSTALL_SOURCE_ONLY=1 to define them without running an install. The
# sourced-ness check makes a leaked env var harmless when the file is executed.
[[ -n "${ARM_INSTALL_SOURCE_ONLY:-}" && "${BASH_SOURCE[0]}" != "$0" ]] && return 0

bootstrap_main "$@"
