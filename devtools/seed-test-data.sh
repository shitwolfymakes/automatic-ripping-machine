#!/usr/bin/env bash
# Seed the running dev DB with comprehensive test data to exercise the whole UI:
# 1 drive + 9 status-spanning jobs + video/audio tracks (full enriched column
# set) + disc fingerprints (crc64 / aacs / musicbrainz) + music CDs (single +
# multi-disc) carrying a MusicBrainz-shaped tracklist in metadata_json, plus a
# per-job aggregated log file for each job (so the Logs screen has data).
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
              1 drive + 9 jobs (spanning statuses) + tracks + fingerprints +
              music tracklists (single + multi-disc) + per-job logs.
  --clean     Remove the seed rows (jobs+tracks+fingerprints+drive) + logs.
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
        echo "stack not running ($svc is down); start it with: docker compose up -d" >&2
        exit 1
    fi
done
if ! docker compose exec -T arm-db psql -U arm -d arm -c 'SELECT 1' >/dev/null 2>&1; then
    echo "cannot reach the database (arm-db); is the stack healthy?" >&2
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
# Args: the 9 job ULIDs in fixture order (Blade Runner, Matrix, Dune, untitled,
# Oppenheimer, Scratched Disc, Abbey Road, The Wall, Cult Double Feature). Emits
# appropriate NDJSON in the arm_common log shape so the Logs screen + its
# level/text filters have data. Status is derived from the job's position
# (matches the INSERT order below).
seed_logs() {
    docker compose exec -T -e SEED_JOB_IDS="$1" arm-backend python - <<'PY'
import json, os
from datetime import datetime, timedelta, UTC

ids = os.environ["SEED_JOB_IDS"].split()
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
]

def script(title, status):
    lines = [
        (0, "info", "arm_backend",          f"job created for disc '{title}'"),
        (2, "info", "arm_backend.identify", "querying provider for disc metadata"),
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
DELETE FROM disc_fingerprints WHERE job_id IN (SELECT id FROM jobs WHERE metadata_json @> '{"seed":true}');
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
    echo "removed seed rows (jobs + tracks + fingerprints + 'Test Drive (seed)')"
    clean_seed_logs
    exit 0
fi

# --- generate real ULIDs via the backend (authoritative; matches route patterns) ---
# 1 drive + 9 jobs + 26 tracks + 4 fingerprints. The 9th job is a multi-title DVD
# (Cult Double Feature) whose 3 video tracks are each matched independently; the
# detail routes validate the ULID pattern, so these must be real backend ULIDs.
ids="$(docker compose exec -T arm-backend python -c "
from arm_common.ulid import new_id
print(new_id('drv'))
for _ in range(9): print(new_id('job'))
for _ in range(26): print(new_id('trk'))
for _ in range(4): print(new_id('dfp'))
")"
mapfile -t ID <<<"$ids"
if [[ "${#ID[@]}" -ne 40 ]]; then
    echo "ULID generation failed (expected 40 ids, got ${#ID[@]})" >&2
    exit 1
fi
DRV="${ID[0]}"
J=("${ID[@]:1:9}")
T=("${ID[@]:10:26}")
F=("${ID[@]:36:4}")

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

INSERT INTO drives (id, hostname, device_path, display_name, status, media_status, media_status_at, drive_mode, uhd_capable)
VALUES ('${DRV}', 'seed-host', '/dev/sr-seed', 'Test Drive (seed)', 'online', 'loaded', now(), 'auto', false);

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

-- Disc fingerprints (read-only fingerprints section): DVD crc64, Blu-ray aacs, CD musicbrainz, multi-DVD crc64.
INSERT INTO disc_fingerprints (id, job_id, algo, value, created_at) VALUES
 ('${F[0]}', '${J[1]}', 'crc64',       'A1B2C3D4E5F60789',                      now()-interval '2 hour'),
 ('${F[1]}', '${J[0]}', 'aacs',        'aacs-0123456789abcdef0123456789abcdef', now()-interval '5 min'),
 ('${F[2]}', '${J[6]}', 'musicbrainz', '6bb3793b-f991-378e-9bff-0bd3117f2298',  now()-interval '6 hour'),
 ('${F[3]}', '${J[8]}', 'crc64',       'D00BLEFEATURE1234',                     now()-interval '4 hour');

COMMIT;
EOF

# Seed logs: prune any prior seed log files (their job ids were regenerated),
# then write a fresh per-job log for each of the 9 new job ids.
clean_seed_logs >/dev/null
seed_logs "${J[*]}"

echo "seeded 1 drive + 9 jobs + 26 tracks + 4 fingerprints + per-job logs (tagged metadata_json {\"seed\":true})"
echo "  spans: ripping / ripped / identified / awaiting_user_id / ripped_partial / failed,"
echo "  video tracks (excluded, custom_filename, failed+last_error, mixed status), CD music"
echo "  tracklists (single + multi-disc), crc64/aacs/musicbrainz fingerprints, and per-job logs."
echo "  view at https://localhost:8081 (login admin / admin); re-run is safe; --clean to remove"
