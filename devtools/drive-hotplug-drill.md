# Drive lifecycle acceptance drill (quark, real hardware)

Spec §7: what tier-1 cannot prove. Run on a **fresh** install before merging the
drive-lifecycle stack (PRs #61/#62/#64). The last step is the acceptance test.

## Fresh install
1. `bash devtools/ripper-containers.sh remove` (if a previous stack ran), `docker compose down -v`, `rm -rf arm/db`.
2. `bash devtools/setup-dev.sh` — no drive questions, no `lsscsi`, no `arm-ripper-srN` in `docker-compose.yml`.
3. `docker compose up -d --build` — builds `arm-ripper:latest`; `docker ps` shows **no** ripper.
4. Log in, rotate the seeded password.

## Checks — each must pass
| # | Action | Expect |
|---|---|---|
| 1 | open Drives | the plugged-in drive is listed under **Detected** with model, serial, `/dev/srN`; Dashboard says `0 / 0` drives |
| 2 | **Enroll** | row moves to Enrolled within a few seconds; `docker ps` shows `arm-ripper-<serial>` with label `arm.drive_id`; its log: `optical nodes: created …`, `drive present at /dev/srN via by_id`, `registered drive_id=…`; Diagnostics `ripper_manager` = ok |
| 3 | insert a known-good DVD | a job is created; makemkv scan finds titles (`TCOUNT` > 0) |
| 4 | unplug the USB cable mid-idle (not mid-rip for this row) | Drives shows **○ detached — reconnect the drive**, row greyed; Dashboard online count drops; container stays `Up`; exactly one `drive absent` log line, no ioctl storm after 2 min |
| 5 | replug | row returns to `online` with the **current** node (may be `/dev/sr1`); log `drive present at /dev/srN via by_id (reattached)` + `boot probe after reattach` |
| 6 | insert a different disc (or re-seat) | **a new job starts with no intervention** — no restart, no compose, no click. This is the acceptance test. |
| 7 | unplug **during** a rip, replug, re-seat | rip fails/abandons cleanly; eject targets the new node; next disc rips |
| 8 | `docker compose build arm-ripper` (touch a comment in `services/ripper/`), `docker compose restart arm-backend` | backend log `ripper reconcile: … recreated=1`; the container runs the new image id; an in-progress rip would have been adopted instead |
| 9 | **Unenroll** | container gone from `docker ps`; row back under Detected |
| 10 | **Ignore** → collapsed section shows `Ignored (1) ▸`; **Un-ignore** → Detected | persisted across a backend restart |
| 11 | `sudo dmesg -T \| grep 'usb .*: reset'` | no reset storm around the replugs (≤1 each) |

Do NOT kill `makemkvcon` with `timeout` during the drill; interrupted SCSI commands make the drive reset.

## Record
Paste the log excerpts for checks 2, 4, 5, 6 and 8 into the PR.
