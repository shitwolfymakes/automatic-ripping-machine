#!/usr/bin/env bash
# Integration drill (NOT part of the zero-infra suite): run the encoder probe
# against the real transcode image to see what HandBrake actually supports.
# Requires the built image + a GPU/render node on this host.
set -euo pipefail
IMAGE="${1:-arm-transcode:latest}"
devflags=()
[[ -d /dev/dri ]] && devflags+=(--device /dev/dri)
command -v nvidia-smi >/dev/null 2>&1 && devflags+=(--gpus all)
echo "probing $IMAGE ..."
docker run --rm "${devflags[@]}" "$IMAGE" python -m arm_transcode.main --probe-encoders
