from __future__ import annotations

from unittest.mock import MagicMock

import docker.errors

from arm_backend.docker_probe import PROBE_TTL_SECONDS, TtlProbe, probe_docker


def test_probe_docker_ok() -> None:
    client = MagicMock()
    assert probe_docker(client, "img:test") == (True, None)
    client.images.get.assert_called_once_with("img:test")


def test_probe_docker_unreachable_wins_over_image() -> None:
    client = MagicMock()
    client.ping.side_effect = docker.errors.DockerException("connect refused")
    client.images.get.side_effect = docker.errors.ImageNotFound("nope")
    ok, detail = probe_docker(client, "img:test")
    assert ok is False and detail == "docker host unreachable: connect refused"
    client.images.get.assert_not_called()


def test_probe_docker_missing_image() -> None:
    client = MagicMock()
    client.images.get.side_effect = docker.errors.ImageNotFound("nope")
    assert probe_docker(client, "img:test") == (False, "image img:test not present on docker host")


def test_probe_docker_image_check_failure() -> None:
    client = MagicMock()
    client.images.get.side_effect = docker.errors.APIError("boom")
    ok, detail = probe_docker(client, "img:test")
    assert ok is False and detail is not None and detail.startswith("image check failed: ")


def test_ttl_probe_caches_failures_within_ttl(monkeypatch) -> None:
    now = {"t": 1000.0}
    monkeypatch.setattr("arm_backend.docker_probe.time.monotonic", lambda: now["t"])
    calls = {"n": 0}

    def fn() -> tuple[bool, str | None]:
        calls["n"] += 1
        return (False, "down")

    probe = TtlProbe(fn)
    assert probe() == (False, "down")
    assert probe() == (False, "down")
    assert calls["n"] == 1
    now["t"] += PROBE_TTL_SECONDS + 1.0
    assert probe() == (False, "down")
    assert calls["n"] == 2
