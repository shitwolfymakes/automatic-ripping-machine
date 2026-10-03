#!/usr/bin/env bash
# shellcheck disable=SC2317,SC2329,SC2034
# (Shadow functions below are invoked indirectly by sourced install.sh code —
# newer shellcheck flags them unreachable; this is the documented
# "ignore if invoked indirectly" case. SC2034: REMOTE_RUN is consumed by
# sourced install.sh functions via "${REMOTE_RUN[@]}", not in this file;
# LOCAL_FP is computed for parity with production but not asserted on here.)
# Plain-bash unit test for the remote-offload walkthrough in deploy/install/offload.sh:
# output helpers, input validators, paste-block generators, verify-step
# classification, and the completion table. Sources the deploy modules directly; no docker, no root, no network.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${HERE}/../deploy"

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

# Settings the modules read. Individual checks re-point them at fixtures.
ARM_DIR="${TMPROOT}/arm"; mkdir -p "${ARM_DIR}"
ENV_FILE="${ARM_DIR}/.env"
ARM_CERTS_DIR="${ARM_DIR}/certs"

for f in lib/common.sh lib/detect.sh lib/certs.sh install/ui.sh install/nvidia.sh install/offload.sh; do
    # shellcheck disable=SC1090
    source "${DEPLOY}/${f}"
done

fail=0
check() {  # check <label> <expected> <actual>
    local label="$1" want="$2" got="$3"
    if [[ "$want" == "$got" ]]; then
        echo "ok   - ${label}"
    else
        echo "FAIL - ${label}: expected '${want}', got '${got}'" >&2
        fail=1
    fi
}


# --- output helpers ----------------------------------------------------------

out="$(log "hello world")"
check "log: plain two-space indent, no marker" "  hello world" "$out"

out="$(section 2 6 "Remote transcode offload")"
check "section: ruled header" "yes" "$( [[ "$out" == *"── [2/6] Remote transcode offload ──"* ]] && echo yes || echo no )"

out="$(okline "docker reachable")"
check "okline: check mark" "  ✓ docker reachable" "$out"
out="$(failline "not authorized")"
check "failline: cross mark" "  ✗ not authorized" "$out"
out="$(warnline "udev skipped")"
check "warnline: bang" "  ! udev skipped" "$out"

out="$(fence_open "paste EVERYTHING between the lines, on 192.168.0.92 (as sam)")"
check "fence_open: labeled rule" "yes" "$( [[ "$out" == *"──── paste EVERYTHING between the lines, on 192.168.0.92 (as sam) ────"* ]] && echo yes || echo no )"
out="$(fence_close)"
check "fence_close: bare rule" "yes" "$( [[ "$out" == ──────* ]] && echo yes || echo no )"

# run_quiet: silent on success, replays captured output on failure
out="$(run_quiet true 2>&1)"
check "run_quiet: silent on success" "" "$out"
rc=0; out="$(run_quiet sh -c 'echo boom-detail >&2; exit 3' 2>&1)" || rc=$?
check "run_quiet: rc passthrough" "3" "$rc"
check "run_quiet: replays output on failure" "yes" "$( [[ "$out" == *boom-detail* ]] && echo yes || echo no )"

# --- input validators --------------------------------------------------------

for good in "ssh://sam@192.168.0.92" "ssh://sam@host.lan:2222" "ssh://10.0.0.5"; do
    rc=0; valid_ssh_endpoint "$good" || rc=$?
    check "endpoint accepts: $good" "0" "$rc"
done
for bad in "sam@192.168.0.92" "ssh://" "ssh://user@" "http://sam@h" "ssh://sam@h:port"; do
    rc=0; valid_ssh_endpoint "$bad" || rc=$?
    check "endpoint rejects: $bad" "1" "$rc"
done
check "endpoint_user" "sam" "$(endpoint_user "ssh://sam@h.lan:2222")"
check "endpoint_user empty" "" "$(endpoint_user "ssh://h.lan")"
check "endpoint_host" "h.lan" "$(endpoint_host "ssh://sam@h.lan:2222")"
check "endpoint_port" "2222" "$(endpoint_port "ssh://sam@h.lan:2222")"
check "endpoint_port empty" "" "$(endpoint_port "ssh://sam@h.lan")"

for good in "https://192.168.0.68:8080" "https://arm.example.com"; do
    rc=0; valid_https_url "$good" || rc=$?
    check "url accepts: $good" "0" "$rc"
done
for bad in "http://192.168.0.68:8080" "192.168.0.68:8080" "https://" "https://h:port" "https://h:8080/api"; do
    rc=0; valid_https_url "$bad" || rc=$?
    check "url rejects: $bad" "1" "$rc"
done
check "url_port" "8080" "$(url_port "https://192.168.0.68:8080")"
check "url_port empty (443 implied)" "" "$(url_port "https://arm.example.com")"

# prompt_valid: feeds one bad then one good line; must re-prompt then echo it
out="$(printf 'garbage\nssh://sam@h\n' | prompt_valid "  Remote docker endpoint" valid_ssh_endpoint "ssh://user@host[:port]" 2>&1)"
check "prompt_valid: re-prompts then accepts" "yes" "$( [[ "$out" == *"expected shape: ssh://user@host[:port]"* && "$out" == *"ssh://sam@h" ]] && echo yes || echo no )"

# --- structural: callback port + certs path ----------------------------------

# offload_backend_port: derives the publish port from the callback URL.
check "publish port from URL" "8080" "$(offload_backend_port "https://192.168.0.68:8080")"
check "publish port default 443" "443" "$(offload_backend_port "https://arm.example.com")"

# certs path: offload on -> remote-user-writable path
check "certs path (offload)" "/home/sam/.arm/certs" "$(offload_certs_path "ssh://sam@192.168.0.92")"


# --- walkthrough: paste generators + verify classification -------------------

PUBLINE='ssh-ed25519 AAAA...xyz armv3-backend@192.168.0.92'
out="$(paste_block_key "$PUBLINE" "192.168.0.92" "sam")"
check "key block: fenced + host/user named" "yes" "$( [[ "$out" == *"on 192.168.0.92 (as sam)"* ]] && echo yes || echo no )"
check "key block: append-if-absent" "yes" "$( [[ "$out" == *"grep -qxF"* && "$out" == *">> ~/.ssh/authorized_keys"* ]] && echo yes || echo no )"
check "key block: chmods" "yes" "$( [[ "$out" == *"chmod 700 ~/.ssh"* && "$out" == *"chmod 600 ~/.ssh/authorized_keys"* ]] && echo yes || echo no )"

CAFIX="$TMPROOT/ca.crt"; printf -- '-----BEGIN CERTIFICATE-----\nAAA\n-----END CERTIFICATE-----\n' > "$CAFIX"
out="$(paste_block_ca "$CAFIX" "/home/sam/.arm/certs" "192.168.0.92" "sam")"
check "ca block: mkdir + tee heredoc + PEM inlined" "yes" "$( [[ "$out" == *"mkdir -p /home/sam/.arm/certs"* && "$out" == *"BEGIN CERTIFICATE"* && "$out" == *"ARM_CA_EOF"* ]] && echo yes || echo no )"

out="$(paste_block_save_load "x/arm-transcode:t" "ssh://sam@192.168.0.92" "/p/ssh/id_ed25519")"
check "save/load: runs on THIS host" "yes" "$( [[ "$out" == *"THIS host"* && "$out" == *"docker save x/arm-transcode:t"* && "$out" == *"docker load"* ]] && echo yes || echo no )"

# verify classification via the REMOTE_RUN seam: shadow runner scripts outcomes.
remote_script() { REMOTE_RUN=(bash -c "$1" --); }
remote_script 'exit 255'
check "verify_docker: ssh failure" "FAIL_SSH" "$(verify_docker_access)"
remote_script 'echo "permission denied while trying to connect to the Docker daemon" >&2; exit 1'
check "verify_docker: docker group" "FAIL_DOCKER" "$(verify_docker_access)"
remote_script 'echo 27.4'
check "verify_docker: pass" "PASS 27.4" "$(verify_docker_access)"

LOCAL_FP="$(openssl x509 -noout -fingerprint -sha256 -in "$CAFIX" 2>/dev/null || sha256sum "$CAFIX")"
remote_script 'exit 1'
check "verify_ca: absent" "FAIL_ABSENT" "$(verify_ca "$CAFIX" /home/sam/.arm/certs)"
remote_script 'echo WRONG-FINGERPRINT'
check "verify_ca: mismatch" "FAIL_MISMATCH" "$(verify_ca "$CAFIX" /home/sam/.arm/certs)"

remote_script 'exit 1'
check "verify_image: fail" "FAIL" "$(verify_image x/arm-transcode:t)"
remote_script 'echo ok'
check "verify_image: pass" "PASS" "$(verify_image x/arm-transcode:t)"

remote_script 'exit 1'
check "verify_paths: all missing" "FAIL /a /b /c" "$(verify_paths /a /b /c)"
remote_script 'exit 0'
check "verify_paths: pass" "PASS" "$(verify_paths /a /b /c)"

# --- completion phase --------------------------------------------------------

remote_script 'echo 27.4'
BACKEND_RUNNING_TEST=(bash -c 'echo false' --)
check "verify_callback: pending when backend down" "PENDING" "$(verify_callback https://h:8080)"
BACKEND_RUNNING_TEST=(bash -c 'echo true' --)
remote_script 'exit 0'
check "verify_callback: pass" "PASS" "$(verify_callback https://h:8080)"
remote_script 'exit 7'
check "verify_callback: fail when up but unreachable" "FAIL" "$(verify_callback https://h:8080)"

# table rendering: drive every row through scripted outcomes.
ENVFIX="$TMPROOT/env"; cat > "$ENVFIX" <<'EOF'
ARM_TRANSCODE_DOCKER_HOST=ssh://sam@192.168.0.92
ARM_TRANSCODE_BACKEND_URL=https://192.168.0.68:8080
ARM_HOST_RAW_PATH=/a
ARM_HOST_MEDIA_PATH=/b
ARM_HOST_LOGS_PATH=/c
ARM_HOST_CERTS_PATH=/home/sam/.arm/certs
ARM_GPUS=[{"vendor":"nvenc","device_path":"nvidia://0"}]
EOF
CAFIX2="$TMPROOT/ca2.crt"; printf 'x\n' > "$CAFIX2"
remote_script 'exit 255'
BACKEND_RUNNING_TEST=(bash -c 'echo false' --)
out="$(OFFLOAD_ENV_FILE="$ENVFIX" OFFLOAD_CA_FILE="$CAFIX2" OFFLOAD_IMAGE_REF=x/t:1 offload_completion_report)"
check "table: header names endpoint" "yes" "$( [[ "$out" == *"Remote offload verification (ssh://sam@192.168.0.92)"* ]] && echo yes || echo no )"
check "table: ssh row FAIL" "yes" "$( [[ "$out" == *"ssh + docker access"*FAIL* ]] && echo yes || echo no )"
check "table: callback PENDING wording" "yes" "$( [[ "$out" == *"PENDING — stack not running"* && "$out" == *"re-run \`armctl install\`"* ]] && echo yes || echo no )"

# --- Critical regression: non-interactive persisted rerun must restore remote state
PERSISTDIR="$TMPROOT/persist"; mkdir -p "$PERSISTDIR/ssh"
cat > "$PERSISTDIR/.env" <<'EOF'
ARM_TRANSCODE_DOCKER_HOST=ssh://sam@192.168.0.92
ARM_TRANSCODE_BACKEND_URL=https://192.168.0.68:8080
ARM_TRANSCODE_PUID=1001
ARM_TRANSCODE_PGID=1000
ARM_GPUS=[{"vendor":"nvenc","device_path":"nvidia://0"}]
ARM_RENDER_GID=
EOF
ARM_DIR="$PERSISTDIR"; ENV_FILE="$PERSISTDIR/.env"; ARM_CERTS_DIR="$PERSISTDIR/certs"
REMOTE_OFFLOAD=0
declare -p REMOTE_RUN >/dev/null 2>&1 && unset REMOTE_RUN
remote_script 'exit 0'
offload_restore_persisted
check "restore: offload flag" "1" "$REMOTE_OFFLOAD"
check "restore: endpoint" "ssh://sam@192.168.0.92" "$REMOTE_DOCKER_HOST"
check "restore: remote gpus" "yes" "$( [[ "$REMOTE_GPUS" == *nvenc* ]] && echo yes || echo no )"
check "restore: backend san" "192.168.0.68" "$REMOTE_BACKEND_SAN"

# order: non-interactive call with persisted config must still restore (tty guard after skip)
REMOTE_OFFLOAD=0; REMOTE_GPUS=""
setup_remote_offload </dev/null >/dev/null 2>&1 || true
check "non-interactive persisted rerun: restored" "1" "$REMOTE_OFFLOAD"
check "non-interactive persisted rerun: gpus kept" "yes" "$( [[ "$REMOTE_GPUS" == *nvenc* ]] && echo yes || echo no )"

# --- final-review fixes ------------------------------------------------------

# F1: ensure_ca creates a CA when absent, reuses when present (real openssl).
CADIR="$TMPROOT/caprefix"; mkdir -p "$CADIR/certs"
ARM_CERTS_DIR="$CADIR/certs" ensure_ca >/dev/null 2>&1
check "ensure_ca: creates" "yes" "$( [[ -s "$CADIR/certs/arm-ca.crt" && -s "$CADIR/certs/arm-ca.key" ]] && echo yes || echo no )"
before="$(sha256sum "$CADIR/certs/arm-ca.crt")"
ARM_CERTS_DIR="$CADIR/certs" ensure_ca >/dev/null 2>&1
check "ensure_ca: idempotent" "$before" "$(sha256sum "$CADIR/certs/arm-ca.crt")"

# F2: unresolved-tag ref renders SKIPPED in the report, no verify call.
remote_script 'echo SHOULD-NOT-RUN; exit 9'
BACKEND_RUNNING_TEST=(bash -c 'echo false' --)
out="$(OFFLOAD_ENV_FILE="$ENVFIX" OFFLOAD_CA_FILE="$CAFIX2" OFFLOAD_IMAGE_REF="x/arm-transcode:" OFFLOAD_REOFFER=0 offload_completion_report)"
check "report: unresolved tag -> SKIPPED row" "yes" "$( [[ "$out" == *"SKIPPED — image tag unresolved"* ]] && echo yes || echo no )"

# F3: GPUs row rendered from env inventory.
check "report: GPUs row present" "yes" "$( [[ "$out" == *"GPUs"* && "$out" == *"nvenc x1"* ]] && echo yes || echo no )"

# F4: FAIL rows re-offer paste blocks when enabled.
KEYDIR="$TMPROOT/persist/ssh"; mkdir -p "$KEYDIR"
printf 'ssh-ed25519 AAAA test@x\n' > "$KEYDIR/id_ed25519.pub"
remote_script 'exit 255'
out="$(ARM_DIR="$TMPROOT/persist" OFFLOAD_ENV_FILE="$ENVFIX" OFFLOAD_CA_FILE="$CAFIX2" OFFLOAD_IMAGE_REF="x/arm-transcode:t" OFFLOAD_REOFFER=1 offload_completion_report)"
check "report: reoffer key block on ssh FAIL" "yes" "$( [[ "$out" == *"Fix-it blocks"* && "$out" == *"authorized_keys"* ]] && echo yes || echo no )"
out="$(ARM_DIR="$TMPROOT/persist" OFFLOAD_ENV_FILE="$ENVFIX" OFFLOAD_CA_FILE="$CAFIX2" OFFLOAD_IMAGE_REF="x/arm-transcode:t" OFFLOAD_REOFFER=0 offload_completion_report)"
check "report: no reoffer when disabled" "no" "$( [[ "$out" == *"Fix-it blocks"* ]] && echo yes || echo no )"


# --- offload_image_ref precedence (live-verification catch) ------------------

REFENV="$TMPROOT/refenv"
printf 'ARM_IMAGE_PREFIX=armv3-local\nARM_IMAGE_TAG=hifi\n' > "$REFENV"
check "image ref: .env prefix+tag pins win" "armv3-local/arm-transcode:hifi" "$(offload_image_ref "$REFENV")"
printf 'ARM_TRANSCODE_IMAGE=ghcr.io/x/custom:v9\nARM_IMAGE_PREFIX=armv3-local\nARM_IMAGE_TAG=hifi\n' > "$REFENV"
check "image ref: ARM_TRANSCODE_IMAGE override wins" "ghcr.io/x/custom:v9" "$(offload_image_ref "$REFENV")"
printf '\n' > "$REFENV"
check "image ref: defaults fallback" "${ARM_IMAGE_PREFIX_DEFAULT}/arm-transcode:${ARM_IMAGE_TAG_DEFAULT}" "$(offload_image_ref "$REFENV")"

# report uses the env-pinned ref (not the default prefix)
printf 'ARM_TRANSCODE_DOCKER_HOST=ssh://sam@h\nARM_TRANSCODE_BACKEND_URL=https://b:8080\nARM_HOST_RAW_PATH=/a\nARM_HOST_MEDIA_PATH=/b\nARM_HOST_LOGS_PATH=/c\nARM_HOST_CERTS_PATH=/x\nARM_GPUS=[{"vendor":"nvenc"}]\nARM_IMAGE_PREFIX=armv3-local\nARM_IMAGE_TAG=hifi\n' > "$REFENV"
remote_script 'exit 0'
BACKEND_RUNNING_TEST=(bash -c 'echo false' --)
out="$(OFFLOAD_ENV_FILE="$REFENV" OFFLOAD_CA_FILE="$CAFIX2" OFFLOAD_REOFFER=0 offload_completion_report)"
check "report: image row honors .env pin" "yes" "$( [[ "$out" == *"armv3-local/arm-transcode:hifi"* ]] && echo yes || echo no )"


# --- leaf key permissions (live-verification catch #2) -----------------------
# Reruns regenerate leaves; a 400 owner-only key crash-loops PUID!=runner
# stacks on their next restart. make_leaf must emit 440 group-readable.
LEAFDIR="$TMPROOT/leafprefix"; mkdir -p "$LEAFDIR/certs"
ARM_CERTS_DIR="$LEAFDIR/certs" ensure_ca >/dev/null 2>&1
ARM_CERTS_DIR="$LEAFDIR/certs" ARM_PGID="$(id -g)" make_leaf test-leaf >/dev/null 2>&1
check "leaf key exists" "yes" "$( [[ -s "$LEAFDIR/certs/test-leaf.key" ]] && echo yes || echo no )"
check "leaf key mode 440" "440" "$(stat -c '%a' "$LEAFDIR/certs/test-leaf.key")"

# --- remote GPU detection ships the shared detection code ---------------------
# ssh is replaced by `cat`, so the "remote output" is the script that would run.
ssh() { cat; }
shipped="$(remote_detect_gpus "ssh://sam@192.168.0.92" /dev/null)"
unset -f ssh
check "remote detect: ships the driver floor" "yes" "$( [[ "$shipped" == *"ARM_NVENC_MIN_DRIVER=530"* ]] && echo yes || echo no )"
check "remote detect: ships detect_gpus and its helpers" "yes" \
    "$( [[ "$shipped" == *"detect_gpus ()"* && "$shipped" == *"nvenc_driver_ok ()"* && "$shipped" == *"arm_warn ()"* ]] && echo yes || echo no )"
check "remote detect: no encoder probe" "no" "$( [[ "$shipped" == *probe_encoder_caps* ]] && echo yes || echo no )"

# --- consent ------------------------------------------------------------------
SKIPPED=(); ARMCTL_ASSUME=yes
rc=0; consent "thing" "Do the thing?" </dev/null || rc=$?
check "consent: --yes accepts without asking" "0" "$rc"
SKIPPED=(); ARMCTL_ASSUME=no
rc=0; consent "thing" "Do the thing?" </dev/null || rc=$?
check "consent: --no-host-changes declines" "1" "$rc"
check "consent: declined step is recorded" "thing (declined by --no-host-changes)" "${SKIPPED[0]}"
SKIPPED=(); ARMCTL_ASSUME=ask
rc=0; consent "thing" "Do the thing?" </dev/null || rc=$?
check "consent: no terminal declines instead of hanging" "1" "$rc"
check "consent: no-terminal skip is recorded" "thing (no terminal to ask on)" "${SKIPPED[0]}"

# --- offload inputs without a terminal -----------------------------------------
NOENV="$TMPROOT/noenv"; mkdir -p "$NOENV"
out="$( (ARM_DIR="$NOENV"; ENV_FILE="$NOENV/.env"; OFFLOAD_HOST_ARG=""; OFFLOAD_URL_ARG=""; setup_remote_offload) </dev/null 2>&1 || true)"
check "offload: no terminal and no flags is an error" "yes" "$( [[ "$out" == *"--offload-host and --offload-backend-url"* ]] && echo yes || echo no )"
out="$( (ARM_DIR="$NOENV"; ENV_FILE="$NOENV/.env"; OFFLOAD_HOST_ARG="not-an-endpoint"; OFFLOAD_URL_ARG="https://h:8443"; setup_remote_offload) </dev/null 2>&1 || true)"
check "offload: a malformed --offload-host is rejected" "yes" "$( [[ "$out" == *"--offload-host must look like"* ]] && echo yes || echo no )"

exit "$fail"
