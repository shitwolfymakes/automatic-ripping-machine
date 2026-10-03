# Installer Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the frozen `install.sh` with a bootstrap that installs a per-release bundle, an `armctl` launcher for install, up, down and upgrade, and a `deploy/lib` shared with `devtools/setup-dev.sh`.

**Architecture:** The functions `setup-dev.sh` already has (host detection, udev rule, lifecycle safety) move unchanged into `deploy/lib/`, and both `setup-dev.sh` and the new `deploy/armctl.sh` load them. Production runs the committed compose template as it is, layered with a small release overlay and a generated host overlay, with Compose's project directory set to the folder that contains `arm`. Root `install.sh` shrinks to a bootstrap that downloads a release bundle (the contents of `deploy/` plus the two template files) into `arm/.armctl/releases/<tag>/` and hands over to `armctl install`.

**Tech Stack:** bash 4+, Docker Engine 24+ with Compose v2, openssl, GitHub Actions, plain-bash test suites (no bats, no docker required).

**Spec:** `docs/superpowers/specs/2026-10-03-installer-rewrite-design.md`

## Global Constraints

- Target hosts: Linux with Docker Engine >= 24 and the Compose v2 plugin; bash >= 4; openssl >= 1.1.1.
- `docker-compose.yml.example` and `.env.example` are **not edited** by this work, except comments in `.env.example` (Task 11).
- `devtools/setup-dev.sh` keeps its commands, flags and output. The only allowed differences are listed in Task 1 under "Allowed differences".
- The install folder is always named `arm`. Data sits directly in it; configuration sits in `arm/.armctl/`.
- The installer refuses to run as root.
- Fresh installs only: no migration code for the old installer's layout.
- Tests are zero-infra: no Docker daemon, no root, no network. A test may use `docker compose config` when Docker is present and must fall back to text checks when it is not.
- Every shell file passes `shellcheck` with no findings (CI runs it on `git ls-files '*.sh'`, so every script ends in `.sh`). A file whose job is to set variables that other sourced files read carries a file-level `# shellcheck disable=SC2034` on line 2, with a one-line reason; if shellcheck reports SC2034 for a variable in `deploy/lib/` that `setup-dev.sh` or `armctl.sh` reads, do the same there.
- GitHub Actions `uses:` lines are pinned to a 40-character commit SHA with a `# vX.Y.Z` comment.
- Commit messages are conventional commits ending with exactly one trailer, `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, and no session link.
- New user-facing messages use no em dashes.
- Run the Python suite as `uv run pytest` from the repo root only. Never add `__init__.py` under any `tests/` folder.

## Review Focus

Inputs the spec implies but does not spell out, most likely first. Each has a test in the task that owns the code.

1. **A storage folder with a space in its name** (a USB disk mounted at `/media/sam/My Passport/rips`). Expected: the install works and the stack mounts that folder. Tests: Task 4 (`overlay quotes a path with spaces`) and Task 5 (contract test, Docker-gated).
2. **`--prefix` given as the arm folder itself** (`--prefix ~/arm`, the old installer's meaning). Expected: installs into `~/arm`, not `~/arm/arm`. Test: Task 8.
3. **An `arm` folder that already exists and is not an armctl install** (an ARM v2 home with `media/` and `config/`, or the old v3 layout with `docker-compose.yml` at the top). Expected: the installer stops with a clear message and changes nothing. Test: Task 8.
4. **A pull that "succeeds" without fetching an image** (registry down, tag typo; Compose tolerates pull failures for services that have a `build:` section). Expected: `armctl up` stops before the guard, the backup or any removal. Test: Task 3.
5. **A session that is not yet in the `docker` group although the user is** (right after Docker was installed, or any later `armctl` command before a re-login). Expected: `armctl` restarts itself under the group once, and never loops. Test: Task 6.

---

## File Structure

**Created**

| Path | Responsibility |
|---|---|
| `deploy/lib/common.sh` | Output helpers, `require`, `compose`, `.env` read/write helpers, `run_quiet`. |
| `deploy/lib/detect.sh` | GPU discovery, NVENC driver floor, render and cdrom group ids, `ARM_GPUS` refresh. |
| `deploy/lib/certs.sh` | CA and leaf certificate generation. |
| `deploy/lib/udev.sh` | The host-wide udev rule and its installation. |
| `deploy/lib/lifecycle.sh` | Guard, backup and pruning, spawned-container cleanup, ripper respawn, retired services, image selection, health wait. |
| `deploy/armctl.sh` | Production launcher: settings, compose wiring, `up`, `down`, `upgrade`, `compose`, lock, root refusal. |
| `deploy/install/ui.sh` | Production output style, prompts, consent handling. |
| `deploy/install/config.sh` | Profile, storage locations, `.env`, image pins, host overlay. |
| `deploy/install/docker.sh` | Docker diagnosis, apt install, restart under the `docker` group. |
| `deploy/install/nvidia.sh` | NVIDIA container toolkit offer. |
| `deploy/install/offload.sh` | The remote transcode offload walkthrough. |
| `deploy/install/pathlink.sh` | Linking `armctl` onto the PATH. |
| `deploy/install/flow.sh` | `cmd_install`: the staged install. |
| `deploy/docker-compose.release.yml` | Release images for `arm-backend`, `arm-data-init`, `arm-ui`. |
| `deploy/build-bundle.sh` | Packs the bundle and its checksum. |
| `deploy/tests/test-armctl.sh` | Zero-infra suite for `armctl.sh` and `deploy/install/*`. |
| `deploy/tests/test-bootstrap.sh` | Zero-infra suite for root `install.sh`. |
| `deploy/tests/test-bundle.sh` | Bundle contents and template identity. |
| `deploy/tests/test-stack-contract.sh` | The layered production compose config. |
| `devtools/install-drill.sh` | Manual end-to-end install against locally built images. |

**Modified**

| Path | Change |
|---|---|
| `devtools/setup-dev.sh` | Loads `deploy/lib/*.sh`; inline copies of the moved functions are deleted. |
| `devtools/test-setup-dev.sh` | Points at the new files; adds dev-output golden checks. |
| `devtools/test-install-walkthrough.sh` | Sources `deploy/install/*` and `deploy/lib/*` instead of `install.sh`. |
| `install.sh` | Replaced by the bootstrap. |
| `.github/workflows/release.yml` | Bundle job. |
| `.github/workflows/ci.yml` | Runs the new suites and packs the bundle. |
| `.dockerignore` | Excludes `deploy/`. |
| Docs, `.env.example` comments, `CLAUDE.md`, `.claude/memory/` | Task 11. |

**Names every task relies on**

Caller settings (set by `setup-dev.sh` and by `armctl.sh` before any library call):

| Variable | Meaning | `setup-dev.sh` value |
|---|---|---|
| `ARM_COMPOSE_CWD` | folder Compose runs from | `${ROOT_DIR}` |
| `ARM_COMPOSE_CMD` | array: compose command and fixed flags | `(docker compose)` |
| `ENV_FILE` | the stack's `.env` | `${ROOT_DIR}/.env` |
| `ARM_DIR` | data folder | `${ROOT_DIR}/arm` |
| `ARM_CERTS_DIR` | certificates folder | `${ARM_DIR}/certs` |
| `DB_SERVICE`, `BACKEND_SERVICE`, `UI_SERVICE` | compose service names | `arm-db`, `arm-backend`, `arm-ui` |
| `RIPPER_ONLY`, `FORCE`, `NO_BACKUP` | flags, `0` or `1` | from the command line |
| `ARM_HINT_FORCE_CMD` | command shown in the guard's refusal | `bash devtools/setup-dev.sh up --force` |
| `ARM_HINT_IMAGES_READY` | first clause of the guard's "nothing changed" line | `Images are built` |
| `ARM_HINT_LOGS_CMD` | command shown when health cannot be checked | `docker compose logs` |
| `ARM_HINT_RIPPER_ONLY` | how this caller names ripper-only | `--ripper-only` |
| `ARM_UDEV_MANAGED_BY` | tool named in the udev rule's header | `devtools/setup-dev.sh` |

---

### Task 0: Branch and baseline

**Files:** none changed.

- [ ] **Step 1: Create the work branch**

The base is `integration/all-prs-3` at the spec commit, unless the owner names another base at plan review.

```bash
git switch integration/all-prs-3
git switch -c feat/installer-rewrite
```

- [ ] **Step 2: Capture the `setup-dev.sh` baseline before touching anything**

```bash
B="${TMPDIR:-/tmp}/arm-installer-baseline"; mkdir -p "$B"
bash devtools/test-setup-dev.sh        > "$B/test-setup-dev.before.txt" 2>&1; echo "rc=$?" >> "$B/test-setup-dev.before.txt"
bash devtools/test-install-walkthrough.sh > "$B/test-walkthrough.before.txt" 2>&1; echo "rc=$?" >> "$B/test-walkthrough.before.txt"
bash devtools/setup-dev.sh --help      > "$B/help.before.txt" 2>&1
bash devtools/setup-dev.sh setup       > "$B/setup.before.txt" 2>&1; echo "rc=$?" >> "$B/setup.before.txt"
cp .env "$B/env.before"; cp docker-compose.yml "$B/compose.before.yml"
```

Expected: both suites end `rc=0`; `setup.before.txt` ends `rc=0`. `setup` is idempotent on a dev host (it re-syncs uv, skips npm when current, keeps `.env` secrets).

No commit.

---

### Task 1: Extract the shared library and rewire `setup-dev.sh`

**Files:**
- Create: `deploy/lib/common.sh`, `deploy/lib/detect.sh`, `deploy/lib/certs.sh`, `deploy/lib/udev.sh`, `deploy/lib/lifecycle.sh`
- Modify: `devtools/setup-dev.sh`, `devtools/test-setup-dev.sh`, `.dockerignore`
- Test: `devtools/test-setup-dev.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: every function and variable in "Names every task relies on", plus:
  - `arm_say <text>`, `arm_sub <line with its indentation>`, `arm_warn <text>`, `arm_err <text>` (does not exit)
  - `require <bin> <hint>`, `require_compose`, `compose <args...>`, `run_quiet <cmd...>`
  - `env_file_value <key>` (reads `ENV_FILE`), `env_set <key> <value> [file]`, `env_unset <key> [file]`
  - `nvenc_driver_ok`, `detect_gpus`, `detect_gpus_once` (fills `DETECTED_GPUS`), `detect_render_gid`, `detect_cdrom_gid`, `refresh_arm_gpus`
  - `ensure_ca`, `make_leaf <name> [san...]`
  - `build_udev_rule_content`, `udev_rule_current`, `ensure_udev_rule`
  - `remove_spawned_containers`, `backend_started_at`, `respawn_rippers_if_needed <started-before>`, `remove_retired_services`, `backup_db`, `prune_backups <dir>`, `guard_running_spawned`, `published_url <service> <container-port>`, `wait_for_backend` (sets `HEALTH_RESULT`), `select_up_services` (fills `UP_SERVICES`; empty means all)

**Allowed differences in `setup-dev.sh` behavior** (agreed in the spec, sections 5.4 and 5.5):
1. On a host with no `arm/certs/arm-ca.crt`, the certificate step no longer runs `install.sh --certs-only`. Its headline changes from `==> generating internal CA + leaves via install.sh --certs-only` to `==> generating internal CA + leaves`, the installer's section banners and prerequisite lines disappear, and certificate lines print as `==> ...`.
2. No per-drive `arm-ripper-srN` leaf certificates are issued.

Everything else must be byte-identical.

- [ ] **Step 1: Add the failing checks to `devtools/test-setup-dev.sh`**

Add `LIB="${ROOT}/deploy/lib"` after the `TEMPLATE=` line. Then insert this block immediately before the line `# --- compose template ---...`:

```bash
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

check "ripper-only GPU message is unchanged" \
    "==> --ripper-only: skipping GPU detection, ARM_GPUS=[]" \
    "$(dev_out 'ENV_FILE="$(mktemp)"; RIPPER_ONLY=1; refresh_arm_gpus; rm -f "${ENV_FILE}"')"

check "env_set appends a new key" "A=1;B=2;" \
    "$(dev_out 'f="$(mktemp)"; echo A=1 > "$f"; env_set B 2 "$f"; tr "\n" ";" < "$f"; rm -f "$f"')"
check "env_set replaces an existing key, even the only one" "A=x|y&z;" \
    "$(dev_out 'f="$(mktemp)"; echo A=1 > "$f"; env_set A "x|y&z" "$f"; tr "\n" ";" < "$f"; rm -f "$f"')"
check "env_unset removes a key" "B=2;" \
    "$(dev_out 'f="$(mktemp)"; printf "A=1\nB=2\n" > "$f"; env_unset A "$f"; tr "\n" ";" < "$f"; rm -f "$f"')"
check "detect_cdrom_gid falls back to 44" "44" \
    "$(dev_out 'getent() { return 2; }; detect_cdrom_gid')"

# No message literal may remain outside the helpers: everything goes through them.
rc=0; grep -nE '"(==> |ERROR: |WARNING: )' "${LIB}"/detect.sh "${LIB}"/certs.sh "${LIB}"/udev.sh "${LIB}"/lifecycle.sh >/dev/null || rc=$?
check "library prints only through the output helpers" 1 "${rc}"
present "setup-dev loads the shared library" 'deploy/lib/\$\{lib\}\.sh' "${SETUP}"
absent  "setup-dev no longer shells out to install.sh" 'install\.sh" *\\$' "${SETUP}"
```

- [ ] **Step 2: Run the suite to see the new checks fail**

Run: `bash devtools/test-setup-dev.sh; echo rc=$?`
Expected: `FAIL` lines for every new check (the library files do not exist), `rc=1`.

- [ ] **Step 3: Create `deploy/lib/common.sh`**

```bash
#!/usr/bin/env bash
# deploy/lib/common.sh: helpers shared by devtools/setup-dev.sh (dev) and
# deploy/armctl.sh (production). Sourced, never executed.
#
# Callers set, before calling anything here:
#   ARM_COMPOSE_CWD   folder `docker compose` runs from
#   ARM_COMPOSE_CMD   array: the compose command plus any fixed flags
#   ENV_FILE          path of the stack's .env

# Output helpers. These defaults print devtools/setup-dev.sh's style, byte for
# byte what it printed before the helpers existed. deploy/armctl.sh redefines
# all four after sourcing this file.
arm_say()  { echo "==> $*"; }
# One continuation line; the caller passes it with its indentation.
arm_sub()  { printf '%s\n' "$1"; }
arm_warn() { echo "WARNING: $*" >&2; }
# Prints only. The caller decides whether to exit.
arm_err()  { echo "ERROR: $*" >&2; }

require() {
    local bin="$1"
    local hint="$2"
    if ! command -v "${bin}" >/dev/null 2>&1; then
        arm_err "'${bin}' not found. ${hint}"
        exit 1
    fi
}

compose() {
    (cd "${ARM_COMPOSE_CWD}" && "${ARM_COMPOSE_CMD[@]}" "$@")
}

require_compose() {
    if ! docker compose version >/dev/null 2>&1; then
        arm_err "'docker compose' (v2 plugin) not available"
        exit 1
    fi
}

# Print KEY's value from ENV_FILE (last uncommented assignment, one layer of
# surrounding quotes stripped), or nothing if it is absent.
env_file_value() {
    local key="$1" val
    [[ -f "${ENV_FILE}" ]] || return 0
    val="$(sed -nE "s/^${key}=(.*)$/\\1/p" "${ENV_FILE}" | tail -n1)"
    val="${val%\"}"; val="${val#\"}"
    val="${val%\'}"; val="${val#\'}"
    printf '%s' "${val}"
}

# Set KEY=VALUE in a .env file (default: ENV_FILE). Delete-then-append rather
# than `sed s|...|value|`: the value may be free text (a URL, a path), and a
# `&` or `|` in it would corrupt a sed replacement. The file is rewritten in
# place so its mode is kept.
env_set() {
    local key="$1" value="$2" file="${3:-${ENV_FILE}}" rest
    if grep -q "^${key}=" "${file}" 2>/dev/null; then
        rest="$(grep -v "^${key}=" "${file}" || true)"
        if [[ -n "${rest}" ]]; then printf '%s\n' "${rest}" > "${file}"; else : > "${file}"; fi
    fi
    printf '%s=%s\n' "${key}" "${value}" >> "${file}"
}

env_unset() {
    local key="$1" file="${2:-${ENV_FILE}}" rest
    grep -q "^${key}=" "${file}" 2>/dev/null || return 0
    rest="$(grep -v "^${key}=" "${file}" || true)"
    if [[ -n "${rest}" ]]; then printf '%s\n' "${rest}" > "${file}"; else : > "${file}"; fi
}

# Run a command silently; replay its captured output only when it fails.
run_quiet() {
    local out rc=0
    out="$("$@" 2>&1)" || rc=$?
    if (( rc != 0 )); then
        printf '%s\n' "$out"
    fi
    return "$rc"
}
```

- [ ] **Step 4: Create `deploy/lib/detect.sh`, `deploy/lib/udev.sh` and `deploy/lib/lifecycle.sh` by moving code out of `devtools/setup-dev.sh`**

Each file starts with:

```bash
#!/usr/bin/env bash
# deploy/lib/<name>.sh: <one line from the File Structure table>.
# Shared by devtools/setup-dev.sh and deploy/armctl.sh. Sourced, never executed.
# Needs deploy/lib/common.sh loaded first.
```

Move each item below **with the comment block that precedes it**, in this order, cutting it from `setup-dev.sh`:

| Into | Items, in order |
|---|---|
| `detect.sh` | `ARM_NVENC_MIN_DRIVER=530`, `nvenc_driver_ok`, `detect_gpus`, `detect_render_gid`, `DETECTED_GPUS=""` + `DETECTED_GPUS_SET=0` + `detect_gpus_once` (keep these three adjacent, in this order), `refresh_arm_gpus` |
| `udev.sh` | `UDEV_RULE_PATH=...`, `build_udev_rule_content`, `ensure_udev_rule` |
| `lifecycle.sh` | `RIPPERS_REMOVED=0` + `remove_spawned_containers` (adjacent), `backend_started_at`, `respawn_rippers_if_needed`, `RETIRED_SERVICES=(arm-ui-neu)` + `remove_retired_services` (adjacent), `BACKUP_MIN_BYTES`, `BACKUP_TMP`, `backup_abort`, `backup_db`, `BACKUP_KEEP` + `prune_backups`, `RIP_PROBE_SH`, `guard_running_spawned`, `published_url`, the four `HEALTH_*` variables, `HEALTH_PY`, `wait_for_backend`, `UP_SERVICES=()` + `select_up_services` (adjacent) |

The adjacency notes matter: `test-setup-dev.sh` extracts these by `awk` range from the variable line to the function's closing `}`.

In the comment above `ARM_NVENC_MIN_DRIVER`, replace the sentence `Mirror any change in install.sh.` with `This is the only shell copy; devtools/setup-dev.sh and deploy/armctl.sh both load it.` In the comment above `detect_gpus`, replace `and the detect_gpus in install.sh` with `(the single shell copy)`.

Then apply these substitutions inside the moved functions. Rules:

- **A.** `echo "==> TEXT"` becomes `arm_say "TEXT"`. A trailing `>&2` is kept.
- **B.** `echo "WARNING: TEXT" >&2` becomes `arm_warn "TEXT"`.
- **C.** `echo "ERROR: TEXT" >&2` becomes `arm_err "TEXT"`. Inside a `{ ...; } >&2` block, `echo "ERROR: TEXT"` becomes `arm_err "TEXT"`.
- **D.** Any other `echo "<spaces>TEXT"` that is a continuation of a message becomes `arm_sub "<spaces>TEXT"`, keeping its indentation and any `>&2`.

Lines that need more than a rule:

| Function | Before | After |
|---|---|---|
| `refresh_arm_gpus` | `echo "==> --ripper-only: skipping GPU detection, ARM_GPUS=[]"` | `arm_say "${ARM_HINT_RIPPER_ONLY}: skipping GPU detection, ARM_GPUS=[]"` |
| `guard_running_spawned` | `printf '      %s\n' "${active[@]}"` (after the `--force` line) | `for found in "${active[@]}"; do arm_sub "      ${found}"; done` |
| `guard_running_spawned` | `printf '         %s\n' "${active[@]}"` (in the error block) | `for found in "${active[@]}"; do arm_sub "         ${found}"; done` |
| `guard_running_spawned` | `echo "       Removing them would kill the rip or transcode in progress. Images are built;"` | `arm_sub "       Removing them would kill the rip or transcode in progress. ${ARM_HINT_IMAGES_READY};"` |
| `guard_running_spawned` | `echo "         bash devtools/setup-dev.sh up --force"` | `arm_sub "         ${ARM_HINT_FORCE_CMD}"` |
| `wait_for_backend` | `(cd "${ROOT_DIR}" && timeout "${HEALTH_ATTEMPT_MAX}" docker compose \` and its continuation `exec -T "${BACKEND_SERVICE}" python -c "${HEALTH_PY}") </dev/null >/dev/null 2>&1 \|\| rc=$?` | `(cd "${ARM_COMPOSE_CWD}" && timeout "${HEALTH_ATTEMPT_MAX}" "${ARM_COMPOSE_CMD[@]}" \` with the same continuation line |
| `wait_for_backend` | `echo "    (${BACKEND_SERVICE} is running; check it by hand: docker compose logs ${BACKEND_SERVICE})"` | `arm_sub "    (${BACKEND_SERVICE} is running; check it by hand: ${ARM_HINT_LOGS_CMD} ${BACKEND_SERVICE})"` |
| `build_udev_rule_content` | the heredoc's first line, `# Managed by devtools/setup-dev.sh — do not edit by hand.` | remove that line from the heredoc and add, before `cat <<'RULE'`: `printf '# Managed by %s — do not edit by hand.\n' "${ARM_UDEV_MANAGED_BY}"` |
| `ensure_udev_rule` | `printf '%s\n' "${desired}"` and `echo "RULE"` (the manual-install instructions) | unchanged and `arm_sub "RULE"` |

`guard_running_spawned` already declares `found` as a local, so the loops need no new variable.

Add to `detect.sh`, after `detect_render_gid`:

```bash
# The host's cdrom group id, or 44 (the Debian/Ubuntu default) when the group
# does not exist.
detect_cdrom_gid() {
    local gid
    gid="$(getent group cdrom | cut -d: -f3 || true)"
    printf '%s' "${gid:-44}"
}
```

In `udev.sh`, add `udev_rule_current` above `ensure_udev_rule` and use it there:

```bash
# True when the installed rule already matches build_udev_rule_content. The
# rule is written with no trailing newline, so compare the same way.
udev_rule_current() {
    local desired
    desired="$(build_udev_rule_content)"
    [[ -r "${UDEV_RULE_PATH}" ]] && diff -q "${UDEV_RULE_PATH}" <(printf '%s' "${desired}") >/dev/null 2>&1
}
```

In `ensure_udev_rule`, replace the condition `[[ -r "${UDEV_RULE_PATH}" ]] && diff -q "${UDEV_RULE_PATH}" <(printf '%s' "${desired}") >/dev/null 2>&1` with `udev_rule_current`.

- [ ] **Step 5: Create `deploy/lib/certs.sh`**

```bash
#!/usr/bin/env bash
# deploy/lib/certs.sh: CA and leaf certificate generation.
# Shared by devtools/setup-dev.sh and deploy/armctl.sh. Sourced, never executed.
# Needs deploy/lib/common.sh loaded first. Callers set ARM_CERTS_DIR.

# Create the internal CA (EC P-384, 10 years) unless it already exists.
ensure_ca() {
    mkdir -p "${ARM_CERTS_DIR}"
    local ca_key="${ARM_CERTS_DIR}/arm-ca.key"
    local ca_crt="${ARM_CERTS_DIR}/arm-ca.crt"
    if [[ -f "$ca_key" && -f "$ca_crt" ]]; then
        arm_say "CA already exists; reusing"
        return 0
    fi
    arm_say "generating CA (EC P-384, 10y)"
    run_quiet openssl ecparam -name secp384r1 -genkey -noout -out "$ca_key"
    chmod 400 "$ca_key"
    run_quiet openssl req -x509 -new -nodes -key "$ca_key" -sha384 -days 3650 \
        -subj "/CN=ARM v3 Local CA" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" \
        -addext "subjectKeyIdentifier=hash" \
        -out "$ca_crt"
    chmod 444 "$ca_crt"
}

# make_leaf <name> [extra SAN ...]: issue a leaf signed by the CA. The name is
# always a DNS SAN; each extra SAN is an IP when it looks like one, DNS otherwise.
# Keys are 440 and group-owned by ARM_PGID so a stack whose PUID differs from
# the user who ran the installer can still read them.
make_leaf() {
    local name="$1"; shift
    local extra_sans=("$@")
    local key="${ARM_CERTS_DIR}/${name}.key"
    local csr="${ARM_CERTS_DIR}/${name}.csr"
    local crt="${ARM_CERTS_DIR}/${name}.crt"
    local ext="${ARM_CERTS_DIR}/${name}.ext"
    local san="DNS:${name}" s
    for s in "${extra_sans[@]:-}"; do
        [[ -z "$s" ]] && continue
        if [[ "$s" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
            san+=",IP:${s}"
        else
            san+=",DNS:${s}"
        fi
    done
    arm_say "issued leaf: ${name} (SANs: ${san})"
    # Clear any earlier 0440/0444 files so openssl can overwrite.
    rm -f "$key" "$crt"
    run_quiet openssl ecparam -name prime256v1 -genkey -noout -out "$key"
    chmod 440 "$key"
    chgrp "${ARM_PGID:-$(id -g)}" "$key" 2>/dev/null || true
    run_quiet openssl req -new -key "$key" -subj "/CN=${name}" -out "$csr"
    cat > "$ext" <<EOF
subjectAltName = ${san}
extendedKeyUsage = serverAuth, clientAuth
EOF
    run_quiet openssl x509 -req -in "$csr" -CA "${ARM_CERTS_DIR}/arm-ca.crt" \
        -CAkey "${ARM_CERTS_DIR}/arm-ca.key" -CAcreateserial \
        -out "$crt" -days 3650 -sha384 -extfile "$ext"
    chmod 444 "$crt"
    rm -f "$csr" "$ext"
}
```

- [ ] **Step 6: Rewire `devtools/setup-dev.sh`**

1. Delete the definitions of `require`, `compose` and `require_compose` (they now come from `common.sh`).
2. Delete `env_file_value` (now in `common.sh`).
3. After the three `*_SERVICE=` lines, insert:

```bash
# Shared deploy library: the same functions deploy/armctl.sh (the production
# launcher) uses. The settings below are this script's side of that contract.
ARM_COMPOSE_CWD="${ROOT_DIR}"
ARM_COMPOSE_CMD=(docker compose)
ARM_CERTS_DIR="${ARM_DIR}/certs"
ARM_HINT_FORCE_CMD="bash devtools/setup-dev.sh up --force"
ARM_HINT_IMAGES_READY="Images are built"
ARM_HINT_LOGS_CMD="docker compose logs"
ARM_HINT_RIPPER_ONLY="--ripper-only"
ARM_UDEV_MANAGED_BY="devtools/setup-dev.sh"
for lib in common detect certs udev lifecycle; do
    # shellcheck source=/dev/null
    source "${ROOT_DIR}/deploy/lib/${lib}.sh"
done
```

4. Replace the certificate `else` branch (the `echo "==> generating internal CA + leaves via install.sh --certs-only"` line and the six-line `bash "${ROOT_DIR}/install.sh" ...` call) with:

```bash
    echo "==> generating internal CA + leaves"
    ensure_ca
    make_leaf arm-backend
    make_leaf arm-db
    make_leaf arm-ui localhost "$(hostname -f 2>/dev/null || hostname || echo localhost)"
```

5. In the `.env` creation branch, replace the two lines `cdrom_gid="$(getent group cdrom | cut -d: -f3 || true)"` and `cdrom_gid="${cdrom_gid:-44}"` with `cdrom_gid="$(detect_cdrom_gid)"`.
6. Leave every top-level `echo "==> ..."` in `setup-dev.sh` as it is. Only the moved functions use the helpers.
7. In the header comment, replace the sentence that says cert generation is delegated to `install.sh` (if present) with `Certificates come from deploy/lib/certs.sh.`

Add `deploy/` on its own line after `install.sh` in `.dockerignore`.

- [ ] **Step 7: Repoint the existing checks in `devtools/test-setup-dev.sh`**

| Check (by label) | Change |
|---|---|
| `setup-dev udev rule covers every optical drive` | file argument `"${SETUP}"` becomes `"${LIB}/udev.sh"` |
| `setup-dev filter names arm-transcode-intel`, `... arm-transcode-amd` | `"${SETUP}"` becomes `"${LIB}/lifecycle.sh"` |
| `detect_gpus emits empty encoder_kinds` | `"${SETUP}"` becomes `"${LIB}/detect.sh"` |
| `select_defs=` | first `awk` reads `"${LIB}/detect.sh"`, second reads `"${LIB}/lifecycle.sh"` |
| `retired_defs=` | reads `"${LIB}/lifecycle.sh"` |
| `spawn_defs=` | all three `awk` calls read `"${LIB}/lifecycle.sh"` |

In each of the three subshell helpers `selected`, `retired` and `respawn`, add as the first line inside the `(`:

```bash
        # shellcheck source=/dev/null
        source "${LIB}/common.sh"
```

It must come before the stub definitions, so the stubs for `compose` and `docker` still win.

After the last `absent ... "${SETUP}"` line of the "no drive enumeration" and "transcode image variants" groups, add a loop so the same patterns stay absent from the library:

```bash
for f in "${LIB}"/*.sh; do
    for pat in 'lsscsi' 'ARM_DRIVE_SERIAL' 'arm-ripper-sr' 'detect_optical_drives' 'ID_PATH' 'probe_encoder_caps' '--probe-encoders' '--remove-orphans'; do
        absent "$(basename "${f}") has no ${pat}" "${pat}" "${f}"
    done
done
```

- [ ] **Step 8: Run the suite**

Run: `bash devtools/test-setup-dev.sh; echo rc=$?`
Expected: every line `ok`, `rc=0`.

- [ ] **Step 9: Compare against the baseline**

```bash
B="${TMPDIR:-/tmp}/arm-installer-baseline"
bash devtools/setup-dev.sh --help > "$B/help.after.txt" 2>&1
diff "$B/help.before.txt" "$B/help.after.txt" && echo HELP-IDENTICAL
bash devtools/setup-dev.sh setup > "$B/setup.after.txt" 2>&1; echo "rc=$?" >> "$B/setup.after.txt"
diff "$B/setup.before.txt" "$B/setup.after.txt" && echo SETUP-IDENTICAL
diff "$B/env.before" .env && echo ENV-IDENTICAL
diff "$B/compose.before.yml" docker-compose.yml && echo COMPOSE-IDENTICAL
shellcheck devtools/setup-dev.sh devtools/test-setup-dev.sh deploy/lib/*.sh
```

Expected: the four `*-IDENTICAL` lines print and shellcheck is silent. `arm/certs/arm-ca.crt` exists on this host, so the certificate step is skipped in both runs and the allowed differences do not show. If a diff appears, a substitution in Step 4 changed text; fix the library, not the baseline.

- [ ] **Step 10: Exercise the certificate path once in isolation**

```bash
T="$(mktemp -d)"
( ARM_CERTS_DIR="$T/certs"; source deploy/lib/common.sh; source deploy/lib/certs.sh
  ensure_ca && make_leaf arm-backend 192.168.0.68 && make_leaf arm-ui localhost
  openssl verify -CAfile "$T/certs/arm-ca.crt" "$T/certs/arm-backend.crt" "$T/certs/arm-ui.crt"
  openssl x509 -in "$T/certs/arm-backend.crt" -noout -ext subjectAltName | tail -n 1
  stat -c '%a' "$T/certs/arm-backend.key" )
rm -rf "$T"
```

Expected: two `OK` lines, `DNS:arm-backend, IP Address:192.168.0.68`, and `440`.

- [ ] **Step 11: Commit**

```bash
git add deploy/lib devtools/setup-dev.sh devtools/test-setup-dev.sh .dockerignore
git commit -m "refactor(deploy): move setup-dev's shared functions into deploy/lib

Host detection, the udev rule, lifecycle safety and certificate generation
now live in deploy/lib and print through caller-supplied output helpers.
setup-dev.sh loads them and no longer shells out to install.sh for certs.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Production output, NVIDIA and offload modules

The old `install.sh` stays in place and untouched until Task 8 replaces it. This task **copies** code out of it into `deploy/install/`, so line numbers below refer to `install.sh` as it is at the start of the branch.

**Files:**
- Create: `deploy/install/ui.sh`, `deploy/install/nvidia.sh`, `deploy/install/offload.sh`
- Modify: `devtools/test-install-walkthrough.sh`
- Test: `devtools/test-install-walkthrough.sh`

**Interfaces:**
- Consumes: `deploy/lib/common.sh` (`env_file_value`, `run_quiet`), `deploy/lib/detect.sh` (`nvenc_driver_ok`, `detect_gpus`, `detect_render_gid`, `ARM_NVENC_MIN_DRIVER`), `deploy/lib/certs.sh` (`ensure_ca`); settings `ARM_DIR`, `ENV_FILE`, `ARM_CERTS_DIR`.
- Produces:
  - `ui.sh`: `log`, `okline`, `failline`, `warnline`, `warn`, `err <text>` (exits 1), `section <n> <total> <title>`, `step <title>` (uses `STEP`, `STEP_TOTAL`), `fence_open <label>`, `fence_close`, `vercmp_ge <a> <b>`, `confirm <prompt>`, `prompt_valid <prompt> <validator> <hint>`, `consent <what> <prompt>`, globals `ARMCTL_ASSUME` (`ask`, `yes` or `no`) and `SKIPPED` (array).
  - `nvidia.sh`: `ensure_nvidia_container_toolkit`.
  - `offload.sh`: `setup_remote_offload` (sets `REMOTE_OFFLOAD`, `REMOTE_DOCKER_HOST`, `REMOTE_BACKEND_URL`, `REMOTE_TRANSCODE_PUID`, `REMOTE_TRANSCODE_PGID`, `REMOTE_BACKEND_SAN`, `REMOTE_GPUS`, `REMOTE_RENDER_GID`), `offload_persisted`, `offload_restore_persisted`, `offload_remote_run_init <endpoint> <key> <known_hosts>`, `offload_completion_report`, `offload_backend_port <url>`, `offload_certs_path <endpoint>`, `offload_image_ref <env file>`, `url_host <url>`; reads `OFFLOAD_HOST_ARG`, `OFFLOAD_URL_ARG`, `OFFLOAD_UIDGID_ARG`, `RAW_PATH`, `MEDIA_PATH`.

- [ ] **Step 1: Rewrite the head of `devtools/test-install-walkthrough.sh` and repoint its checks**

Replace everything from `HERE=` through `source "$INSTALL"` (the seam check included) with:

```bash
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
```

Delete the later `TMPROOT="$(mktemp -d)"` and its `trap` line (now set above). Update the file's header comment: replace `install.sh's remote-offload walkthrough machinery` with `the remote-offload walkthrough in deploy/install/offload.sh`, and `Sources install.sh via ARM_INSTALL_SOURCE_ONLY` with `Sources the deploy modules directly`.

Then apply these edits:

| Location | Change |
|---|---|
| The block from `# compose injection: run the awk-injection helper...` through the `check "injection idempotent" ...` line | delete (the overlay replaces injection; tested in Task 4) |
| The block from `# idempotence with a CHANGED port...` through `check "single ports key" ...` | delete |
| `check "table: callback PENDING wording" ...` | replace `re-run \`bash install.sh\`` with `re-run \`armctl install\`` |
| `CERTS_ONLY=0` followed by `PREFIX="$PERSISTDIR"` | replace both lines with `ARM_DIR="$PERSISTDIR"; ENV_FILE="$PERSISTDIR/.env"; ARM_CERTS_DIR="$PERSISTDIR/certs"` |
| `PREFIX="$PERSISTDIR"; CERTS_ONLY=0` | delete the line (the settings above still apply) |
| `PREFIX="$CADIR" ensure_ca` (two lines) | `ARM_CERTS_DIR="$CADIR/certs" ensure_ca` |
| `PREFIX="$TMPROOT/persist" OFFLOAD_ENV_FILE=...` (two lines) | replace `PREFIX="$TMPROOT/persist"` with `ARM_DIR="$TMPROOT/persist"` |
| `PREFIX="$LEAFDIR" ensure_ca` and `PREFIX="$LEAFDIR" ARM_PGID=... make_leaf` | replace `PREFIX="$LEAFDIR"` with `ARM_CERTS_DIR="$LEAFDIR/certs"` |

Add this block before the final `exit "$fail"`:

```bash
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
```

- [ ] **Step 2: Run it to see it fail**

Run: `bash devtools/test-install-walkthrough.sh; echo rc=$?`
Expected: fails at the `source` loop with `No such file or directory` for `install/ui.sh`.

- [ ] **Step 3: Create `deploy/install/ui.sh`**

```bash
#!/usr/bin/env bash
# deploy/install/ui.sh: production output style, prompts and consent.
# Sourced by deploy/armctl.sh; needs deploy/lib/common.sh loaded first.

# Output vocabulary: plain indented detail lines; marks only for verification
# results and warnings. Everything else is plain.
log()      { printf '  %s\n' "$*"; }
okline()   { printf '  ✓ %s\n' "$*"; }
failline() { printf '  ✗ %s\n' "$*"; }
warnline() { printf '  ! %s\n' "$*"; }
warn()     { printf 'WARN: %s\n' "$*" >&2; }
err()      { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

_RULE="────────────────────────────────────────────────────────────────────────"
section() {
    local n="$1" total="$2" title="$3" head
    head="── [${n}/${total}] ${title} "
    printf '\n%s%s\n' "$head" "${_RULE:0:$(( ${#_RULE} - ${#head} > 0 ? ${#_RULE} - ${#head} : 4 ))}"
}
# step <title>: the next numbered section of `armctl install`.
STEP=0
STEP_TOTAL=7
step() {
    STEP=$(( STEP + 1 ))
    section "${STEP}" "${STEP_TOTAL}" "$1"
}
fence_open() {
    local label="$1" head
    head="──── ${label} "
    printf '\n%s%s\n' "$head" "${_RULE:0:$(( ${#_RULE} - ${#head} > 0 ? ${#_RULE} - ${#head} : 4 ))}"
}
fence_close() { printf '%s\n\n' "$_RULE"; }

# vercmp_ge <a> <b>: true when version a >= version b.
vercmp_ge() {
    local lower
    lower="$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n 1)"
    [[ "$lower" = "$2" ]]
}

# confirm <prompt>: yes/no question. Without a terminal it reads one line from
# stdin (so tests and pipes can answer) and treats end-of-input as "no".
confirm() {
    local prompt="$1" reply
    if [[ ! -t 0 ]]; then
        read -r reply || reply="n"
    else
        read -rp "$prompt [y/N] " reply
    fi
    [[ "$reply" =~ ^[yY]([eE][sS])?$ ]]
}

# prompt_valid <prompt> <validator> <shape-hint>: loop until valid; echo value.
prompt_valid() {
    local prompt="$1" validator="$2" hint="$3" value
    while true; do
        read -rp "${prompt} (${hint}): " value
        if "$validator" "$value"; then
            printf '%s' "$value"
            return 0
        fi
        printf '    ! expected shape: %s   (you entered: %s)\n' "$hint" "$value" >&2
    done
}

# Host changes (Docker, NVIDIA toolkit, udev rule, a PATH link that needs sudo)
# go through consent. ARMCTL_ASSUME is `yes` (--yes), `no` (--no-host-changes)
# or `ask`. With `ask` and no terminal the step is declined, never left hanging.
# Every declined step is recorded in SKIPPED for the end-of-install summary.
ARMCTL_ASSUME="ask"
SKIPPED=()
consent() {  # consent <what, for the summary> <prompt>
    local what="$1" prompt="$2"
    case "${ARMCTL_ASSUME}" in
        yes) return 0 ;;
        no)  SKIPPED+=("${what} (declined by --no-host-changes)"); return 1 ;;
    esac
    if [[ ! -t 0 ]]; then
        SKIPPED+=("${what} (no terminal to ask on)")
        return 1
    fi
    if confirm "${prompt}"; then
        return 0
    fi
    SKIPPED+=("${what} (declined)")
    return 1
}
```

- [ ] **Step 4: Create `deploy/install/nvidia.sh`**

```bash
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
```

- [ ] **Step 5: Create `deploy/install/offload.sh` from `install.sh`**

Start the file with:

```bash
#!/usr/bin/env bash
# deploy/install/offload.sh: the remote transcode offload walkthrough.
# Sourced by deploy/armctl.sh. Needs deploy/lib/{common,detect,certs}.sh and
# deploy/install/ui.sh loaded first. Reads ARM_DIR, ENV_FILE, ARM_CERTS_DIR.

# Defaults for the image reference; deploy/install/config.sh sets the real ones.
: "${ARM_IMAGE_PREFIX_DEFAULT:=docker.io/automaticrippingmachine}"
: "${ARM_IMAGE_TAG_DEFAULT:=}"
```

Then copy, in order, with their comment blocks:

1. From `install.sh`: `url_host`, `offload_image_ref`, and the "offload input validation" section (`is_ugid`, `valid_ssh_endpoint`, `endpoint_user`, `endpoint_host`, `endpoint_port`, `valid_https_url`, `url_port`, `offload_backend_port`, `offload_certs_path`). Do **not** copy `prompt_valid` (it is in `ui.sh`).
2. From `install.sh`: everything from the comment above `remote_detect_gpus` through the end of `setup_remote_offload` (lines 613 to 1057). This skips the installer's own `nvenc_driver_ok`, `probe_encoder_caps`, `detect_gpus` and `detect_render_gid`, which are replaced by `deploy/lib/detect.sh`.

Then make these changes in the new file:

**a. Paths.** Replace every `$PREFIX/.env` with `${ENV_FILE}`, every `$PREFIX/ssh` with `${ARM_DIR}/ssh`, and every `$PREFIX/certs` with `${ARM_CERTS_DIR}`. Check:

```bash
grep -n 'PREFIX' deploy/install/offload.sh | grep -v 'ARM_IMAGE_PREFIX'
```

Expected: no output.

**b. `remote_detect_gpus`.** Replace the comment above it and its whole body with:

```bash
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
```

**c. The head of `setup_remote_offload`.** Replace everything from the function's opening line through the line `REMOTE_BACKEND_SAN="$(url_host "$REMOTE_BACKEND_URL")"` with:

```bash
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
    REMOTE_TRANSCODE_PUID="${uidgid%%:*}"
    REMOTE_TRANSCODE_PGID="${uidgid##*:}"
    REMOTE_BACKEND_SAN="$(url_host "$REMOTE_BACKEND_URL")"
```

The rest of the function (key generation and the four verify steps) stays as copied.

**d. Data paths.** In `setup_remote_offload`, the three lines that read `raw_p`, `media_p` and `logs_p` with `sed` become:

```bash
    raw_p="${RAW_PATH:-$(env_file_value ARM_HOST_RAW_PATH)}"
    media_p="${MEDIA_PATH:-$(env_file_value ARM_HOST_MEDIA_PATH)}"
    logs_p="${ARM_DIR}/logs"
```

On a fresh install `.env` does not exist yet when the walkthrough runs; `RAW_PATH` and `MEDIA_PATH` are the storage answers the install flow collected just before (Task 7).

**e. Completion table wording.** In `offload_completion_report`, replace the string `` '`docker compose up -d`, re-run `bash install.sh`' `` with `` '`armctl up`, then re-run `armctl install`' ``.

- [ ] **Step 6: Run the suite**

Run: `bash devtools/test-install-walkthrough.sh; echo rc=$?` then `shellcheck deploy/install/*.sh devtools/test-install-walkthrough.sh`
Expected: every line `ok`, `rc=0`; shellcheck silent. If shellcheck reports functions in `offload.sh` as unused or variables as unassigned, they are consumed by other modules: add `# shellcheck disable=SC2034` on the specific line, not file-wide.

- [ ] **Step 7: Commit**

```bash
git add deploy/install/ui.sh deploy/install/nvidia.sh deploy/install/offload.sh devtools/test-install-walkthrough.sh
git commit -m "feat(deploy): production output, NVIDIA and offload modules

Copies the installer's output vocabulary, NVIDIA toolkit offer and remote
offload walkthrough into deploy/install. Remote GPU detection now ships the
shared detect.sh functions, offload inputs can come from flags, and host
changes go through one consent helper that never blocks without a terminal.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: `armctl` core: settings, `up`, `down`, `compose`

**Files:**
- Create: `deploy/armctl.sh`, `deploy/tests/test-armctl.sh`
- Test: `deploy/tests/test-armctl.sh`

**Interfaces:**
- Consumes: all of `deploy/lib/`, `deploy/install/ui.sh`.
- Produces:
  - Globals: `ARMCTL_RELEASE_DIR` (folder holding `armctl.sh`), `ARM_PARENT_DIR`, `ARM_STATE_DIR` (`${ARM_DIR}/.armctl`), `HOST_OVERLAY` (`${ARM_STATE_DIR}/host-overlay.yml`), `ARMCTL_CMD` (how the user should invoke armctl, default `${ARM_DIR}/armctl`), `ARMCTL_ARGV` (array, the original arguments), `PROFILE`, `NO_PULL`.
  - Functions: `armctl_settings`, `use_env_file <path>` (sets `ENV_FILE` and rebuilds `ARM_COMPOSE_CMD`), `refuse_root`, `current_uid`, `acquire_lock`, `require_installed`, `load_profile`, `require_docker_ready`, `stack_services`, `pull_images`, `verify_images_present`, `stack_up`, `go_live`, `finish_up`, `cmd_up`, `cmd_down`, `armctl_main`.
  - Test seam: sourcing with `ARMCTL_SOURCE_ONLY=1` defines everything and runs nothing.

- [ ] **Step 1: Write the failing suite, `deploy/tests/test-armctl.sh`**

```bash
#!/usr/bin/env bash
# shellcheck disable=SC2317,SC2329,SC2034,SC2030,SC2031
# (Stubs below are called indirectly by sourced armctl code, and most checks
# run in subshells on purpose so one check's stubs cannot leak into the next.)
# Zero-infra suite for deploy/armctl.sh and deploy/install/*: no docker, no
# root, no network. Sources armctl.sh through its ARMCTL_SOURCE_ONLY seam.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${HERE}/.."

export ARMCTL_SOURCE_ONLY=1
# shellcheck disable=SC1091
source "${DEPLOY}/armctl.sh"

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
has() {  # has <label> <needle> <haystack>
    check "$1" "yes" "$( [[ "$3" == *"$2"* ]] && echo yes || echo no )"
}
lacks() {  # lacks <label> <needle> <haystack>
    check "$1" "no" "$( [[ "$3" == *"$2"* ]] && echo yes || echo no )"
}

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

# new_install <name>: a throwaway arm folder with settings loaded.
new_install() {
    ARM_DIR="${TMPROOT}/$1/arm"
    mkdir -p "${ARM_DIR}/.armctl"
    armctl_settings
    printf 'ARMCTL_PROFILE=full\n' > "${ENV_FILE}"
}

# --- output style -------------------------------------------------------------
check "arm_say: two-space indent" "  hello" "$(arm_say hello)"
check "arm_sub: re-indents the line it is given" "      detail" "$(arm_sub '         detail')"
check "arm_warn: bang, on stderr" "  ! careful" "$(arm_warn careful 2>&1 >/dev/null)"
check "arm_err: ERROR, on stderr" "ERROR: broken" "$(arm_err broken 2>&1 >/dev/null)"

# --- root refusal ---------------------------------------------------------------
out="$( (current_uid() { echo 0; }; refuse_root) 2>&1 || true)"
has "root is refused with the reason" "do not run armctl as root" "$out"
rc=0; (current_uid() { echo 0; }; refuse_root) >/dev/null 2>&1 || rc=$?
check "root refusal exits 1" "1" "$rc"
rc=0; (current_uid() { echo 1000; }; refuse_root) >/dev/null 2>&1 || rc=$?
check "a normal user passes" "0" "$rc"

# --- settings -------------------------------------------------------------------
out="$( (unset ARM_DIR; armctl_settings) 2>&1 || true)"
has "missing ARM_DIR is explained" "ARM_DIR is not set" "$out"
out="$( (ARM_DIR="${TMPROOT}/ripper"; armctl_settings) 2>&1 || true)"
has "a folder not named arm is rejected" "must be named 'arm'" "$out"
new_install settings
check "state dir is under the arm folder" "${ARM_DIR}/.armctl" "${ARM_STATE_DIR}"
check "env file is in the state dir" "${ARM_DIR}/.armctl/.env" "${ENV_FILE}"
check "compose runs from the parent of arm" "${TMPROOT}/settings" "${ARM_COMPOSE_CWD}"
has "compose is told the project directory" "--project-directory ${TMPROOT}/settings" "${ARM_COMPOSE_CMD[*]}"
has "compose reads the template" "-f ${ARMCTL_RELEASE_DIR}/docker-compose.yml.example" "${ARM_COMPOSE_CMD[*]}"
has "compose reads the release overlay" "-f ${ARMCTL_RELEASE_DIR}/docker-compose.release.yml" "${ARM_COMPOSE_CMD[*]}"
joined="${ARM_COMPOSE_CMD[*]}"
has "compose reads the host overlay last" "-f ${ARM_DIR}/.armctl/host-overlay.yml" "${joined##*release.yml}"
use_env_file "${ARM_STATE_DIR}/.env.next"
has "use_env_file switches the env file compose reads" "--env-file ${ARM_STATE_DIR}/.env.next" "${ARM_COMPOSE_CMD[*]}"

# --- profile --------------------------------------------------------------------
new_install profile
printf 'ARMCTL_PROFILE=ripper-only\n' > "${ENV_FILE}"; load_profile
check "ripper-only profile sets RIPPER_ONLY" "1" "${RIPPER_ONLY}"
printf 'ARMCTL_PROFILE=full\n' > "${ENV_FILE}"; load_profile
check "full profile clears RIPPER_ONLY" "0" "${RIPPER_ONLY}"
: > "${ENV_FILE}"; load_profile
check "no saved profile means full" "full" "${PROFILE}"
out="$( (rm -f "${ENV_FILE}"; require_installed) 2>&1 || true)"
has "commands before install say what to run" "armctl install" "$out"

# --- images must be present after the pull (Review Focus 4) ---------------------
# compose tolerates a failed pull for a service that has a build section, so
# armctl checks for itself before it touches the running stack.
images() {  # images <image that is missing, or empty>
    (
        new_install images
        missing_image="$1"
        compose() {
            case "$*" in
                "config --services") printf '%s\n' arm-db arm-backend ;;
                config) printf 'name: armv3\nservices:\n  arm-backend:\n    build:\n      context: /x\n    image: reg/arm-backend:v3.1.0\n  arm-db:\n    image: postgres:18\nvolumes:\n  arm-data: {}\n' ;;
            esac
        }
        docker() { [[ "$1 $2" == "image inspect" && "$3" != "${missing_image}" ]]; }
        UP_SERVICES=()
        verify_images_present
    )
}
rc=0; images "" >/dev/null 2>&1 || rc=$?
check "all images present: passes" "0" "$rc"
rc=0; out="$(images "reg/arm-backend:v3.1.0" 2>&1)" || rc=$?
check "a missing image stops the run" "1" "$rc"
has "the missing image is named" "arm-backend (reg/arm-backend:v3.1.0)" "$out"
has "the user is told nothing changed" "Nothing has been changed" "$out"

# --- up and down ordering ---------------------------------------------------------
STEPS=(select_up_services pull_images verify_images_present guard_running_spawned refresh_arm_gpus backup_db remove_spawned_containers remove_retired_services respawn_rippers_if_needed wait_for_backend)
# run_cmd <install name> <FAIL_AT step or ''> <command> [args...]: run an
# armctl command with every step replaced by a recorder; print the order.
run_cmd() {
    (
        new_install "$1"; fail_at="$2"; shift 2
        log_file="${TMPROOT}/steps.log"; : > "${log_file}"
        for fn in "${STEPS[@]}"; do
            eval "${fn}() { echo ${fn} >> \"\${log_file}\"; if [[ \"\${fail_at}\" == ${fn} ]]; then exit 1; fi; }"
        done
        backend_started_at() { echo T1; }
        published_url() { :; }
        compose() { echo "compose $*" >> "${log_file}"; }
        HEALTH_RESULT="backend healthy"
        UP_SERVICES=()
        # A failing step calls `exit`, so run the command one subshell down and
        # record the flags from its EXIT trap.
        (
            trap 'echo "FORCE=${FORCE} NO_BACKUP=${NO_BACKUP}" >> "${log_file}"' EXIT
            "$@"
        ) >/dev/null 2>&1 || true
        tr '\n' ';' < "${log_file}"
    )
}
check "up: pull and verify come before anything changes" \
    "select_up_services;pull_images;verify_images_present;guard_running_spawned;refresh_arm_gpus;backup_db;remove_spawned_containers;remove_retired_services;compose up -d --no-build;respawn_rippers_if_needed;wait_for_backend;FORCE=0 NO_BACKUP=0;" \
    "$(run_cmd up-ok '' cmd_up)"
check "up: a missing image stops before the guard, backup and removal" \
    "select_up_services;pull_images;verify_images_present;FORCE=0 NO_BACKUP=0;" \
    "$(run_cmd up-noimg verify_images_present cmd_up)"
check "up: active work stops before the backup and removal" \
    "select_up_services;pull_images;verify_images_present;guard_running_spawned;FORCE=0 NO_BACKUP=0;" \
    "$(run_cmd up-busy guard_running_spawned cmd_up)"
has "up: --force and --no-backup reach the library" "FORCE=1 NO_BACKUP=1;" "$(run_cmd up-flags '' cmd_up --force --no-backup)"
check "down: guard, then spawned containers, then the stack" \
    "guard_running_spawned;remove_spawned_containers;remove_retired_services;compose down;FORCE=0 NO_BACKUP=0;" \
    "$(run_cmd down-ok '' cmd_down)"
check "down: active work stops before anything is removed" \
    "guard_running_spawned;FORCE=0 NO_BACKUP=0;" \
    "$(run_cmd down-busy guard_running_spawned cmd_down)"
has "down: --force reaches the guard" "FORCE=1" "$(run_cmd down-force '' cmd_down --force)"
out="$( (new_install hints; guard_running_spawned() { echo "${ARM_HINT_FORCE_CMD}"; }; remove_spawned_containers() { :; }; remove_retired_services() { :; }; compose() { :; }; cmd_down) 2>&1)"
has "down: the refusal names armctl down --force" "armctl down --force" "$out"

# --- lock -------------------------------------------------------------------------
if command -v flock >/dev/null 2>&1; then
    out="$( (new_install lock; acquire_lock; (unset ARMCTL_LOCK_HELD; acquire_lock) 2>&1 || true) )"
    has "a second armctl run is refused" "another armctl command is already running" "$out"
    rc=0; (new_install lock2; acquire_lock; acquire_lock) >/dev/null 2>&1 || rc=$?
    check "the lock holder can re-enter" "0" "$rc"
else
    echo "skip - flock not available"
fi

# --- dispatch -----------------------------------------------------------------------
rc=0; (ARM_DIR="${TMPROOT}/settings/arm"; current_uid() { echo 1000; }; armctl_main frobnicate) >/dev/null 2>&1 || rc=$?
check "an unknown command exits 2" "2" "$rc"
has "help lists the commands" "upgrade" "$(armctl_main help)"

exit "$fail"
```

- [ ] **Step 2: Run it to see it fail**

Run: `bash deploy/tests/test-armctl.sh; echo rc=$?`
Expected: fails at `source` with `deploy/armctl.sh: No such file or directory`.

- [ ] **Step 3: Create `deploy/armctl.sh`**

```bash
#!/usr/bin/env bash
# shellcheck disable=SC2034 # the settings assigned here are read by the sourced library and modules
# deploy/armctl.sh: the production launcher for ARM v3.
#
# Lives inside a release bundle at <arm>/.armctl/releases/<tag>/armctl.sh and
# is reached through the generated launcher <arm>/armctl, which exports ARM_DIR.
# The lifecycle functions it calls are the ones devtools/setup-dev.sh uses
# (deploy/lib/). See docs/developers/architecture/06-deployment.md.
set -euo pipefail

ARMCTL_RELEASE_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

armctl_usage() {
    cat <<'USAGE'
Usage: armctl <command> [options]

  install            configure this host and start ARM (re-run to change answers)
  up                 pull images, back up the database, (re)start the stack
  down               stop the stack and the rippers/transcoders it spawned
  upgrade            move to the latest stable release (or --version <tag>)
  compose <args...>  run any `docker compose` command against this install

  up and upgrade:
    --force          go ahead even while a rip or transcode is running (kills it)
    --no-backup      skip the database backup
  down:
    --force          stop even while a rip or transcode is running (kills it)

  `armctl install --help` lists the install options.
USAGE
}

for _lib in common detect certs udev lifecycle; do
    # shellcheck source=/dev/null
    source "${ARMCTL_RELEASE_DIR}/lib/${_lib}.sh"
done
# shellcheck disable=SC2043 # one module for now; later tasks extend this list
for _mod in ui; do
    # shellcheck source=/dev/null
    source "${ARMCTL_RELEASE_DIR}/install/${_mod}.sh"
done
unset _lib _mod

# Production output style. These replace the setup-dev defaults that
# lib/common.sh defines; the shared lifecycle functions print through them.
arm_say()  { printf '  %s\n' "$*"; }
# The library passes continuation lines with setup-dev's indentation; strip it
# and apply this style's.
arm_sub()  { local line="$1"; line="${line#"${line%%[![:space:]]*}"}"; printf '      %s\n' "${line}"; }
arm_warn() { printf '  ! %s\n' "$*" >&2; }
arm_err()  { printf 'ERROR: %s\n' "$*" >&2; }

current_uid() { id -u; }

# ARM records the installing user as the owner of the media files (PUID/PGID),
# and arm-data-init refuses PUID 0, so a root run can only produce a broken
# install.
refuse_root() {
    if [[ "$(current_uid)" -eq 0 ]]; then
        arm_err "do not run armctl as root or with sudo."
        arm_sub "ARM records the user who runs it as the owner of your media files, and root is not accepted."
        arm_sub "Run it as your normal user; it asks for sudo only when a step needs it."
        exit 1
    fi
}

# use_env_file <path>: the .env the stack is configured from. An upgrade points
# this at a candidate file until it switches over.
use_env_file() {
    ENV_FILE="$1"
    ARM_COMPOSE_CMD=(docker compose
        --project-directory "${ARM_PARENT_DIR}"
        --env-file "${ENV_FILE}"
        -f "${ARMCTL_RELEASE_DIR}/docker-compose.yml.example"
        -f "${ARMCTL_RELEASE_DIR}/docker-compose.release.yml"
        -f "${HOST_OVERLAY}")
}

# The compose template writes its paths as ./arm/..., so compose runs from the
# folder that CONTAINS arm, and that folder must be named arm.
armctl_settings() {
    if [[ -z "${ARM_DIR:-}" ]]; then
        arm_err "ARM_DIR is not set. Run armctl through the launcher in your arm folder (for example ~/arm/armctl)."
        exit 1
    fi
    if [[ "$(basename "${ARM_DIR}")" != "arm" ]]; then
        arm_err "the install folder must be named 'arm' (got ${ARM_DIR})."
        exit 1
    fi
    ARM_PARENT_DIR="$(dirname "${ARM_DIR}")"
    ARM_STATE_DIR="${ARM_DIR}/.armctl"
    HOST_OVERLAY="${ARM_STATE_DIR}/host-overlay.yml"
    ARM_CERTS_DIR="${ARM_DIR}/certs"
    ARM_COMPOSE_CWD="${ARM_PARENT_DIR}"
    DB_SERVICE="arm-db"
    BACKEND_SERVICE="arm-backend"
    UI_SERVICE="arm-ui"
    RIPPER_ONLY=0
    FORCE=0
    NO_BACKUP=0
    NO_PULL=0
    PROFILE="full"
    ARMCTL_CMD="${ARMCTL_CMD:-${ARM_DIR}/armctl}"
    ARM_HINT_FORCE_CMD="${ARMCTL_CMD} up --force"
    ARM_HINT_IMAGES_READY="Images are pulled"
    ARM_HINT_LOGS_CMD="${ARMCTL_CMD} compose logs"
    ARM_HINT_RIPPER_ONLY="ripper-only profile"
    ARM_UDEV_MANAGED_BY="armctl (the ARM installer)"
    use_env_file "${ARM_STATE_DIR}/.env"
}

# One armctl command at a time per install. An upgrade hands the lock to the
# new release's armctl through ARMCTL_LOCK_HELD.
acquire_lock() {
    if [[ -n "${ARMCTL_LOCK_HELD:-}" ]]; then
        return 0
    fi
    mkdir -p "${ARM_STATE_DIR}"
    if ! command -v flock >/dev/null 2>&1; then
        arm_warn "flock not found; cannot guard against two armctl commands running at once"
        return 0
    fi
    exec 9>"${ARM_STATE_DIR}/lock"
    if ! flock -n 9; then
        arm_err "another armctl command is already running for ${ARM_DIR}. Wait for it to finish."
        exit 1
    fi
    export ARMCTL_LOCK_HELD=1
}

require_installed() {
    if [[ ! -f "${ENV_FILE}" ]]; then
        arm_err "no install found in ${ARM_DIR} (missing ${ENV_FILE}). Run: ${ARMCTL_CMD} install"
        exit 1
    fi
}

load_profile() {
    PROFILE="$(env_file_value ARMCTL_PROFILE)"
    PROFILE="${PROFILE:-full}"
    RIPPER_ONLY=0
    if [[ "${PROFILE}" == "ripper-only" ]]; then
        RIPPER_ONLY=1
    fi
}

require_docker_ready() {
    require docker "Install Docker first: https://docs.docker.com/engine/install/"
    require_compose
}

# The services this host pulls and starts, one per line. select_up_services
# leaves UP_SERVICES empty when nothing is skipped.
stack_services() {
    if [[ ${#UP_SERVICES[@]} -gt 0 ]]; then
        printf '%s\n' "${UP_SERVICES[@]}"
    else
        compose config --services
    fi
}

pull_images() {
    if [[ "${NO_PULL}" -eq 1 ]]; then
        arm_say "skipping the image pull (--no-pull)"
        return 0
    fi
    local rc=0
    if [[ ${#UP_SERVICES[@]} -gt 0 ]]; then
        arm_say "pulling images: ${UP_SERVICES[*]}"
        compose pull "${UP_SERVICES[@]}" || rc=$?
    else
        arm_say "pulling images"
        compose pull || rc=$?
    fi
    if [[ "${rc}" -ne 0 ]]; then
        arm_err "the image pull failed."
        arm_sub "Nothing has been changed; the running stack is untouched."
        exit 1
    fi
}

# compose reports success for a pull that could not fetch an image when the
# service also has a build section (the dev template's services all do). So
# check that every image this host needs is really here before the guard, the
# backup or any removal.
verify_images_present() {
    local cfg svc img missing=()
    cfg="$(compose config)"
    while IFS= read -r svc; do
        [[ -n "${svc}" ]] || continue
        img="$(awk -v s="  ${svc}:" '$0 == s {f=1; next} f && /^  [a-z]/ {exit} f && /^    image:/ {print $2; exit}' <<<"${cfg}")"
        if [[ -z "${img}" ]]; then
            missing+=("${svc} (no release image is set for it)")
        elif ! docker image inspect "${img}" >/dev/null 2>&1; then
            missing+=("${svc} (${img})")
        fi
    done < <(stack_services)
    if [[ ${#missing[@]} -eq 0 ]]; then
        return 0
    fi
    arm_err "these images are not on this host after the pull:"
    for svc in "${missing[@]}"; do
        arm_sub "${svc}"
    done
    arm_sub "Nothing has been changed; the running stack is untouched."
    arm_sub "Check the network and ARM_IMAGE_TAG in ${ENV_FILE}, then run the command again."
    exit 1
}

# Remove what the backend spawned, start from the pulled images, and bring the
# rippers back. Everything before this point leaves the running stack alone.
go_live() {
    local started_before
    started_before="$(backend_started_at)"
    remove_spawned_containers
    remove_retired_services
    arm_say "starting the stack"
    if [[ ${#UP_SERVICES[@]} -gt 0 ]]; then
        compose up -d --no-build "${UP_SERVICES[@]}"
    else
        compose up -d --no-build
    fi
    respawn_rippers_if_needed "${started_before}"
}

# Same order as devtools/setup-dev.sh `up`, with a pull in place of the build.
stack_up() {
    select_up_services
    pull_images
    verify_images_present
    guard_running_spawned
    refresh_arm_gpus
    backup_db
    go_live
}

finish_up() {
    local ui_url
    wait_for_backend
    ui_url="$(published_url "${UI_SERVICE}" 443)"
    ui_url="${ui_url:-https://localhost:8081}"
    arm_say "stack is up; ${HEALTH_RESULT}"
    arm_say "open ${ui_url}"
}

cmd_up() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force)     FORCE=1 ;;
            --no-backup) NO_BACKUP=1 ;;
            --no-pull)   NO_PULL=1 ;;
            *) arm_err "unknown option for up: $1"; exit 2 ;;
        esac
        shift
    done
    require_installed
    load_profile
    ARM_HINT_FORCE_CMD="${ARMCTL_CMD} up --force"
    ARM_HINT_IMAGES_READY="Images are pulled"
    stack_up
    finish_up
}

cmd_down() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force) FORCE=1 ;;
            *) arm_err "unknown option for down: $1"; exit 2 ;;
        esac
        shift
    done
    require_installed
    ARM_HINT_FORCE_CMD="${ARMCTL_CMD} down --force"
    ARM_HINT_IMAGES_READY="The stack is still running"
    guard_running_spawned
    remove_spawned_containers
    remove_retired_services
    arm_say "stopping the stack"
    compose down
}

armctl_main() {
    local cmd="${1:-help}"
    if [[ $# -gt 0 ]]; then
        shift
    fi
    case "${cmd}" in
        -h|--help|help) armctl_usage; return 0 ;;
    esac
    refuse_root
    armctl_settings
    ARMCTL_ARGV=("${cmd}" "$@")
    case "${cmd}" in
        up)      require_docker_ready; acquire_lock; cmd_up "$@" ;;
        down)    require_docker_ready; acquire_lock; cmd_down "$@" ;;
        compose) require_docker_ready; require_installed; compose "$@" ;;
        *)       arm_err "unknown command: ${cmd}"; armctl_usage >&2; exit 2 ;;
    esac
}

# Test seam: lets deploy/tests/test-armctl.sh source the functions above
# without running a command. The sourced-ness check makes a leaked env var
# harmless when the script is executed.
[[ -n "${ARMCTL_SOURCE_ONLY:-}" && "${BASH_SOURCE[0]}" != "$0" ]] && return 0

armctl_main "$@"
```

Make it executable: `chmod 755 deploy/armctl.sh`.

- [ ] **Step 4: Run the suite**

Run: `bash deploy/tests/test-armctl.sh; echo rc=$?` then `shellcheck deploy/armctl.sh deploy/tests/test-armctl.sh`
Expected: every line `ok` (or the one `skip` when `flock` is absent), `rc=0`; shellcheck silent.

- [ ] **Step 5: Commit**

```bash
git add deploy/armctl.sh deploy/tests/test-armctl.sh
git commit -m "feat(deploy): armctl launcher with up, down and compose

Runs the unchanged compose template from the folder that contains arm,
with the same lifecycle order as setup-dev up (pull in place of build).
Checks every image is present after the pull, guards down against active
work, refuses root and takes a per-install lock.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Configuration: profile, storage, `.env`, image pins, host overlay

**Files:**
- Create: `deploy/install/config.sh`
- Modify: `deploy/armctl.sh` (module list), `deploy/tests/test-armctl.sh`
- Test: `deploy/tests/test-armctl.sh`

**Interfaces:**
- Consumes: `env_set`, `env_unset`, `env_file_value`, `detect_cdrom_gid`, `detect_render_gid`, `refresh_arm_gpus` (lib); `log`, `okline`, `err` (ui); `offload_backend_port`, `offload_certs_path` and the `REMOTE_*` variables (offload); `ARMCTL_RELEASE_DIR`, `ARM_DIR`, `ENV_FILE`, `HOST_OVERLAY`.
- Produces:
  - Globals: `ARM_IMAGE_PREFIX_DEFAULT`, `ARM_IMAGE_TAG_DEFAULT` (the tag to pin; the install flow sets it), flag inputs `PROFILE_ARG`, `RAW_ARG`, `MEDIA_ARG`, `IMAGE_PREFIX_ARG`, answers `PROFILE`, `RAW_PATH`, `MEDIA_PATH`.
  - Functions: `choose_profile` (sets `PROFILE`, `RIPPER_ONLY`), `valid_storage_path <path>`, `pick_storage <label> <flag value> <env key> <default>` (prints the path), `prepare_storage <dir>`, `choose_storage` (sets `RAW_PATH`, `MEDIA_PATH`), `env_merge_new_keys <example> <env>`, `write_image_pins <tag> [env file]`, `write_env`, `write_host_overlay`.

- [ ] **Step 1: Add the failing checks to `deploy/tests/test-armctl.sh`**

Insert before the `# --- dispatch ---` section:

```bash
# --- config: storage paths --------------------------------------------------------
for p in "/mnt/nas/raw" "/media/sam/My Passport/rips"; do
    rc=0; valid_storage_path "$p" || rc=$?
    check "storage path accepted: ${p}" "0" "$rc"
done
for p in "relative/path" "/a:b" '/a"b' '/a$b' "/a#b" '/a\b' "/a'b"; do
    rc=0; valid_storage_path "$p" || rc=$?
    check "storage path rejected: ${p}" "1" "$rc"
done
new_install storage
check "storage: a flag wins" "/srv/rips" \
    "$(pick_storage "raw rips" "/srv/rips" ARM_HOST_RAW_PATH "${ARM_DIR}/raw" </dev/null)"
check "storage: no terminal takes the default" "${ARM_DIR}/raw" \
    "$(pick_storage "raw rips" "" ARM_HOST_RAW_PATH "${ARM_DIR}/raw" </dev/null)"
printf 'ARM_HOST_RAW_PATH=/mnt/saved\n' > "${ENV_FILE}"
check "storage: a saved answer becomes the default" "/mnt/saved" \
    "$(pick_storage "raw rips" "" ARM_HOST_RAW_PATH "${ARM_DIR}/raw" </dev/null)"
# shellcheck disable=SC2016 # the literal ${PWD} is what .env.example ships
printf 'ARM_HOST_RAW_PATH=${PWD}/arm/raw\n' > "${ENV_FILE}"
check "storage: the template's \${PWD} placeholder is not a saved answer" "${ARM_DIR}/raw" \
    "$(pick_storage "raw rips" "" ARM_HOST_RAW_PATH "${ARM_DIR}/raw" </dev/null)"
out="$( (pick_storage "raw rips" "not/absolute" ARM_HOST_RAW_PATH /x </dev/null) 2>&1 || true)"
has "storage: a bad flag value is rejected" "must be a full path" "$out"
( prepare_storage "${ARM_DIR}/raw" )
check "storage: a folder inside arm is created setgid, group-writable" "2775" "$(stat -c '%a' "${ARM_DIR}/raw")"
ro="${TMPROOT}/readonly"; mkdir -p "$ro"; chmod 555 "$ro"
out="$( (prepare_storage "$ro") 2>&1 || true)"
has "storage: an unwritable folder is an error" "is not writable" "$out"
check "storage: a folder outside arm keeps its mode" "555" "$(stat -c '%a' "$ro")"

# --- config: profile ---------------------------------------------------------------
new_install profile-choice; : > "${ENV_FILE}"
check "profile: a flag wins" "ripper-only" "$( (PROFILE_ARG=ripper-only; choose_profile >/dev/null </dev/null; echo "${PROFILE}") )"
check "profile: ripper-only sets RIPPER_ONLY" "1" "$( (PROFILE_ARG=ripper-only; choose_profile >/dev/null </dev/null; echo "${RIPPER_ONLY}") )"
check "profile: no terminal defaults to full" "full" "$( (PROFILE_ARG=""; choose_profile >/dev/null </dev/null; echo "${PROFILE}") )"
printf 'ARMCTL_PROFILE=offload\n' > "${ENV_FILE}"
check "profile: no terminal keeps the saved profile" "offload" "$( (PROFILE_ARG=""; choose_profile >/dev/null </dev/null; echo "${PROFILE}") )"
out="$( (PROFILE_ARG=everything; choose_profile </dev/null) 2>&1 || true)"
has "profile: an unknown profile is rejected" "must be full, ripper-only or offload" "$out"

# --- config: host overlay (Review Focus 1: a path with spaces) ----------------------
new_install overlay
PROFILE=full; RAW_PATH="/media/sam/My Passport/rips"; MEDIA_PATH="/mnt/nas/media"; write_host_overlay
ov="$(cat "${HOST_OVERLAY}")"
has "overlay quotes a path with spaces" '      - "/media/sam/My Passport/rips:/raw"' "$ov"
has "overlay mounts the media folder" '      - "/mnt/nas/media:/media"' "$ov"
lacks "overlay: no published port without offload" "ports:" "$ov"
PROFILE=offload; REMOTE_BACKEND_URL="https://192.168.0.68:8080"; write_host_overlay
ov="$(cat "${HOST_OVERLAY}")"
has "overlay: offload publishes the callback port" '      - "8080:8443"' "$ov"
has "overlay: offload mounts the ssh folder read-only" "      - \"${ARM_DIR}/ssh:/home/arm/.ssh:ro\"" "$ov"
check "overlay: one ports key after a re-run" "1" "$(grep -c '^    ports:$' "${HOST_OVERLAY}")"

# --- config: .env -------------------------------------------------------------------
REL="${TMPROOT}/rel"; mkdir -p "${REL}"; cp "${DEPLOY}/../.env.example" "${REL}/.env.example"
# env_case <install name> <profile> [keep]: run write_env; print the .env.
# `keep` re-runs on the existing .env instead of starting fresh.
env_case() {
    (
        # Not new_install: that would overwrite the .env a `keep` run re-uses.
        ARM_DIR="${TMPROOT}/$1/arm"; mkdir -p "${ARM_DIR}/.armctl"; armctl_settings
        if [[ "${3:-}" != keep ]]; then rm -f "${ENV_FILE}"; fi
        ARMCTL_RELEASE_DIR="${REL}"
        PROFILE="$2"; RIPPER_ONLY=0
        if [[ "$2" == ripper-only ]]; then RIPPER_ONLY=1; fi
        RAW_PATH="/r"; MEDIA_PATH="/m"; ARM_IMAGE_TAG_DEFAULT="v3.1.0"; IMAGE_PREFIX_ARG=""
        REMOTE_DOCKER_HOST="ssh://sam@192.168.0.92"; REMOTE_BACKEND_URL="https://192.168.0.68:8080"
        REMOTE_TRANSCODE_PUID=1001; REMOTE_TRANSCODE_PGID=1000
        REMOTE_GPUS='[{"vendor":"nvenc","device_path":"nvidia://0","encoder_kinds":[]}]'; REMOTE_RENDER_GID=""
        detect_gpus() { printf '[]'; }
        detect_render_gid() { echo 993; }
        detect_cdrom_gid() { printf 24; }
        DETECTED_GPUS_SET=0
        write_env >/dev/null
        cat "${ENV_FILE}"
        stat -c 'MODE=%a' "${ENV_FILE}"
    )
}
e="$(env_case env-full full)"
lacks "env: placeholders are replaced by generated secrets" "change-me" "$e"
has "env: readable by the owner only" "MODE=600" "$e"
has "env: profile is recorded" "ARMCTL_PROFILE=full" "$e"
has "env: full box is transcode-capable" "ARM_TRANSCODE_CAPABLE=true" "$e"
has "env: raw path is absolute" "ARM_HOST_RAW_PATH=/r" "$e"
has "env: logs path is absolute" "ARM_HOST_LOGS_PATH=${TMPROOT}/env-full/arm/logs" "$e"
has "env: certs path is the local folder" "ARM_HOST_CERTS_PATH=${TMPROOT}/env-full/arm/certs" "$e"
lacks "env: no \${PWD} paths remain" 'ARM_HOST_RAW_PATH=${PWD}' "$e"
has "env: release tag is pinned" "ARM_IMAGE_TAG=v3.1.0" "$e"
has "env: ripper image is pinned" "ARM_RIPPER_IMAGE=docker.io/automaticrippingmachine/arm-ripper:v3.1.0" "$e"
has "env: base transcode image is pinned" "ARM_TRANSCODE_IMAGE=docker.io/automaticrippingmachine/arm-transcode:v3.1.0" "$e"
has "env: intel variant is pinned" "ARM_TRANSCODE_IMAGE_QSV=docker.io/automaticrippingmachine/arm-transcode:v3.1.0-intel" "$e"
has "env: amd variant is pinned" "ARM_TRANSCODE_IMAGE_VAAPI=docker.io/automaticrippingmachine/arm-transcode:v3.1.0-amd" "$e"
has "env: UI origin is allowed" "ARM_ALLOWED_ORIGINS=https://localhost:8081" "$e"
has "env: cdrom gid is detected" "CDROM_GID=24" "$e"
has "env: render gid is detected" "ARM_RENDER_GID=993" "$e"
lacks "env: no offload keys on a full box" "ARM_TRANSCODE_DOCKER_HOST=" "$e"

e="$(env_case env-ripper ripper-only)"
has "env: ripper-only is not transcode-capable" "ARM_TRANSCODE_CAPABLE=false" "$e"
has "env: ripper-only records no GPUs" "ARM_GPUS=[]" "$e"

e="$(env_case env-offload offload)"
has "env: offload records the remote daemon" "ARM_TRANSCODE_DOCKER_HOST=ssh://sam@192.168.0.92" "$e"
has "env: offload points transcoder certs at the remote path" "ARM_HOST_CERTS_PATH=/home/sam/.arm/certs" "$e"
has "env: offload keeps rippers on the local certs" "ARM_RIPPER_CERTS_PATH=${TMPROOT}/env-offload/arm/certs" "$e"
has "env: offload records the remote GPUs" 'ARM_GPUS=[{"vendor":"nvenc"' "$e"

pw_before="$(env_case env-rerun full | grep '^POSTGRES_PASSWORD=')"
echo 'NEW_SETTING=7' >> "${REL}/.env.example"
e="$(env_case env-rerun full keep)"
check "env: a re-run keeps the database password" "$pw_before" "$(grep '^POSTGRES_PASSWORD=' <<<"$e")"
has "env: a re-run adds settings the new release introduced" "NEW_SETTING=7" "$e"
env_case env-switch offload >/dev/null
e="$(env_case env-switch full keep)"
lacks "env: leaving the offload profile removes its keys" "ARM_TRANSCODE_DOCKER_HOST=" "$e"
lacks "env: leaving the offload profile removes the ripper certs override" "ARM_RIPPER_CERTS_PATH=" "$e"

pin="${TMPROOT}/pin.env"; printf 'ARM_IMAGE_PREFIX=ghcr.io/fork\nARM_IMAGE_TAG=v3.0.0\n' > "$pin"
( IMAGE_PREFIX_ARG=""; write_image_pins v3.2.0 "$pin" )
has "pins: an existing prefix is kept across an upgrade" "ARM_RIPPER_IMAGE=ghcr.io/fork/arm-ripper:v3.2.0" "$(cat "$pin")"
out="$( (write_image_pins "" "$pin") 2>&1 || true)"
has "pins: an empty version is refused" "no release version" "$out"
```

- [ ] **Step 2: Run it to see it fail**

Run: `bash deploy/tests/test-armctl.sh; echo rc=$?`
Expected: stops at `valid_storage_path: command not found`.

- [ ] **Step 3: Create `deploy/install/config.sh`**

```bash
#!/usr/bin/env bash
# shellcheck disable=SC2034 # the answers assigned here are read by other sourced modules
# deploy/install/config.sh: profile, storage locations, .env, image pins and
# the generated host overlay. Sourced by deploy/armctl.sh; needs deploy/lib/*
# and deploy/install/ui.sh loaded first.

ARM_IMAGE_PREFIX_DEFAULT="docker.io/automaticrippingmachine"
# The release this run pins. The install flow sets it from the bundle's VERSION.
ARM_IMAGE_TAG_DEFAULT=""

# Answers from flags (empty = not given) and the resolved answers.
PROFILE_ARG=""
RAW_ARG=""
MEDIA_ARG=""
IMAGE_PREFIX_ARG=""
RAW_PATH=""
MEDIA_PATH=""

valid_profile() {
    [[ "$1" == full || "$1" == ripper-only || "$1" == offload ]]
}

# Sets PROFILE and RIPPER_ONLY. Order: the --profile flag, then (with no
# terminal) the saved profile or `full`, then a prompt defaulting to the saved
# profile.
choose_profile() {
    local saved reply def
    saved="$(env_file_value ARMCTL_PROFILE)"
    if [[ -n "${PROFILE_ARG}" ]]; then
        valid_profile "${PROFILE_ARG}" || err "--profile must be full, ripper-only or offload (got '${PROFILE_ARG}')"
        PROFILE="${PROFILE_ARG}"
    elif [[ ! -t 0 ]]; then
        PROFILE="${saved:-full}"
    else
        def="${saved:-full}"
        printf '  How will this host be used?\n'
        printf '    1) full         rip and transcode on this host\n'
        printf '    2) ripper-only  rip here, never transcode here\n'
        printf '    3) offload      rip here, transcode on another host over ssh\n'
        while true; do
            read -rp "  Choice [${def}]: " reply
            case "${reply:-${def}}" in
                1|full)        PROFILE=full; break ;;
                2|ripper-only) PROFILE=ripper-only; break ;;
                3|offload)     PROFILE=offload; break ;;
                *) printf '    ! enter 1, 2 or 3\n' >&2 ;;
            esac
        done
    fi
    RIPPER_ONLY=0
    if [[ "${PROFILE}" == ripper-only ]]; then
        RIPPER_ONLY=1
    fi
    okline "profile: ${PROFILE}"
}

# A storage folder must be a full path, and free of the characters that the
# overlay's "host:container" mount syntax or an unquoted .env value cannot
# carry. Spaces are fine.
valid_storage_path() {
    [[ "$1" == /* ]] || return 1
    case "$1" in
        *$'\n'*|*:*|*\"*|*\$*|*\#*|*\\*|*\'*) return 1 ;;
    esac
    return 0
}

# pick_storage <label> <flag value> <env key> <default>: print the folder to
# use. Order: the flag, then (with no terminal) the saved answer or the
# default, then a prompt.
pick_storage() {
    local label="$1" arg="$2" key="$3" def="$4" saved reply
    saved="$(env_file_value "${key}")"
    # .env.example ships these keys as ${PWD}/arm/...; that is not an answer.
    if [[ "${saved}" != /* ]]; then
        saved=""
    fi
    def="${saved:-${def}}"
    if [[ -n "${arg}" ]]; then
        valid_storage_path "${arg}" \
            || err "the folder for ${label} must be a full path starting with / and without : \" \$ # \\ or quote characters (got '${arg}')"
        printf '%s' "${arg}"
        return 0
    fi
    if [[ ! -t 0 ]]; then
        printf '%s' "${def}"
        return 0
    fi
    while true; do
        read -rp "  Folder for ${label} [${def}]: " reply
        reply="${reply:-${def}}"
        if valid_storage_path "${reply}"; then
            printf '%s' "${reply}"
            return 0
        fi
        printf '    ! enter a full path starting with / and without : " $ # \\ or quote characters\n' >&2
    done
}

# Create the folder if needed and make sure this user can write to it. Folders
# inside the arm folder get the setgid, group-writable mode the stack expects;
# a folder the user pointed us at elsewhere is theirs, so its mode is left alone.
prepare_storage() {
    local dir="$1"
    if [[ ! -d "${dir}" ]]; then
        mkdir -p "${dir}" 2>/dev/null \
            || err "cannot create ${dir}. Create it yourself, writable by $(id -un), then run the installer again."
    fi
    [[ -w "${dir}" ]] \
        || err "${dir} is not writable by $(id -un). Fix its ownership or choose another folder, then run the installer again."
    if [[ "${dir}" == "${ARM_DIR}/"* ]]; then
        chmod 2775 "${dir}"
    fi
}

choose_storage() {
    RAW_PATH="$(pick_storage "raw rips" "${RAW_ARG}" ARM_HOST_RAW_PATH "${ARM_DIR}/raw")"
    MEDIA_PATH="$(pick_storage "finished media" "${MEDIA_ARG}" ARM_HOST_MEDIA_PATH "${ARM_DIR}/media")"
    prepare_storage "${RAW_PATH}"
    prepare_storage "${MEDIA_PATH}"
    okline "raw rips:       ${RAW_PATH}"
    okline "finished media: ${MEDIA_PATH}"
}

# env_merge_new_keys <example> <env>: append every KEY=value line of the
# example whose key the env file does not have yet. This is how a setting
# introduced by a newer release gets its default on re-run and on upgrade.
env_merge_new_keys() {
    local example="$1" env="$2" line key
    while IFS= read -r line; do
        [[ "${line}" =~ ^[A-Z][A-Z0-9_]*= ]] || continue
        key="${line%%=*}"
        if ! grep -q "^${key}=" "${env}"; then
            printf '%s\n' "${line}" >> "${env}"
        fi
    done < "${example}"
}

# write_image_pins <tag> [env file]: pin every image to one release. The
# backend, data-init and UI images come from ARM_IMAGE_PREFIX/ARM_IMAGE_TAG
# through docker-compose.release.yml; the ripper and transcode images are
# variables the compose template already reads.
write_image_pins() {
    local tag="$1" file="${2:-${ENV_FILE}}" prefix
    [[ -n "${tag}" ]] || err "no release version to pin the images to"
    prefix="${IMAGE_PREFIX_ARG:-}"
    if [[ -z "${prefix}" ]]; then
        prefix="$(sed -nE 's/^ARM_IMAGE_PREFIX=(.+)$/\1/p' "${file}" 2>/dev/null | tail -n1)"
    fi
    prefix="${prefix:-${ARM_IMAGE_PREFIX_DEFAULT}}"
    env_set ARM_IMAGE_PREFIX "${prefix}" "${file}"
    env_set ARM_IMAGE_TAG "${tag}" "${file}"
    env_set ARM_RIPPER_IMAGE "${prefix}/arm-ripper:${tag}" "${file}"
    env_set ARM_TRANSCODE_IMAGE "${prefix}/arm-transcode:${tag}" "${file}"
    env_set ARM_TRANSCODE_IMAGE_QSV "${prefix}/arm-transcode:${tag}-intel" "${file}"
    env_set ARM_TRANSCODE_IMAGE_VAAPI "${prefix}/arm-transcode:${tag}-amd" "${file}"
}

# Write ENV_FILE from the bundle's .env.example. Secrets are generated once
# and kept on every later run; everything detected or answered is rewritten.
write_env() {
    local example="${ARMCTL_RELEASE_DIR}/.env.example" key
    if [[ -f "${ENV_FILE}" ]]; then
        log ".env exists; keeping its secrets and refreshing detected values"
        env_merge_new_keys "${example}" "${ENV_FILE}"
    else
        log "generating .env with random secrets"
        mkdir -p "$(dirname "${ENV_FILE}")"
        sed \
            -e "s|change-me-openssl-rand-hex-24|$(openssl rand -hex 24)|" \
            -e "s|change-me-openssl-rand-hex-32|$(openssl rand -hex 32)|" \
            "${example}" > "${ENV_FILE}"
        chmod 600 "${ENV_FILE}"
    fi

    env_set PUID "$(id -u)"
    env_set PGID "$(id -g)"
    env_set CDROM_GID "$(detect_cdrom_gid)"
    env_set ARMCTL_PROFILE "${PROFILE}"
    # The template defaults these from ${PWD}, the folder compose was started
    # in. armctl can be run from anywhere, so they are always written in full.
    env_set ARM_HOST_RAW_PATH "${RAW_PATH}"
    env_set ARM_HOST_MEDIA_PATH "${MEDIA_PATH}"
    env_set ARM_HOST_LOGS_PATH "${ARM_DIR}/logs"
    if [[ -z "$(env_file_value ARM_ALLOWED_ORIGINS)" ]]; then
        env_set ARM_ALLOWED_ORIGINS "https://localhost:8081"
    fi
    write_image_pins "${ARM_IMAGE_TAG_DEFAULT}"

    if [[ "${PROFILE}" == ripper-only ]]; then
        env_set ARM_TRANSCODE_CAPABLE false
    else
        env_set ARM_TRANSCODE_CAPABLE true
    fi

    if [[ "${PROFILE}" == offload ]]; then
        env_set ARM_TRANSCODE_DOCKER_HOST "${REMOTE_DOCKER_HOST}"
        env_set ARM_TRANSCODE_BACKEND_URL "${REMOTE_BACKEND_URL}"
        env_set ARM_TRANSCODE_PUID "${REMOTE_TRANSCODE_PUID}"
        env_set ARM_TRANSCODE_PGID "${REMOTE_TRANSCODE_PGID}"
        env_set ARM_TRANSCODE_SSH_DIR "${ARM_DIR}/ssh"
        # Transcoders run on the remote daemon and mount certs from ITS path;
        # rippers run on this host and need the local folder.
        env_set ARM_HOST_CERTS_PATH "$(offload_certs_path "${REMOTE_DOCKER_HOST}")"
        env_set ARM_RIPPER_CERTS_PATH "${ARM_DIR}/certs"
        env_set ARM_GPUS "${REMOTE_GPUS:-[]}"
        env_set ARM_RENDER_GID "${REMOTE_RENDER_GID:-}"
    else
        for key in ARM_TRANSCODE_DOCKER_HOST ARM_TRANSCODE_BACKEND_URL ARM_TRANSCODE_PUID \
                   ARM_TRANSCODE_PGID ARM_TRANSCODE_SSH_DIR ARM_RIPPER_CERTS_PATH; do
            env_unset "${key}"
        done
        env_set ARM_HOST_CERTS_PATH "${ARM_DIR}/certs"
        refresh_arm_gpus
        env_set ARM_RENDER_GID "$(detect_render_gid || true)"
    fi
}

# The per-install compose overlay: where raw rips and finished media live,
# and, for offload, the ssh folder and the published callback port. It is
# rewritten in full each time, so a changed answer never leaves a stale entry.
# Compose replaces a template mount that targets the same container path.
write_host_overlay() {
    local tmp="${HOST_OVERLAY}.tmp"
    mkdir -p "$(dirname "${HOST_OVERLAY}")"
    {
        # shellcheck disable=SC2016 # backticks are literal text in the comment
        printf '# Generated by armctl install. Do not edit; run `armctl install` again to change it.\n'
        printf 'services:\n'
        printf '  arm-backend:\n'
        printf '    volumes:\n'
        printf '      - "%s:/raw"\n' "${RAW_PATH}"
        printf '      - "%s:/media"\n' "${MEDIA_PATH}"
        if [[ "${PROFILE}" == offload ]]; then
            printf '      - "%s:/home/arm/.ssh:ro"\n' "${ARM_DIR}/ssh"
            printf '    ports:\n'
            printf '      - "%s:8443"\n' "$(offload_backend_port "${REMOTE_BACKEND_URL}")"
        fi
    } > "${tmp}"
    mv "${tmp}" "${HOST_OVERLAY}"
}
```

- [ ] **Step 4: Load the new modules in `deploy/armctl.sh`**

Change `for _mod in ui; do` to `for _mod in ui config nvidia offload; do`, and delete the `# shellcheck disable=SC2043` line above it (the loop now has more than one item).

- [ ] **Step 5: Run the suites**

Run: `bash deploy/tests/test-armctl.sh; echo rc=$?` and `bash devtools/test-install-walkthrough.sh; echo rc=$?` and `shellcheck deploy/armctl.sh deploy/install/*.sh deploy/tests/*.sh`
Expected: all `ok`, both `rc=0`, shellcheck silent.

- [ ] **Step 6: Commit**

```bash
git add deploy/install/config.sh deploy/armctl.sh deploy/tests/test-armctl.sh
git commit -m "feat(deploy): install configuration (profile, storage, .env, overlay)

Builds the production .env from the bundled .env.example, pins every image
to one release, records the profile, and writes storage locations and
offload settings into a generated compose overlay.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Release overlay, bundle and stack contract

**Files:**
- Create: `deploy/docker-compose.release.yml`, `deploy/build-bundle.sh`, `deploy/tests/test-bundle.sh`, `deploy/tests/test-stack-contract.sh`
- Test: the two new suites

**Interfaces:**
- Consumes: `deploy/armctl.sh` (seam), `write_env`, `write_host_overlay`, `compose`.
- Produces:
  - `deploy/build-bundle.sh <tag> <out-dir>`: writes `<out-dir>/arm-installer-<tag>.tar.gz` and `<out-dir>/arm-installer-<tag>.tar.gz.sha256`, prints the archive path on stdout. Archive members are relative (`./armctl.sh`, `./lib/common.sh`, `./install/ui.sh`, `./docker-compose.yml.example`, `./docker-compose.release.yml`, `./.env.example`, `./install.sh`, `./VERSION`). `VERSION` holds the tag.
  - The release overlay's variables: `ARM_IMAGE_PREFIX`, `ARM_IMAGE_TAG`.

- [ ] **Step 1: Write `deploy/tests/test-bundle.sh`**

```bash
#!/usr/bin/env bash
# Zero-infra suite: the release bundle has the expected files and carries the
# compose template unchanged.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${HERE}/.."
ROOT="${DEPLOY}/.."

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

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

archive="$(bash "${DEPLOY}/build-bundle.sh" v3.9.9 "${TMP}/out")"
check "archive is named after the tag" "${TMP}/out/arm-installer-v3.9.9.tar.gz" "${archive}"
rc=0; (cd "${TMP}/out" && sha256sum -c "arm-installer-v3.9.9.tar.gz.sha256" >/dev/null 2>&1) || rc=$?
check "checksum file verifies the archive" "0" "$rc"

listing="$(tar -tzf "${archive}")"
for f in armctl.sh install.sh docker-compose.yml.example docker-compose.release.yml .env.example VERSION; do
    rc=0; grep -qx "./${f}" <<<"${listing}" || rc=$?
    check "bundle has ${f}" "0" "$rc"
done
# Every library and install module in the checkout must be in the bundle.
while IFS= read -r f; do
    rc=0; grep -qx "./${f}" <<<"${listing}" || rc=$?
    check "bundle has ${f}" "0" "$rc"
done < <(cd "${DEPLOY}" && find lib install -type f -name '*.sh' | sort)
rc=0; grep -qE '(^|/)(tests|build-bundle\.sh)' <<<"${listing}" || rc=$?
check "bundle leaves out tests and the bundler" "1" "$rc"
rc=0; grep -qE '(^/|(^|/)\.\.(/|$))' <<<"${listing}" || rc=$?
check "no absolute or parent paths in the archive" "1" "$rc"

mkdir -p "${TMP}/x"; tar -xzf "${archive}" -C "${TMP}/x"
rc=0; cmp -s "${ROOT}/docker-compose.yml.example" "${TMP}/x/docker-compose.yml.example" || rc=$?
check "compose template is byte-identical to the committed one" "0" "$rc"
rc=0; cmp -s "${ROOT}/.env.example" "${TMP}/x/.env.example" || rc=$?
check ".env.example is byte-identical to the committed one" "0" "$rc"
check "VERSION holds the tag" "v3.9.9" "$(cat "${TMP}/x/VERSION")"
check "armctl.sh is executable" "yes" "$( [[ -x "${TMP}/x/armctl.sh" ]] && echo yes || echo no )"

bash "${DEPLOY}/build-bundle.sh" v3.9.9 "${TMP}/out2" >/dev/null
check "the bundle is reproducible" \
    "$(cut -d' ' -f1 "${TMP}/out/arm-installer-v3.9.9.tar.gz.sha256")" \
    "$(cut -d' ' -f1 "${TMP}/out2/arm-installer-v3.9.9.tar.gz.sha256")"

rc=0; bash "${DEPLOY}/build-bundle.sh" >/dev/null 2>&1 || rc=$?
check "a missing tag is a usage error" "2" "$rc"

exit "$fail"
```

- [ ] **Step 2: Write `deploy/tests/test-stack-contract.sh`**

```bash
#!/usr/bin/env bash
# shellcheck disable=SC2317,SC2329,SC2034
# The production stack contract: the committed compose template layered with
# the release overlay and a host overlay. Text checks always run; the
# `docker compose config` checks run when docker is present.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${HERE}/.."
ROOT="${DEPLOY}/.."
TEMPLATE="${ROOT}/docker-compose.yml.example"
OVERLAY="${DEPLOY}/docker-compose.release.yml"

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
# image_of <service> <compose yaml>: the service's image, or nothing.
image_of() {
    awk -v s="  $1:" '$0 == s {f=1; next} f && /^  [a-z]/ {exit} f && /^    image:/ {print $2; exit}' <<<"$2"
}

# --- text: every service the template only builds gets a release image -----------
# This is the one thing a new built-from-source service needs: a line in the
# release overlay. Everything else in the template reaches production as is.
built_only="$(awk '
    /^  [a-z][a-z0-9-]*:$/ { svc=$1; sub(":", "", svc); order[++n]=svc; next }
    /^    image:/ { img[svc]=1 }
    /^    build:/ { bld[svc]=1 }
    END { for (i = 1; i <= n; i++) if (bld[order[i]] && !img[order[i]]) print order[i] }
' "${TEMPLATE}")"
check "the template's build-only services are the three we expect" \
    "arm-backend arm-data-init arm-ui" "$(tr '\n' ' ' <<<"${built_only}" | sed 's/ $//')"
overlay_text="$(cat "${OVERLAY}")"
while IFS= read -r svc; do
    [[ -n "${svc}" ]] || continue
    got="$(image_of "${svc}" "${overlay_text}")"
    check "release overlay names an image for ${svc}" "yes" "$( [[ "${got}" == *'${ARM_IMAGE_PREFIX'*'${ARM_IMAGE_TAG'* ]] && echo yes || echo no )"
done <<<"${built_only}"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "skip - docker compose not available; contract checked by text only"
    exit "$fail"
fi

# --- docker compose config: the layered stack as armctl runs it -------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
archive="$(bash "${DEPLOY}/build-bundle.sh" v3.9.9 "${TMP}/out")"
ARM_DIR="${TMP}/home/arm"
REL="${ARM_DIR}/.armctl/releases/v3.9.9"
mkdir -p "${REL}"; tar -xzf "${archive}" -C "${REL}"

export ARMCTL_SOURCE_ONLY=1
# shellcheck disable=SC1091
source "${REL}/armctl.sh"
armctl_settings

# A storage folder with a space in its name (Review Focus 1).
PROFILE=full; RIPPER_ONLY=0
RAW_PATH="${TMP}/My Passport/rips"; MEDIA_PATH="${TMP}/nas/media"
mkdir -p "${RAW_PATH}" "${MEDIA_PATH}"
ARM_IMAGE_TAG_DEFAULT="v3.9.9"; IMAGE_PREFIX_ARG=""
detect_gpus() { printf '[]'; }
detect_render_gid() { :; }
write_env >/dev/null
write_host_overlay

rc=0; cfg="$(compose config 2>"${TMP}/config.err")" || rc=$?
check "layered config is valid" "0" "$rc"
if [[ "$rc" -ne 0 ]]; then cat "${TMP}/config.err" >&2; exit 1; fi

check "project name is armv3" "armv3" "$(sed -n 's/^name: //p' <<<"${cfg}" | head -n 1)"
while IFS= read -r svc; do
    img="$(image_of "${svc}" "${cfg}")"
    case "${img}" in
        postgres:*|docker.io/automaticrippingmachine/arm-*:v3.9.9|docker.io/automaticrippingmachine/arm-*:v3.9.9-intel|docker.io/automaticrippingmachine/arm-*:v3.9.9-amd)
            check "${svc} runs a release image" "yes" "yes" ;;
        *)  check "${svc} runs a release image" "a registry image at v3.9.9" "${img:-none}" ;;
    esac
done < <(compose config --services)

# Mounts: the backend's /raw and /media come from the chosen folders, and
# every other host path is inside the arm folder or a system path the template
# names on purpose.
mounts="$(awk '
    /^  [a-z][a-z0-9-]*:$/ { svc=$1; sub(":", "", svc) }
    /^ *source: / { src=$0; sub(/^ *source: /, "", src) }
    /^ *target: / { if (src != "") { t=$0; sub(/^ *target: /, "", t); print svc "|" src "|" t; src="" } }
' <<<"${cfg}")"
check "backend /raw is the chosen folder, spaces and all" "arm-backend|${RAW_PATH}|/raw" "$(grep '^arm-backend|.*|/raw$' <<<"${mounts}")"
check "backend /media is the chosen folder" "arm-backend|${MEDIA_PATH}|/media" "$(grep '^arm-backend|.*|/media$' <<<"${mounts}")"
stray=""
while IFS='|' read -r svc src target; do
    case "${src}" in
        "${ARM_DIR}"/*|"${RAW_PATH}"|"${MEDIA_PATH}"|/var/run/docker.sock|/dev/disk) ;;
        /*) stray+="${svc}:${src} " ;;
        *)  ;;   # a named volume
    esac
done <<<"${mounts}"
check "no host path escapes the arm folder" "" "${stray}"

env_raw="$(awk '/^  arm-backend:$/ {f=1} f && /ARM_HOST_RAW_PATH:/ {sub(/^ *ARM_HOST_RAW_PATH: /, ""); print; exit}' <<<"${cfg}")"
check "backend is told the raw folder for spawned containers" "${RAW_PATH}" "${env_raw}"

exit "$fail"
```

- [ ] **Step 3: Run both to see them fail**

Run: `bash deploy/tests/test-bundle.sh; echo rc=$?` and `bash deploy/tests/test-stack-contract.sh; echo rc=$?`
Expected: the first fails with `build-bundle.sh: No such file or directory`; the second fails at `cat: .../docker-compose.release.yml: No such file`.

- [ ] **Step 4: Create `deploy/docker-compose.release.yml`**

```yaml
# deploy/docker-compose.release.yml: the production overlay.
#
# Production runs docker-compose.yml.example exactly as committed, layered
# with this file. The template builds these three services from source and
# gives them no image name, so this overlay names the published image for
# each. Everything else in the template (environment, mounts, the ripper and
# transcode images, which are already variables) reaches production unchanged.
#
# A new service that the template builds from source needs one entry here;
# deploy/tests/test-stack-contract.sh fails until it has one.
#
# ARM_IMAGE_PREFIX and ARM_IMAGE_TAG are written to .env by armctl.
services:
  arm-backend:
    image: ${ARM_IMAGE_PREFIX:?armctl writes ARM_IMAGE_PREFIX to .env}/arm-backend:${ARM_IMAGE_TAG:?armctl writes ARM_IMAGE_TAG to .env}
  arm-data-init:
    image: ${ARM_IMAGE_PREFIX:?armctl writes ARM_IMAGE_PREFIX to .env}/arm-backend:${ARM_IMAGE_TAG:?armctl writes ARM_IMAGE_TAG to .env}
  arm-ui:
    image: ${ARM_IMAGE_PREFIX:?armctl writes ARM_IMAGE_PREFIX to .env}/arm-ui:${ARM_IMAGE_TAG:?armctl writes ARM_IMAGE_TAG to .env}
```

- [ ] **Step 5: Create `deploy/build-bundle.sh`**

```bash
#!/usr/bin/env bash
# deploy/build-bundle.sh <tag> <out-dir>: pack the release bundle.
#
# The bundle is what the bootstrap (install.sh) downloads into
# <arm>/.armctl/releases/<tag>/: the launcher, the shared library, the install
# modules, the release overlay, and the compose template and .env.example
# exactly as committed. Nothing in it is generated except VERSION.
# Prints the archive path. Used by release.yml, CI and devtools/install-drill.sh.
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: build-bundle.sh <tag> <out-dir>" >&2
    exit 2
fi
tag="$1"
out="$2"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"

stage="$(mktemp -d)"
trap 'rm -rf "${stage}"' EXIT

mkdir -p "${stage}/lib" "${stage}/install"
cp "${HERE}/armctl.sh" "${stage}/armctl.sh"
cp "${HERE}"/lib/*.sh "${stage}/lib/"
cp "${HERE}"/install/*.sh "${stage}/install/"
cp "${HERE}/docker-compose.release.yml" "${stage}/docker-compose.release.yml"
cp "${ROOT}/docker-compose.yml.example" "${stage}/docker-compose.yml.example"
cp "${ROOT}/.env.example" "${stage}/.env.example"
cp "${ROOT}/install.sh" "${stage}/install.sh"
printf '%s\n' "${tag}" > "${stage}/VERSION"
chmod 755 "${stage}/armctl.sh" "${stage}/install.sh"
chmod 644 "${stage}"/lib/*.sh "${stage}"/install/*.sh "${stage}/docker-compose.release.yml" \
    "${stage}/docker-compose.yml.example" "${stage}/.env.example" "${stage}/VERSION"

mkdir -p "${out}"
out="$(cd "${out}" && pwd)"
name="arm-installer-${tag}.tar.gz"
# Fixed order, owner and timestamps, and no gzip header time, so the same
# commit always produces the same archive and checksum.
tar -C "${stage}" --sort=name --owner=0 --group=0 --numeric-owner \
    --mtime='2000-01-01 00:00:00Z' -cf - . | gzip -n > "${out}/${name}"
(cd "${out}" && sha256sum "${name}" > "${name}.sha256")
printf '%s\n' "${out}/${name}"
```

Run `chmod 755 deploy/build-bundle.sh`.

- [ ] **Step 6: Run both suites**

Run: `bash deploy/tests/test-bundle.sh; echo rc=$?` and `bash deploy/tests/test-stack-contract.sh; echo rc=$?`
Expected: all `ok`, both `rc=0`. On a host with Docker the contract suite runs the `docker compose config` checks.

This is where the spec's unverified items (section 6.5) are settled against the real template. If a Docker-gated check fails, do not weaken it. The likely causes and their fixes:
- **A path with spaces does not survive `.env`** (the `ARM_HOST_RAW_PATH` check fails): in `write_env`, write the two storage keys quoted, `env_set ARM_HOST_RAW_PATH "\"${RAW_PATH}\""` (and the same for media). `env_file_value` already strips one layer of quotes. Update the Task 4 expectations `ARM_HOST_RAW_PATH=/r` to `ARM_HOST_RAW_PATH="/r"`.
- **The `/raw` mount is duplicated instead of replaced**: the overlay must then use Compose's `!override` tag on `volumes` and list every backend mount; stop and report this to the owner, because it breaks the "no translation" property the spec relies on.

- [ ] **Step 7: Commit**

```bash
git add deploy/docker-compose.release.yml deploy/build-bundle.sh deploy/tests/test-bundle.sh deploy/tests/test-stack-contract.sh
git commit -m "feat(deploy): release overlay, bundle builder and stack contract test

Production runs the committed compose template layered with an overlay
that names the release images for the three build-only services. The
contract test fails when a new build-only service has no release image.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Docker setup and the PATH link

**Files:**
- Create: `deploy/install/docker.sh`, `deploy/install/pathlink.sh`
- Modify: `deploy/armctl.sh`, `deploy/tests/test-armctl.sh`
- Test: `deploy/tests/test-armctl.sh`

**Interfaces:**
- Consumes: `vercmp_ge`, `consent`, `log`, `okline`, `failline`, `warnline`, `err`, `SKIPPED` (ui); `arm_err`, `arm_sub`; `ARMCTL_CMD`, `ARMCTL_ARGV`, `ARM_DIR`.
- Produces:
  - `docker.sh`: `os_family` (prints `debian`, `ubuntu` or `other`), `os_codename`, `docker_state` (prints `ok`, `missing`, `old:<version>`, `no-compose`, `daemon-down` or `no-group`), `user_in_docker_group_file`, `docker_apt_install <family>`, `ensure_docker` (install-time: fixes what it can, with consent), `require_docker_ready` (every other command), `reexec_under_docker_group`, `run_sg_exec <command string>`; settings `OS_RELEASE_FILE`, `DOCKER_DOCS_URL`.
  - `pathlink.sh`: `link_armctl` (sets `ARMCTL_CMD` to `armctl` when a link is in place), `place_link <dest> <src> <sudo or empty>`, `path_has <dir>`; setting `ARMCTL_SYSTEM_BIN` (default `/usr/local/bin`).

- [ ] **Step 1: Add the failing checks to `deploy/tests/test-armctl.sh`**

Insert before the `# --- dispatch ---` section:

```bash
# --- docker diagnosis ---------------------------------------------------------------
# dstate <stub code>: run docker_state with `command -v docker` succeeding and
# `docker` replaced by the given stub body.
dstate() {
    (
        command() { if [[ "$1" == -v && "$2" == docker ]]; then return 0; fi; builtin command "$@"; }
        eval "docker() { $1; }"
        docker_state
    )
}
check "docker: not installed" "missing" \
    "$( (command() { if [[ "$1" == -v && "$2" == docker ]]; then return 1; fi; builtin command "$@"; }; docker_state) )"
check "docker: too old" "old:20.10.24" \
    "$(dstate 'case "$1" in --version) echo "Docker version 20.10.24+dfsg1, build 297e128" ;; esac')"
check "docker: no compose plugin" "no-compose" \
    "$(dstate 'case "$1" in --version) echo "Docker version 27.3.1, build ce12230" ;; compose) return 1 ;; esac')"
check "docker: daemon not running" "daemon-down" \
    "$(dstate 'case "$1" in --version) echo "Docker version 27.3.1, build x" ;; compose) return 0 ;; info) echo "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?" >&2; return 1 ;; esac')"
check "docker: session lacks the docker group" "no-group" \
    "$(dstate 'case "$1" in --version) echo "Docker version 27.3.1, build x" ;; compose) return 0 ;; info) echo "permission denied while trying to connect to the Docker daemon socket" >&2; return 1 ;; esac')"
check "docker: ready" "ok" \
    "$(dstate 'case "$1" in --version) echo "Docker version 27.3.1, build x" ;; *) return 0 ;; esac')"

osr="${TMPROOT}/os-release"
printf 'ID=debian\nVERSION_CODENAME=trixie\n' > "$osr"
check "os: debian" "debian" "$(OS_RELEASE_FILE="$osr" os_family)"
check "os: codename" "trixie" "$(OS_RELEASE_FILE="$osr" os_codename)"
printf 'ID=ubuntu\nVERSION_CODENAME=noble\n' > "$osr"
check "os: ubuntu" "ubuntu" "$(OS_RELEASE_FILE="$osr" os_family)"
printf 'ID=linuxmint\nID_LIKE="ubuntu debian"\n' > "$osr"
check "os: a derivative is not automated" "other" "$(OS_RELEASE_FILE="$osr" os_family)"
check "os: no os-release file" "other" "$(OS_RELEASE_FILE="${TMPROOT}/absent" os_family)"

# --- docker group restart (Review Focus 5) --------------------------------------------
# regroup <ARMCTL_SG_REEXEC value> <sg available: yes|no>
regroup() {
    (
        new_install regroup
        ARMCTL_ARGV=(up --force); ARMCTL_SG_REEXEC="$1"
        me="$(id -un)"
        getent() { echo "docker:x:998:someone,${me}"; }
        if [[ "$2" == yes ]]; then
            command() { if [[ "$1" == -v && "$2" == sg ]]; then return 0; fi; builtin command "$@"; }
            sg() { return 0; }
        else
            command() { if [[ "$1" == -v && "$2" == sg ]]; then return 1; fi; builtin command "$@"; }
        fi
        run_sg_exec() { echo "EXEC $1"; exit 0; }
        reexec_under_docker_group
    )
}
out="$(regroup "" yes 2>&1)"
has "regroup: restarts the same command under the docker group" "EXEC ARMCTL_SG_REEXEC=1 " "$out"
has "regroup: the restart carries the original arguments" "armctl up --force" "$out"
rc=0; out="$(regroup 1 yes 2>&1)" || rc=$?
check "regroup: never restarts twice" "1" "$rc"
lacks "regroup: a second attempt does not exec" "EXEC" "$out"
has "regroup: a second attempt asks for a new login" "Log out and back in" "$out"
rc=0; out="$(regroup "" no 2>&1)" || rc=$?
check "regroup: without sg it stops" "1" "$rc"
has "regroup: without sg it names the command to run after login" "armctl up --force" "$out"

# --- ensure_docker -----------------------------------------------------------------
# edocker <first state> <os id> <ARMCTL_ASSUME>
edocker() {
    (
        new_install edocker
        statefile="${TMPROOT}/dstate"; echo "$1" > "${statefile}"
        printf 'ID=%s\nVERSION_CODENAME=trixie\n' "$2" > "${TMPROOT}/osr"; OS_RELEASE_FILE="${TMPROOT}/osr"
        ARMCTL_ASSUME="$3"; SKIPPED=()
        docker_state() { cat "${statefile}"; }
        docker_apt_install() { echo "APT $1"; echo ok > "${statefile}"; }
        ensure_docker </dev/null
    )
}
out="$(edocker ok debian ask 2>&1)"
has "ensure_docker: nothing to do when ready" "Docker is ready" "$out"
out="$(edocker missing debian yes 2>&1)"
has "ensure_docker: installs on debian with consent" "APT debian" "$out"
has "ensure_docker: ready after the install" "Docker is ready" "$out"
rc=0; out="$(edocker missing debian ask 2>&1)" || rc=$?
check "ensure_docker: no terminal and no --yes stops" "1" "$rc"
lacks "ensure_docker: nothing is installed without consent" "APT" "$out"
has "ensure_docker: the docs are linked" "docs.docker.com/engine/install" "$out"
rc=0; out="$(edocker old:20.10.24 fedora yes 2>&1)" || rc=$?
check "ensure_docker: another distro stops even with --yes" "1" "$rc"
lacks "ensure_docker: another distro is never automated" "APT" "$out"
has "ensure_docker: another distro gets the docs link" "docs.docker.com/engine/install" "$out"
has "ensure_docker: the reason is stated" "too old" "$out"

# --- PATH link ---------------------------------------------------------------------
# plink <case name> <PATH has ~/.local/bin: yes|no> <ARMCTL_ASSUME> [pre-existing: foreign|own]
plink() {
    (
        new_install "plink-$1"
        HOME="${TMPROOT}/plink-$1/home"; mkdir -p "${HOME}/.local/bin"
        ARMCTL_SYSTEM_BIN="${TMPROOT}/plink-$1/sysbin"; mkdir -p "${ARMCTL_SYSTEM_BIN}"
        printf '#!/bin/sh\n' > "${ARM_DIR}/armctl"
        if [[ "$2" == yes ]]; then PATH="${HOME}/.local/bin:${PATH}"; dest="${HOME}/.local/bin/armctl"; else dest="${ARMCTL_SYSTEM_BIN}/armctl"; fi
        case "${4:-}" in
            foreign) echo other > "${dest}" ;;
            own)     ln -s "${ARM_DIR}/armctl" "${dest}" ;;
        esac
        ARMCTL_ASSUME="$3"; SKIPPED=()
        sudo() { "$@"; }
        link_armctl </dev/null >/dev/null 2>&1
        if [[ -L "${dest}" ]]; then echo "LINK=$(readlink "${dest}")"; else echo "LINK=none"; fi
        echo "CMD=${ARMCTL_CMD}"
        echo "SKIPPED=${SKIPPED[*]:-}"
        if [[ -f "${dest}" && ! -L "${dest}" ]]; then echo "FOREIGN=$(cat "${dest}")"; fi
    )
}
out="$(plink local yes ask)"
has "path link: ~/.local/bin on the PATH gets the link, no sudo, no question" "LINK=${TMPROOT}/plink-local/arm/armctl" "$out"
has "path link: the short command is advertised" "CMD=armctl" "$out"
out="$(plink sys-yes no yes)"
has "path link: the system folder is used with consent" "LINK=${TMPROOT}/plink-sys-yes/arm/armctl" "$out"
out="$(plink sys-ask no ask)"
has "path link: no terminal skips the sudo link" "LINK=none" "$out"
has "path link: the full path is advertised when skipped" "CMD=${TMPROOT}/plink-sys-ask/arm/armctl" "$out"
has "path link: the skip is recorded" "armctl on the PATH" "$out"
out="$(plink foreign yes ask foreign)"
has "path link: a file we did not create is left alone" "FOREIGN=other" "$out"
has "path link: the full path is advertised when blocked" "CMD=${TMPROOT}/plink-foreign/arm/armctl" "$out"
out="$(plink own yes ask own)"
has "path link: our own link is kept" "CMD=armctl" "$out"
```

- [ ] **Step 2: Run it to see it fail**

Run: `bash deploy/tests/test-armctl.sh; echo rc=$?`
Expected: stops at `docker_state: command not found`.

- [ ] **Step 3: Create `deploy/install/docker.sh`**

```bash
#!/usr/bin/env bash
# deploy/install/docker.sh: Docker diagnosis and setup.
# Sourced by deploy/armctl.sh; needs deploy/install/ui.sh loaded first.
#
# `armctl install` fixes what it can (ensure_docker), with consent. Every
# other command only checks (require_docker_ready), except that it restarts
# itself under the docker group when the only problem is a login session that
# predates the user's membership.

OS_RELEASE_FILE="${OS_RELEASE_FILE:-/etc/os-release}"
DOCKER_DOCS_URL="https://docs.docker.com/engine/install/"

# Only Debian and Ubuntu themselves are automated. A derivative (Mint, Pop!_OS)
# has its own release codenames, which Docker's apt repository does not carry,
# so it is treated like any other distro: a link, no automation.
os_family() {
    local id=""
    if [[ -r "${OS_RELEASE_FILE}" ]]; then
        id="$(sed -nE 's/^ID=//p' "${OS_RELEASE_FILE}" | tr -d '"' | head -n 1)"
    fi
    case "${id}" in
        debian|ubuntu) printf '%s' "${id}" ;;
        *)             printf 'other' ;;
    esac
}

os_codename() {
    [[ -r "${OS_RELEASE_FILE}" ]] || return 0
    sed -nE 's/^VERSION_CODENAME=//p' "${OS_RELEASE_FILE}" | tr -d '"' | head -n 1
}

# Print one of: ok | missing | old:<version> | no-compose | daemon-down | no-group
docker_state() {
    local ver info_err
    if ! command -v docker >/dev/null 2>&1; then
        printf 'missing'; return 0
    fi
    ver="$(docker --version 2>/dev/null | sed -E 's/^Docker version ([0-9.]+).*/\1/')"
    if [[ -z "${ver}" ]] || ! vercmp_ge "${ver}" "24.0.0"; then
        printf 'old:%s' "${ver:-unknown}"; return 0
    fi
    if ! docker compose version >/dev/null 2>&1; then
        printf 'no-compose'; return 0
    fi
    if info_err="$(docker info 2>&1 >/dev/null)"; then
        printf 'ok'; return 0
    fi
    if [[ "${info_err}" == *"permission denied"* ]]; then
        printf 'no-group'
    else
        printf 'daemon-down'
    fi
}

# True when the group database lists this user in `docker`, whatever groups
# the current login session happens to have.
user_in_docker_group_file() {
    local members
    members="$(getent group docker | cut -d: -f4)"
    [[ ",${members}," == *",$(id -un),"* ]]
}

# Its own function so tests can replace it: `exec` cannot be stubbed.
run_sg_exec() {
    exec sg docker -c "$1"
}

relogin_needed() {
    arm_err "this login session cannot use Docker yet."
    arm_sub "Your user is in the docker group, but that only applies to new logins."
    arm_sub "Log out and back in (or reboot), then run: ${ARMCTL_CMD} ${ARMCTL_ARGV[*]}"
    exit 1
}

# Restart this armctl command under the docker group, once. ARMCTL_SG_REEXEC
# marks the restarted process so a restart that did not help cannot loop.
reexec_under_docker_group() {
    local cmd
    if [[ -n "${ARMCTL_SG_REEXEC:-}" ]]; then
        relogin_needed
    fi
    if command -v sg >/dev/null 2>&1 && user_in_docker_group_file && sg docker -c true >/dev/null 2>&1; then
        log "restarting under the docker group (this login predates your membership)"
        printf -v cmd '%q ' "${ARMCTL_CMD}" "${ARMCTL_ARGV[@]}"
        run_sg_exec "ARMCTL_SG_REEXEC=1 ${cmd}"
    fi
    relogin_needed
}

# Docker's own apt repository steps, for Debian and Ubuntu.
docker_apt_install() {
    local family="$1" codename arch
    codename="$(os_codename)"
    [[ -n "${codename}" ]] \
        || err "cannot read this system's release codename from ${OS_RELEASE_FILE}. Install Docker by hand: ${DOCKER_DOCS_URL}"
    arch="$(dpkg --print-architecture)"
    log "installing Docker Engine and the compose plugin from download.docker.com (sudo)"
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL "https://download.docker.com/linux/${family}/gpg" -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' \
        "${arch}" "${family}" "${codename}" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

fix_docker_group() {
    local me
    me="$(id -un)"
    if ! user_in_docker_group_file; then
        consent "docker group" "Add ${me} to the docker group so ARM can use Docker without sudo (needs sudo)?" \
            || err "ARM needs ${me} to be in the docker group. Add it with: sudo usermod -aG docker ${me}"
        sudo usermod -aG docker "${me}"
    fi
    reexec_under_docker_group
}

# Install-time: diagnose Docker and fix what can be fixed, each fix with consent.
ensure_docker() {
    local state family
    state="$(docker_state)"
    case "${state}" in
        ok)
            okline "Docker is ready"
            return 0 ;;
        no-group)
            fix_docker_group ;;
        daemon-down)
            failline "Docker is installed but its service is not running"
            consent "start Docker" "Start the Docker service now (needs sudo)?" \
                || err "Docker must be running. Start it with: sudo systemctl enable --now docker"
            sudo systemctl enable --now docker ;;
        missing|old:*|no-compose)
            case "${state}" in
                missing)    failline "Docker is not installed" ;;
                old:*)      failline "Docker ${state#old:} is too old (ARM needs Engine 24 or newer)" ;;
                no-compose) failline "the Docker Compose v2 plugin is missing" ;;
            esac
            family="$(os_family)"
            if [[ "${family}" == other ]]; then
                err "this installer sets Docker up only on Debian and Ubuntu. Install Docker Engine 24 or newer with the compose plugin for your distro (${DOCKER_DOCS_URL}), then run the installer again."
            fi
            consent "install Docker" "Install Docker Engine and the compose plugin from Docker's apt repository (needs sudo; replaces the distro's docker.io package if present)?" \
                || err "ARM needs Docker Engine 24 or newer with the compose plugin. Install it (${DOCKER_DOCS_URL}), then run the installer again."
            docker_apt_install "${family}" ;;
    esac
    state="$(docker_state)"
    case "${state}" in
        ok)       okline "Docker is ready" ;;
        no-group) fix_docker_group ;;
        *)        err "Docker is still not usable (${state}). See ${DOCKER_DOCS_URL}" ;;
    esac
}

# Every command other than install: check, never change the host.
require_docker_ready() {
    local state
    state="$(docker_state)"
    case "${state}" in
        ok) return 0 ;;
        no-group)
            if user_in_docker_group_file; then
                reexec_under_docker_group
            fi
            arm_err "your user cannot use Docker. Run: ${ARMCTL_CMD} install"
            exit 1 ;;
        *)
            arm_err "Docker is not usable (${state}). Run: ${ARMCTL_CMD} install"
            exit 1 ;;
    esac
}
```

- [ ] **Step 4: Create `deploy/install/pathlink.sh`**

```bash
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
```

- [ ] **Step 5: Wire both into `deploy/armctl.sh`**

1. Change the module list to `for _mod in ui config docker nvidia offload pathlink; do`.
2. Delete the `require_docker_ready` function from `armctl.sh` (the one in `docker.sh` replaces it; `armctl.sh` is sourced after the modules and would otherwise override it).

- [ ] **Step 6: Run the suites**

Run: `bash deploy/tests/test-armctl.sh; echo rc=$?` then `bash deploy/tests/test-bundle.sh; echo rc=$?` then `shellcheck deploy/armctl.sh deploy/install/*.sh deploy/tests/*.sh`
Expected: all `ok`, `rc=0` twice, shellcheck silent.

- [ ] **Step 7: Commit**

```bash
git add deploy/install/docker.sh deploy/install/pathlink.sh deploy/armctl.sh deploy/tests/test-armctl.sh
git commit -m "feat(deploy): Docker setup and the armctl PATH link

Diagnoses Docker (missing, too old, no compose plugin, daemon down, session
without the docker group), offers the apt install on Debian and Ubuntu, and
restarts armctl under the docker group once instead of asking for a re-login.
Links armctl onto the PATH without replacing anything it did not create.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: `armctl install`

**Files:**
- Create: `deploy/install/flow.sh`
- Modify: `deploy/armctl.sh`, `deploy/tests/test-armctl.sh`
- Test: `deploy/tests/test-armctl.sh`

**Interfaces:**
- Consumes: everything produced by Tasks 1 to 6.
- Produces: `cmd_install [options]`, `install_usage`, `ensure_layout`, `install_udev_rule`, `print_install_summary <started 0|1>`. Reads `${ARMCTL_RELEASE_DIR}/VERSION` for the release to pin. Saves `ARMCTL_RELEASE_REPO` in `.env` when `--release-repo` is given.

The stages run in this order: Profile, Host, Storage, Remote transcode offload, Certificates, Configuration, Start, Finish. Profile comes before Host so that the answer is known before a possible restart under the `docker` group, and is carried across it.

- [ ] **Step 1: Add the failing checks to `deploy/tests/test-armctl.sh`**

Insert before the `# --- dispatch ---` section:

```bash
# --- install flow ----------------------------------------------------------------------
echo v3.1.0 > "${REL}/VERSION"
FLOW_STEPS=(ensure_docker acquire_lock ensure_layout choose_storage ensure_ca write_host_overlay ensure_nvidia_container_toolkit install_udev_rule link_armctl stack_up finish_up offload_completion_report)
# flow <install name> [install args...]: run cmd_install with every stage
# replaced by a recorder; print the order, then the parsed answers.
flow() {
    (
        ARM_DIR="${TMPROOT}/$1/arm"; mkdir -p "${ARM_DIR}/.armctl"; armctl_settings; rm -f "${ENV_FILE}"
        shift
        ARMCTL_RELEASE_DIR="${REL}"
        log_file="${TMPROOT}/flow.log"; : > "${log_file}"
        for fn in "${FLOW_STEPS[@]}"; do
            eval "${fn}() { echo ${fn} >> \"\${log_file}\"; }"
        done
        choose_profile() { PROFILE="${PROFILE_ARG:-full}"; echo "choose_profile ${PROFILE}" >> "${log_file}"; }
        setup_remote_offload() { REMOTE_BACKEND_SAN="192.168.0.68"; echo setup_remote_offload >> "${log_file}"; }
        write_env() { echo write_env >> "${log_file}"; if [[ "${PROFILE}" == offload ]]; then echo 'ARM_TRANSCODE_DOCKER_HOST=ssh://sam@h' > "${ENV_FILE}"; else : > "${ENV_FILE}"; fi; }
        make_leaf() { echo "make_leaf $*" >> "${log_file}"; }
        offload_remote_run_init() { :; }
        hostname() { echo testhost; }
        ARMCTL_ARGV=(install "$@")
        cmd_install "$@" </dev/null >/dev/null 2>&1
        echo "ASSUME=${ARMCTL_ASSUME} RAW=${RAW_ARG} MEDIA=${MEDIA_ARG} PREFIX=${IMAGE_PREFIX_ARG} TAG=${ARM_IMAGE_TAG_DEFAULT}" >> "${log_file}"
        echo "ARGV=${ARMCTL_ARGV[*]}" >> "${log_file}"
        tr '\n' ';' < "${log_file}"
    )
}
check "install: full box runs every stage in order" \
    "choose_profile full;ensure_docker;acquire_lock;ensure_layout;choose_storage;ensure_ca;make_leaf arm-backend;make_leaf arm-db;make_leaf arm-ui localhost testhost;write_env;write_host_overlay;ensure_nvidia_container_toolkit;install_udev_rule;link_armctl;stack_up;finish_up;ASSUME=ask RAW= MEDIA= PREFIX= TAG=v3.1.0;ARGV=install --profile full;" \
    "$(flow flow-full)"
out="$(flow flow-offload --profile offload)"
has "install: offload runs the walkthrough after storage" "choose_storage;setup_remote_offload;ensure_ca;" "$out"
has "install: offload puts the callback address on the backend certificate" "make_leaf arm-backend 192.168.0.68;" "$out"
lacks "install: offload does not offer the local NVIDIA toolkit" "ensure_nvidia_container_toolkit" "$out"
has "install: offload ends with the verification table" "finish_up;offload_completion_report;" "$out"
has "install: a profile given by flag is not repeated in the restart arguments" "ARGV=install --profile offload;" "$out"
out="$(flow flow-ripper --profile ripper-only)"
lacks "install: ripper-only does not offer the NVIDIA toolkit" "ensure_nvidia_container_toolkit" "$out"
lacks "install: ripper-only has no offload walkthrough" "setup_remote_offload" "$out"
out="$(flow flow-nostart --no-start)"
lacks "install: --no-start does not start the stack" "stack_up" "$out"
has "install: --no-start still configures" "write_env;write_host_overlay;" "$out"
out="$(flow flow-flags --yes --raw-path /r --media-path=/m --image-prefix ghcr.io/fork)"
has "install: flags are parsed in both --x v and --x=v forms" "ASSUME=yes RAW=/r MEDIA=/m PREFIX=ghcr.io/fork TAG=v3.1.0;" "$out"
out="$(flow flow-decline --no-host-changes)"
has "install: --no-host-changes declines host changes" "ASSUME=no " "$out"
out="$( (new_install flow-bad; ARMCTL_RELEASE_DIR="${REL}"; ARMCTL_ARGV=(install); cmd_install --bogus) 2>&1 || true)"
has "install: an unknown option is rejected" "unknown option for install: --bogus" "$out"
out="$( (new_install flow-noval; ARMCTL_RELEASE_DIR="${REL}"; ARMCTL_ARGV=(install); cmd_install --raw-path) 2>&1 || true)"
has "install: an option without its value is rejected" "--raw-path needs a value" "$out"
out="$( (new_install flow-nover; ARMCTL_RELEASE_DIR="${TMPROOT}/empty-rel"; mkdir -p "${ARMCTL_RELEASE_DIR}"; ARMCTL_ARGV=(install); cmd_install) 2>&1 || true)"
has "install: a bundle without VERSION is rejected" "no VERSION file" "$out"
has "install: --help lists the options" "--offload-backend-url" "$(install_usage)"

# layout and summary, for real
new_install layout; ( ensure_layout )
check "layout: certs folder is private" "700" "$(stat -c '%a' "${ARM_DIR}/certs")"
check "layout: state folder is private" "700" "$(stat -c '%a' "${ARM_STATE_DIR}")"
check "layout: logs folder is setgid, group-writable" "2775" "$(stat -c '%a' "${ARM_DIR}/logs")"
for d in db backups scripts iso-library; do
    check "layout: ${d} exists" "yes" "$( [[ -d "${ARM_DIR}/${d}" ]] && echo yes || echo no )"
done
out="$( (SKIPPED=("udev rule (no terminal to ask on)"); print_install_summary 1) )"
has "summary: names the URL" "https://localhost:8081" "$out"
has "summary: lists what was skipped" "udev rule (no terminal to ask on)" "$out"
has "summary: says how to revisit skipped steps" "armctl install" "$out"
out="$( (SKIPPED=(); print_install_summary 0) )"
has "summary: --no-start says how to start" "armctl up" "$out"
lacks "summary: nothing skipped, no skipped section" "skipped during this install" "$out"

# udev: consent gates the write; a current rule asks nothing
udev_case() {  # udev_case <rule current: yes|no> <ARMCTL_ASSUME>
    (
        command() { if [[ "$1" == -v && "$2" == udevadm ]]; then return 0; fi; builtin command "$@"; }
        # eval, so the helper's own $1 is baked into the stub.
        eval "udev_rule_current() { [[ $1 == yes ]]; }"
        ensure_udev_rule() { echo WROTE; }
        sudo() { return 0; }
        ARMCTL_ASSUME="$2"; SKIPPED=()
        install_udev_rule </dev/null
        echo "SKIPPED=${SKIPPED[*]:-}"
    )
}
lacks "udev: a current rule is not rewritten" "WROTE" "$(udev_case yes yes)"
has "udev: with consent the rule is written" "WROTE" "$(udev_case no yes)"
out="$(udev_case no ask)"
lacks "udev: no terminal does not write" "WROTE" "$out"
has "udev: the skip is recorded" "SKIPPED=udev rule" "$out"
```

- [ ] **Step 2: Run it to see it fail**

Run: `bash deploy/tests/test-armctl.sh; echo rc=$?`
Expected: `FAIL` lines for the install checks (`cmd_install: command not found` inside the subshells), `rc=1`.

- [ ] **Step 3: Create `deploy/install/flow.sh`**

```bash
#!/usr/bin/env bash
# shellcheck disable=SC2034 # the flag values assigned here are read by the other modules
# deploy/install/flow.sh: `armctl install`, the staged install.
# Sourced by deploy/armctl.sh after every other module.

install_usage() {
    cat <<'USAGE'
Usage: armctl install [options]

Run with no options to be asked. Every question has a flag, so an install
can also run unattended.

  --profile <full|ripper-only|offload>
                          full: rip and transcode on this host (default)
                          ripper-only: rip here, never transcode here
                          offload: rip here, transcode on another host over ssh
  --raw-path <dir>        folder for raw rips (default: <arm>/raw)
  --media-path <dir>      folder for finished media (default: <arm>/media)
  --yes                   accept every host change: Docker, the NVIDIA toolkit,
                          the udev rule, the armctl link in /usr/local/bin
  --no-host-changes       decline every host change
  --no-start              configure only; do not start the stack
  --rotate-ca             replace the CA and every certificate
  --image-prefix <registry/namespace>
                          pull images from another registry (forks)
  --release-repo <owner/repo>
                          GitHub repo that `armctl upgrade` takes releases from

  Offload profile, for an unattended install:
  --offload-host <ssh://user@host[:port]>
  --offload-backend-url <https://host:port>
  --offload-uidgid <uid:gid>
USAGE
}

# The folders the stack expects. raw/ and media/ are created by choose_storage
# because they may live elsewhere.
ensure_layout() {
    mkdir -p "${ARM_DIR}"/{certs,db,logs,backups,scripts,iso-library} "${ARM_STATE_DIR}"
    chmod 700 "${ARM_DIR}/certs" "${ARM_STATE_DIR}"
    # setgid + group-writable: files ARM creates inherit the folder's group.
    chmod 2775 "${ARM_DIR}/logs"
}

# The host-wide rule that stops a desktop session auto-mounting discs, which
# makes eject fail after a rip. Writing it needs sudo, so it needs consent.
install_udev_rule() {
    if ! command -v udevadm >/dev/null 2>&1; then
        log "udevadm not found; skipping the disc auto-mount rule"
        return 0
    fi
    if udev_rule_current; then
        okline "disc auto-mount rule already in place"
        return 0
    fi
    if consent "udev rule" "Write a udev rule so the desktop stops auto-mounting discs ARM is ripping (needs sudo)?"; then
        # Ask for the sudo password now, so ensure_udev_rule's non-interactive
        # check passes. Without a terminal this fails and ensure_udev_rule
        # prints the commands to run by hand.
        sudo -v || true
        ensure_udev_rule
    else
        warnline "without the rule, a desktop session can hold the disc and block eject after a rip"
    fi
}

print_install_summary() {  # print_install_summary <started 0|1>
    local started="$1" s
    printf '\n'
    if [[ "${started}" -eq 1 ]]; then
        log "ARM is running. Open https://localhost:8081 and follow the setup walkthrough."
    else
        log "ARM is configured but not started. Start it with: ${ARMCTL_CMD} up"
    fi
    log "First-login credentials (you will be asked to change the password):"
    log "  docker exec armv3-backend cat /logs/first-boot.log"
    log "To stop the browser's certificate warning, import ${ARM_CERTS_DIR}/arm-ca.crt"
    log "into your browser or OS trust store."
    log "Everyday commands: ${ARMCTL_CMD} up | down | upgrade | compose ps"
    if [[ ${#SKIPPED[@]} -gt 0 ]]; then
        printf '\n'
        warnline "skipped during this install:"
        for s in "${SKIPPED[@]}"; do
            log "  ${s}"
        done
        log "Run '${ARMCTL_CMD} install' again to revisit them."
    fi
}

cmd_install() {
    local start=1 rotate_ca=0 release_repo="" backend_san args=() a
    OFFLOAD_HOST_ARG=""; OFFLOAD_URL_ARG=""; OFFLOAD_UIDGID_ARG=""
    REMOTE_OFFLOAD=0; REMOTE_DOCKER_HOST=""; REMOTE_BACKEND_URL=""; REMOTE_BACKEND_SAN=""
    REMOTE_TRANSCODE_PUID=""; REMOTE_TRANSCODE_PGID=""; REMOTE_GPUS=""; REMOTE_RENDER_GID=""

    # Accept --key=value as well as --key value.
    for a in "$@"; do
        if [[ "${a}" == --*=* ]]; then
            args+=("${a%%=*}" "${a#*=}")
        else
            args+=("${a}")
        fi
    done
    set -- "${args[@]+"${args[@]}"}"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --profile|--raw-path|--media-path|--image-prefix|--release-repo|--offload-host|--offload-backend-url|--offload-uidgid)
                [[ $# -ge 2 ]] || err "$1 needs a value"
                case "$1" in
                    --profile)             PROFILE_ARG="$2" ;;
                    --raw-path)            RAW_ARG="$2" ;;
                    --media-path)          MEDIA_ARG="$2" ;;
                    --image-prefix)        IMAGE_PREFIX_ARG="$2" ;;
                    --release-repo)        release_repo="$2" ;;
                    --offload-host)        OFFLOAD_HOST_ARG="$2" ;;
                    --offload-backend-url) OFFLOAD_URL_ARG="$2" ;;
                    --offload-uidgid)      OFFLOAD_UIDGID_ARG="$2" ;;
                esac
                shift 2 ;;
            --yes)             ARMCTL_ASSUME=yes; shift ;;
            --no-host-changes) ARMCTL_ASSUME=no; shift ;;
            --no-start)        start=0; shift ;;
            --rotate-ca)       rotate_ca=1; shift ;;
            -h|--help)         install_usage; return 0 ;;
            *) err "unknown option for install: $1 (see: ${ARMCTL_CMD} install --help)" ;;
        esac
    done

    ARM_IMAGE_TAG_DEFAULT="$(cat "${ARMCTL_RELEASE_DIR}/VERSION" 2>/dev/null || true)"
    [[ -n "${ARM_IMAGE_TAG_DEFAULT}" ]] \
        || err "this release bundle has no VERSION file; download the installer again"

    STEP=0; STEP_TOTAL=8
    step "Profile"
    choose_profile
    # ensure_docker may restart this command under the docker group; carry the
    # answer across so the question is not asked twice.
    if [[ -z "${PROFILE_ARG}" ]]; then
        ARMCTL_ARGV+=(--profile "${PROFILE}")
    fi

    step "Host"
    ensure_docker
    acquire_lock
    require openssl "openssl is needed to generate certificates and secrets; install it and run the installer again"
    ensure_layout

    step "Storage"
    choose_storage

    step "Remote transcode offload"
    if [[ "${PROFILE}" == offload ]]; then
        setup_remote_offload
    else
        log "not used by the ${PROFILE} profile"
    fi

    step "Certificates"
    if [[ "${rotate_ca}" -eq 1 ]]; then
        warnline "--rotate-ca replaces the CA: every browser and device that trusted the old one must import the new arm-ca.crt"
        if [[ "${ARMCTL_ASSUME}" != yes ]]; then
            confirm "Replace the CA?" || err "kept the existing CA; nothing was changed"
        fi
        rm -f "${ARM_CERTS_DIR}/arm-ca.key" "${ARM_CERTS_DIR}/arm-ca.crt"
    fi
    ensure_ca
    # With offload, the remote transcoder verifies the backend's certificate
    # against the address it calls back on, so that address must be a SAN.
    backend_san="${REMOTE_BACKEND_SAN:-}"
    if [[ -n "${backend_san}" ]]; then
        make_leaf arm-backend "${backend_san}"
    else
        make_leaf arm-backend
    fi
    make_leaf arm-db
    make_leaf arm-ui localhost "$(hostname -f 2>/dev/null || hostname || echo localhost)"

    step "Configuration"
    write_env
    if [[ -n "${release_repo}" ]]; then
        env_set ARMCTL_RELEASE_REPO "${release_repo}"
    fi
    write_host_overlay
    if [[ "${PROFILE}" == full ]]; then
        ensure_nvidia_container_toolkit
    fi
    install_udev_rule
    link_armctl

    step "Start"
    if [[ "${start}" -eq 1 ]]; then
        stack_up
        finish_up
    else
        log "not starting the stack (--no-start)"
    fi

    step "Finish"
    if offload_persisted; then
        if [[ -z "${REMOTE_RUN+x}" ]]; then
            offload_remote_run_init "$(env_file_value ARM_TRANSCODE_DOCKER_HOST)" \
                "${ARM_DIR}/ssh/id_ed25519" "${ARM_DIR}/ssh/known_hosts"
        fi
        offload_completion_report
    fi
    print_install_summary "${start}"
}
```

- [ ] **Step 4: Wire it into `deploy/armctl.sh`**

1. Module list becomes `for _mod in ui config docker nvidia offload pathlink flow; do`.
2. In `armctl_main`, add to the `case "${cmd}"` block, above `up)`:

```bash
        install) cmd_install "$@" ;;
```

`cmd_install` checks Docker and takes the lock itself, after the profile question.

- [ ] **Step 5: Run the suites**

Run: `bash deploy/tests/test-armctl.sh; echo rc=$?` then `bash deploy/tests/test-bundle.sh; echo rc=$?` then `shellcheck deploy/armctl.sh deploy/install/*.sh deploy/tests/*.sh`
Expected: all `ok`, `rc=0` twice, shellcheck silent.

- [ ] **Step 6: Commit**

```bash
git add deploy/install/flow.sh deploy/armctl.sh deploy/tests/test-armctl.sh
git commit -m "feat(deploy): armctl install, the staged production install

Profile, host, storage, offload, certificates, configuration, start and
finish. Every question has a flag, host changes go through consent, and a
run without a terminal takes defaults and lists what it skipped.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: The bootstrap (`install.sh`)

This task replaces the old installer. Everything still needed from it was copied out in Tasks 1 and 2.

**Files:**
- Modify (full replacement): `install.sh`
- Create: `deploy/tests/test-bootstrap.sh`
- Test: `deploy/tests/test-bootstrap.sh`

**Interfaces:**
- Consumes: `deploy/build-bundle.sh` (checkout mode only); the bundle layout from Task 5.
- Produces (also used by Task 9, which sources this file with `ARM_INSTALL_SOURCE_ONLY=1`):
  - `ARM_RELEASE_REPO` (global, default `automatic-ripping-machine/automatic-ripping-machine`)
  - `bootstrap_resolve_tag` (prints the latest stable v3 tag; exits 1 with a message on failure)
  - `bootstrap_fetch_bundle <tag> <dest dir> [local bundle path]` (verifies the checksum, unpacks into `<dest>`; exits 1 leaving `<dest>` absent or untouched on failure)
  - `bootstrap_arm_dir <prefix>`, `bootstrap_check_target <arm dir>`, `bootstrap_write_launcher <arm dir>`, `bootstrap_handover <launcher> <args...>`, `bootstrap_uid`, `bootstrap_main`.
  - The generated launcher `<arm>/armctl`, which exports `ARM_DIR` and runs `<arm>/.armctl/current/armctl.sh`.

- [ ] **Step 1: Write the failing suite, `deploy/tests/test-bootstrap.sh`**

```bash
#!/usr/bin/env bash
# shellcheck disable=SC2317,SC2329,SC2034,SC2030,SC2031
# Zero-infra suite for the installer bootstrap (root install.sh): no docker,
# no root, no network. Sources install.sh through ARM_INSTALL_SOURCE_ONLY.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${HERE}/.."
ROOT="$(cd "${DEPLOY}/.." && pwd)"

export ARM_INSTALL_SOURCE_ONLY=1
# shellcheck disable=SC1091
source "${ROOT}/install.sh"

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
has()   { check "$1" "yes" "$( [[ "$3" == *"$2"* ]] && echo yes || echo no )"; }
lacks() { check "$1" "no"  "$( [[ "$3" == *"$2"* ]] && echo yes || echo no )"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- where the arm folder goes (Review Focus 2) -----------------------------------
check "prefix names the parent folder" "/srv/arm" "$(bootstrap_arm_dir /srv)"
check "a prefix that already ends in arm is the arm folder itself" "/srv/arm" "$(bootstrap_arm_dir /srv/arm)"
check "a trailing slash changes nothing" "/srv/arm" "$(bootstrap_arm_dir /srv/arm/)"

# --- an existing folder that is not ours (Review Focus 3) -------------------------
rc=0; (bootstrap_check_target "${TMP}/absent/arm") >/dev/null 2>&1 || rc=$?
check "a folder that does not exist yet is fine" "0" "$rc"
mkdir -p "${TMP}/empty/arm"
rc=0; (bootstrap_check_target "${TMP}/empty/arm") >/dev/null 2>&1 || rc=$?
check "an empty folder is fine" "0" "$rc"
mkdir -p "${TMP}/ours/arm/.armctl" "${TMP}/ours/arm/media"
rc=0; (bootstrap_check_target "${TMP}/ours/arm") >/dev/null 2>&1 || rc=$?
check "an existing armctl install is fine (re-run)" "0" "$rc"
mkdir -p "${TMP}/v2/arm/media" "${TMP}/v2/arm/config"
rc=0; out="$( (bootstrap_check_target "${TMP}/v2/arm") 2>&1)" || rc=$?
check "an ARM v2 home is refused" "1" "$rc"
has "the refusal says it was not created by this installer" "was not created by this installer" "$out"
has "the refusal says how to choose another place" "--prefix" "$out"
mkdir -p "${TMP}/oldv3/arm"; echo x > "${TMP}/oldv3/arm/docker-compose.yml"
rc=0; (bootstrap_check_target "${TMP}/oldv3/arm") >/dev/null 2>&1 || rc=$?
check "the old v3 installer's layout is refused" "1" "$rc"
check "a refused folder is left untouched" "x" "$(cat "${TMP}/oldv3/arm/docker-compose.yml")"
mkdir -p "${TMP}/file"; echo x > "${TMP}/file/arm"
rc=0; (bootstrap_check_target "${TMP}/file/arm") >/dev/null 2>&1 || rc=$?
check "a file named arm is refused" "1" "$rc"

# --- picking the release ----------------------------------------------------------
tagfor() {  # tagfor <curl stub body>
    ( eval "curl() { $1; }"; bootstrap_resolve_tag )
}
check "latest stable v3 tag is used" "v3.1.0" "$(tagfor 'echo "{ \"tag_name\": \"v3.1.0\", \"name\": \"x\" }"' 2>/dev/null)"
rc=0; out="$(tagfor 'echo "{ \"tag_name\": \"2.21.5\" }"' 2>&1)" || rc=$?
check "a v2 release is refused" "1" "$rc"
has "the v2 refusal explains" "not a v3 release" "$out"
rc=0; out="$(tagfor 'return 22' 2>&1)" || rc=$?
check "an unreachable GitHub is an error" "1" "$rc"
has "the error says what to try" "--version" "$out"

# --- fetching and verifying a bundle ----------------------------------------------
archive="$(bash "${DEPLOY}/build-bundle.sh" v3.9.9 "${TMP}/out")"
( bootstrap_fetch_bundle v3.9.9 "${TMP}/rel/v3.9.9" "${archive}" ) >/dev/null
check "a good bundle is unpacked" "yes" "$( [[ -x "${TMP}/rel/v3.9.9/armctl.sh" && -f "${TMP}/rel/v3.9.9/lib/common.sh" ]] && echo yes || echo no )"
check "no partial folder is left behind" "no" "$( [[ -e "${TMP}/rel/v3.9.9.partial" ]] && echo yes || echo no )"

mkdir -p "${TMP}/bad"; cp "${archive}" "${TMP}/bad/b.tar.gz"
echo "0000000000000000000000000000000000000000000000000000000000000000  b.tar.gz" > "${TMP}/bad/b.tar.gz.sha256"
rc=0; out="$( (bootstrap_fetch_bundle v3.9.9 "${TMP}/rel/tampered" "${TMP}/bad/b.tar.gz") 2>&1)" || rc=$?
check "a checksum mismatch is refused" "1" "$rc"
has "the mismatch is named" "checksum" "$out"
check "nothing is unpacked from a bad bundle" "no" "$( [[ -e "${TMP}/rel/tampered" ]] && echo yes || echo no )"

mkdir -p "${TMP}/evil-src"; echo pwned > "${TMP}/evil-src/evil"
tar -P -C "${TMP}/evil-src" --transform 's|^evil$|../evil|' -czf "${TMP}/bad/e.tar.gz" evil 2>/dev/null
(cd "${TMP}/bad" && sha256sum e.tar.gz > e.tar.gz.sha256)
rc=0; out="$( (bootstrap_fetch_bundle v3.9.9 "${TMP}/rel/escape" "${TMP}/bad/e.tar.gz") 2>&1)" || rc=$?
check "an archive that escapes its folder is refused" "1" "$rc"
check "the escaping file was not written" "no" "$( [[ -e "${TMP}/rel/evil" ]] && echo yes || echo no )"

rc=0; out="$( (curl() { return 22; }; bootstrap_fetch_bundle v3.9.9 "${TMP}/rel/offline") 2>&1)" || rc=$?
check "a failed download is an error" "1" "$rc"
check "a failed download leaves no folder" "no" "$( [[ -e "${TMP}/rel/offline" ]] && echo yes || echo no )"

# An existing release folder is only replaced once the new one is complete.
mkdir -p "${TMP}/rel/keep"; echo old > "${TMP}/rel/keep/marker"
( bootstrap_fetch_bundle v3.9.9 "${TMP}/rel/keep" "${TMP}/bad/b.tar.gz" ) >/dev/null 2>&1 || true
check "a failed fetch leaves an existing release as it was" "old" "$(cat "${TMP}/rel/keep/marker")"

# --- the whole bootstrap, with the handover recorded ------------------------------
# boot <case name> [install.sh args...]
boot() {
    (
        HOME="${TMP}/$1/home"; mkdir -p "${HOME}"; shift
        bootstrap_uid() { echo 1000; }
        bootstrap_handover() { echo "HANDOVER ARM_DIR=${ARM_DIR} ARGS=$*"; }
        bootstrap_main "$@"
    )
}
out="$(boot default --bundle "${archive}" --version v3.9.9 --profile ripper-only --yes)"
arm="${TMP}/default/home/arm"
has "default location is ~/arm" "HANDOVER ARM_DIR=${arm} " "$out"
has "the launcher is what gets run, with install first" "ARGS=${arm}/armctl install " "$out"
has "flags the bootstrap does not own are passed through" "--profile ripper-only --yes" "$out"
lacks "the bootstrap's own flags are not passed through" "--bundle" "$out"
check "the release is unpacked under .armctl" "yes" "$( [[ -f "${arm}/.armctl/releases/v3.9.9/armctl.sh" ]] && echo yes || echo no )"
check "current points at the release" "releases/v3.9.9" "$(readlink "${arm}/.armctl/current")"
check "the launcher is executable" "yes" "$( [[ -x "${arm}/armctl" ]] && echo yes || echo no )"

out="$(boot prefixed --prefix "${TMP}/prefixed/srv" --bundle "${archive}" --version v3.9.9)"
has "--prefix names the parent" "ARM_DIR=${TMP}/prefixed/srv/arm " "$out"
out="$(boot repo --bundle "${archive}" --version v3.9.9 --release-repo me/fork)"
has "--release-repo is also passed on, for upgrades" "--release-repo me/fork" "$out"

# A user named `arm` has HOME=/home/arm; the default must still be ~/arm.
out="$( (HOME="${TMP}/userarm/arm"; mkdir -p "${HOME}"; echo dotfile > "${HOME}/.profile"
         bootstrap_uid() { echo 1000; }; bootstrap_handover() { echo "HANDOVER ARM_DIR=${ARM_DIR}"; }
         bootstrap_main --bundle "${archive}" --version v3.9.9) )"
has "a home folder named arm does not become the install folder" "ARM_DIR=${TMP}/userarm/arm/arm" "$out"

rc=0; out="$( (bootstrap_uid() { echo 0; }; bootstrap_main --bundle "${archive}" --version v3.9.9) 2>&1)" || rc=$?
check "root is refused" "1" "$rc"
has "the root refusal explains" "as root" "$out"
rc=0; out="$( (bootstrap_uid() { echo 1000; }; HOME="${TMP}/nover"; mkdir -p "${HOME}"; cd "${TMP}"; bootstrap_main --bundle "${archive}") 2>&1)" || rc=$?
check "--bundle without --version is refused" "1" "$rc"
has "the refusal says --version is needed" "--bundle needs --version" "$out"
mkdir -p "${TMP}/v2home/home/arm/media"
rc=0; out="$( (HOME="${TMP}/v2home/home"; bootstrap_uid() { echo 1000; }; bootstrap_handover() { echo HANDOVER; }
              bootstrap_main --bundle "${archive}" --version v3.9.9) 2>&1)" || rc=$?
check "a foreign arm folder stops the bootstrap" "1" "$rc"
lacks "nothing is handed over" "HANDOVER" "$out"
check "nothing was added to the foreign folder" "media" "$(cd "${TMP}/v2home/home/arm" && echo *)"

# --- the generated launcher -------------------------------------------------------
L="${TMP}/launch/arm"; mkdir -p "${L}/.armctl/releases/v1"
# shellcheck disable=SC2016 # the fake armctl.sh must expand these itself, at run time
printf '#!/usr/bin/env bash\necho "ARM_DIR=${ARM_DIR} ARGS=$*"\n' > "${L}/.armctl/releases/v1/armctl.sh"
chmod 755 "${L}/.armctl/releases/v1/armctl.sh"
ln -s releases/v1 "${L}/.armctl/current"
bootstrap_write_launcher "${L}"
check "the launcher runs the current release with ARM_DIR set" "ARM_DIR=${L} ARGS=up --force" "$("${L}/armctl" up --force)"
mkdir -p "${TMP}/bin"; ln -s "${L}/armctl" "${TMP}/bin/armctl"
check "the launcher works through a PATH link" "ARM_DIR=${L} ARGS=down" "$(cd / && "${TMP}/bin/armctl" down)"

exit "$fail"
```

- [ ] **Step 2: Run it to see it fail**

Run: `bash deploy/tests/test-bootstrap.sh; echo rc=$?`
Expected: fails early with `bootstrap_arm_dir: command not found` (the old `install.sh` defines none of these functions).

- [ ] **Step 3: Replace `install.sh` with the bootstrap**

The whole file becomes:

```bash
#!/usr/bin/env bash
# ARM v3 installer.
#
# This file is only a bootstrap. It picks a release, downloads that release's
# installer bundle into <location>/arm/.armctl/releases/<tag>/, writes the
# `armctl` launcher, and hands over to `armctl install`, which does the rest.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/install.sh | bash
#   bash install.sh                      # install into ~/arm
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

# bootstrap_fetch_bundle <tag> <dest dir> [local bundle path]
# Download (or copy) the bundle and its checksum, verify, and unpack into
# <dest>. On any failure <dest> is left exactly as it was: the bundle is
# unpacked beside it first and moved into place only when complete.
bootstrap_fetch_bundle() {
    local tag="$1" dest="$2" local_bundle="${3:-}" tmp archive base want got
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
            --version)        [[ $# -ge 2 ]] || bootstrap_err "--version needs a release tag"; version="$2"; shift 2 ;;
            --version=*)      version="${1#*=}"; shift ;;
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

    mkdir -p "${arm_dir}/.armctl/releases"
    chmod 700 "${arm_dir}/.armctl"
    bootstrap_fetch_bundle "${tag}" "${arm_dir}/.armctl/releases/${tag}" "${bundle}"
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
```

In the test `bootstrap_check_target` runs before the release folder is created, so a refused folder gains nothing: that is what the `nothing was added to the foreign folder` check pins.

- [ ] **Step 4: Run every shell suite**

```bash
for t in deploy/tests/test-bootstrap.sh deploy/tests/test-bundle.sh deploy/tests/test-armctl.sh deploy/tests/test-stack-contract.sh devtools/test-setup-dev.sh devtools/test-install-walkthrough.sh; do
    bash "$t" > /dev/null 2>&1 && echo "PASS $t" || echo "FAIL $t"
done
shellcheck install.sh deploy/*.sh deploy/lib/*.sh deploy/install/*.sh deploy/tests/*.sh
```

Expected: six `PASS` lines; shellcheck silent.

- [ ] **Step 5: Commit**

```bash
git add install.sh deploy/tests/test-bootstrap.sh
git commit -m "feat(install)!: install.sh becomes a bootstrap for the release bundle

Picks a release, downloads and verifies its installer bundle into
<location>/arm/.armctl, writes the armctl launcher and hands over to
armctl install. Refuses root and any existing folder it did not create.

BREAKING CHANGE: --certs-only, --no-env, --no-compose, --no-udev and
--start are gone, and --prefix now names the folder the arm folder goes in.
Installs made by the previous installer are not migrated.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: `armctl upgrade`

**Files:**
- Modify: `deploy/armctl.sh`, `deploy/tests/test-armctl.sh`
- Test: `deploy/tests/test-armctl.sh`

**Interfaces:**
- Consumes: `bootstrap_resolve_tag`, `bootstrap_fetch_bundle` (from the release's own `install.sh`), `env_merge_new_keys`, `write_image_pins`, `use_env_file`, `select_up_services`, `pull_images`, `verify_images_present`, `guard_running_spawned`, `refresh_arm_gpus`, `backup_db`, `go_live`, `finish_up`.
- Produces: `cmd_upgrade [--version <tag>] [--bundle <file>] [--force] [--no-backup] [--no-pull]`, `cmd_apply_upgrade --from <tag> --to <tag> [--force] [--no-backup] [--no-pull]` (internal; run from the new release), `run_new_release <armctl.sh> <args...>`, `after_switch_failure <from> <to>`, `prune_releases <keep>...`.

The old release downloads the new bundle and then runs the **new** release's `armctl.sh apply-upgrade`, so the code that performs the upgrade matches the stack being upgraded to. Nothing live changes until the switch inside `cmd_apply_upgrade`.

- [ ] **Step 1: Add the failing checks to `deploy/tests/test-armctl.sh`**

Insert before the `# --- dispatch ---` section:

```bash
# --- upgrade: the old release fetches, then hands over ------------------------------
# upgrade_case <name> <resolved tag> <fetch: ok|fail> [upgrade args...]
upgrade_case() {
    (
        ARM_DIR="${TMPROOT}/$1/arm"; mkdir -p "${ARM_DIR}/.armctl/releases/v3.1.0"; armctl_settings
        ln -sfn releases/v3.1.0 "${ARM_STATE_DIR}/current"
        printf 'ARMCTL_PROFILE=full\nARM_IMAGE_TAG=v3.1.0\n' > "${ENV_FILE}"
        resolved="$2"; fetch="$3"; shift 3
        ARMCTL_RELEASE_DIR="${TMPROOT}/fake-rel"; mkdir -p "${ARMCTL_RELEASE_DIR}"
        log_file="${TMPROOT}/upgrade.log"; : > "${log_file}"
        # The release's own install.sh, as a stub.
        cat > "${ARMCTL_RELEASE_DIR}/install.sh" <<'STUB'
bootstrap_resolve_tag() { printf '%s' "${resolved}"; }
bootstrap_fetch_bundle() {
    echo "fetch $1 [${3:-}]" >> "${log_file}"
    if [[ "${fetch}" == fail ]]; then echo "ERROR: download failed" >&2; exit 1; fi
    mkdir -p "$2"
}
STUB
        run_new_release() { echo "handover $*" >> "${log_file}"; }
        rc=0; ( cmd_upgrade "$@" ) > "${TMPROOT}/upgrade.out" 2>&1 || rc=$?
        echo "rc=${rc}" >> "${log_file}"
        echo "TAG=$(grep '^ARM_IMAGE_TAG=' "${ENV_FILE}" | cut -d= -f2)" >> "${log_file}"
        echo "CURRENT=$(readlink "${ARM_STATE_DIR}/current")" >> "${log_file}"
        tr '\n' ';' < "${log_file}"
        cat "${TMPROOT}/upgrade.out"
    )
}
out="$(upgrade_case upg-same v3.1.0 ok)"
has "upgrade: already on the latest does nothing" "already on v3.1.0" "$out"
lacks "upgrade: already on the latest fetches nothing" "fetch " "$out"
out="$(upgrade_case upg-new v3.2.0 ok --force)"
has "upgrade: the new bundle is fetched" "fetch v3.2.0 []" "$out"
has "upgrade: the NEW release carries out the upgrade" "handover ${TMPROOT}/upg-new/arm/.armctl/releases/v3.2.0/armctl.sh apply-upgrade --from v3.1.0 --to v3.2.0 --force" "$out"
has "upgrade: the old release changes nothing itself" "TAG=v3.1.0;CURRENT=releases/v3.1.0;" "$out"
out="$(upgrade_case upg-named v3.2.0 ok --version v3.1.5)"
has "upgrade: --version names the target" "fetch v3.1.5 []" "$out"
out="$(upgrade_case upg-offline v3.2.0 fail)"
has "upgrade: a failed download stops" "rc=1" "$out"
lacks "upgrade: a failed download hands nothing over" "handover" "$out"
has "upgrade: a failed download leaves the install as it was" "TAG=v3.1.0;CURRENT=releases/v3.1.0;" "$out"
out="$(upgrade_case upg-bundle v3.2.0 ok --bundle /tmp/b.tar.gz)"
has "upgrade: --bundle without --version is refused" "--bundle needs --version" "$out"

# --- upgrade: the new release applies it ----------------------------------------------
# apply_case <name> <FAIL_AT step or ''>
apply_case() {
    (
        ARM_DIR="${TMPROOT}/$1/arm"; state="${ARM_DIR}/.armctl"
        mkdir -p "${state}/releases/v3.0.0" "${state}/releases/v3.1.0" "${state}/releases/v3.2.0"
        armctl_settings
        ln -sfn releases/v3.1.0 "${ARM_STATE_DIR}/current"
        printf 'ARMCTL_PROFILE=full\nARM_IMAGE_PREFIX=reg\nARM_IMAGE_TAG=v3.1.0\nARM_RIPPER_IMAGE=reg/arm-ripper:v3.1.0\n' > "${ENV_FILE}"
        chmod 600 "${ENV_FILE}"
        ARMCTL_RELEASE_DIR="${REL}"; IMAGE_PREFIX_ARG=""
        fail_at="$2"
        log_file="${TMPROOT}/apply.log"; : > "${log_file}"
        for fn in "${STEPS[@]}"; do
            eval "${fn}() { echo ${fn} >> \"\${log_file}\"; if [[ \"\${fail_at}\" == ${fn} ]]; then exit 1; fi; }"
        done
        backend_started_at() { echo T1; }
        published_url() { :; }
        compose() { echo "compose $*" >> "${log_file}"; }
        HEALTH_RESULT="backend healthy"
        rc=0; ( cmd_apply_upgrade --from v3.1.0 --to v3.2.0 ) > "${TMPROOT}/apply.out" 2>&1 || rc=$?
        echo "rc=${rc}" >> "${log_file}"
        echo "TAG=$(grep '^ARM_IMAGE_TAG=' "${ARM_STATE_DIR}/.env" | cut -d= -f2)" >> "${log_file}"
        echo "RIPPER=$(grep '^ARM_RIPPER_IMAGE=' "${ARM_STATE_DIR}/.env" | cut -d= -f2)" >> "${log_file}"
        echo "CURRENT=$(readlink "${ARM_STATE_DIR}/current")" >> "${log_file}"
        echo "RELEASES=$(cd "${ARM_STATE_DIR}/releases" && echo *)" >> "${log_file}"
        echo "MODE=$(stat -c '%a' "${ARM_STATE_DIR}/.env")" >> "${log_file}"
        tr '\n' ';' < "${log_file}"
        cat "${TMPROOT}/apply.out"
    )
}
out="$(apply_case apply-ok '')"
has "apply: pull, verify, guard and backup all come before the switch" \
    "select_up_services;pull_images;verify_images_present;guard_running_spawned;refresh_arm_gpus;backup_db;remove_spawned_containers;remove_retired_services;compose up -d --no-build;respawn_rippers_if_needed;wait_for_backend;rc=0;" "$out"
has "apply: .env is on the new release" "TAG=v3.2.0;RIPPER=reg/arm-ripper:v3.2.0;" "$out"
has "apply: current points at the new release" "CURRENT=releases/v3.2.0;" "$out"
has "apply: the previous release is kept, older ones pruned" "RELEASES=v3.1.0 v3.2.0;" "$out"
has "apply: .env stays private" "MODE=600;" "$out"
has "apply: the switch is announced" "switched to v3.2.0" "$out"

for step in pull_images verify_images_present guard_running_spawned backup_db; do
    out="$(apply_case "apply-${step}" "${step}")"
    has "apply: a failure at ${step} stops the upgrade" "rc=1;" "$out"
    has "apply: a failure at ${step} leaves .env on the old release" "TAG=v3.1.0;RIPPER=reg/arm-ripper:v3.1.0;" "$out"
    has "apply: a failure at ${step} leaves current on the old release" "CURRENT=releases/v3.1.0;" "$out"
    lacks "apply: a failure at ${step} removes no container" "remove_spawned_containers" "$out"
done

out="$(apply_case apply-unhealthy wait_for_backend)"
has "apply: an unhealthy backend after the switch is an error" "rc=1;" "$out"
has "apply: the install stays on the new release" "TAG=v3.2.0;" "$out"
has "apply: the user is told it was not rolled back, and why" "not rolled back" "$out"
has "apply: the previous release is still there for a manual rollback" "RELEASES=v3.0.0 v3.1.0 v3.2.0;" "$out"
has "apply: the user is told where the previous release is" "releases/v3.1.0" "$out"
```

- [ ] **Step 2: Run it to see it fail**

Run: `bash deploy/tests/test-armctl.sh; echo rc=$?`
Expected: `FAIL` lines for the upgrade checks (`cmd_upgrade: command not found`), `rc=1`.

- [ ] **Step 3: Add the upgrade commands to `deploy/armctl.sh`**

Insert after `cmd_down`:

```bash
# Its own function so tests can replace it: `exec` cannot be stubbed. The
# lock (fd 9) and ARMCTL_LOCK_HELD pass to the new process.
run_new_release() {
    exec "$@"
}

# Remove every release folder except the ones named.
prune_releases() {
    local dir name keep k
    for dir in "${ARM_STATE_DIR}/releases"/*/; do
        [[ -d "${dir}" ]] || continue
        name="$(basename "${dir}")"
        keep=0
        for k in "$@"; do
            if [[ "${name}" == "${k}" ]]; then
                keep=1
            fi
        done
        if [[ "${keep}" -eq 0 ]]; then
            rm -rf "${ARM_STATE_DIR}/releases/${name}"
        fi
    done
}

after_switch_failure() {
    local from="$1" to="$2" f newest=""
    for f in "${ARM_DIR}/backups"/pg-backup-*.sql.gz; do
        if [[ -f "${f}" ]]; then
            newest="${f}"
        fi
    done
    arm_err "the stack was switched to ${to}, but the backend did not become healthy."
    arm_sub "The install is now on ${to}. It was not rolled back, because database migrations cannot be reversed."
    if [[ -n "${newest}" ]]; then
        arm_sub "Database backup from before the switch: ${newest}"
    fi
    arm_sub "Previous release kept at: ${ARM_STATE_DIR}/releases/${from}"
    arm_sub "Logs: ${ARMCTL_CMD} compose logs ${BACKEND_SERVICE}"
    arm_sub "To go back by hand, see 'Rolling back' on the Upgrading page of the ARM docs."
}

# Runs in the release that is currently installed: pick the target, download
# and verify its bundle, then let the NEW release's armctl do the upgrade.
cmd_upgrade() {
    local version="" bundle="" pass=() current target repo new_dir
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --version)
                if [[ $# -lt 2 ]]; then arm_err "--version needs a release tag"; exit 2; fi
                version="$2"; shift 2 ;;
            --bundle)
                if [[ $# -lt 2 ]]; then arm_err "--bundle needs a file"; exit 2; fi
                bundle="$2"; shift 2 ;;
            --force|--no-backup|--no-pull) pass+=("$1"); shift ;;
            *) arm_err "unknown option for upgrade: $1"; exit 2 ;;
        esac
    done
    require_installed
    if [[ -n "${bundle}" && -z "${version}" ]]; then
        arm_err "--bundle needs --version <tag>, the release the bundle is for"
        exit 2
    fi
    # The bootstrap's release lookup and bundle fetch, from this release's copy.
    # shellcheck source=/dev/null
    ARM_INSTALL_SOURCE_ONLY=1 source "${ARMCTL_RELEASE_DIR}/install.sh"
    repo="$(env_file_value ARMCTL_RELEASE_REPO)"
    if [[ -n "${repo}" ]]; then
        ARM_RELEASE_REPO="${repo}"
    fi
    current="$(env_file_value ARM_IMAGE_TAG)"
    if [[ -n "${version}" ]]; then
        target="${version}"
    else
        target="$(bootstrap_resolve_tag)"
    fi
    if [[ "${target}" == "${current}" ]]; then
        arm_say "already on ${current}; nothing to upgrade"
        return 0
    fi
    arm_say "upgrading ${current} to ${target}"
    new_dir="${ARM_STATE_DIR}/releases/${target}"
    bootstrap_fetch_bundle "${target}" "${new_dir}" "${bundle}"
    run_new_release "${new_dir}/armctl.sh" apply-upgrade --from "${current}" --to "${target}" "${pass[@]+"${pass[@]}"}"
}

# Runs in the NEW release. Everything up to "The switch" works on a candidate
# .env and leaves the running install exactly as it was.
cmd_apply_upgrade() {
    local from="" to="" live_env env_next
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --from)      from="$2"; shift 2 ;;
            --to)        to="$2"; shift 2 ;;
            --force)     FORCE=1; shift ;;
            --no-backup) NO_BACKUP=1; shift ;;
            --no-pull)   NO_PULL=1; shift ;;
            *) arm_err "unknown option for apply-upgrade: $1"; exit 2 ;;
        esac
    done
    if [[ -z "${from}" || -z "${to}" ]]; then
        arm_err "apply-upgrade is run by 'armctl upgrade'; do not call it directly"
        exit 2
    fi
    require_installed
    load_profile
    ARM_HINT_FORCE_CMD="${ARMCTL_CMD} upgrade --force"
    ARM_HINT_IMAGES_READY="The new images are pulled"

    # The candidate .env: the live one, plus any settings this release adds,
    # with every image pinned to the new release.
    live_env="${ENV_FILE}"
    env_next="${ARM_STATE_DIR}/.env.next"
    rm -f "${env_next}"
    cp -p "${live_env}" "${env_next}"
    env_merge_new_keys "${ARMCTL_RELEASE_DIR}/.env.example" "${env_next}"
    write_image_pins "${to}" "${env_next}"
    use_env_file "${env_next}"

    select_up_services
    pull_images
    verify_images_present
    guard_running_spawned
    refresh_arm_gpus
    backup_db

    # The switch. From here the install is on the new release.
    mv "${env_next}" "${live_env}"
    use_env_file "${live_env}"
    ln -sfn "releases/${to}" "${ARM_STATE_DIR}/current"
    arm_say "switched to ${to}"

    go_live
    if ! ( finish_up ); then
        after_switch_failure "${from}" "${to}"
        exit 1
    fi
    prune_releases "${to}" "${from}"
    arm_say "upgrade to ${to} complete"
}
```

In `armctl_main`, add to the `case "${cmd}"` block, above `compose)`:

```bash
        upgrade)       require_docker_ready; acquire_lock; cmd_upgrade "$@" ;;
        apply-upgrade) require_docker_ready; acquire_lock; cmd_apply_upgrade "$@" ;;
```

- [ ] **Step 4: Run every shell suite**

```bash
for t in deploy/tests/test-armctl.sh deploy/tests/test-bootstrap.sh deploy/tests/test-bundle.sh deploy/tests/test-stack-contract.sh devtools/test-setup-dev.sh devtools/test-install-walkthrough.sh; do
    bash "$t" > /dev/null 2>&1 && echo "PASS $t" || echo "FAIL $t"
done
shellcheck install.sh deploy/*.sh deploy/lib/*.sh deploy/install/*.sh deploy/tests/*.sh
```

Expected: six `PASS` lines; shellcheck silent.

- [ ] **Step 5: Commit**

```bash
git add deploy/armctl.sh deploy/tests/test-armctl.sh
git commit -m "feat(deploy): armctl upgrade

The installed release downloads and verifies the new bundle, then the new
release's armctl pulls, checks the images, runs the guard and backs up the
database against a candidate .env before switching. A failure before the
switch leaves the install untouched; after it, the user is told what
happened and where the backup and the previous release are.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: CI and the release pipeline

**Files:**
- Modify: `.github/workflows/ci.yml`, `.github/workflows/release.yml`

**Interfaces:**
- Consumes: the four suites under `deploy/tests/`, `deploy/build-bundle.sh`.
- Produces: release assets `arm-installer-<tag>.tar.gz` and `arm-installer-<tag>.tar.gz.sha256` on the GitHub release named `<tag>`, which is what `bootstrap_fetch_bundle` downloads.

- [ ] **Step 1: Add the suites to the `test-shell` job in `.github/workflows/ci.yml`**

Replace the comment and step for the installer walkthrough suite:

```yaml
      # Zero-infra unit test for the remote-offload walkthrough and the
      # production output helpers in deploy/install (no docker, no root, <1s).
      - name: Offload walkthrough suite
        run: bash devtools/test-install-walkthrough.sh
```

Then add, after the `setup-dev / compose template suite` step:

```yaml
      # Zero-infra suites for the production installer: the armctl launcher,
      # the install.sh bootstrap, the release bundle, and the layered compose
      # stack production runs (docker compose config; the runner has docker).
      - name: armctl suite
        run: bash deploy/tests/test-armctl.sh
      - name: Installer bootstrap suite
        run: bash deploy/tests/test-bootstrap.sh
      - name: Release bundle suite
        run: bash deploy/tests/test-bundle.sh
      - name: Production stack contract suite
        run: bash deploy/tests/test-stack-contract.sh
```

The bundle suite packs the bundle on every PR, so a packaging break is caught before a tag.

- [ ] **Step 2: Add the bundle job to `.github/workflows/release.yml`**

Append to `jobs:` (same indentation as `publish:`):

```yaml
  bundle:
    name: publish (installer bundle)
    # Only after every image leg has published: the installer pins the images
    # of the release it is attached to.
    needs: publish
    runs-on: ubuntu-latest
    permissions:
      contents: write   # create the GitHub release if it is missing, attach the bundle
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1

      - name: Pack the installer bundle
        run: bash deploy/build-bundle.sh "${GITHUB_REF_NAME}" dist

      - name: Attach it to the GitHub release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          tag="${GITHUB_REF_NAME}"
          if ! gh release view "${tag}" >/dev/null 2>&1; then
            # A tag with a hyphen (v3.1.0-rc1) is a pre-release, so the
            # installer's "latest stable" lookup skips it.
            pre=()
            if [[ "${tag}" == *-* ]]; then pre=(--prerelease); fi
            gh release create "${tag}" --title "${tag}" --generate-notes --verify-tag "${pre[@]}"
          fi
          gh release upload "${tag}" \
            "dist/arm-installer-${tag}.tar.gz" \
            "dist/arm-installer-${tag}.tar.gz.sha256" \
            --clobber
```

In the header comment of `release.yml`, add one line to the list of what a release publishes: `#   - the installer bundle (deploy/build-bundle.sh), attached to the GitHub release`.

- [ ] **Step 3: Validate the workflow files**

Run: `uv run pre-commit run --files .github/workflows/ci.yml .github/workflows/release.yml`
Expected: all hooks pass. Then confirm the pinning rule by eye: `grep -n 'uses:' .github/workflows/release.yml | grep -v '@[0-9a-f]\{40\} # v'` prints nothing.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/release.yml
git commit -m "ci: run the installer suites and publish the installer bundle

CI runs the armctl, bootstrap, bundle and stack-contract suites. A release
tag packs the installer bundle and attaches it, with its checksum, to the
GitHub release once every image has published.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: Install drill, docs and memory

**Files:**
- Create: `devtools/install-drill.sh`
- Modify: `docs/user/Getting-Started.md`, `docs/user/Upgrading.md`, `docs/user/Uninstall.md`, `docs/user/Home.md`, `docs/user/FAQ.md`, `docs/user/Configuring-ARM.md`, `docs/user/Troubleshooting.md`, `docs/user/Hardware-Transcoding.md`, `docs/developers/architecture/06-deployment.md`, `docs/developers/architecture/05-cross-cutting.md`, `docs/developers/architecture/02-job-lifecycle.md`, `devtools/README.md`, `.env.example` (comments only), `CLAUDE.md`, `.claude/memory/*`

**Before staging anything in this task:** `CLAUDE.md` and `.claude/memory/MEMORY.md` had uncommitted edits by the owner when this branch was cut. Run `git status --short CLAUDE.md .claude/memory/`. If either shows changes you did not make, stop and ask the owner to commit or stash them first; do not fold them into this work.

- [ ] **Step 1: Create `devtools/install-drill.sh`**

```bash
#!/usr/bin/env bash
# devtools/install-drill.sh: end-to-end drill of the production installer
# against images built from this checkout. Manual, not in CI.
#
# It installs into a throwaway folder with the ripper-only profile, starts the
# stack, checks the backend's health, runs `armctl down`, and removes what it
# created. No host changes are made (--no-host-changes).
#
# Run it on a host that has NO ARM v3 stack: the stack's container names and
# its data volume are fixed (armv3-*, armv3_arm-data), so a drill beside a dev
# stack or a real install would collide with it. The script refuses if it
# finds either.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PFX="arm-drill"
TAG="drill"

# Captured first: with pipefail, `docker ... | grep -q` can report failure when
# grep matches and exits early, which would skip this guard.
containers="$(docker ps -a --format '{{.Names}}')"
volumes="$(docker volume ls -q)"
if grep -q '^armv3-' <<<"${containers}" || grep -qx 'armv3_arm-data' <<<"${volumes}"; then
    echo "ERROR: an ARM v3 stack or its data volume already exists on this host." >&2
    echo "       Run the drill on a host without one (bash devtools/setup-dev.sh down does not remove the volume)." >&2
    exit 1
fi

WORK="$(mktemp -d)"
cleanup() {
    echo "==> cleaning up"
    if [[ -x "${WORK}/arm/armctl" ]]; then
        "${WORK}/arm/armctl" down --force >/dev/null 2>&1 || true
    fi
    docker volume rm armv3_arm-data >/dev/null 2>&1 || true
    # The database folder is written by the postgres container's user.
    docker run --rm -v "${WORK}:/w" postgres:18 sh -c 'rm -rf /w/arm' >/dev/null 2>&1 || true
    rm -rf "${WORK}"
}
trap cleanup EXIT

echo "==> building images from this checkout as ${PFX}/arm-*:${TAG}"
docker build -q -f "${ROOT}/services/backend/Dockerfile" -t "${PFX}/arm-backend:${TAG}" "${ROOT}"
docker build -q -f "${ROOT}/services/ripper/Dockerfile"  -t "${PFX}/arm-ripper:${TAG}"  "${ROOT}"
docker build -q -f "${ROOT}/services/ui-neu/Dockerfile"  -t "${PFX}/arm-ui:${TAG}"      "${ROOT}"
docker pull -q postgres:18

echo "==> packing the bundle"
bundle="$(bash "${ROOT}/deploy/build-bundle.sh" "${TAG}" "${WORK}/bundle")"

echo "==> installing into ${WORK}/arm (ripper-only, no host changes, not started)"
bash "${ROOT}/install.sh" --prefix "${WORK}" --bundle "${bundle}" --version "${TAG}" \
    --profile ripper-only --image-prefix "${PFX}" --no-host-changes --no-start </dev/null

echo "==> starting from the local images"
"${WORK}/arm/armctl" up --no-pull --no-backup

echo "==> checks"
"${WORK}/arm/armctl" compose ps
test -f "${WORK}/arm/certs/arm-ca.crt"
test "$(stat -c '%a' "${WORK}/arm/.armctl/.env")" = "600"
grep -q '^ARM_TRANSCODE_CAPABLE=false$' "${WORK}/arm/.armctl/.env"

echo "==> a second up, to exercise the backup and the ripper cleanup"
"${WORK}/arm/armctl" up --no-pull
ls "${WORK}/arm/backups"/pg-backup-*.sql.gz >/dev/null

echo "==> down"
"${WORK}/arm/armctl" down

echo "DRILL PASSED"
```

Run `chmod 755 devtools/install-drill.sh` and `shellcheck devtools/install-drill.sh` (expected: silent; if shellcheck flags the `ls` used as an existence check, replace that line with `compgen -G "${WORK}/arm/backups/pg-backup-*.sql.gz" >/dev/null`).

Do not run the drill on the development host: it refuses there, by design. It is run on a clean host in Task 12, Step 5.

- [ ] **Step 2: Rewrite `docs/user/Upgrading.md`**

Replace the sections `## Minor / patch upgrade` and `## Major-version upgrade` (everything from the first of those headings up to `## Before you upgrade`) with:

````markdown
## Upgrade

```bash
armctl upgrade
```

That moves the install to the latest stable release. In order, it:

1. downloads the new release's installer bundle and checks it;
2. pulls the new images;
3. refuses to go further while a rip or transcode is running;
4. backs up the database into `~/arm/backups/` (the newest five are kept);
5. switches to the new release, restarts the stack and recreates the rippers;
6. waits for the backend to report healthy.

Until step 5, nothing about the running install has changed, so a failed
download, a failed pull or an active rip leaves it exactly as it was. Run the
command again when the cause is fixed.

Options:

| Option | Effect |
|---|---|
| `--version v3.1.0` | Move to that release instead of the latest stable one. |
| `--force` | Go ahead while a rip or transcode is running. It is killed. |
| `--no-backup` | Skip the database backup. |

If `armctl` is not on your PATH, use `~/arm/armctl upgrade`.

To change an answer you gave at install time (profile, storage folders),
run `armctl install` again. It keeps your secrets and certificates authority
and asks the same questions with your earlier answers as the defaults.
````

In `## Before you upgrade`, replace the manual `pg_dump` bullet's command block and lead-in with: `**No schema rollback.** Alembic downgrade is not supported across versions. \`armctl upgrade\` takes a database backup before it switches; the files are in \`~/arm/backups/\` and contain plaintext secrets, so treat them like a password export.`

Replace the body of `## Rolling back` with:

```markdown
There is no automatic rollback, because a database migration cannot be
reversed. `armctl upgrade` keeps the previous release in
`~/arm/.armctl/releases/` and the backup it took in `~/arm/backups/`.

If the schema did not change between the two releases, going back is:

    armctl upgrade --version <previous tag>

If it did, restore the backup taken before the upgrade into a fresh database
first, then run the same command.
```

- [ ] **Step 3: Update `docs/user/Getting-Started.md`**

Keep the page's structure. Replace these three sections wholesale (from each heading to the next `## ` heading):

````markdown
## Install

```bash
curl -fsSL https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/install.sh | bash
```

Run it as your normal user, not as root and not with `sudo`. It asks for
`sudo` only for the steps that need it.

Prefer to read it first?

```bash
curl -fsSLo install.sh https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/install.sh
less install.sh
bash install.sh
```

The installer asks a few questions:

- **How the host is used.** Full box (rip and transcode here), ripper-only, or
  rip here and transcode on another machine.
- **Where raw rips and finished media go.** The default is inside `~/arm`;
  point them at a NAS mount or a second disk if you have one.
- **Host changes, one at a time.** Installing Docker (Debian and Ubuntu only),
  the NVIDIA container toolkit if you have an NVIDIA GPU, and a udev rule that
  stops a desktop session auto-mounting discs. You can decline any of them.

On a distro other than Debian or Ubuntu, install Docker Engine 24 or newer with
the Compose plugin yourself first
([Docker's instructions](https://docs.docker.com/engine/install/)); the
installer then does everything else.

To install somewhere other than your home folder, add `--prefix /srv`, which
gives `/srv/arm`. For an unattended install, every question has a flag:

```bash
bash install.sh --profile ripper-only --raw-path /mnt/rips --media-path /mnt/media --yes
```

## What the installer creates

Everything lives in one folder, `~/arm`:

| Path | What it is |
|---|---|
| `armctl` | The command you use to start, stop and upgrade ARM. |
| `raw/`, `media/` | Raw rips and finished media, unless you chose other folders. |
| `logs/` | Job and service logs. |
| `certs/` | ARM's own certificate authority and the service certificates. |
| `db/` | The database. |
| `backups/` | Database backups taken before each restart and upgrade. |
| `scripts/` | Your notification scripts. |
| `iso-library/` | Disc images for "Rip from ISO". |
| `.armctl/` | Configuration: `.env` (secrets, settings) and the installed release. |

## Start the stack

The installer starts ARM for you. Afterwards:

```bash
armctl up        # start, or restart after a change
armctl down      # stop
armctl upgrade   # move to the latest release
armctl compose ps                  # any docker compose command
armctl compose logs arm-backend
```

`armctl up` and `armctl down` refuse to run while a rip or transcode is in
progress, so they cannot kill a job by accident; add `--force` to override.
If `armctl` is not found, use `~/arm/armctl`.
````

- [ ] **Step 4: Update the remaining pages by rule, then review each hit**

Apply these replacements in `docs/user/*.md`, `docs/developers/architecture/02-job-lifecycle.md`, `05-cross-cutting.md`, `06-deployment.md` and `devtools/README.md`, **only where the text is about a production install** (leave dev instructions that use `devtools/setup-dev.sh` or a checkout's `docker compose` alone):

| Before | After |
|---|---|
| `cd ~/arm` followed by `docker compose up -d` | `armctl up` |
| `docker compose pull` then `docker compose up -d` | `armctl upgrade` (changing release) or `armctl up` (same release) |
| `docker compose down` | `armctl down` |
| any other `docker compose <x>` run in `~/arm` | `armctl compose <x>` |
| `~/arm/.env` | `~/arm/.armctl/.env` |
| `~/arm/docker-compose.yml` as something the user edits | remove; say settings live in `~/arm/.armctl/.env` and that `armctl install` regenerates the rest |
| "re-run the installer" / "re-run `install.sh`" | "run `armctl install` again" |

Specific edits:

- `docs/user/Configuring-ARM.md`: the paragraph beginning "Until the installer rewrite lands, a production ripper-only install needs" becomes: `A ripper-only install is the \`ripper-only\` profile: choose it when the installer asks, or run \`armctl install --profile ripper-only\`.`
- `docs/user/Uninstall.md`: the stop command becomes `armctl down`; add after it: `Then remove the folder (\`rm -rf ~/arm\`; the database folder may need \`sudo\`), the data volume (\`docker volume rm armv3_arm-data\`), and the PATH link if one was made (\`rm ~/.local/bin/armctl\` or \`sudo rm /usr/local/bin/armctl\`).`
- `docs/developers/architecture/02-job-lifecycle.md`, the "Tier 1" bullet: replace `the installer rewrite's equivalent in production` with `\`armctl install --profile ripper-only\` in production`.
- `docs/developers/architecture/05-cross-cutting.md`, the internal CA bullet: replace `\`install.sh\` produces` with `\`armctl install\` (via \`deploy/lib/certs.sh\`) produces`.
- `docs/developers/architecture/06-deployment.md`: replace the section that documents the installer (the one containing the `curl ... install.sh | bash` line and the description of what it generates) with a section titled `## Installer` whose body is sections 4, 6, 7 and 8 of `docs/superpowers/specs/2026-10-03-installer-rewrite-design.md`, adapted from future to present tense, and add this sentence at its top: `Production runs \`docker-compose.yml.example\` exactly as committed, layered with \`deploy/docker-compose.release.yml\` and a generated host overlay; nothing translates the template.`
- `devtools/README.md`: replace the two statements that cert generation is delegated to `install.sh` (the numbered step that calls `bash install.sh --certs-only ...` and the paragraph beginning "Cert generation is delegated to") with: `Certificates come from \`deploy/lib/certs.sh\`, the same code the production installer uses. \`setup-dev.sh\` and \`deploy/armctl.sh\` share \`deploy/lib/\`: host detection, the udev rule and the lifecycle safety steps have one definition.` Add a row or bullet for `devtools/install-drill.sh` using its header comment's first paragraph.
- `.env.example` comments: every sentence that says `install.sh` does something becomes `armctl install`; the note under `ARM_TRANSCODE_SSH_DIR` that begins "NOTE: this env var alone does nothing on a hand-copied compose file" becomes: `NOTE: this variable alone mounts nothing. \`armctl install\` adds the matching read-only mount to the generated host overlay; on a hand-built stack, add \`<dir>:/home/arm/.ssh:ro\` to arm-backend yourself.` Do not change any `KEY=value` line.

Then list what is left and read each hit:

```bash
grep -rnE 'install\.sh|docker compose (up|down|pull)|~/arm/\.env|installer rewrite' docs/user docs/developers/architecture devtools/README.md .env.example \
  | grep -v 'docs/superpowers'
```

Expected: the only remaining hits are the `curl ... install.sh | bash` lines, dev-checkout instructions, and `setup-dev.sh`'s own `uv` install hint. Fix anything else.

- [ ] **Step 5: Update `CLAUDE.md` and project memory**

`CLAUDE.md`:
- In the Architecture "Layout" list, add: `- [deploy/](deploy/) — the production installer: \`armctl.sh\` (install, up, down, upgrade), \`lib/\` (shared with \`devtools/setup-dev.sh\`), \`install/\` (production-only steps), and \`docker-compose.release.yml\`. Root \`install.sh\` is only a bootstrap that downloads a release bundle of this folder.`
- In "Gotchas / invariants", add: `- **Production runs the dev compose template unchanged.** \`docker-compose.yml.example\` is shipped as is and layered with \`deploy/docker-compose.release.yml\`. Never add production-only branches to the template; a new service built from source needs one image line in the release overlay (\`deploy/tests/test-stack-contract.sh\` fails until it has one).` and `- **\`deploy/lib/\` is shared.** A change there changes \`setup-dev.sh\` and production at once; \`devtools/test-setup-dev.sh\` pins the dev output text.`
- In the Tests section, add after the `uv run pytest` block: `Shell suites (zero-infra): \`bash devtools/test-setup-dev.sh\`, \`bash devtools/test-install-walkthrough.sh\`, and \`bash deploy/tests/test-{armctl,bootstrap,bundle,stack-contract}.sh\`.`

`.claude/memory/`:
- Delete `feedback_install_sh_legacy.md` (the freeze it records is over). It has no line in `MEMORY.md`; confirm with `grep -n install_sh_legacy .claude/memory/MEMORY.md` (expected: no output).
- `feedback_nvenc_header_driver_pin.md` and its `MEMORY.md` line: replace "in **both** install.sh and setup-dev.sh" / "(install.sh & setup-dev.sh)" with "in `deploy/lib/detect.sh` (the one shell copy, loaded by both setup-dev.sh and armctl.sh)".
- `feedback_ui_port_8081.md`: replace "(install.sh itself is legacy and frozen)" with "(the installer is `deploy/armctl.sh`; root `install.sh` is its bootstrap)".
- `project_no_transcode_mode.md`, follow-up item 4 ("install.sh compose heredoc lacks `ARM_TRANSCODE_CAPABLE` passthrough"): mark it done: "DONE 2026-10: production runs the template itself; `armctl install --profile ripper-only` writes the flag."
- `project_encoder_first_presets.md`, the line ending "install.sh has no variant awareness.": replace that clause with "`armctl` pins and pulls the `-intel`/`-amd` variants (`write_image_pins`, `select_up_services`)."

- [ ] **Step 6: Check the docs build**

The docs site fails its tests on a broken link. Run the site's test script the way `site/package.json` defines it:

```bash
grep -n '"test"' site/package.json
npm test --prefix site
```

Expected: pass. A failure names the broken link; fix the page.

- [ ] **Step 7: Commit**

```bash
git add devtools/install-drill.sh docs/user docs/developers/architecture devtools/README.md .env.example CLAUDE.md .claude/memory
git status --short    # confirm nothing unexpected is staged
git commit -m "docs: installer rewrite (armctl), install drill, memory

User pages describe the armctl commands and the new ~/arm layout. Developer
pages describe the shared deploy library and the unchanged-template model.
Retires the install.sh freeze note.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: Final verification

**Files:** none changed unless a check fails.

- [ ] **Step 1: Every suite, shellcheck, pre-commit**

```bash
for t in devtools/test-setup-dev.sh devtools/test-install-walkthrough.sh deploy/tests/test-armctl.sh deploy/tests/test-bootstrap.sh deploy/tests/test-bundle.sh deploy/tests/test-stack-contract.sh services/_common/test-entrypoint-optical.sh services/_common/test-entrypoint-guard.sh services/_common/test-entrypoint-render.sh; do
    bash "$t" > /dev/null 2>&1 && echo "PASS $t" || echo "FAIL $t"
done
mapfile -t files < <(git ls-files '*.sh'); shellcheck "${files[@]}"
uv run pre-commit run --all-files
uv run pytest -q
```

Expected: nine `PASS` lines, shellcheck silent, pre-commit clean, pytest green (the Python suites are untouched by this work; a failure there is pre-existing or a stray file).

- [ ] **Step 2: `setup-dev.sh` is unchanged**

```bash
B="${TMPDIR:-/tmp}/arm-installer-baseline"
bash devtools/setup-dev.sh --help > "$B/help.final.txt" 2>&1;  diff "$B/help.before.txt" "$B/help.final.txt" && echo HELP-IDENTICAL
bash devtools/setup-dev.sh setup > "$B/setup.final.txt" 2>&1; echo "rc=$?" >> "$B/setup.final.txt"
diff "$B/setup.before.txt" "$B/setup.final.txt" && echo SETUP-IDENTICAL
diff "$B/env.before" .env && echo ENV-IDENTICAL
diff "$B/compose.before.yml" docker-compose.yml && echo COMPOSE-IDENTICAL
```

Expected: the four `*-IDENTICAL` lines.

- [ ] **Step 3: `setup-dev.sh up` still deploys (ask the owner first)**

This rebuilds images and restarts the dev stack on this host. Ask before running. With a yes:

```bash
bash devtools/setup-dev.sh up 2>&1 | tee "${TMPDIR:-/tmp}/arm-installer-baseline/up.final.txt" | tail -n 15
```

Expected: ends with `stack is up; backend healthy at ...`, and every status line still starts with `==> `.

- [ ] **Step 4: A configure-only production install from the checkout**

Starts nothing and changes nothing on the host (`--no-start`, `--no-host-changes`, and a throwaway `HOME` so no PATH link lands in the real one).

```bash
T="$(mktemp -d)"; mkdir -p "$T/home"
HOME="$T/home" bash install.sh --prefix "$T" --profile ripper-only --no-host-changes --no-start </dev/null
ls -A "$T/arm" "$T/arm/.armctl"
stat -c '%a %n' "$T/arm/.armctl/.env" "$T/arm/certs"
grep -E '^(ARMCTL_PROFILE|ARM_TRANSCODE_CAPABLE|ARM_IMAGE_TAG|ARM_HOST_RAW_PATH|ARM_RIPPER_IMAGE)=' "$T/arm/.armctl/.env"
cat "$T/arm/.armctl/host-overlay.yml"
ARM_DIR="$T/arm" "$T/arm/armctl" compose config --services
openssl verify -CAfile "$T/arm/certs/arm-ca.crt" "$T/arm/certs/arm-backend.crt"
rm -rf "$T"
```

Expected: the eight sections print in order with a "skipped during this install" list (udev rule, PATH link); `.env` is `600` and `certs` is `700`; the profile is `ripper-only`, `ARM_TRANSCODE_CAPABLE=false`, the tag is `v` plus the contents of `VERSION`, the raw path is `$T/arm/raw`; the overlay mounts `/raw` and `/media`; the service list includes `arm-backend`, `arm-ripper` and `arm-data-init` and no `arm-ripper-sr*`; the certificate verifies `OK`.

- [ ] **Step 5: The install drill, on a host without an ARM stack**

This needs a clean Linux host with Docker (a VM is fine). It is the only check that starts the production stack. If no such host is available, say so in the PR description rather than skipping silently.

```bash
bash devtools/install-drill.sh
```

Expected: ends with `DRILL PASSED`.

- [ ] **Step 6: Open the PR**

One PR from `feat/installer-rewrite`. The description states: what was verified (Steps 1 to 4, and Step 5 or the reason it was not run), the two agreed differences in `setup-dev.sh` (Task 1), that a curl install needs a GitHub release carrying the bundle, and the departures from the spec listed below.

---

## Where this plan departs from the spec

Each is a refinement found while planning. None changes a requirement.

1. **Stage order (spec 7.2).** The profile is asked first and there are always eight stages (offload prints "not used" for other profiles). Asking first lets the answer survive the restart under the `docker` group.
2. **Running from a checkout (spec 4.1, 7.1).** The bootstrap packs a bundle from the checkout and installs it, instead of running `deploy/armctl.sh` in place. One code path, and the checkout does not have the template beside `armctl.sh`.
3. **File names.** The launcher in the bundle is `armctl.sh` (so shellcheck's `*.sh` rule covers it); `<arm>/armctl` is a small generated script that runs it.
4. **The `compose` helper (spec 5.4).** It is defined once in `deploy/lib/common.sh` and driven by `ARM_COMPOSE_CWD` and `ARM_COMPOSE_CMD`, which each caller sets, because the health wait has to run Compose under `timeout`, which cannot call a shell function.
5. **Host overlay (spec 6.3).** It always carries the `/raw` and `/media` mounts, not only when they are outside the arm folder. One shape, fewer branches.
6. **Image check after the pull.** `verify_images_present` is new: Compose can report a successful pull without having fetched an image for a service that has a `build:` section, so `armctl` checks before it changes anything.
7. **Existing folders.** The bootstrap refuses a non-empty `arm` folder that it did not create, instead of the spec's silence on the case.
8. **`setup-dev.sh` certificate step.** On a host without certificates its output changes (it no longer prints the old installer's banners). Listed under Task 1's allowed differences.

