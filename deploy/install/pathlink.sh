#!/usr/bin/env bash
# shellcheck disable=SC2034 # ARMCTL_CMD is read by armctl.sh and the other modules
# deploy/install/pathlink.sh: put `armctl` on the PATH.
# Sourced by deploy/armctl.sh; needs deploy/install/ui.sh loaded first.
#
# Guards: ~/.local/bin is used only when it is already on the PATH; the system
# folder needs consent (it needs sudo); a file or link that this installer did
# not create is never replaced. When no link is made, ARMCTL_CMD stays the
# full path, and that is what the end-of-install messages print.

ARMCTL_SYSTEM_BIN="${ARMCTL_SYSTEM_BIN:-/usr/local/bin}"

path_has() {
    [[ ":${PATH}:" == *":$1:"* ]]
}

# place_link <dest> <src> <sudo or empty>: 0 when dest is our link afterwards.
place_link() {
    local dest="$1" src="$2" sudo_cmd="$3"
    if [[ -L "${dest}" && "$(readlink "${dest}")" == "${src}" ]]; then
        okline "armctl is on the PATH (${dest})"
        return 0
    fi
    if [[ -e "${dest}" || -L "${dest}" ]]; then
        warnline "${dest} already exists and was not created by this installer; leaving it alone"
        SKIPPED+=("armctl on the PATH (${dest} is in the way)")
        return 1
    fi
    if [[ -n "${sudo_cmd}" ]]; then
        sudo ln -s "${src}" "${dest}"
    else
        ln -s "${src}" "${dest}"
    fi
    okline "linked ${dest}"
}

link_armctl() {
    local src="${ARM_DIR}/armctl" local_bin="${HOME}/.local/bin" sys_dest="${ARMCTL_SYSTEM_BIN}/armctl"
    if path_has "${local_bin}"; then
        mkdir -p "${local_bin}"
        if place_link "${local_bin}/armctl" "${src}" ""; then
            ARMCTL_CMD="armctl"
        fi
        return 0
    fi
    if [[ -L "${sys_dest}" && "$(readlink "${sys_dest}")" == "${src}" ]]; then
        okline "armctl is on the PATH (${sys_dest})"
        ARMCTL_CMD="armctl"
        return 0
    fi
    if [[ -e "${sys_dest}" || -L "${sys_dest}" ]]; then
        warnline "${sys_dest} already exists and was not created by this installer; leaving it alone"
        SKIPPED+=("armctl on the PATH (${sys_dest} is in the way)")
        return 0
    fi
    if consent "armctl on the PATH" "Link armctl into ${ARMCTL_SYSTEM_BIN} so it works from any folder (needs sudo)?"; then
        if place_link "${sys_dest}" "${src}" sudo; then
            ARMCTL_CMD="armctl"
        fi
    fi
    return 0
}
