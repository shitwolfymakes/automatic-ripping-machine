#!/usr/bin/env bash
# shellcheck disable=SC2317,SC2329
# (Shadow functions below are invoked indirectly by sourced install.sh code —
# newer shellcheck flags them unreachable; this is the documented
# "ignore if invoked indirectly" case.)
# Plain-bash unit test for install.sh's remote-offload walkthrough machinery:
# output helpers, input validators, paste-block generators, verify-step
# classification, and the completion table. Sources install.sh via
# ARM_INSTALL_SOURCE_ONLY; no docker, no root, no network.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL="${HERE}/../install.sh"

if ! grep -q 'ARM_INSTALL_SOURCE_ONLY' "$INSTALL"; then
    echo "FAIL - install.sh has no ARM_INSTALL_SOURCE_ONLY seam; refusing to source it" >&2
    exit 1
fi

export ARM_INSTALL_SOURCE_ONLY=1
# shellcheck disable=SC1090
source "$INSTALL"

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

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

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

# compose injection: run the awk-injection helper against a fixture compose.
FIX="$TMPROOT/compose-fixture.yml"
cat > "$FIX" <<'EOF'
  arm-backend:
    image: x/arm-backend:t
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
EOF
inject_offload_compose "$FIX" "https://192.168.0.68:8080"
check "ssh mount injected" "1" "$(grep -c '/home/arm/.ssh:ro' "$FIX")"
check "port published" "1" "$(grep -c '"8080:8443"' "$FIX")"
# idempotent: second run must not duplicate
inject_offload_compose "$FIX" "https://192.168.0.68:8080"
check "injection idempotent" "1" "$(grep -c '"8080:8443"' "$FIX")"

# certs path: offload on -> remote-user-writable path
check "certs path (offload)" "/home/sam/.arm/certs" "$(offload_certs_path "ssh://sam@192.168.0.92")"

exit "$fail"
