#!/usr/bin/env bash
# devtools/test-setup-dev.sh — zero-infra assertions that the dev installer
# and the compose template no longer enumerate drives (drive lifecycle §5).
# Uses `docker compose config` when docker is present, grep otherwise.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
SETUP="${ROOT}/devtools/setup-dev.sh"
TEMPLATE="${ROOT}/docker-compose.yml.example"
LIB="${ROOT}/deploy/lib"

fail=0
check() {  # check <label> <expected-rc> <actual-rc>
    local label="$1" want="$2" got="$3"
    if [[ "${want}" == "${got}" ]]; then echo "ok   - ${label}"; else echo "FAIL - ${label} (want rc=${want}, got rc=${got})"; fail=1; fi
}
absent() {  # absent <label> <pattern> <file>
    local rc=0; grep -qE -- "$2" "$3" || rc=$?
    check "$1" 1 "${rc}"
}
present() {  # present <label> <pattern> <file>
    local rc=0; grep -qE -- "$2" "$3" || rc=$?
    check "$1" 0 "${rc}"
}

# --- setup-dev.sh: no drive enumeration -------------------------------------
absent "setup-dev has no lsscsi"                'lsscsi'                    "${SETUP}"
absent "setup-dev has no ARM_DRIVE_SERIAL"      'ARM_DRIVE_SERIAL'          "${SETUP}"
absent "setup-dev has no ripper sentinel"       'arm-ripper services'       "${SETUP}"
absent "setup-dev has no per-ripper leaf certs" 'arm-ripper-sr'             "${SETUP}"
absent "setup-dev has no detect_optical_drives" 'detect_optical_drives'     "${SETUP}"
absent "setup-dev has no ensure_ripper_certs"   'ensure_ripper_certs'       "${SETUP}"
present "setup-dev udev rule covers every optical drive" 'KERNEL=="sr\[0-9\]\*", ENV\{UDISKS_AUTO\}="0"' "${LIB}/udev.sh"
absent "setup-dev udev rule no longer scopes by ID_PATH" 'ID_PATH'          "${SETUP}"

# --- setup-dev.sh: transcode image variants ----------------------------------
absent  "setup-dev has no probe_encoder_caps"          'probe_encoder_caps'   "${SETUP}"
absent  "setup-dev no longer runs --probe-encoders"    '--probe-encoders'     "${SETUP}"
for f in "${LIB}"/*.sh; do
    for pat in 'lsscsi' 'ARM_DRIVE_SERIAL' 'arm-ripper-sr' 'detect_optical_drives' 'ID_PATH' 'probe_encoder_caps' '--probe-encoders' '^[^#]*--remove-orphans'; do
        absent "$(basename "${f}") has no ${pat}" "${pat}" "${f}"
    done
done
present "setup-dev filter names arm-transcode-intel"   '^ *arm-transcode-intel\)$' "${LIB}/lifecycle.sh"
present "setup-dev filter names arm-transcode-amd"     '^ *arm-transcode-amd\)$'   "${LIB}/lifecycle.sh"
present "detect_gpus emits empty encoder_kinds"        'encoder_kinds\\":\[\]\}' "${LIB}/detect.sh"

# select_up_services, run for real against stubbed compose/detect_gpus: prints
# the services it would build ("ALL" when nothing is skipped).
select_defs="$(awk '/^DETECTED_GPUS=""$/,/^}$/' "${LIB}/detect.sh"; awk '/^UP_SERVICES=\(\)$/,/^}$/' "${LIB}/lifecycle.sh")"
selected() {  # selected <ripper_only> <remote_host 0|1> <ARM_GPUS json>
    # The variables and stubs below are consumed by the eval'd setup-dev code.
    # shellcheck disable=SC2034,SC2317,SC2329
    (
        # shellcheck source=/dev/null
        source "${LIB}/common.sh"
        RIPPER_ONLY="$1"
        ENV_FILE="$(mktemp)"
        trap 'rm -f "${ENV_FILE}"' EXIT
        [[ "$2" == 1 ]] && echo 'ARM_TRANSCODE_DOCKER_HOST=ssh://transcode-host' > "${ENV_FILE}"
        stub_gpus="$3"
        compose() { printf '%s\n' arm-db arm-backend arm-transcode arm-transcode-intel arm-transcode-amd arm-ripper; }
        detect_gpus() { printf '%s' "${stub_gpus}"; }
        eval "${select_defs}"
        select_up_services
        echo "${UP_SERVICES[*]:-ALL}"
    )
}
qsv='{"vendor":"qsv","device_path":"/dev/dri/renderD128","encoder_kinds":[]}'
amd='{"vendor":"vaapi","device_path":"/dev/dri/renderD129","encoder_kinds":[]}'
check "--ripper-only builds no transcode image (base, intel, amd)" "arm-db arm-backend arm-ripper" "$(selected 1 0 "[${qsv},${amd}]")"
check "no GPU builds base only"            "arm-db arm-backend arm-transcode arm-ripper" "$(selected 0 0 '[]')"
check "qsv GPU adds arm-transcode-intel"   "arm-db arm-backend arm-transcode arm-transcode-intel arm-ripper" "$(selected 0 0 "[${qsv}]")"
check "vaapi GPU adds arm-transcode-amd"   "arm-db arm-backend arm-transcode arm-transcode-amd arm-ripper" "$(selected 0 0 "[${amd}]")"
check "qsv + vaapi GPUs build everything"  "ALL" "$(selected 0 0 "[${qsv},${amd}]")"
check "remote transcode host skips both variants, keeps base" "arm-db arm-backend arm-transcode arm-ripper" "$(selected 0 1 "[${qsv},${amd}]")"

# remove_retired_services, run for real against stubbed compose/docker: prints
# the docker filters it queried and the ids it removed.
retired_defs="$(awk '/^RETIRED_SERVICES=/,/^}$/' "${LIB}/lifecycle.sh")"
retired() {  # retired <compose project name, empty = config fails> <ids docker ps returns>
    # shellcheck disable=SC2034,SC2317,SC2329
    (
        # shellcheck source=/dev/null
        source "${LIB}/common.sh"
        stub_project="$1" stub_ids="$2"
        compose() { [[ -n "${stub_project}" ]] && printf 'name: %s\n\nservices:\n' "${stub_project}"; }
        docker() {
            case "$1" in
                ps) printf 'ps %s %s\n' "$4" "$6" >&2; [[ -n "${stub_ids}" ]] && printf '%s\n' "${stub_ids}" ;;
                rm) shift; printf 'rm %s\n' "$*" >&2 ;;
            esac
        }
        eval "${retired_defs}"
        remove_retired_services 2>&1 >/dev/null | tr '\n' ';'
    )
}
check "retired arm-ui-neu container is removed by project + service label" \
    "ps label=com.docker.compose.project=armv3 label=com.docker.compose.service=arm-ui-neu;rm -f c0ffee;" \
    "$(retired armv3 c0ffee)"
check "no retired container: nothing removed" \
    "ps label=com.docker.compose.project=armv3 label=com.docker.compose.service=arm-ui-neu;" \
    "$(retired armv3 '')"
check "unreadable compose config: no docker calls" "" "$(retired '' c0ffee)"
present "up removes retired services"   '^    remove_retired_services$' "${SETUP}"

# remove_spawned_containers + respawn_rippers_if_needed, run for real against
# stubbed compose/docker: prints RIPPERS_REMOVED and whether the backend was
# restarted. The backend respawns rippers only at startup, so a deploy that
# leaves it running must restart it.
spawn_defs="$(awk '/^RIPPERS_REMOVED=0$/,/^}$/' "${LIB}/lifecycle.sh"; awk '/^backend_started_at\(\) \{$/,/^}$/' "${LIB}/lifecycle.sh"; awk '/^respawn_rippers_if_needed\(\) \{/,/^}$/' "${LIB}/lifecycle.sh")"
respawn() {  # respawn <ripper ids> <transcoder ids> <StartedAt before> <StartedAt after>
    # shellcheck disable=SC2034,SC2317,SC2329
    (
        # shellcheck source=/dev/null
        source "${LIB}/common.sh"
        stub_rippers="$1" stub_tasks="$2" before="$3" stub_after="$4"
        BACKEND_SERVICE=arm-backend
        compose() {
            case "$1" in
                ps) [[ -n "${stub_after}" ]] && echo backend-id ;;
                restart) echo "restart $2" >&2 ;;
            esac
        }
        docker() {
            case "$1" in
                ps) case "$4" in
                        label=arm.drive_id) [[ -n "${stub_rippers}" ]] && printf '%s\n' "${stub_rippers}" ;;
                        label=arm.task_id) [[ -n "${stub_tasks}" ]] && printf '%s\n' "${stub_tasks}" ;;
                    esac ;;
                rm) ;;
                inspect) echo "${stub_after}" ;;
            esac
            return 0
        }
        eval "${spawn_defs}"
        remove_spawned_containers >/dev/null
        out="$(respawn_rippers_if_needed "${before}" 2>&1 >/dev/null)"
        echo "removed=${RIPPERS_REMOVED} ${out:-no-restart}"
    )
}
check "ripper removed, backend kept running: backend restarted" \
    "removed=1 restart arm-backend" "$(respawn r1 '' T1 T1)"
check "ripper removed, backend recreated by compose: no restart" \
    "removed=1 no-restart" "$(respawn r1 '' T1 T2)"
check "only a transcoder removed: no restart" \
    "removed=0 no-restart" "$(respawn '' t1 T1 T1)"
check "nothing removed: no restart" \
    "removed=0 no-restart" "$(respawn '' '' T1 T1)"
check "backend was not running before up: no restart" \
    "removed=1 no-restart" "$(respawn r1 '' '' T2)"
present "up restarts a kept backend after removing rippers" '^    respawn_rippers_if_needed "\$\{BACKEND_STARTED_BEFORE\}"$' "${SETUP}"
absent  "setup-dev never runs --remove-orphans" '^[^#]*--remove-orphans' "${SETUP}"

# --- shared library: dev output is unchanged ---------------------------------
# dev_out <snippet>: run a snippet with the library loaded the way setup-dev.sh
# loads it. The golden strings below are what setup-dev.sh printed before the
# functions moved into deploy/lib/.
dev_out() {
    # shellcheck disable=SC2034,SC1090
    (
        ARM_HINT_FORCE_CMD="bash devtools/setup-dev.sh up --force"
        ARM_HINT_IMAGES_READY="Images are built"
        ARM_HINT_LOGS_CMD="docker compose logs"
        ARM_HINT_RIPPER_ONLY="--ripper-only"
        ARM_UDEV_MANAGED_BY="devtools/setup-dev.sh"
        FORCE=0 NO_BACKUP=0 RIPPER_ONLY=0
        for lib in common detect certs udev lifecycle; do source "${LIB}/${lib}.sh"; done
        eval "$1"
    )
}
check "arm_say prints the ==> prefix"      "==> hello"       "$(dev_out 'arm_say hello')"
check "arm_sub prints the line verbatim"   "    (detail)"    "$(dev_out 'arm_sub "    (detail)"')"
check "arm_warn prints WARNING: to stderr" "WARNING: careful" "$(dev_out 'arm_warn careful' 2>&1 >/dev/null)"
check "arm_err prints ERROR: to stderr"    "ERROR: broken"   "$(dev_out 'arm_err broken' 2>&1 >/dev/null)"

want_guard=$'ERROR: backend-spawned containers have ACTIVE work:\n         t1 (transcoder)\n       Removing them would kill the rip or transcode in progress. Images are built;\n       nothing has been backed up, removed or restarted yet.\n       Wait for the job to finish, or re-run the same command with --force, e.g.:\n         bash devtools/setup-dev.sh up --force'
# shellcheck disable=SC2016  # the snippet expands inside dev_out's eval, not here
got_guard="$(dev_out 'docker() { [[ "$3" == "label=arm.task_id" ]] && echo t1; return 0; }; guard_running_spawned' 2>&1 >/dev/null || true)"
check "guard refusal text is unchanged" "${want_guard}" "${got_guard}"

want_abort=$'ERROR: pre-deploy database backup failed: boom\n       Aborting before anything is removed or restarted; the running stack is untouched.\n       Fix the cause, or re-run with --no-backup to deploy without a backup.'
check "backup abort text is unchanged" "${want_abort}" "$(dev_out 'backup_abort boom' 2>&1 >/dev/null || true)"

check "udev rule header names setup-dev" \
    "# Managed by devtools/setup-dev.sh — do not edit by hand." \
    "$(dev_out build_udev_rule_content | head -n 1)"
check "udev rule body is the host-wide rule" \
    'SUBSYSTEM=="block", KERNEL=="sr[0-9]*", ENV{UDISKS_AUTO}="0"' \
    "$(dev_out build_udev_rule_content | tail -n 1)"

# shellcheck disable=SC2016  # the snippet expands inside dev_out's eval, not here
check "ripper-only GPU message is unchanged" \
    "==> --ripper-only: skipping GPU detection, ARM_GPUS=[]" \
    "$(dev_out 'ENV_FILE="$(mktemp)"; RIPPER_ONLY=1; refresh_arm_gpus; rm -f "${ENV_FILE}"')"

# shellcheck disable=SC2016  # the snippet expands inside dev_out's eval, not here
check "env_set appends a new key" "A=1;B=2;" \
    "$(dev_out 'f="$(mktemp)"; echo A=1 > "$f"; env_set B 2 "$f"; tr "\n" ";" < "$f"; rm -f "$f"')"
# shellcheck disable=SC2016  # the snippet expands inside dev_out's eval, not here
check "env_set replaces an existing key, even the only one" "A=x|y&z;" \
    "$(dev_out 'f="$(mktemp)"; echo A=1 > "$f"; env_set A "x|y&z" "$f"; tr "\n" ";" < "$f"; rm -f "$f"')"
# shellcheck disable=SC2016  # the snippet expands inside dev_out's eval, not here
check "env_unset removes a key" "B=2;" \
    "$(dev_out 'f="$(mktemp)"; printf "A=1\nB=2\n" > "$f"; env_unset A "$f"; tr "\n" ";" < "$f"; rm -f "$f"')"
check "detect_cdrom_gid falls back to 44" "44" \
    "$(dev_out 'getent() { return 2; }; detect_cdrom_gid')"

# No message literal may remain outside the helpers: everything goes through them.
rc=0; grep -nE '"(==> |ERROR: |WARNING: )' "${LIB}"/detect.sh "${LIB}"/certs.sh "${LIB}"/udev.sh "${LIB}"/lifecycle.sh >/dev/null || rc=$?
check "library prints only through the output helpers" 1 "${rc}"
present "setup-dev loads the shared library" 'deploy/lib/\$\{lib\}\.sh' "${SETUP}"
absent  "setup-dev no longer shells out to install.sh" 'install\.sh" *\\$' "${SETUP}"

# --- compose template -----------------------------------------------------------
absent  "template has no generated region"      'arm-ripper services'       "${TEMPLATE}"
absent  "template has no arm-ripper-srN"        'arm-ripper-sr'             "${TEMPLATE}"
present "template has the arm-ripper service"   '^  arm-ripper:$'           "${TEMPLATE}"
present "arm-ripper image defaults like transcode" 'ARM_RIPPER_IMAGE:-arm-ripper:latest' "${TEMPLATE}"
present "template has the arm-transcode-intel service" '^  arm-transcode-intel:$' "${TEMPLATE}"
present "template has the arm-transcode-amd service"   '^  arm-transcode-amd:$'   "${TEMPLATE}"
present "arm-transcode-intel image defaults to latest-intel" 'ARM_TRANSCODE_IMAGE_QSV:-arm-transcode:latest-intel' "${TEMPLATE}"
present "arm-transcode-amd image defaults to latest-amd"     'ARM_TRANSCODE_IMAGE_VAAPI:-arm-transcode:latest-amd' "${TEMPLATE}"
present "backend gets /dev/disk read-only"      '/dev/disk:/host-disk:ro'   "${TEMPLATE}"
present "backend receives ARM_RIPPER_IMAGE"     'ARM_RIPPER_IMAGE: \$\{ARM_RIPPER_IMAGE' "${TEMPLATE}"
present "backend forwards ripper poll tunable"  'ARM_RIPPER_POLL_INTERVAL_SECONDS' "${TEMPLATE}"
present "template has the arm-data-init service" '^  arm-data-init:$'        "${TEMPLATE}"
present "backend waits for arm-data-init"      'condition: service_completed_successfully' "${TEMPLATE}"

# --- compose template: ISO library mount ------------------------------------
present "backend mounts the ISO library read-only" 'ARM_HOST_ISO_LIBRARY_PATH:-\./arm/iso-library\}:/ingress:ro' "${TEMPLATE}"
present "backend receives ARM_HOST_ISO_LIBRARY_PATH" 'ARM_HOST_ISO_LIBRARY_PATH: \$\{ARM_HOST_ISO_LIBRARY_PATH:-\}' "${TEMPLATE}"
present "setup-dev creates the iso-library dir" 'iso-library' "${SETUP}"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    envfile="$(mktemp)"
    printf 'POSTGRES_USER=a\nPOSTGRES_PASSWORD=b\nPOSTGRES_DB=c\nARM_SERVICE_TOKEN=t\n' > "${envfile}"
    services=""
    services="$(cd "${ROOT}" && docker compose --env-file "${envfile}" -f "${TEMPLATE}" config --services 2>/dev/null)" || true
    rm -f "${envfile}"
    rc=0; grep -qx 'arm-ripper' <<<"${services}" || rc=$?
    check "compose config lists arm-ripper" 0 "${rc}"
    rc=0; grep -q 'arm-ripper-sr' <<<"${services}" || rc=$?
    check "compose config lists no arm-ripper-srN" 1 "${rc}"
    rc=0; grep -qx 'arm-data-init' <<<"${services}" || rc=$?
    check "compose config lists arm-data-init" 0 "${rc}"
    for svc in arm-transcode arm-transcode-intel arm-transcode-amd; do
        rc=0; grep -qx "${svc}" <<<"${services}" || rc=$?
        check "compose config lists ${svc}" 0 "${rc}"
    done
    envfile="$(mktemp)"
    printf 'POSTGRES_USER=a\nPOSTGRES_PASSWORD=b\nPOSTGRES_DB=c\nARM_SERVICE_TOKEN=t\n' > "${envfile}"
    replicas=""
    replicas="$(cd "${ROOT}" && docker compose --env-file "${envfile}" -f "${TEMPLATE}" config 2>/dev/null | awk '/^  arm-ripper:$/{f=1} f && /replicas:/{print $2; exit}')" || true
    rm -f "${envfile}"
    check "arm-ripper has replicas: 0" "0" "${replicas:-missing}"
    envfile="$(mktemp)"
    printf 'POSTGRES_USER=a\nPOSTGRES_PASSWORD=b\nPOSTGRES_DB=c\nARM_SERVICE_TOKEN=t\n' > "${envfile}"
    rendered=""
    rendered="$(cd "${ROOT}" && docker compose --env-file "${envfile}" -f "${TEMPLATE}" config 2>/dev/null)" || true
    rm -f "${envfile}"
    for pair in arm-transcode:base arm-transcode-intel:intel arm-transcode-amd:amd; do
        svc="${pair%%:*}"
        got="$(awk -v s="  ${svc}:" '$0 == s {f=1; next} f && /^  [a-z]/ {exit} f && /target:/ {print $2}' <<<"${rendered}")"
        check "${svc} builds Dockerfile target ${pair#*:}" "${pair#*:}" "${got:-missing}"
        got="$(awk -v s="  ${svc}:" '$0 == s {f=1; next} f && /^  [a-z]/ {exit} f && /replicas:/ {print $2}' <<<"${rendered}")"
        check "${svc} has replicas: 0" "0" "${got:-missing}"
    done
else
    echo "skip - docker compose not available; template checked by grep only"
fi

# --- iso-smoke.sh: ISO-rip API, not a borrowed drive ------------------------
SMOKE="${ROOT}/devtools/iso-smoke.sh"
absent  "iso-smoke no longer mounts per-ripper certs" 'arm-ripper-sr0\.(crt|key)' "${SMOKE}"
absent  "iso-smoke has no arm-ripper-sr0 service"     'RIPPER_SERVICE="arm-ripper-sr0"' "${SMOKE}"
absent  "iso-smoke no longer borrows a drive"         'pause_managed_ripper|ARM_MANUAL_TRIGGER_ISO' "${SMOKE}"
present "iso-smoke uses the ISO rip API"              '/api/iso/rips' "${SMOKE}"
rc=0; bash -n "${SMOKE}" || rc=$?
check "iso-smoke parses" 0 "${rc}"

exit "${fail}"
