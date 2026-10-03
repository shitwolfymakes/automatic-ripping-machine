#!/usr/bin/env bash
# Manage the ripper containers the backend creates per enrolled drive.
# They carry the label arm.drive_id and live OUTSIDE the compose project, so
# `docker compose down` leaves them running (and they pin the network).
#
#   bash devtools/ripper-containers.sh list     # name, drive id, image, state
#   bash devtools/ripper-containers.sh stop     # stop all (they restart on `docker start` / backend boot)
#   bash devtools/ripper-containers.sh remove   # stop + remove all (the backend recreates enrolled ones at next boot)
#
# Do not run `remove` while a drive is ripping — `docker rm -f` SIGKILLs makemkvcon.
set -euo pipefail

LABEL="arm.drive_id"
cmd="${1:-list}"

ids() { docker ps -aq --filter "label=${LABEL}"; }

case "${cmd}" in
    list)
        docker ps -a --filter "label=${LABEL}" \
            --format 'table {{.Names}}\t{{.Label "arm.drive_id"}}\t{{.Image}}\t{{.Status}}'
        ;;
    stop)
        mapfile -t targets < <(ids)
        if (( ${#targets[@]} == 0 )); then echo "no ripper containers"; exit 0; fi
        docker stop "${targets[@]}"
        ;;
    remove)
        mapfile -t targets < <(ids)
        if (( ${#targets[@]} == 0 )); then echo "no ripper containers"; exit 0; fi
        docker rm -f "${targets[@]}"
        echo "removed ${#targets[@]} container(s); enrolled drives are recreated when arm-backend next starts"
        echo "run \`docker compose restart arm-backend\` to recreate enrolled drives now"
        ;;
    *)
        echo "usage: $0 {list|stop|remove}" >&2
        exit 2
        ;;
esac
