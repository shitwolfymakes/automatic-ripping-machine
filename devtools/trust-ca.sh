#!/usr/bin/env bash
# Trust the ARM v3 local CA (arm/certs/arm-ca.crt) on this dev machine so
# https://localhost:8081 loads without the self-signed warning and
# curl/wget stop needing -k.
#
# Installs into the Linux trust store (update-ca-certificates) and — when
# running under WSL — the Windows CurrentUser Root store (certutil.exe -user,
# no UAC) so Chrome/Edge on Windows trust it too. Idempotent + rotation-safe
# (remove-then-add), so re-run freely (e.g. after install.sh --rotate-ca).
# `--untrust` removes the CA from both stores.
#
# Dev-only. Not shipped, not invoked by setup-dev.sh or CI. install.sh owns
# CA *generation*; this only trusts an already-minted CA.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: bash devtools/trust-ca.sh [--untrust] [-h|--help]

  (no args)   Trust the ARM local CA in the Linux store and, under WSL, the
              Windows CurrentUser Root store. Idempotent / rotation-safe.
  --untrust   Remove the ARM CA from both stores and exit.
  -h, --help  Show this help.

Linux store needs sudo (prompts). Windows uses the CurrentUser store (no UAC).
EOF
}

MODE="trust"
case "${1:-}" in
    --untrust) MODE="untrust" ;;
    -h|--help) usage; exit 0 ;;
    "") ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 2 ;;
esac

ROOT_DIR="$(git rev-parse --show-toplevel)"
CA="${ROOT_DIR}/arm/certs/arm-ca.crt"
CA_CN="ARM v3 Local CA"
LINUX_DEST="/usr/local/share/ca-certificates/arm-v3-local-ca.crt"

if [[ ! -f "$CA" ]]; then
    echo "CA not found at ${CA}" >&2
    echo "generate it first: bash devtools/setup-dev.sh  (or: bash install.sh --certs-only)" >&2
    exit 1
fi

is_wsl() {
    grep -qi microsoft /proc/version 2>/dev/null \
        && command -v certutil.exe >/dev/null 2>&1 \
        && command -v wslpath >/dev/null 2>&1
}

linux_ok=0; win_ok=0; attempted=0

# ---------------- Linux trust store ----------------
attempted=1
if [[ "$MODE" == "untrust" ]]; then
    if sudo rm -f "$LINUX_DEST" && sudo update-ca-certificates >/dev/null 2>&1; then
        echo "✓ Linux: removed ARM CA from the trust store"; linux_ok=1
    else
        echo "✗ Linux: failed to remove from the trust store" >&2
    fi
else
    # remove-then-add via a fixed filename → in-place replace (rotation-safe)
    if sudo install -m 0644 "$CA" "$LINUX_DEST" && sudo update-ca-certificates >/dev/null 2>&1; then
        echo "✓ Linux: trusted ARM CA (update-ca-certificates)"; linux_ok=1
    else
        echo "✗ Linux: failed to install into the trust store" >&2
    fi
fi

# ---------------- Windows CurrentUser Root (WSL only) ----------------
if is_wsl; then
    attempted=1
    WIN_CA="$(wslpath -w "$CA")"
    # delstore first (removes ALL matches incl. a stale rotated CA); no-op if absent.
    certutil.exe -user -delstore Root "$CA_CN" >/dev/null 2>&1 || true
    if [[ "$MODE" == "untrust" ]]; then
        echo "✓ Windows: removed ARM CA from CurrentUser Root"; win_ok=1
    else
        if certutil.exe -user -addstore Root "$WIN_CA" >/dev/null 2>&1; then
            echo "✓ Windows: trusted ARM CA in CurrentUser Root (no UAC)"; win_ok=1
        else
            echo "✗ Windows: certutil -addstore failed" >&2
        fi
    fi
else
    echo "• Windows: skipped (not WSL, or certutil.exe/wslpath unavailable)"
fi

# ---------------- summary / exit ----------------
if [[ "$MODE" == "trust" && "$linux_ok" -eq 1 ]]; then
    echo "  done — browsers may need a restart to pick up the new root."
    printf '%s\n' "  verify (Linux): curl -s -o /dev/null -w '%{http_code}\\n' https://localhost:8081/   # 200, no -k"
fi

# Fail only if every attempted store failed.
if [[ "$attempted" -eq 1 && "$linux_ok" -eq 0 && "$win_ok" -eq 0 ]]; then
    echo "all trust-store updates failed" >&2
    exit 1
fi
