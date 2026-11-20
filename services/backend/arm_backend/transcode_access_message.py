"""A transcoder that cannot use its folders, in the operator's terms.

The container entrypoint refuses to start when a mounted folder is not usable
by the uid:gid it drops to, with a `FATAL: … is not writable by arm …` (or
`… is not readable by arm (read-only mount) …`) line. These helpers find that
line and turn it into a message naming the folder on the host, the machine it
is on, and the two ways to fix it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from arm_backend.config import Settings
from arm_backend.transcode_container_spec import task_volumes

ACCESS_ERROR_PREFIX = "Transcodes will fail: "

_FATAL = re.compile(
    r"FATAL: (?P<dir>\S+) is not (?P<verb>writable|readable) by arm (?:\(read-only mount\) )?"
    r"\(PUID:PGID=(?P<run_as>\d+:\d+)\); dir owner is (?P<owner>\d+:\d+)"
)

_FOLDER_NAMES = {"/raw": "raw rips folder", "/media": "media folder", "/logs": "logs folder"}


@dataclass(frozen=True)
class AccessFailure:
    container_dir: str
    mode: Literal["write", "read"]
    run_as: str
    owner: str


def parse_access_failure(stderr: bytes | str) -> AccessFailure | None:
    """The entrypoint's first folder-access FATAL line, or None when there is none."""
    text = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else stderr
    match = _FATAL.search(text)
    if match is None:
        return None
    mode: Literal["write", "read"] = "write" if match["verb"] == "writable" else "read"
    return AccessFailure(match["dir"], mode, match["run_as"], match["owner"])


def _host_path(container_dir: str, settings: Settings) -> str:
    for host, mount in task_volumes(settings).items():
        if mount["bind"] == container_dir:
            return host
    return container_dir


def _machine(settings: Settings) -> str:
    host = urlparse(settings.ARM_TRANSCODE_DOCKER_HOST).hostname if settings.ARM_TRANSCODE_DOCKER_HOST else None
    return f"on transcode host {host}" if host else "on this machine"


def access_failure_message(failure: AccessFailure, settings: Settings) -> str:
    """What is wrong, where, and how to fix it."""
    folder = f"{_FOLDER_NAMES.get(failure.container_dir, 'folder')} {_host_path(failure.container_dir, settings)}"
    where = f"{folder} {_machine(settings)}"
    owner_uid, owner_gid = failure.owner.split(":")
    fix = f"Set ARM_TRANSCODE_PUID={owner_uid} and ARM_TRANSCODE_PGID={owner_gid} in .env, or make the folder"
    if failure.mode == "write":
        return (
            f"{ACCESS_ERROR_PREFIX}the transcoder runs as user {failure.run_as}, but its {where} is owned by "
            f"{failure.owner}. {fix} writable by {failure.run_as}."
        )
    return (
        f"{ACCESS_ERROR_PREFIX}the transcoder runs as user {failure.run_as} and cannot read its {where}, "
        f"which is owned by {failure.owner}. {fix} readable by {failure.run_as}."
    )
