#!/usr/bin/env bash
# deploy/install/nvidia.sh: offer the NVIDIA container toolkit.
# Sourced by deploy/armctl.sh; needs deploy/install/ui.sh loaded first.
#
# NVENC transcodes run in the transcode container with --gpus, which needs the
# NVIDIA Container Toolkit on the host. Without it the daemon rejects the device
# request and the transcode never starts.
#
# The step is optional (CPU transcoding works without it), so nothing in it
# may end the install: every failure is a warning and a SKIPPED entry.

# True when any ARM container is running: the stack (armv3-*) or a ripper or
# transcoder the backend spawned. Also true when docker cannot be asked, since
# then nothing proves the restart is safe.
arm_containers_running() {
    local names spawned
    names="$(docker ps --format '{{.Names}}' 2>/dev/null)" || return 0
    spawned="$(docker ps -q --filter "label=arm.drive_id" 2>/dev/null)" || return 0
    spawned+="$(docker ps -q --filter "label=arm.task_id" 2>/dev/null)" || return 0
    [[ -n "${spawned}" ]] && return 0
    grep -q '^armv3-' <<<"${names}"
}

# The install itself. Each command is checked, because this runs as an `if`
# condition, where errexit does not apply.
install_nvidia_toolkit_steps() {
    local key list keyring=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    key="$(curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey)" || return 1
    sudo gpg --batch --yes --dearmor -o "${keyring}" <<<"${key}" || return 1
    list="$(curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list)" || return 1
    list="${list//"deb https://"/"deb [signed-by=${keyring}] https://"}"
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null <<<"${list}" || return 1
    sudo apt-get update || return 1
    sudo apt-get install -y nvidia-container-toolkit || return 1
    sudo nvidia-ctk runtime configure --runtime=docker || return 1
    sudo systemctl restart docker || return 1
}

ensure_nvidia_container_toolkit() {
    local pci info
    if ! command -v lspci >/dev/null 2>&1; then
        return 0
    fi
    # Captured first, then searched: `producer | grep -q` under pipefail can
    # report a miss when grep stops reading early.
    pci="$(lspci 2>/dev/null || true)"
    if ! grep -qi 'nvidia' <<<"${pci}"; then
        return 0  # no NVIDIA hardware
    fi
    if command -v nvidia-ctk >/dev/null 2>&1; then
        info="$(docker info 2>/dev/null || true)"
        if grep -q 'nvidia' <<<"${info}"; then
            return 0  # installed and registered with docker
        fi
    fi
    if ! command -v apt-get >/dev/null 2>&1; then
        warn "NVIDIA GPU detected but nvidia-container-toolkit isn't set up (non-apt host)."
        cat >&2 <<'CTK'
    Install it for your distro, then re-run `armctl install`:
      https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
    After install: sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
    Skipping for now. CPU transcoding still works.
CTK
        SKIPPED+=("NVIDIA container toolkit (non-apt host; install it by hand)")
        return 0
    fi
    log "NVIDIA GPU detected; nvidia-container-toolkit enables NVENC transcoding."
    # Installing it restarts Docker, which stops every container on this host,
    # a rip or transcode in progress included.
    if arm_containers_running; then
        warnline "installing nvidia-container-toolkit restarts Docker, which would stop the ARM containers running now"
        SKIPPED+=("NVIDIA container toolkit (ARM is running and the install restarts Docker; run '${ARMCTL_CMD} down', then '${ARMCTL_CMD} install' again)")
        return 0
    fi
    if ! consent "NVIDIA container toolkit" "Install nvidia-container-toolkit now (needs sudo, and restarts Docker)?"; then
        warnline "skipping nvidia-container-toolkit. NVENC stays off until it's installed; CPU transcoding still works."
        return 0
    fi
    log "installing nvidia-container-toolkit (sudo)"
    if ! install_nvidia_toolkit_steps; then
        warnline "the nvidia-container-toolkit install failed (see the messages above). NVENC stays off; CPU transcoding still works."
        SKIPPED+=("NVIDIA container toolkit (the install failed; fix the cause, then run '${ARMCTL_CMD} install' again)")
        return 0
    fi
    log "nvidia-container-toolkit installed; docker 'nvidia' runtime registered"
}
