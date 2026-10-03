#!/usr/bin/env bash
# deploy/install/offload.sh: the remote transcode offload walkthrough.
# Sourced by deploy/armctl.sh. Needs deploy/lib/{common,detect,certs}.sh and
# deploy/install/ui.sh loaded first. Reads ARM_DIR, ENV_FILE, ARM_CERTS_DIR.

# Defaults for the image reference; deploy/install/config.sh sets the real ones.
: "${ARM_IMAGE_PREFIX_DEFAULT:=docker.io/automaticrippingmachine}"
: "${ARM_IMAGE_TAG_DEFAULT:=}"

# Extract the bare host from a URL: strip scheme://, any user@, :port, and /path.
# https://192.168.0.68:8080/api -> 192.168.0.68 ; https://h.example -> h.example
url_host() {
    local url="$1" hostport
    url="${url#*://}"      # drop scheme://
    url="${url%%/*}"       # drop /path
    url="${url##*@}"       # drop user@ (if present)
    hostport="$url"
    url="${hostport%%:*}"  # drop :port
    printf '%s' "$url"
}

# offload_image_ref <envfile> — the transcode image ref the REMOTE daemon
# must hold, honoring the same precedence compose uses: ARM_TRANSCODE_IMAGE
# override > .env ARM_IMAGE_PREFIX/ARM_IMAGE_TAG pins > script defaults.
# (Live-verification catch: the report checked the DEFAULT prefix and
# spuriously FAILed on deployments pinning a local prefix in .env.)
offload_image_ref() {
    local envf="$1" override prefix tag
    override="$(sed -nE 's/^ARM_TRANSCODE_IMAGE=(.+)$/\1/p' "$envf" 2>/dev/null | head -n1)"
    if [[ -n "$override" ]]; then printf '%s' "$override"; return 0; fi
    prefix="$(sed -nE 's/^ARM_IMAGE_PREFIX=(.+)$/\1/p' "$envf" 2>/dev/null | head -n1)"
    tag="$(sed -nE 's/^ARM_IMAGE_TAG=(.+)$/\1/p' "$envf" 2>/dev/null | head -n1)"
    printf '%s/arm-transcode:%s' "${prefix:-$ARM_IMAGE_PREFIX_DEFAULT}" "${tag:-$ARM_IMAGE_TAG_DEFAULT}"
}

# ------------------------------------------------ offload input validation

# Validate numeric UID/GID (non-zero).
is_ugid() {
    [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

# ssh://[user@]host[:port] — host is a DNS name or IPv4; port numeric.
valid_ssh_endpoint() {
    [[ "$1" =~ ^ssh://([A-Za-z0-9._-]+@)?[A-Za-z0-9.-]+(:[0-9]+)?$ ]]
}
endpoint_user() { local s="${1#ssh://}"; [[ "$s" == *@* ]] && printf '%s' "${s%%@*}"; true; }
endpoint_host() { local s="${1#ssh://}"; s="${s##*@}"; printf '%s' "${s%%:*}"; }
endpoint_port() { local s="${1#ssh://}"; s="${s##*@}"; [[ "$s" == *:* ]] && printf '%s' "${s##*:}"; true; }

# https://host[:port] — no path/query (the installer appends /api/... itself).
valid_https_url() {
    [[ "$1" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?$ ]]
}
url_port() { local s="${1#https://}"; [[ "$s" == *:* ]] && printf '%s' "${s##*:}"; true; }

# offload helpers
offload_backend_port() { local p; p="$(url_port "$1")"; printf '%s' "${p:-443}"; }
offload_certs_path()   { printf '/home/%s/.arm/certs' "$(endpoint_user "$1")"; }

# Run GPU detection ON the remote host over ssh, using the dedicated key.
# Prints two lines: <ARM_GPUS json> then <render_gid>. Non-zero on ssh failure.
# The remote does not have the installer, so the shared detection functions
# from deploy/lib/detect.sh are shipped inline, with the output helpers they
# call. Like the local path, this only reports which devices exist; the backend
# probes what each can encode.
remote_detect_gpus() {
    local target="$1" key="$2" out
    # target is ssh://user@host: strip the scheme for the ssh CLI.
    local sshdest="${target#ssh://}"
    # shellcheck disable=SC2029 # intentional: function bodies are expanded client-side and shipped as source to the remote bash -s
    out="$(
        {
            printf 'ARM_NVENC_MIN_DRIVER=%q\n' "${ARM_NVENC_MIN_DRIVER}"
            declare -f arm_say arm_warn nvenc_driver_ok detect_gpus detect_render_gid
            # shellcheck disable=SC2016 # single quotes are intentional: $(...) must expand on the remote, not here
            printf 'printf "%%s\\n" "$(detect_gpus)"\n'
            # shellcheck disable=SC2016 # single quotes are intentional: $(...) must expand on the remote, not here
            printf 'printf "%%s\\n" "$(detect_render_gid || true)"\n'
        } | ssh -i "$key" -o BatchMode=yes -o ConnectTimeout=10 \
                -o StrictHostKeyChecking=accept-new "$sshdest" bash -s 2>/dev/null
    )" || return 1
    printf '%s\n' "$out"
}

# REMOTE_RUN seam: how verification reaches the remote. Tests pre-set the
# array; production initializes it from the endpoint + the dedicated key.
offload_remote_run_init() {  # <endpoint> <keyfile> <known_hosts>
    if ! declare -p REMOTE_RUN >/dev/null 2>&1; then
        local host port user dest
        user="$(endpoint_user "$1")"; host="$(endpoint_host "$1")"; port="$(endpoint_port "$1")"
        dest="${user:+${user}@}${host}"
        REMOTE_RUN=(ssh -i "$2" -o BatchMode=yes -o ConnectTimeout=10
                    -o UserKnownHostsFile="$3" -o StrictHostKeyChecking=accept-new
                    ${port:+-p "$port"} "$dest")
    fi
}

paste_block_key() {  # <pubkey-line> <host> <user>
    fence_open "paste EVERYTHING between the lines, on $2 (as $3)"
    printf 'mkdir -p ~/.ssh && chmod 700 ~/.ssh\n'
    printf "grep -qxF '%s' ~/.ssh/authorized_keys 2>/dev/null || \\\\\n" "$1"
    printf "  echo '%s' >> ~/.ssh/authorized_keys\n" "$1"
    printf 'chmod 600 ~/.ssh/authorized_keys\n'
    fence_close
}

paste_block_ca() {  # <ca-file> <certs-path> <host> <user>
    fence_open "paste EVERYTHING between the lines, on $3 (as $4)"
    printf 'mkdir -p %s\n' "$2"
    printf "tee %s/arm-ca.crt >/dev/null <<'ARM_CA_EOF'\n" "$2"
    cat "$1"
    printf 'ARM_CA_EOF\n'
    fence_close
}

paste_block_pull() {  # <ref>
    fence_open "run on the REMOTE host"
    printf 'docker pull %s\n' "$1"
    fence_close
}

paste_block_save_load() {  # <ref> <endpoint> <keyfile>
    local user host; user="$(endpoint_user "$2")"; host="$(endpoint_host "$2")"
    fence_open "run on THIS host (not the remote)"
    printf 'docker save %s | \\\n  ssh -i %s %s docker load\n' "$1" "$3" "${user:+${user}@}${host}"
    fence_close
}

verify_docker_access() {
    local out rc=0
    out="$("${REMOTE_RUN[@]}" docker info --format '{{.ServerVersion}}' 2>&1)" || rc=$?
    if (( rc == 255 )); then printf 'FAIL_SSH'; return 0; fi
    if (( rc != 0 )); then
        [[ "$out" == *"permission denied"* ]] && { printf 'FAIL_DOCKER'; return 0; }
        printf 'FAIL_SSH'; return 0
    fi
    printf 'PASS %s' "$(printf '%s' "$out" | tail -n1)"
}

verify_ca() {  # <local-ca-file> <remote-certs-path>
    local want got rc=0
    want="$(sha256sum "$1" | cut -d" " -f1)"
    got="$("${REMOTE_RUN[@]}" sha256sum "$2/arm-ca.crt" 2>/dev/null)" || rc=$?
    got="${got%% *}"
    if (( rc != 0 )) || [[ -z "$got" ]]; then printf 'FAIL_ABSENT'; return 0; fi
    if [[ "$got" == "$want" ]]; then printf 'PASS'; else printf 'FAIL_MISMATCH'; fi
}

verify_image() {  # <ref>
    "${REMOTE_RUN[@]}" docker image inspect --format ok "$1" >/dev/null 2>&1 \
        && printf 'PASS' || printf 'FAIL'
}

verify_paths() {  # <p...> — report every missing path
    local missing=() p
    for p in "$@"; do
        "${REMOTE_RUN[@]}" test -d "$p" >/dev/null 2>&1 || missing+=("$p")
    done
    (( ${#missing[@]} == 0 )) && printf 'PASS' || printf 'FAIL %s' "${missing[*]}"
}

# offload_persisted: rc 0 iff a prior run already seeded a remote offload host
# into .env — used both to skip the questionnaire on rerun and to gate the
# completion report.
offload_persisted() {
    [[ -f "${ENV_FILE}" ]] && grep -q '^ARM_TRANSCODE_DOCKER_HOST=.\+' "${ENV_FILE}"
}

# Seam-able "is the local backend container running?" probe (mirrors REMOTE_RUN).
if ! declare -p BACKEND_RUNNING_TEST >/dev/null 2>&1; then
    BACKEND_RUNNING_TEST=(docker inspect -f '{{.State.Running}}' armv3-backend)
fi

verify_callback() {  # <url> — PASS / FAIL / PENDING
    local running
    running="$("${BACKEND_RUNNING_TEST[@]}" 2>/dev/null || true)"
    [[ "$running" != "true" ]] && { printf 'PENDING'; return 0; }
    "${REMOTE_RUN[@]}" curl -ksf -o /dev/null --max-time 10 "$1/api/health" >/dev/null 2>&1 \
        && printf 'PASS' || printf 'FAIL'
}

# _report_row <label> <status> — pad label with dots to column 28, print status.
_report_row() {
    local label="$1" status="$2" dots=""
    local n=$(( 28 - ${#label} ))
    (( n < 1 )) && n=1
    dots="$(printf '.%.0s' $(seq 1 "$n"))"
    printf '    %s %s %s\n' "$label" "$dots" "$status"
}

# offload_completion_report — read config (env-file/CA/image overridable for
# tests via OFFLOAD_ENV_FILE/OFFLOAD_CA_FILE/OFFLOAD_IMAGE_REF), run the
# read-only battery, print the table. Informational: never exits non-zero.
#
# OFFLOAD_REOFFER seam: gates whether FAILed rows re-print their paste block
# after the table. Defaults to the tty state (interactive runs get the
# fix-it blocks re-offered; non-interactive/piped runs don't spam a block
# nobody can paste anywhere) — tests pre-set it to force either branch.
offload_completion_report() {
    if ! declare -p OFFLOAD_REOFFER >/dev/null 2>&1; then
        if [[ -t 0 ]]; then OFFLOAD_REOFFER=1; else OFFLOAD_REOFFER=0; fi
    fi

    local envf="${OFFLOAD_ENV_FILE:-${ENV_FILE}}"
    local caf="${OFFLOAD_CA_FILE:-${ARM_CERTS_DIR}/arm-ca.crt}"
    eget() { sed -nE "s/^$1=(.+)\$/\\1/p" "$envf" | head -n1; }
    local endpoint url raw_p media_p logs_p certs_p image_ref gpus_raw
    endpoint="$(eget ARM_TRANSCODE_DOCKER_HOST)"; url="$(eget ARM_TRANSCODE_BACKEND_URL)"
    raw_p="$(eget ARM_HOST_RAW_PATH)"; media_p="$(eget ARM_HOST_MEDIA_PATH)"; logs_p="$(eget ARM_HOST_LOGS_PATH)"
    certs_p="$(eget ARM_HOST_CERTS_PATH)"
    gpus_raw="$(eget ARM_GPUS)"
    image_ref="${OFFLOAD_IMAGE_REF:-$(offload_image_ref "$envf")}"
    [[ -n "$endpoint" ]] || return 0

    local failed_steps=()

    printf '\n  Remote offload verification (%s):\n' "$endpoint"
    local v
    v="$(verify_docker_access)"
    case "$v" in PASS*) _report_row "ssh + docker access" "PASS" ;;
                 FAIL_DOCKER) _report_row "ssh + docker access" "FAIL — remote user not in docker group"; failed_steps+=(key) ;;
                 *) _report_row "ssh + docker access" "FAIL — ssh/key"; failed_steps+=(key) ;; esac
    case "$(verify_ca "$caf" "$certs_p")" in
        PASS) _report_row "CA fingerprint" "PASS" ;;
        FAIL_MISMATCH) _report_row "CA fingerprint" "FAIL — stale CA at ${certs_p}"; failed_steps+=(ca) ;;
        *) _report_row "CA fingerprint" "FAIL — absent at ${certs_p}"; failed_steps+=(ca) ;; esac
    # F2: the ref ends in ":" when ARM_IMAGE_TAG_DEFAULT (and no persisted
    # ARM_IMAGE_TAG) resolved to empty — running verify_image against that
    # always FAILs and is not actionable; report it as unresolved instead.
    if [[ "$image_ref" == *: ]]; then
        _report_row "transcode image" "SKIPPED — image tag unresolved this run"
    else
        case "$(verify_image "$image_ref")" in
            PASS) _report_row "transcode image" "PASS  (${image_ref})" ;;
            *) _report_row "transcode image" "FAIL — not on remote daemon"; failed_steps+=(image) ;; esac
    fi
    v="$(verify_paths "$raw_p" "$media_p" "$logs_p")"
    case "$v" in PASS) _report_row "data paths" "PASS  (raw, media, logs)" ;;
                 *) _report_row "data paths" "FAIL — missing: ${v#FAIL }" ;; esac
    # F3: inventory-from-.env row (informational — not a live re-probe of the
    # remote; the walkthrough's remote_detect_gpus already did the live probe).
    if [[ -n "$gpus_raw" && "$gpus_raw" == *'"vendor"'* ]]; then
        local gpu_count vendor_list
        gpu_count="$(grep -o '"vendor"' <<<"$gpus_raw" | wc -l)"
        vendor_list="$(grep -o '"vendor":"[a-z]*"' <<<"$gpus_raw" | head -n1 | sed -E 's/.*:"([a-z]*)"/\1/')"
        _report_row "GPUs" "PASS  (${vendor_list} x${gpu_count})"
    else
        _report_row "GPUs" "FAIL — no GPU inventory (CPU-only transcodes)"
    fi
    case "$(verify_callback "$url")" in
        PASS) _report_row "backend callback URL" "PASS  (reachable from the remote)" ;;
        FAIL) _report_row "backend callback URL" "FAIL — backend is up but ${url} is unreachable from the remote (published port? firewall?)" ;;
        *)    _report_row "backend callback URL" "PENDING — stack not running; after"
              # shellcheck disable=SC2016 # backticks are literal text here, not command substitution
              printf '    %-27s %s\n' "" '`armctl up`, then re-run `armctl install`' ;; esac

    # F4: re-offer the paste block for any FAILed step that has one (paths /
    # callback / GPUs have no one-liner fix — mounting shares and opening
    # firewall ports aren't paste-able — so only key/ca/image re-offer).
    if (( ${#failed_steps[@]} > 0 )) && [[ "${OFFLOAD_REOFFER}" == "1" ]]; then
        echo; log "Fix-it blocks for the FAILed rows:"
        local step remote_user_disp
        remote_user_disp="$(endpoint_user "$endpoint")"
        for step in "${failed_steps[@]}"; do
            case "$step" in
                key)
                    if [[ -f "${ARM_DIR}/ssh/id_ed25519.pub" ]]; then
                        paste_block_key "$(cat "${ARM_DIR}/ssh/id_ed25519.pub")" \
                            "$(endpoint_host "$endpoint")" "${remote_user_disp:-<user>}"
                    fi
                    ;;
                ca)
                    paste_block_ca "$caf" "$certs_p" "$(endpoint_host "$endpoint")" "${remote_user_disp:-<user>}"
                    ;;
                image)
                    if [[ "$image_ref" == *.*/* || "$image_ref" == docker.io/* || "$image_ref" == ghcr.io/* ]]; then
                        log "  Pull it there:"
                        paste_block_pull "$image_ref"
                    else
                        log "  This is a locally-built image pin — transfer it from this host:"
                        paste_block_save_load "$image_ref" "$endpoint" "${ARM_DIR}/ssh/id_ed25519"
                    fi
                    ;;
            esac
        done
    fi
}

# offload_restore_persisted — re-derive the REMOTE_* globals from a prior
# run's .env (ARM_TRANSCODE_DOCKER_HOST etc.) without prompting. Used both by
# setup_remote_offload's persisted-skip path (interactive rerun) and by the
# non-interactive path — it must be tty-independent, since a headless rerun
# of an already-offloaded deployment still needs its remote GPU inventory
# restored, or seed_env's local GPU detection silently overwrites it.
offload_restore_persisted() {
    REMOTE_DOCKER_HOST="$(sed -nE 's/^ARM_TRANSCODE_DOCKER_HOST=(.+)$/\1/p' "${ENV_FILE}" | head -n1)"
    REMOTE_BACKEND_URL="$(sed -nE 's/^ARM_TRANSCODE_BACKEND_URL=(.+)$/\1/p' "${ENV_FILE}" | head -n1)"
    REMOTE_TRANSCODE_PUID="$(sed -nE 's/^ARM_TRANSCODE_PUID=(.+)$/\1/p' "${ENV_FILE}" | head -n1)"
    REMOTE_TRANSCODE_PGID="$(sed -nE 's/^ARM_TRANSCODE_PGID=(.+)$/\1/p' "${ENV_FILE}" | head -n1)"
    REMOTE_BACKEND_SAN="$(url_host "$REMOTE_BACKEND_URL")"
    REMOTE_OFFLOAD=1
    offload_remote_run_init "$REMOTE_DOCKER_HOST" "${ARM_DIR}/ssh/id_ed25519" "${ARM_DIR}/ssh/known_hosts"
    REMOTE_GPUS="$(sed -nE 's/^ARM_GPUS=(.+)$/\1/p' "${ENV_FILE}" | head -n1)"
    REMOTE_RENDER_GID="$(sed -nE 's/^ARM_RENDER_GID=(.*)$/\1/p' "${ENV_FILE}" | head -n1)"
}

# The walkthrough's pauses. With a terminal the user pastes a block, then
# presses Enter to have it verified. Without one (flags on an unattended run)
# there is nobody to wait for: each step is verified once, nothing is read
# from stdin, and a failed step is reported in the completion table.
pause_to_verify() {
    if [[ -t 0 ]]; then
        read -rp "  Press Enter to verify... " _ || true
    fi
}
skip_note() {
    if [[ -t 0 ]]; then
        warnline "step skipped"
    else
        warnline "no terminal to wait on; not retried. The completion table reports this step."
    fi
}

# Interactive: offer remote transcode offload. On yes, provision a dedicated
# ssh key, print the authorize line, detect the REMOTE GPU inventory, and set
# the REMOTE_* globals the rest of install.sh consumes. On no/non-interactive,
# leaves REMOTE_OFFLOAD empty => byte-for-byte local behavior downstream.
setup_remote_offload() {
    REMOTE_OFFLOAD=0

    # Already configured and nothing new was passed in: restore, don't re-ask.
    if offload_persisted && [[ -z "${OFFLOAD_HOST_ARG:-}" && -z "${OFFLOAD_URL_ARG:-}" ]]; then
        offload_restore_persisted
        log "offload already configured (${REMOTE_DOCKER_HOST}); skipping questionnaire; verification runs at completion"
        return 0
    fi

    if [[ ! -t 0 && ( -z "${OFFLOAD_HOST_ARG:-}" || -z "${OFFLOAD_URL_ARG:-}" ) ]]; then
        err "the offload profile needs --offload-host and --offload-backend-url when there is no terminal to ask on"
    fi
    # shellcheck disable=SC2034 # read by the install flow modules that source this file
    REMOTE_OFFLOAD=1

    if [[ -n "${OFFLOAD_HOST_ARG:-}" ]]; then
        valid_ssh_endpoint "${OFFLOAD_HOST_ARG}" \
            || err "--offload-host must look like ssh://user@host[:port] (got '${OFFLOAD_HOST_ARG}')"
        REMOTE_DOCKER_HOST="${OFFLOAD_HOST_ARG}"
    else
        REMOTE_DOCKER_HOST="$(prompt_valid "  Remote docker endpoint" valid_ssh_endpoint "ssh://user@host[:port]")"
    fi
    if [[ -z "$(endpoint_user "$REMOTE_DOCKER_HOST")" ]]; then
        warnline "no user in endpoint; docker's ssh:// URL usually needs one (user@host)"
    fi

    if [[ -n "${OFFLOAD_URL_ARG:-}" ]]; then
        valid_https_url "${OFFLOAD_URL_ARG}" \
            || err "--offload-backend-url must look like https://host:port (got '${OFFLOAD_URL_ARG}')"
        REMOTE_BACKEND_URL="${OFFLOAD_URL_ARG}"
    else
        REMOTE_BACKEND_URL="$(prompt_valid "  Routable backend URL the transcoder calls back" valid_https_url "https://host:port")"
    fi
    if [[ -z "$(url_port "$REMOTE_BACKEND_URL")" ]]; then
        warnline "no port in URL; the stack serves 8443 internally, so a portless URL is almost certainly wrong"
    fi

    local def_puid="${ARM_PUID:-$(id -u)}" def_pgid="${ARM_PGID:-$(id -g)}" uidgid
    if [[ -n "${OFFLOAD_UIDGID_ARG:-}" ]]; then
        uidgid="${OFFLOAD_UIDGID_ARG}"
        if ! { is_ugid "${uidgid%%:*}" && is_ugid "${uidgid##*:}"; }; then
            err "--offload-uidgid must be uid:gid, numeric and non-zero (got '${uidgid}')"
        fi
    elif [[ ! -t 0 ]]; then
        uidgid="${def_puid}:${def_pgid}"
    else
        while true; do
            read -rp "  Transcoder write UID:GID for shared media [${def_puid}:${def_pgid}]: " uidgid
            uidgid="${uidgid:-${def_puid}:${def_pgid}}"
            if is_ugid "${uidgid%%:*}" && is_ugid "${uidgid##*:}"; then break; fi
            printf '    ! expected shape: uid:gid (numeric, non-zero)   (you entered: %s)\n' "$uidgid" >&2
        done
    fi
    # shellcheck disable=SC2034 # read by the install flow modules that source this file
    REMOTE_TRANSCODE_PUID="${uidgid%%:*}"
    # shellcheck disable=SC2034 # read by the install flow modules that source this file
    REMOTE_TRANSCODE_PGID="${uidgid##*:}"
    # shellcheck disable=SC2034 # read by the install flow modules that source this file
    REMOTE_BACKEND_SAN="$(url_host "$REMOTE_BACKEND_URL")"

    # Dedicated ed25519 key for backend -> remote docker daemon.
    local sshdir="${ARM_DIR}/ssh" key="${ARM_DIR}/ssh/id_ed25519"
    # Use the new endpoint helper functions to split the ssh endpoint.
    local remote_user remote_host remote_port
    remote_user="$(endpoint_user "$REMOTE_DOCKER_HOST")"
    remote_host="$(endpoint_host "$REMOTE_DOCKER_HOST")"
    remote_port="$(endpoint_port "$REMOTE_DOCKER_HOST")"
    mkdir -p "$sshdir"
    if [[ ! -f "$key" ]]; then
        ssh-keygen -t ed25519 -N "" -C "armv3-backend@${remote_host}" -f "$key" >/dev/null \
            || err "could not generate the ssh key ${key} for the offload host"
        log "generated dedicated ssh key: $key"
    fi
    # Pre-populate known_hosts (best-effort). StrictHostKeyChecking below is
    # accept-new (NOT yes) — matching remote_detect_gpus's detection path — so a
    # keyscan miss self-heals on the first real connection instead of permanently
    # disabling offload with an unusable strict-yes + empty known_hosts.
    ssh-keyscan -t ed25519 ${remote_port:+-p "$remote_port"} "$remote_host" \
        > "$sshdir/known_hosts" 2>/dev/null || \
        warn "ssh-keyscan of ${remote_host}${remote_port:+:$remote_port} failed; known_hosts seeded empty (first connect will accept-new)"
    {
        printf 'Host %s\n' "$remote_host"
        [[ -n "$remote_user" ]] && printf '  User %s\n' "$remote_user"
        [[ -n "$remote_port" ]] && printf '  Port %s\n' "$remote_port"
        printf '  IdentityFile /home/arm/.ssh/id_ed25519\n'
        printf '  UserKnownHostsFile /home/arm/.ssh/known_hosts\n'
        printf '  StrictHostKeyChecking accept-new\n'
    } > "$sshdir/config"
    chmod 700 "$sshdir"; chmod 600 "$key" "$sshdir/known_hosts" "$sshdir/config"
    # Own the ssh bundle as the BACKEND's runtime uid (this installer's own
    # id -u:id -g, i.e. top-level PUID/PGID — the entrypoint's gosu target),
    # NOT REMOTE_TRANSCODE_PUID/PGID: that's a different uid by design — the
    # one the *transcoder* drops to for writing the shared media export. The
    # backend is what mounts this dir :ro and reads the 600 key/config, so it
    # must be the owner or ssh transport fails silently.
    chown -R "${def_puid}:${def_pgid}" "$sshdir" 2>/dev/null || true

    offload_remote_run_init "$REMOTE_DOCKER_HOST" "$key" "$sshdir/known_hosts"
    local remote_user_disp; remote_user_disp="$(endpoint_user "$REMOTE_DOCKER_HOST")"

    # Step 1 — authorize the ARM key
    echo; log "Step 1 of 5 — authorize the ARM key on the remote"
    paste_block_key "$(cat "$key.pub")" "$remote_host" "${remote_user_disp:-<user>}"
    while true; do
        pause_to_verify
        case "$(verify_docker_access)" in
            PASS*) okline "docker reachable over the ARM key"; break ;;
            FAIL_DOCKER)
                failline "ssh reached ${remote_host} but docker was denied."
                log "  Likely cause: user '${remote_user_disp}' is not in the remote docker group."
                log "  Fix on the remote:  sudo usermod -aG docker ${remote_user_disp}   (then log out/in there)" ;;
            *)  failline "ssh to ${remote_host} failed — key not authorized yet, or host unreachable." ;;
        esac
        confirm "  Re-check now? (No = skip; offload will FAIL in the completion table)" || { skip_note; break; }
    done

    # Step 2 — CA for transcoder callbacks
    # ensure_ca: the CA is normally created in section 3 (make_ca), which runs
    # AFTER this walkthrough (section 2) — on a fresh interactive install
    # there's no CA on disk yet, and paste_block_ca's `cat` of a missing file
    # would crash under `set -e`. Make it idempotently here; section 3's
    # make_ca call below is a no-op reuse in that case.
    ensure_ca
    local certs_path; certs_path="$(offload_certs_path "$REMOTE_DOCKER_HOST")"
    echo; log "Step 2 of 5 — place the CA for transcoder callbacks"
    paste_block_ca "${ARM_CERTS_DIR}/arm-ca.crt" "$certs_path" "$remote_host" "${remote_user_disp:-<user>}"
    while true; do
        pause_to_verify
        case "$(verify_ca "${ARM_CERTS_DIR}/arm-ca.crt" "$certs_path")" in
            PASS) okline "CA present, fingerprint matches"; break ;;
            FAIL_MISMATCH) failline "a DIFFERENT CA is at ${certs_path}/arm-ca.crt — stale from a previous install? Re-paste the block." ;;
            *) failline "CA not found at ${certs_path}/arm-ca.crt" ;;
        esac
        confirm "  Re-check now? (No = skip)" || { skip_note; break; }
    done

    # Step 3 — transcode image. ARM_IMAGE_TAG_DEFAULT is empty until
    # resolve_image_tag runs in main() (after this walkthrough), so on a fresh
    # install there's no tag yet — check .env too (same precedence
    # resolve_image_tag itself uses on a rerun) before deciding it's unresolved.
    local persisted_tag=""
    [[ -f "${ENV_FILE}" ]] && \
        persisted_tag="$(sed -nE 's/^ARM_IMAGE_TAG=(.+)$/\1/p' "${ENV_FILE}" | head -n1)"
    echo; log "Step 3 of 5 — transcode image on the remote"
    if [[ -z "${ARM_IMAGE_TAG_DEFAULT:-}" && -z "$persisted_tag" ]]; then
        log "  (image tag not resolved yet — checked in the completion table)"
    else
        local image_ref; image_ref="$(offload_image_ref "${ENV_FILE}")"
        if [[ "$(verify_image "$image_ref")" == PASS ]]; then
            okline "image present on remote (${image_ref})"
        else
            failline "${image_ref} not present on the remote daemon."
            if [[ "$image_ref" == *.*/* || "$image_ref" == docker.io/* || "$image_ref" == ghcr.io/* ]]; then
                log "  Pull it there:"
                paste_block_pull "$image_ref"
            else
                log "  This is a locally-built image pin — transfer it from this host:"
                paste_block_save_load "$image_ref" "$REMOTE_DOCKER_HOST" "$key"
            fi
            while true; do
                confirm "  Re-check now? (No = skip)" || { skip_note; break; }
                [[ "$(verify_image "$image_ref")" == PASS ]] && { okline "image present on remote"; break; }
                failline "still not present"
            done
        fi
    fi

    # Step 4 — shared data paths (best effort: env may not be seeded yet on a
    # first run; read the .env when present, else skip with a note — the
    # completion battery re-checks with final values).
    echo; log "Step 4 of 5 — shared data paths on the remote"
    local raw_p media_p logs_p
    raw_p="${RAW_PATH:-$(env_file_value ARM_HOST_RAW_PATH)}"
    media_p="${MEDIA_PATH:-$(env_file_value ARM_HOST_MEDIA_PATH)}"
    logs_p="${ARM_DIR}/logs"
    if [[ -n "$raw_p" && -n "$media_p" && -n "$logs_p" ]]; then
        local v; v="$(verify_paths "$raw_p" "$media_p" "$logs_p")"
        case "$v" in
            PASS) okline "data paths exist on the remote" ;;
            *) warnline "missing on the remote: ${v#FAIL } — mount the shared export there" ;;
        esac
    else
        log "  (paths not seeded yet — checked in the completion table)"
    fi

    # Step 5 — remote GPU detection doubles as the connectivity test (uses the dedicated key).
    echo; log "Step 5 of 5 — remote GPU detection"
    REMOTE_GPUS=""; REMOTE_RENDER_GID=""
    while true; do
        local detect
        if detect="$(remote_detect_gpus "$REMOTE_DOCKER_HOST" "$key")"; then
            REMOTE_GPUS="$(printf '%s' "$detect" | sed -n '1p')"
            REMOTE_RENDER_GID="$(printf '%s' "$detect" | sed -n '2p')"
            log "remote GPUs: ${REMOTE_GPUS:-[]}  render_gid=${REMOTE_RENDER_GID:-(none)}"
            break
        fi
        warn "remote GPU detection failed (ssh to ${remote_host} — key authorized? host reachable?)"
        if ! confirm "  Re-check now? (No = skip; transcodes run CPU-only until fixed)"; then
            warn "skipping remote GPU detection; seeding ARM_GPUS=[] (CPU-only on the box)"
            REMOTE_GPUS="[]"; REMOTE_RENDER_GID=""
            break
        fi
    done
}
