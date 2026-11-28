#!/usr/bin/env bash
# Seed the running dev DB with comprehensive test data to exercise the whole UI:
# 3 drives + 18 status-spanning jobs + video/audio tracks (full enriched column
# set) + disc fingerprints (crc64 / aacs / musicbrainz) + music CDs (single +
# multi-disc) carrying a MusicBrainz-shaped tracklist in metadata_json, plus a
# per-job aggregated log file for each job (so the Logs screen has data).
#
# Project-blackbird fixture (migrations 0051-0056):
#   - Blu-ray title classes on tracks (source_file, playlist_name, title_class,
#     title_class_ref = the source_ref of the kept title a copy points at), one
#     track per TitleClass value, ticked state as the classifier defaults it
#     (primary/edition ticked; duplicate/decoy/angle/subset/variant/view unticked):
#       Neon Skyline 3D        awaiting_review: primary, 3D primary, angle, subset,
#                              2D view twin, variant
#       The Final Expedition   awaiting_review: two primaries each with a raw-stream
#                              duplicate, 10 decoy playlists, an extra
#       The Glass Orchard      ripped per title: two editions, SKIPPED duplicate +
#                              decoy, extras; one track_stages row per StageStatus
#   - failed jobs carrying jobs.failure_reason (six operator texts; Scratched Disc
#     keeps it NULL like a job that failed before 0054)
#   - drives.scanning (drive 2) and the per-drive rip_end_on_completion_message
#     override (true on drive 1, NULL on drive 2, false on drive 3); the global
#     config row is not touched
#   - per-job logs with bd_structure and "makemkvcon run end" lines
# tracks.sha256 is gone (0055); nothing here writes it.
#
# ASCII ONLY: all seeded strings are plain ASCII (no em-dashes, smart quotes,
# or non-ASCII hyphens) so the UI renders nothing odd.
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
              3 drives (scanning + rip-end override) + 18 jobs (spanning
              statuses, failure reasons) + tracks (incl. Blu-ray title
              classes) + track stages + fingerprints + music tracklists
              (single + multi-disc) + per-job logs.
  --clean     Remove the seed rows (jobs+tracks+stages+fingerprints+drives) + logs.
  -h, --help  Show this help.

Requires the dev stack running: bash devtools/setup-dev.sh up
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
        echo "stack not running ($svc is down); start it with: bash devtools/setup-dev.sh up" >&2
        exit 1
    fi
done
if ! docker compose exec -T arm-db psql -U arm -d arm -c 'SELECT 1' >/dev/null 2>&1; then
    echo "cannot reach the database (arm-db); is the stack healthy?" >&2
    exit 1
fi

psql_exec() { docker compose exec -T arm-db psql -U arm -d arm "$@"; }
# Run inside arm-backend as the service user, not root: the backend drops to
# PUID/PGID at boot, so anything this script creates under /logs (the
# per-job log files and the /logs/jobs directory itself) must belong to that
# user or the backend's own per-job log appends fail with EACCES afterwards.
backend_exec() {
    local puid pgid
    puid="$(grep -E '^PUID=' .env 2>/dev/null | cut -d= -f2)"
    pgid="$(grep -E '^PGID=' .env 2>/dev/null | cut -d= -f2)"
    docker compose exec -T --user "${puid:-1000}:${pgid:-1000}" "$@"
}

# --- remove seed-owned per-job log files (tagged extra.seed=true in line 1) ---
# Job ULIDs are regenerated each run, so we can't match by id; instead each
# seeded /logs/jobs/<id>.log carries "seed": true in its first line's `extra`,
# and this prunes exactly those (real job logs never carry it).
clean_seed_logs() {
    backend_exec arm-backend python - <<'PY'
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
# Args: the 18 job ULIDs in fixture order (Blade Runner, Matrix, Dune, untitled,
# Oppenheimer, Scratched Disc, Abbey Road, The Wall, Cult Double Feature, the
# three Blu-ray class jobs, the six scan-failure jobs). Emits
# appropriate NDJSON in the arm_common log shape so the Logs screen + its
# level/text filters have data. Status is derived from the job's position
# (matches the INSERT order below).
seed_logs() {
    backend_exec -e SEED_JOB_IDS="$1" -e SEED_FAIL_REASONS="$2" arm-backend python - <<'PY'
import json, os
from datetime import datetime, timedelta, UTC

ids = os.environ["SEED_JOB_IDS"].split()
fail_reasons = os.environ["SEED_FAIL_REASONS"].split("\n")
# (title, status) per fixture position - keep in sync with the jobs INSERT.
META = [
    ("Blade Runner 2049", "ripping"),
    ("The Matrix",        "ripped"),
    ("Dune: Part Two",    "identified"),
    ("(untitled disc)",   "awaiting_user_id"),
    ("Oppenheimer",       "ripped_partial"),
    ("Scratched Disc",    "failed"),
    ("Abbey Road",        "ripped"),
    ("The Wall",          "awaiting_user_id"),
    ("Cult Double Feature", "ripped"),
    ("Neon Skyline 3D",   "awaiting_review"),
    ("The Final Expedition", "awaiting_review"),
    ("The Glass Orchard", "ripped"),
    ("(untitled disc)",   "scan_failed"),
    ("Dusty Disc",        "scan_failed"),
    ("Slow Disc",         "scan_failed"),
    ("Expired Build Disc", "scan_failed"),
    ("Odd Disc",          "scan_failed"),
    ("Empty Image",       "scan_failed"),
]
BD_STRUCT = {"Neon Skyline 3D": (14, 22, 1840), "The Final Expedition": (31, 46, 2210), "The Glass Orchard": (9, 15, 960),
             "Blade Runner 2049": (5, 8, 710), "Dune: Part Two": (6, 9, 780), "Oppenheimer": (5, 7, 650)}
FAIL_BY_JOB = {i: r for i, r in zip(range(12, 18), fail_reasons)}

def script(title, status, pos, jid):
    if status == "scan_failed":
        return [
            (0, "info", "arm_backend",              f"job created for disc '{title}'"),
            (3, "info", "arm_ripper.makemkv",       "scanning disc titles"),
            (20, "warning", "arm_backend.job_failure", f"job_id={jid} failed: {FAIL_BY_JOB[pos]}"),
        ]
    lines = [
        (0, "info", "arm_backend",          f"job created for disc '{title}'"),
        (2, "info", "arm_backend.identify", "querying provider for disc metadata"),
    ]
    if status != "awaiting_user_id":
        lines.append((5, "info", "arm_backend.identify", f"identified as '{title}'"))
    if title in BD_STRUCT:
        n_pl, n_clip, ms = BD_STRUCT[title]
        lines.append((6, "info", "arm_ripper.scan.bd_structure",
                      f"bd_structure device=/dev/sr-seed playlists={n_pl} clips={n_clip} elapsed_ms={ms} reason=ok"))
    if status == "awaiting_review":
        lines += [
            (9,  "info", "arm_ripper.makemkv", "scanning disc titles"),
            (14, "info", "arm_backend",        "scan classified titles (primary, duplicate, decoy, angle, subset, view)"),
            (15, "info", "arm_backend",        "holding for operator review (timed gate)"),
        ]
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
            (149, "info", "arm_ripper.makemkv",       "makemkvcon run end: policy=on ended_on_completion=True completion_msg_at=+147.9s save_full_at=+148.4s last_stdout_at=+148.5s last_file_write_at=+148.2s ended_at=+149.1s"),
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
    return sorted(lines, key=lambda t: t[0])

os.makedirs("/logs/jobs", exist_ok=True)
t0 = datetime(2026, 6, 18, 20, 0, 0, tzinfo=UTC)
for pos, (jid, (title, status)) in enumerate(zip(ids, META)):
    with open(f"/logs/jobs/{jid}.log", "w", encoding="utf-8") as fh:
        for off, level, logger, msg in script(title, status, pos, jid):
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
DELETE FROM disc_fingerprints WHERE job_id IN (SELECT id FROM jobs WHERE metadata_json @> '{"seed":true}');
DELETE FROM track_stages WHERE job_id IN (SELECT id FROM jobs WHERE metadata_json @> '{"seed":true}');
DELETE FROM tracks WHERE job_id IN (SELECT id FROM jobs WHERE metadata_json @> '{"seed":true}');
DELETE FROM jobs   WHERE metadata_json @> '{"seed":true}';
DELETE FROM drives WHERE display_name IN ('Test Drive (seed)', 'Test Drive 2 (seed)', 'Test Drive 3 (seed)');
EOF
)

if [[ "$MODE" == "clean" ]]; then
    psql_exec -v ON_ERROR_STOP=1 <<EOF
BEGIN;
${CLEAN_SQL}
COMMIT;
EOF
    echo "removed seed rows (jobs + tracks + stages + fingerprints + the 3 'Test Drive (seed)' drives)"
    clean_seed_logs
    exit 0
fi

# --- generate real ULIDs via the backend (authoritative; matches route patterns) ---
# 3 drives + 18 jobs + 54 tracks + 6 fingerprints + 5 track stages. The 9th job is a multi-title DVD
# (Cult Double Feature) whose 3 video tracks are each matched independently; the
# detail routes validate the ULID pattern, so these must be real backend ULIDs.
ids="$(backend_exec arm-backend python -c "
from arm_common.ulid import new_id
for _ in range(3): print(new_id('drv'))
for _ in range(18): print(new_id('job'))
for _ in range(54): print(new_id('trk'))
for _ in range(6): print(new_id('dfp'))
for _ in range(5): print(new_id('stg'))
")"
mapfile -t ID <<<"$ids"
if [[ "${#ID[@]}" -ne 86 ]]; then
    echo "ULID generation failed (expected 86 ids, got ${#ID[@]})" >&2
    exit 1
fi
DRV="${ID[0]}"
DRV2="${ID[1]}"
DRV3="${ID[2]}"
J=("${ID[@]:3:18}")
T=("${ID[@]:21:54}")
F=("${ID[@]:75:6}")
S=("${ID[@]:81:5}")

# jobs.failure_reason texts (0054): the operator sentences the backend writes for
# a failed scan. Index order = the six failed jobs J[12]..J[17]; the same strings
# feed the SQL and the per-job logs. ASCII only, no newlines.
FAIL_REASONS=(
    "MakeMKV could not decrypt this disc: its volume key is unknown and could not be downloaded. MakeMKV fetches keys from its online server over HTTPS (TCP 443); check that your firewall or router allows it, then re-insert the disc."
    "MakeMKV could not open this disc. Check that it is clean and undamaged and that the drive can read it, then re-insert it."
    "MakeMKV took too long to read this disc and was stopped. Re-insert the disc to try again; if it keeps happening, check the disc and the drive."
    "This MakeMKV build has expired and refuses to scan discs. Update the ripper image to get a current one."
    "MakeMKV could not scan this disc. The job log has MakeMKV's last output."
    "MakeMKV found no titles in this ISO, even after unpacking it. To keep a copy of the image anyway, rip it again with the \"ISO: Full-disc dump\" session."
)
FR=()
for r in "${FAIL_REASONS[@]}"; do FR+=("${r//\'/\'\'}"); done

# Ten decoy playlists of The Final Expedition's main feature (J[10], T[36]..T[45]):
# same length and clips as t00 in another order, so the review table collapses them.
DECOY_ROWS=""
for i in 0 1 2 3 4 5 6 7 8 9; do
    DECOY_ROWS+=" ('${T[$((36 + i))]}', '${J[10]}', 'video_title', $((4 + i)), '$((4 + i))', 'Playlist 0090${i}', 'queued', 0, 7620, 24500000000, true, '0090${i}.mpls', 'FPL_Decoy${i}', 'decoy', '0'),"$'\n'
done

# --- MusicBrainz-shaped tracklists (ASCII only) for the CD jobs ---
# Abbey Road (single disc, 17 tracks) for the ripped music CD.
ABBEY_TRACKS='[
 {"title":"Come Together","position":1,"length_ms":259066,"disc_number":1},
 {"title":"Something","position":2,"length_ms":182493,"disc_number":1},
 {"title":"Maxwell s Silver Hammer","position":3,"length_ms":207573,"disc_number":1},
 {"title":"Oh! Darling","position":4,"length_ms":206573,"disc_number":1},
 {"title":"Octopus s Garden","position":5,"length_ms":171000,"disc_number":1},
 {"title":"I Want You (She s So Heavy)","position":6,"length_ms":467280,"disc_number":1},
 {"title":"Here Comes the Sun","position":7,"length_ms":185773,"disc_number":1},
 {"title":"Because","position":8,"length_ms":165560,"disc_number":1},
 {"title":"You Never Give Me Your Money","position":9,"length_ms":242000,"disc_number":1},
 {"title":"Sun King","position":10,"length_ms":146146,"disc_number":1},
 {"title":"Mean Mr. Mustard","position":11,"length_ms":66066,"disc_number":1},
 {"title":"Polythene Pam","position":12,"length_ms":72000,"disc_number":1},
 {"title":"She Came In Through the Bathroom Window","position":13,"length_ms":117000,"disc_number":1},
 {"title":"Golden Slumbers","position":14,"length_ms":91000,"disc_number":1},
 {"title":"Carry That Weight","position":15,"length_ms":96000,"disc_number":1},
 {"title":"The End","position":16,"length_ms":140000,"disc_number":1},
 {"title":"Her Majesty","position":17,"length_ms":25200,"disc_number":1}
]'

# A 2-disc set (disc 2 of 2) so the multi-disc disc_number path renders.
WALL_TRACKS='[
 {"title":"Hey You","position":1,"length_ms":280000,"disc_number":2},
 {"title":"Is There Anybody Out There?","position":2,"length_ms":160000,"disc_number":2},
 {"title":"Nobody Home","position":3,"length_ms":206000,"disc_number":2},
 {"title":"Vera","position":4,"length_ms":95000,"disc_number":2},
 {"title":"Bring the Boys Back Home","position":5,"length_ms":87000,"disc_number":2},
 {"title":"Comfortably Numb","position":6,"length_ms":384000,"disc_number":2}
]'

# --- clean-then-seed, one transaction ---
psql_exec -v ON_ERROR_STOP=1 <<EOF
BEGIN;

${CLEAN_SQL}

-- Drive 1 carries every seed job; rip_end_on_completion_message true (0056 per-drive override).
-- Drive 2 is mid pre-job scan (scanning true, 0053) and follows the global rip-end setting (NULL).
-- Drive 3 overrides the global setting off (false).
INSERT INTO drives (id, hostname, device_path, display_name, status, media_status, media_status_at, drive_mode, uhd_capable, scanning, rip_end_on_completion_message)
VALUES ('${DRV}',  'seed-host',   '/dev/sr-seed',  'Test Drive (seed)',   'online', 'loaded', now(), 'auto', false, false, true),
       ('${DRV2}', 'seed-host-2', '/dev/sr-seed2', 'Test Drive 2 (seed)', 'online', 'loaded', now(), 'auto', true,  true,  NULL),
       ('${DRV3}', 'seed-host-3', '/dev/sr-seed3', 'Test Drive 3 (seed)', 'online', 'loaded', now(), 'auto', false, false, false);

-- 9 jobs spanning statuses + disc types (incl. a multi-title DVD). resumed_from_crash on one; disc_number/total on the multi-disc CD.
INSERT INTO jobs (id, drive_id, disc_type, title, year, status, metadata_json, resumed_from_crash, disc_number, disc_total, started_at, ripped_at, created_at, poster_url) VALUES
 ('${J[0]}', '${DRV}', 'bluray', 'Blade Runner 2049', 2017, 'ripping',          '{"seed":true}'::jsonb,                                              false, NULL, NULL, now()-interval '5 min',  NULL,                    now()-interval '5 min',  'https://image.tmdb.org/t/p/w300/gajva2L0rPYkEWjzgFlBXCAVBE5.jpg'),
 ('${J[1]}', '${DRV}', 'dvd',    'The Matrix',         1999, 'ripped',           '{"seed":true}'::jsonb,                                              true,  NULL, NULL, now()-interval '2 hour', now()-interval '90 min', now()-interval '2 hour', 'https://image.tmdb.org/t/p/w300/p96dm7sCMn4VYAStA6siNz30G1r.jpg'),
 ('${J[2]}', '${DRV}', 'bluray', 'Dune: Part Two',     2024, 'identified',       '{"seed":true}'::jsonb,                                              false, NULL, NULL, NULL,                    NULL,                    now()-interval '10 min', 'https://image.tmdb.org/t/p/w300/1pdfLvkbY9ohJlCjQH2CZjjYVvJ.jpg'),
 ('${J[3]}', '${DRV}', 'dvd',    NULL,                 NULL, 'awaiting_user_id', '{"seed":true}'::jsonb,                                              false, NULL, NULL, NULL,                    NULL,                    now()-interval '3 min',  NULL),
 ('${J[4]}', '${DRV}', 'bluray', 'Oppenheimer',        2023, 'ripped_partial',   '{"seed":true}'::jsonb,                                              false, NULL, NULL, now()-interval '3 hour', now()-interval '2 hour', now()-interval '3 hour', 'https://image.tmdb.org/t/p/w300/8Gxv8gSFCU0XGDykEGv7zR1n2ua.jpg'),
 ('${J[5]}', '${DRV}', 'dvd',    'Scratched Disc',     2010, 'failed',           '{"seed":true}'::jsonb,                                              false, NULL, NULL, now()-interval '1 day',  NULL,                    now()-interval '1 day',  NULL),
 ('${J[6]}', '${DRV}', 'cd',     'Abbey Road',         1969, 'ripped',           jsonb_build_object('seed',true,'artist','The Beatles','album','Abbey Road','tracks', '${ABBEY_TRACKS}'::jsonb), false, 1, 1, now()-interval '6 hour', now()-interval '5 hour', now()-interval '6 hour', 'https://coverartarchive.org/release/6bb3793b-f991-378e-9bff-0bd3117f2298/front'),
 ('${J[7]}', '${DRV}', 'cd',     'The Wall',           1979, 'awaiting_user_id', jsonb_build_object('seed',true,'artist','Pink Floyd','album','The Wall','tracks', '${WALL_TRACKS}'::jsonb),  false, 2, 2, NULL,                    NULL,                    now()-interval '20 min', NULL),
 ('${J[8]}', '${DRV}', 'dvd',    'Cult Double Feature', NULL, 'ripped',          jsonb_build_object('seed',true,'multi_title',true),                  false, NULL, NULL, now()-interval '4 hour', now()-interval '3 hour', now()-interval '4 hour', NULL);

-- Video tracks for The Matrix (J1): main feature + special feature (excluded + custom filename) + a FAILED audio track with last_error.
INSERT INTO tracks (id, job_id, kind, index, source_ref, label, status, attempts, duration_seconds, expected_duration_seconds, size_bytes, expected_size_bytes, output_path, last_error, excluded, custom_filename, title) VALUES
 ('${T[0]}', '${J[1]}', 'video_title', 0, 'title00',       'Main Feature',    'done',   1, 8160, 8160, 28339200000, 28000000000, '/media/movie/The Matrix (1999)/The Matrix.mkv',     NULL,                                                              false, NULL,                'The Matrix'),
 ('${T[1]}', '${J[1]}', 'video_title', 1, 'title01',       'Special Feature', 'done',   2, 1320, 1320,  1572864000,  1500000000, '/media/movie/The Matrix (1999)/extras/behind.mkv', NULL,                                                              true,  'behind_the_scenes', 'Behind the Scenes'),
 ('${T[2]}', '${J[1]}', 'audio_track', 2, 'title00.audio', 'Commentary',      'failed', 3, NULL, 8160, NULL,        NULL,        NULL,                                                'makemkvcon: read error at 00:42:13 - disc surface scratched', false, NULL,                'Director Commentary');

-- Oppenheimer (J4, ripped_partial): one done, one still queued (mixed status in the table).
INSERT INTO tracks (id, job_id, kind, index, source_ref, label, status, attempts, duration_seconds, expected_duration_seconds, size_bytes, expected_size_bytes, output_path, title) VALUES
 ('${T[3]}', '${J[4]}', 'video_title', 0, 'title00', 'Main Feature', 'done',   1, 10800, 10800, 41943040000, 41000000000, '/media/movie/Oppenheimer (2023)/Oppenheimer.mkv', 'Oppenheimer'),
 ('${T[4]}', '${J[4]}', 'video_title', 1, 'title01', 'Trailer',      'queued', 0, NULL,   150,   NULL,        180000000,   NULL,                                              NULL);

-- Blade Runner 2049 (J0, ripping): one in-progress track.
INSERT INTO tracks (id, job_id, kind, index, source_ref, label, status, attempts, duration_seconds, expected_duration_seconds, expected_size_bytes, title) VALUES
 ('${T[5]}', '${J[0]}', 'video_title', 0, 'title00', 'Main Feature', 'in_progress', 1, NULL, 9840, 45000000000, 'Blade Runner 2049');

-- Audio tracks for Abbey Road (J6, ripped) so the CD has real track rows alongside
-- metadata_json. ALL 17 tracks: the disc track-count must match the album so the
-- "match track count" search filter finds the real 17-track Abbey Road release (a
-- 2-track stub matched 2-track singles instead). Durations mirror ABBEY_TRACKS.
INSERT INTO tracks (id, job_id, kind, index, source_ref, label, status, attempts, duration_seconds, expected_duration_seconds, output_path) VALUES
 ('${T[6]}',  '${J[6]}', 'audio_track', 0,  '1',  'Come Together',                            'done', 1, 259, 259, '/media/music/The Beatles/Abbey Road/01 Come Together.flac'),
 ('${T[7]}',  '${J[6]}', 'audio_track', 1,  '2',  'Something',                                'done', 1, 182, 182, '/media/music/The Beatles/Abbey Road/02 Something.flac'),
 ('${T[11]}', '${J[6]}', 'audio_track', 2,  '3',  'Maxwell s Silver Hammer',                  'done', 1, 208, 208, '/media/music/The Beatles/Abbey Road/03 Maxwell s Silver Hammer.flac'),
 ('${T[12]}', '${J[6]}', 'audio_track', 3,  '4',  'Oh! Darling',                              'done', 1, 207, 207, '/media/music/The Beatles/Abbey Road/04 Oh! Darling.flac'),
 ('${T[13]}', '${J[6]}', 'audio_track', 4,  '5',  'Octopus s Garden',                         'done', 1, 171, 171, '/media/music/The Beatles/Abbey Road/05 Octopus s Garden.flac'),
 ('${T[14]}', '${J[6]}', 'audio_track', 5,  '6',  'I Want You (She s So Heavy)',              'done', 1, 467, 467, '/media/music/The Beatles/Abbey Road/06 I Want You.flac'),
 ('${T[15]}', '${J[6]}', 'audio_track', 6,  '7',  'Here Comes the Sun',                       'done', 1, 186, 186, '/media/music/The Beatles/Abbey Road/07 Here Comes the Sun.flac'),
 ('${T[16]}', '${J[6]}', 'audio_track', 7,  '8',  'Because',                                  'done', 1, 166, 166, '/media/music/The Beatles/Abbey Road/08 Because.flac'),
 ('${T[17]}', '${J[6]}', 'audio_track', 8,  '9',  'You Never Give Me Your Money',             'done', 1, 242, 242, '/media/music/The Beatles/Abbey Road/09 You Never Give Me Your Money.flac'),
 ('${T[18]}', '${J[6]}', 'audio_track', 9,  '10', 'Sun King',                                 'done', 1, 146, 146, '/media/music/The Beatles/Abbey Road/10 Sun King.flac'),
 ('${T[19]}', '${J[6]}', 'audio_track', 10, '11', 'Mean Mr. Mustard',                         'done', 1, 66,  66,  '/media/music/The Beatles/Abbey Road/11 Mean Mr. Mustard.flac'),
 ('${T[20]}', '${J[6]}', 'audio_track', 11, '12', 'Polythene Pam',                            'done', 1, 72,  72,  '/media/music/The Beatles/Abbey Road/12 Polythene Pam.flac'),
 ('${T[21]}', '${J[6]}', 'audio_track', 12, '13', 'She Came In Through the Bathroom Window',   'done', 1, 117, 117, '/media/music/The Beatles/Abbey Road/13 She Came In Through the Bathroom Window.flac'),
 ('${T[22]}', '${J[6]}', 'audio_track', 13, '14', 'Golden Slumbers',                          'done', 1, 91,  91,  '/media/music/The Beatles/Abbey Road/14 Golden Slumbers.flac'),
 ('${T[23]}', '${J[6]}', 'audio_track', 14, '15', 'Carry That Weight',                        'done', 1, 96,  96,  '/media/music/The Beatles/Abbey Road/15 Carry That Weight.flac'),
 ('${T[24]}', '${J[6]}', 'audio_track', 15, '16', 'The End',                                  'done', 1, 140, 140, '/media/music/The Beatles/Abbey Road/16 The End.flac'),
 ('${T[25]}', '${J[6]}', 'audio_track', 16, '17', 'Her Majesty',                              'done', 1, 25,  25,  '/media/music/The Beatles/Abbey Road/17 Her Majesty.flac');

-- Multi-title DVD (J8, ripped): a double feature whose 3 video tracks are each a
-- separate movie. Titles are UNSET on purpose so the disc demonstrates per-track
-- matching (click a track's Title cell -> search/Set manually -> applies to that
-- track only). Two main features + a short excluded trailers reel.
INSERT INTO tracks (id, job_id, kind, index, source_ref, label, status, attempts, duration_seconds, expected_duration_seconds, size_bytes, expected_size_bytes, output_path, excluded) VALUES
 ('${T[8]}',  '${J[8]}', 'video_title', 0, 'title00', 'Feature A', 'done', 1, 5520, 5520, 6900000000, 6900000000, '/media/movie/Cult Double Feature/title00.mkv', false),
 ('${T[9]}',  '${J[8]}', 'video_title', 1, 'title01', 'Feature B', 'done', 1, 5280, 5280, 6600000000, 6600000000, '/media/movie/Cult Double Feature/title01.mkv', false),
 ('${T[10]}', '${J[8]}', 'video_title', 2, 'title02', 'Trailers',  'done', 1, 540,  540,  700000000,  700000000,  '/media/movie/Cult Double Feature/title02.mkv', true);

-- Blu-ray title-class jobs + scan-failure jobs (project blackbird, 0051/0054). The 3 Blu-ray
-- jobs are in the review gate / ripped per title; the 6 failed jobs carry failure_reason.
INSERT INTO jobs (id, drive_id, disc_type, title, year, status, metadata_json, resumed_from_crash, wait_start_time, started_at, ripped_at, created_at, failure_reason) VALUES
 ('${J[9]}',  '${DRV}', 'bluray',  'Neon Skyline 3D',      2024, 'awaiting_review', '{"seed":true}'::jsonb, false, now()-interval '1 min', NULL, NULL, now()-interval '2 min', NULL),
 ('${J[10]}', '${DRV}', 'bluray',  'The Final Expedition', 1989, 'awaiting_review', '{"seed":true}'::jsonb, false, now()-interval '1 min', NULL, NULL, now()-interval '3 min', NULL),
 ('${J[11]}', '${DRV}', 'bluray',  'The Glass Orchard',    2011, 'ripped',          '{"seed":true}'::jsonb, false, NULL, now()-interval '50 min', now()-interval '20 min', now()-interval '50 min', NULL),
 ('${J[12]}', '${DRV}', 'bluray',  NULL,                   NULL, 'failed',          '{"seed":true}'::jsonb, false, NULL, NULL, now()-interval '2 day', now()-interval '2 day', '${FR[0]}'),
 ('${J[13]}', '${DRV}', 'dvd',     'Dusty Disc',           2004, 'failed',          '{"seed":true}'::jsonb, false, NULL, NULL, now()-interval '3 day', now()-interval '3 day', '${FR[1]}'),
 ('${J[14]}', '${DRV}', 'bluray',  'Slow Disc',            2015, 'failed',          '{"seed":true}'::jsonb, false, NULL, NULL, now()-interval '4 day', now()-interval '4 day', '${FR[2]}'),
 ('${J[15]}', '${DRV}', 'dvd',     'Expired Build Disc',   2001, 'failed',          '{"seed":true}'::jsonb, false, NULL, NULL, now()-interval '5 day', now()-interval '5 day', '${FR[3]}'),
 ('${J[16]}', '${DRV}', 'bluray',  'Odd Disc',             2019, 'failed',          '{"seed":true}'::jsonb, false, NULL, NULL, now()-interval '6 day', now()-interval '6 day', '${FR[4]}'),
 ('${J[17]}', '${DRV}', 'unknown', 'Empty Image',          NULL, 'failed',          '{"seed":true}'::jsonb, false, NULL, NULL, now()-interval '7 day', now()-interval '7 day', '${FR[5]}');

-- Neon Skyline 3D (J9, awaiting_review): every kept/alternate class around one 3D feature.
-- title_class_ref '1' = source_ref of the kept 3D feature (t01). Primaries ticked, alternates unticked.
INSERT INTO tracks (id, job_id, kind, index, source_ref, label, status, attempts, expected_duration_seconds, expected_size_bytes, excluded, source_file, playlist_name, title_class, title_class_ref) VALUES
 ('${T[26]}', '${J[9]}', 'video_title', 0, '0', 'Making Of',                'queued', 0, 2700, 6500000000,  false, '00010.mpls', 'FPL_MakingOf',     'primary', NULL),
 ('${T[27]}', '${J[9]}', 'video_title', 1, '1', 'Main Feature (3D)',       'queued', 0, 9000, 46000000000, false, '00800.mpls', 'FPL_MainFeature3D', 'primary', NULL),
 ('${T[28]}', '${J[9]}', 'video_title', 2, '2', 'Main Feature (3D, angle 2)', 'queued', 0, 9000, 46000000000, true, '00800.mpls', 'FPL_MainFeature3D', 'angle',   '1'),
 ('${T[29]}', '${J[9]}', 'video_title', 3, '3', 'Main Feature (no chapters)', 'queued', 0, 8940, 45500000000, true, '00801.mpls', 'FPL_NoChapters',    'subset',  '1'),
 ('${T[30]}', '${J[9]}', 'video_title', 4, '4', 'Main Feature (2D)',       'queued', 0, 9000, 31000000000, true,  '00802.mpls', 'FPL_MainFeature2D', 'view',    '1'),
 ('${T[31]}', '${J[9]}', 'video_title', 5, '5', 'Main Feature (with intro)', 'queued', 0, 9030, 46100000000, true, '00803.mpls', 'FPL_WithIntro',     'variant', '1');

-- The Final Expedition (J10, awaiting_review): two primaries each with a raw .m2ts duplicate
-- (no playlist name), ten same-length decoy playlists of t00, and one extra.
INSERT INTO tracks (id, job_id, kind, index, source_ref, label, status, attempts, expected_duration_seconds, expected_size_bytes, excluded, source_file, playlist_name, title_class, title_class_ref) VALUES
 ('${T[32]}', '${J[10]}', 'video_title', 0, '0', 'Main Feature',            'queued', 0, 7620, 24500000000, false, '00800.mpls', 'FPL_MainFeature', 'primary',   NULL),
 ('${T[33]}', '${J[10]}', 'video_title', 1, '1', 'Main Feature (stream)',   'queued', 0, 7620, 24500000000, true,  '00121.m2ts', NULL,              'duplicate', '0'),
 ('${T[34]}', '${J[10]}', 'video_title', 2, '2', 'Alternate Cut',           'queued', 0, 7020, 22800000000, false, '00801.mpls', 'FPL_AltCut',      'primary',   NULL),
 ('${T[35]}', '${J[10]}', 'video_title', 3, '3', 'Alternate Cut (stream)',  'queued', 0, 7020, 22800000000, true,  '00122.m2ts', NULL,              'duplicate', '2');
INSERT INTO tracks (id, job_id, kind, index, source_ref, label, status, attempts, expected_duration_seconds, expected_size_bytes, excluded, source_file, playlist_name, title_class, title_class_ref) VALUES
${DECOY_ROWS} ('${T[46]}', '${J[10]}', 'video_title', 14, '14', 'Trailer', 'queued', 0, 150, 800000000, false, '00050.mpls', 'FPL_Trailer', 'primary', NULL);

-- The Glass Orchard (J11, ripped per title): two editions, a SKIPPED duplicate + decoy (not
-- ripped), three extras. Each ripped track has one track_stages row, one per StageStatus.
INSERT INTO tracks (id, job_id, kind, index, source_ref, label, status, attempts, duration_seconds, expected_duration_seconds, size_bytes, expected_size_bytes, output_path, excluded, source_file, playlist_name, title_class, title_class_ref) VALUES
 ('${T[47]}', '${J[11]}', 'video_title', 0, '0', 'Theatrical Cut',   'done',    1, 7200, 7200, 21000000000, 21000000000, '/raw/The Glass Orchard/title00.mkv', false, '00800.mpls', 'FPL_Theatrical', 'edition',   NULL),
 ('${T[48]}', '${J[11]}', 'video_title', 1, '1', 'Director''s Cut', 'done',    1, 7800, 7800, 22800000000, 22800000000, '/raw/The Glass Orchard/title01.mkv', false, '00801.mpls', 'FPL_Directors', 'edition',   NULL),
 ('${T[49]}', '${J[11]}', 'video_title', 2, '2', 'Theatrical (stream)', 'skipped', 0, NULL, 7200, NULL, 21000000000, NULL, true, '00045.m2ts', NULL,             'duplicate', '0'),
 ('${T[50]}', '${J[11]}', 'video_title', 3, '3', 'Decoy Playlist',   'skipped', 0, NULL, 7200, NULL, 21000000000, NULL, true, '00900.mpls', 'FPL_Decoy0',     'decoy',     '0'),
 ('${T[51]}', '${J[11]}', 'video_title', 4, '4', 'Making Of',        'done',    1, 1800, 1800, 3100000000, 3100000000, '/raw/The Glass Orchard/title04.mkv', false, '00020.mpls', 'FPL_MakingOf',   'primary',   NULL),
 ('${T[52]}', '${J[11]}', 'video_title', 5, '5', 'Deleted Scenes',   'done',    1, 900,  900,  1500000000, 1500000000, '/raw/The Glass Orchard/title05.mkv', false, '00021.mpls', 'FPL_Deleted',    'primary',   NULL),
 ('${T[53]}', '${J[11]}', 'video_title', 6, '6', 'Gag Reel',         'done',    1, 420,  420,  700000000,  700000000,  '/raw/The Glass Orchard/title06.mkv', false, '00022.mpls', 'FPL_GagReel',    'primary',   NULL);

-- Staging copies (0052): staged / copying / pending / failed / stalled, one per track.
INSERT INTO track_stages (id, track_id, job_id, status, source_path, source_size, source_mtime_ns, dest_path, bytes_durable, linked, attempts, last_error, heartbeat_at, staged_at) VALUES
 ('${S[0]}', '${T[47]}', '${J[11]}', 'staged',  '/raw/The Glass Orchard/title00.mkv', 21000000000, 1796000000000000000, '/staging/The Glass Orchard/title00.mkv', 21000000000, true,  1, NULL, now()-interval '15 min', now()-interval '15 min'),
 ('${S[1]}', '${T[48]}', '${J[11]}', 'copying', '/raw/The Glass Orchard/title01.mkv', 22800000000, 1796000000000000001, '/staging/The Glass Orchard/title01.mkv', 9100000000,  false, 1, NULL, now(),                   NULL),
 ('${S[2]}', '${T[51]}', '${J[11]}', 'pending', '/raw/The Glass Orchard/title04.mkv', NULL,        NULL,                '/staging/The Glass Orchard/title04.mkv', 0,           NULL,  0, NULL, NULL,                    NULL),
 ('${S[3]}', '${T[52]}', '${J[11]}', 'failed',  '/raw/The Glass Orchard/title05.mkv', 1500000000,  1796000000000000002, '/staging/The Glass Orchard/title05.mkv', 400000000,   false, 3, 'source file vanished from /raw during copy', now()-interval '10 min', NULL),
 ('${S[4]}', '${T[53]}', '${J[11]}', 'stalled', '/raw/The Glass Orchard/title06.mkv', 700000000,   1796000000000000003, '/staging/The Glass Orchard/title06.mkv', 120000000,   false, 1, NULL, now()-interval '8 min',  NULL);

-- Disc fingerprints (read-only fingerprints section): DVD crc64, Blu-ray aacs, CD musicbrainz, multi-DVD crc64.
INSERT INTO disc_fingerprints (id, job_id, algo, value, created_at) VALUES
 ('${F[0]}', '${J[1]}', 'crc64',       'A1B2C3D4E5F60789',                      now()-interval '2 hour'),
 ('${F[1]}', '${J[0]}', 'aacs',        'aacs-0123456789abcdef0123456789abcdef', now()-interval '5 min'),
 ('${F[2]}', '${J[6]}', 'musicbrainz', '6bb3793b-f991-378e-9bff-0bd3117f2298',  now()-interval '6 hour'),
 ('${F[3]}', '${J[8]}', 'crc64',       'D00BLEFEATURE1234',                     now()-interval '4 hour'),
 ('${F[4]}', '${J[9]}', 'aacs',        'aacs-3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d', now()-interval '2 min'),
 ('${F[5]}', '${J[10]}', 'aacs',       'aacs-decoy0decoy0decoy0decoy0decoy0de', now()-interval '3 min');

COMMIT;
EOF

# Seed logs: prune any prior seed log files (their job ids were regenerated),
# then write a fresh per-job log for each of the 18 new job ids.
clean_seed_logs >/dev/null
seed_logs "${J[*]}" "$(printf '%s\n' "${FAIL_REASONS[@]}")"

echo "seeded 3 drives + 18 jobs + 54 tracks + 5 track stages + 6 fingerprints + per-job logs (tagged metadata_json {\"seed\":true})"
echo "  spans: ripping / ripped / identified / awaiting_user_id / awaiting_review / ripped_partial / failed,"
echo "  video tracks (excluded, custom_filename, failed+last_error, mixed status), CD music"
echo "  tracklists (single + multi-disc), crc64/aacs/musicbrainz fingerprints, and per-job logs."
echo "  blackbird: Blu-ray title classes (3D angle/subset/view, decoys, duplicates, editions),"
echo "  staging rows in every stage, failure reasons, a scanning drive, per-drive rip-end override."
echo "  view at https://localhost:8081 (login admin / admin); re-run is safe; --clean to remove"
