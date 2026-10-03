#!/usr/bin/env bash
# deploy/install/nvidia.sh: offer the NVIDIA container toolkit.
# Sourced by deploy/armctl.sh; needs deploy/install/ui.sh loaded first.
#
# NVENC transcodes run in the transcode container with --gpus, which needs the
# NVIDIA Container Toolkit on the host. Without it the daemon rejects the device
# request and the transcode never starts.
ensure_nvidia_container_toolkit() {
    if ! command -v lspci >/dev/null 2>&1; then
        return 0
    fi
    if ! lspci 2>/dev/null | grep -qi 'nvidia'; then
        return 0  # no NVIDIA hardware
    fi
    if command -v nvidia-ctk >/dev/null 2>&1 && docker info 2>/dev/null | grep -q 'nvidia'; then
        return 0  # installed and registered with docker
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
    if ! consent "NVIDIA container toolkit" "Install nvidia-container-toolkit now (needs sudo)?"; then
        warnline "skipping nvidia-container-toolkit. NVENC stays off until it's installed; CPU transcoding still works."
        return 0
    fi
    log "installing nvidia-container-toolkit (sudo)"
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
        | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
        | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
        | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
    sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    log "nvidia-container-toolkit installed; docker 'nvidia' runtime registered"
}
