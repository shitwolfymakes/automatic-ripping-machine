#!/usr/bin/env bash
# Seed the running dev DB with test data to exercise the UI:
# 1 drive + 7 status-spanning jobs + 3 tracks (on the ripped job), plus a
# per-job aggregated log file for each job (so the Logs screen has data).
#
# Dev-only. Not shipped, not invoked by setup-dev.sh or CI. Requires the
# dev stack running (arm-db + arm-backend). Idempotent: a default run
# clean-then-seeds (wipes prior seed rows, re-inserts a fresh fixture), so
# it's safe to re-run. `--clean` removes the seed rows and exits.
#
# Seed rows are tagged metadata_json {"seed":true} (jobs) and the drive by
# its display_name; --clean / re-runs key off those. IDs are real ULIDs
# generated via the backend (the detail routes validate the ULID pattern;
# readable ids 422). Per-job log files at /logs/jobs/<id>.log mirror the
# arm_common JSON-log format ({ts, level, service, job_id, msg, extra}) and
# carry extra.seed=true so --clean can prune exactly the seeded ones.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: bash devtools/seed-test-data.sh [--clean] [-h|--help]

  (no args)   Clean any existing seed rows, then insert a fresh fixture:
              1 drive + 7 jobs (spanning statuses) + 3 tracks + per-job logs.
  --clean     Remove the seed rows (jobs+tracks+drive) + seed logs and exit.
  -h, --help  Show this help.

Requires the dev stack running: docker compose up -d
EOF
}

MODE="seed"
case "${1:-}" in
    --clean) MODE="clean" ;;
    -h|--help) usage; exit 0 ;;
    "") ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 2 ;;
esac

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

# --- preflight: stack must be up (db for SQL, backend for ULID gen) ---
running="$(docker compose ps --status running --services 2>/dev/null || true)"
for svc in arm-db arm-backend; do
    if ! grep -qx "$svc" <<<"$running"; then
        echo "stack not running ($svc is down) — start it with: docker compose up -d" >&2
        exit 1
    fi
done
if ! docker compose exec -T arm-db psql -U arm -d arm -c 'SELECT 1' >/dev/null 2>&1; then
    echo "cannot reach the database (arm-db) — is the stack healthy?" >&2
    exit 1
fi

psql_exec() { docker compose exec -T arm-db psql -U arm -d arm "$@"; }

# --- remove seed-owned per-job log files (tagged extra.seed=true in line 1) ---
# Job ULIDs are regenerated each run, so we can't match by id; instead each
# seeded /logs/jobs/<id>.log carries "seed": true in its first line's `extra`,
# and this prunes exactly those (real job logs never carry it).
clean_seed_logs() {
    docker compose exec -T arm-backend python - <<'PY'
import glob, json, os
removed = 0
for p in glob.glob("/logs/jobs/*.log"):
    try:
        with open(p, encoding="utf-8") as fh:
            first = fh.readline()
        rec = json.loads(first) if first.strip() else {}
    except (OSError, ValueError):
        continue
    if isinstance(rec, dict) and isinstance(rec.get("extra"), dict) and rec["extra"].get("seed") is True:
        os.remove(p)
        removed += 1
print(f"  removed {removed} seed log file(s)")
PY
}

# --- write a per-job aggregated log for each seeded job ---
# Args: the 7 job ULIDs in fixture order (Blade Runner, Matrix, Dune, untitled,
# Oppenheimer, Scratched Disc, Audio CD). Emits realistic status-appropriate
# NDJSON in the arm_common log shape so the Logs screen + its level/text
# filters have data. Status is derived from the job's position (matches the
# INSERT order below).
seed_logs() {
    docker compose exec -T -e SEED_JOB_IDS="$1" arm-backend python - <<'PY'
import json, os
from datetime import datetime, timedelta, UTC

ids = os.environ["SEED_JOB_IDS"].split()
# (title, status) per fixture position — keep in sync with the jobs INSERT.
META = [
    ("Blade Runner 2049", "ripping"),
    ("The Matrix",        "ripped"),
    ("Dune: Part Two",    "identified"),
    ("(untitled disc)",   "awaiting_user_id"),
    ("Oppenheimer",       "ripped_partial"),
    ("Scratched Disc",    "failed"),
    ("Some Audio CD",     "abandoned"),
]

def script(title, status):
    lines = [
        (0, "info", "arm_backend",          f"job created for disc '{title}'"),
        (2, "info", "arm_backend.identify", "querying OMDb for disc metadata"),
    ]
    if status != "awaiting_user_id":
        lines.append((5, "info", "arm_backend.identify", f"identified as '{title}'"))
    if status in ("ripping", "ripped", "ripped_partial", "failed"):
        lines += [
            (8,  "info",  "arm_ripper.makemkv", "scanning disc titles"),
            (9,  "info",  "arm_ripper.makemkv", "found 3 titles; selecting main feature (title 0)"),
            (12, "info",  "arm_ripper.makemkv", "makemkvcon mkv disc:0 all -> /raw"),
            (40, "debug", "arm_ripper.makemkv", "title 0: 1.2% done"),
            (95, "debug", "arm_ripper.makemkv", "title 0: 64.0% done"),
        ]
    if status == "ripping":
        lines.append((140, "info", "arm_ripper.makemkv", "title 0: 88.0% done (in progress)"))
    if status in ("ripped", "ripped_partial"):
        lines += [
            (150, "info", "arm_ripper.makemkv",       "rip complete: 1 title, 28.4 GiB"),
            (151, "info", "arm_backend.transcode",    "queued transcode task"),
            (320, "info", "arm_transcode.handbrake",  "HandBrake: 100.00 % (avg 142 fps)"),
            (322, "info", "arm_backend.transcode",    "transcode complete -> /media"),
        ]
    if status == "ripped_partial":
        lines.append((180, "warning", "arm_ripper.makemkv", "title 2 failed (read error at 47%); kept title 0 only"))
    if status == "failed":
        lines += [
            (60, "warning", "arm_ripper.makemkv", "read retry 1/3 at sector 102400"),
            (75, "warning", "arm_ripper.makemkv", "read retry 3/3 at sector 102400"),
            (78, "error",   "arm_ripper.makemkv", "makemkvcon exited 22: SCSI error - medium read failed"),
            (79, "error",   "arm_backend",        "job failed: ripper reported unrecoverable read error"),
        ]
    if status == "identified":
        lines.append((8, "info", "arm_backend", "awaiting rip start"))
    if status == "abandoned":
        lines.append((30, "warning", "arm_backend", "no user identification within timeout; job abandoned"))
    return sorted(lines, key=lambda t: t[0])

os.makedirs("/logs/jobs", exist_ok=True)
t0 = datetime(2026, 6, 18, 20, 0, 0, tzinfo=UTC)
for jid, (title, status) in zip(ids, META):
    with open(f"/logs/jobs/{jid}.log", "w", encoding="utf-8") as fh:
        for off, level, logger, msg in script(title, status):
            fh.write(json.dumps({
                "ts": (t0 + timedelta(seconds=off)).isoformat(),
                "level": level,
                "service": logger.split(".")[0].replace("_", "-"),
                "job_id": jid,
                "track_id": None,
                "session_application_id": None,
                "msg": msg,
                "extra": {"logger": logger, "seed": True},
            }) + "\n")
print(f"  wrote {len(ids)} per-job log file(s) under /logs/jobs/")
PY
}

# --- the FK-safe cleanup block (shared by --clean and the start of a seed run) ---
CLEAN_SQL=$(cat <<'EOF'
DELETE FROM tracks WHERE job_id IN (SELECT id FROM jobs WHERE metadata_json @> '{"seed":true}');
DELETE FROM jobs   WHERE metadata_json @> '{"seed":true}';
DELETE FROM drives WHERE display_name = 'Test Drive (seed)';
EOF
)

if [[ "$MODE" == "clean" ]]; then
    psql_exec -v ON_ERROR_STOP=1 <<EOF
BEGIN;
${CLEAN_SQL}
COMMIT;
EOF
    echo "✓ removed seed rows (jobs + tracks + 'Test Drive (seed)')"
    clean_seed_logs
    exit 0
fi

# --- generate real ULIDs via the backend (authoritative; matches route patterns) ---
ids="$(docker compose exec -T arm-backend python -c "
from arm_common.ulid import new_id
print(new_id('drv'))
for _ in range(7): print(new_id('job'))
for _ in range(3): print(new_id('trk'))
")"
mapfile -t ID <<<"$ids"
if [[ "${#ID[@]}" -ne 11 ]]; then
    echo "ULID generation failed (expected 11 ids, got ${#ID[@]})" >&2
    exit 1
fi
DRV="${ID[0]}"
J=("${ID[@]:1:7}")
T=("${ID[@]:8:3}")

# --- clean-then-seed, one transaction ---
psql_exec -v ON_ERROR_STOP=1 <<EOF
BEGIN;

${CLEAN_SQL}

INSERT INTO drives (id, hostname, device_path, display_name, status, media_status, media_status_at, drive_mode, uhd_capable)
VALUES ('${DRV}', 'seed-host', '/dev/sr-seed', 'Test Drive (seed)', 'online', 'loaded', now(), 'auto', false);

INSERT INTO jobs (id, drive_id, disc_type, title, year, status, metadata_json, started_at, ripped_at, created_at, poster_url) VALUES
 ('${J[0]}', '${DRV}', 'bluray', 'Blade Runner 2049', 2017, 'ripping',          '{"seed":true}'::jsonb, now()-interval '5 min',  NULL,                    now()-interval '5 min',  'https://image.tmdb.org/t/p/w300/gajva2L0rPYkEWjzgFlBXCAVBE5.jpg'),
 ('${J[1]}', '${DRV}', 'dvd',    'The Matrix',         1999, 'ripped',           '{"seed":true}'::jsonb, now()-interval '2 hour', now()-interval '90 min', now()-interval '2 hour', 'https://image.tmdb.org/t/p/w300/p96dm7sCMn4VYAStA6siNz30G1r.jpg'),
 ('${J[2]}', '${DRV}', 'bluray', 'Dune: Part Two',     2024, 'identified',       '{"seed":true}'::jsonb, NULL,                    NULL,                    now()-interval '10 min', 'https://image.tmdb.org/t/p/w300/1pdfLvkbY9ohJlCjQH2CZjjYVvJ.jpg'),
 ('${J[3]}', '${DRV}', 'dvd',    NULL,                 NULL, 'awaiting_user_id', '{"seed":true}'::jsonb, NULL,                    NULL,                    now()-interval '3 min',  NULL),
 ('${J[4]}', '${DRV}', 'bluray', 'Oppenheimer',        2023, 'ripped_partial',   '{"seed":true}'::jsonb, now()-interval '3 hour', now()-interval '2 hour', now()-interval '3 hour', 'https://image.tmdb.org/t/p/w300/8Gxv8gSFCU0XGDykEGv7zR1n2ua.jpg'),
 ('${J[5]}', '${DRV}', 'dvd',    'Scratched Disc',     2010, 'failed',           '{"seed":true}'::jsonb, now()-interval '1 day',  NULL,                    now()-interval '1 day',  NULL),
 ('${J[6]}', '${DRV}', 'cd',     'Some Audio CD',      NULL, 'abandoned',        '{"seed":true}'::jsonb, NULL,                    NULL,                    now()-interval '2 day',  NULL);

INSERT INTO tracks (id, job_id, kind, index, source_ref, label, status, duration_seconds, output_path, title) VALUES
 ('${T[0]}', '${J[1]}', 'video_title', 0, 'title00',       'Main Feature',    'done', 8160, '/media/movie/The Matrix (1999)/The Matrix.mkv',       'The Matrix'),
 ('${T[1]}', '${J[1]}', 'video_title', 1, 'title01',       'Special Feature', 'done', 1320, '/media/movie/The Matrix (1999)/extras/behind.mkv',   'Behind the Scenes'),
 ('${T[2]}', '${J[1]}', 'audio_track', 2, 'title00.audio', 'Commentary',      'done', 8160, NULL,                                                  'Director Commentary');

COMMIT;
EOF

# Seed logs: prune any prior seed log files (their job ids were regenerated),
# then write a fresh per-job log for each of the 7 new job ids.
clean_seed_logs >/dev/null
seed_logs "${J[*]}"

echo "✓ seeded 1 drive + 7 jobs + 3 tracks + per-job logs (tagged metadata_json {\"seed\":true})"
echo "  view at https://localhost:8082 (login admin / adminadmin); re-run is safe; --clean to remove"
