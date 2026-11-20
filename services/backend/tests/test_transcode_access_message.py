"""The plain-language message for a transcoder that cannot use its folders."""

from __future__ import annotations

from typing import Any

from arm_backend.config import Settings
from arm_backend.transcode_access_message import (
    ACCESS_ERROR_PREFIX,
    AccessFailure,
    access_failure_message,
    parse_access_failure,
)

_WRITE = "FATAL: /logs is not writable by arm (PUID:PGID=1000:1000); dir owner is 1001:1001."
_READ = "FATAL: /raw is not readable by arm (read-only mount) (PUID:PGID=1000:1000); dir owner is 1001:1001."


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "ARM_HOST_RAW_PATH": "/home/nue_arm/arm/raw",
        "ARM_HOST_MEDIA_PATH": "/home/nue_arm/arm/media",
        "ARM_HOST_LOGS_PATH": "/home/nue_arm/arm/logs",
        "ARM_HOST_CERTS_PATH": "/home/nue_arm/arm/certs",
        "ARM_TRANSCODE_DOCKER_HOST": "",
    }
    base.update(overrides)
    return Settings.model_construct(**base)


def test_parses_the_not_writable_line() -> None:
    assert parse_access_failure(_WRITE) == AccessFailure("/logs", "write", "1000:1000", "1001:1001")


def test_parses_the_read_only_line() -> None:
    assert parse_access_failure(_READ) == AccessFailure("/raw", "read", "1000:1000", "1001:1001")


def test_finds_the_line_among_the_entrypoints_other_output_and_bytes() -> None:
    stderr = ("arm: dropping to 1000:1000\n" + _WRITE + "\n       ARM does not chown user-mounted volumes.\n").encode()
    assert parse_access_failure(stderr) == AccessFailure("/logs", "write", "1000:1000", "1001:1001")


def test_no_fatal_line_is_not_an_access_failure() -> None:
    assert parse_access_failure("Traceback (most recent call last):\n  boom") is None


def test_local_write_message() -> None:
    msg = access_failure_message(parse_access_failure(_WRITE), _settings())  # type: ignore[arg-type]
    assert msg == (
        "Transcodes will fail: the transcoder runs as user 1000:1000, but its logs folder "
        "/home/nue_arm/arm/logs on this machine is owned by 1001:1001. Set ARM_TRANSCODE_PUID=1001 "
        "and ARM_TRANSCODE_PGID=1001 in .env, or make the folder writable by 1000:1000."
    )
    assert msg.startswith(ACCESS_ERROR_PREFIX)


def test_remote_write_message_names_the_host_and_its_folder() -> None:
    failure = AccessFailure("/media", "write", "1000:1000", "1003:1003")
    msg = access_failure_message(
        failure, _settings(ARM_HOST_MEDIA_PATH="/mnt/nas/media", ARM_TRANSCODE_DOCKER_HOST="ssh://sam@192.168.0.92")
    )
    assert "its media folder /mnt/nas/media on transcode host 192.168.0.92 is owned by 1003:1003" in msg
    assert "Set ARM_TRANSCODE_PUID=1003 and ARM_TRANSCODE_PGID=1003 in .env" in msg


def test_read_message_for_the_raw_folder() -> None:
    msg = access_failure_message(parse_access_failure(_READ), _settings())  # type: ignore[arg-type]
    assert msg == (
        "Transcodes will fail: the transcoder runs as user 1000:1000 and cannot read its raw rips folder "
        "/home/nue_arm/arm/raw on this machine, which is owned by 1001:1001. Set ARM_TRANSCODE_PUID=1001 "
        "and ARM_TRANSCODE_PGID=1001 in .env, or make the folder readable by 1000:1000."
    )


def test_a_tcp_docker_host_names_its_address() -> None:
    failure = AccessFailure("/logs", "write", "1000:1000", "1001:1001")
    msg = access_failure_message(failure, _settings(ARM_TRANSCODE_DOCKER_HOST="tcp://10.0.0.5:2375"))
    assert "on transcode host 10.0.0.5" in msg


def test_a_docker_host_without_a_hostname_reads_as_this_machine() -> None:
    failure = AccessFailure("/logs", "write", "1000:1000", "1001:1001")
    msg = access_failure_message(failure, _settings(ARM_TRANSCODE_DOCKER_HOST="unix:///var/run/docker.sock"))
    assert "on this machine" in msg


def test_an_unmapped_folder_falls_back_to_its_container_path() -> None:
    failure = AccessFailure("/data", "write", "1000:1000", "1001:1001")
    msg = access_failure_message(failure, _settings())
    assert "its folder /data on this machine" in msg
