"""stack_identity_env: the uid/gid (and cdrom gid) a spawned container drops to."""

from __future__ import annotations

from typing import Any

from arm_backend.config import Settings
from arm_backend.stack_identity import stack_identity_env


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "DATABASE_URL": "postgresql://x:x@localhost/x",
        "ARM_SERVICE_TOKEN": "tok-service",
        "PUID": "",
        "PGID": "",
        "CDROM_GID": "",
    }
    base.update(overrides)
    return Settings(**base)


def test_returns_the_stack_puid_and_pgid() -> None:
    assert stack_identity_env(_settings(PUID="1001", PGID="1001")) == {"PUID": "1001", "PGID": "1001"}


def test_adds_the_cdrom_gid_when_asked() -> None:
    env = stack_identity_env(_settings(PUID="1001", PGID="1001", CDROM_GID="24"), include_cdrom=True)
    assert env == {"PUID": "1001", "PGID": "1001", "CDROM_GID": "24"}


def test_leaves_out_the_cdrom_gid_unless_asked() -> None:
    assert "CDROM_GID" not in stack_identity_env(_settings(PUID="1001", PGID="1001", CDROM_GID="24"))


def test_an_override_replaces_only_its_own_id() -> None:
    env = stack_identity_env(_settings(PUID="1001", PGID="1001"), overrides={"PUID": "2000"})
    assert env == {"PUID": "2000", "PGID": "1001"}


def test_an_empty_override_falls_back_to_the_stack_value() -> None:
    env = stack_identity_env(_settings(PUID="1001", PGID="1001"), overrides={"PUID": "", "PGID": ""})
    assert env == {"PUID": "1001", "PGID": "1001"}


def test_nothing_set_returns_nothing() -> None:
    assert stack_identity_env(_settings(), include_cdrom=True) == {}


def test_an_override_alone_is_used_when_the_stack_value_is_empty() -> None:
    assert stack_identity_env(_settings(), overrides={"PUID": "2000"}) == {"PUID": "2000"}
