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


# --- transcode CA check -----------------------------------------------------


def _pem(seed: bytes) -> str:
    import base64

    body = base64.encodebytes(seed * 20).decode()
    return f"-----BEGIN CERTIFICATE-----\n{body}-----END CERTIFICATE-----\n"


def _ca_client(host_pem: bytes | Exception) -> MagicMock:
    client = MagicMock()
    if isinstance(host_pem, Exception):
        client.containers.run.side_effect = host_pem
    else:
        client.containers.run.return_value = host_pem
    return client


def _settings_for_ca(**over):
    from tests.test_transcode_dispatcher import _settings

    return _settings(ARM_TRANSCODE_IMAGE="arm-transcode:test", **over)


def test_certs_dir_difference_flags_local_transcode_with_two_certs_dirs() -> None:
    from arm_backend.docker_probe import certs_dir_difference

    msg = certs_dir_difference(_settings_for_ca(ARM_HOST_CERTS_PATH="/a/certs", ARM_RIPPER_CERTS_PATH="/b/certs"))
    assert msg is not None
    assert "/a/certs" in msg and "/b/certs" in msg


def test_certs_dir_difference_ignores_equal_unset_and_remote() -> None:
    from arm_backend.docker_probe import certs_dir_difference

    assert (
        certs_dir_difference(_settings_for_ca(ARM_HOST_CERTS_PATH="/a/certs", ARM_RIPPER_CERTS_PATH="/a/certs/"))
        is None
    )
    assert certs_dir_difference(_settings_for_ca(ARM_HOST_CERTS_PATH="/a/certs", ARM_RIPPER_CERTS_PATH="")) is None
    remote = _settings_for_ca(
        ARM_HOST_CERTS_PATH="/a", ARM_RIPPER_CERTS_PATH="/b", ARM_TRANSCODE_DOCKER_HOST="ssh://u@h"
    )
    assert certs_dir_difference(remote) is None


def test_ca_probe_ok_when_the_mounted_ca_is_the_backends_ca(tmp_path) -> None:
    from arm_backend.docker_probe import probe_transcode_ca

    ca = tmp_path / "arm-ca.crt"
    ca.write_text(_pem(b"mine"))
    client = _ca_client(_pem(b"mine").encode())
    assert probe_transcode_ca(client, _settings_for_ca(), ca_file=str(ca)) == (True, None)
    kwargs = client.containers.run.call_args.kwargs
    assert kwargs["entrypoint"] == ["cat"]
    mount = kwargs["mounts"][0]
    assert mount["Source"] == "/host/certs/arm-ca.crt" and mount["ReadOnly"] is True


def test_ca_probe_flags_a_ca_that_did_not_sign_this_backend(tmp_path) -> None:
    from arm_backend.docker_probe import probe_transcode_ca

    ca = tmp_path / "arm-ca.crt"
    ca.write_text(_pem(b"mine"))
    ok, detail = probe_transcode_ca(_ca_client(_pem(b"other").encode()), _settings_for_ca(), ca_file=str(ca))
    assert ok is False
    assert detail is not None
    assert "/host/certs/arm-ca.crt" in detail and "ARM_HOST_CERTS_PATH" in detail


def test_ca_probe_reports_an_unreadable_mount(tmp_path) -> None:
    from arm_backend.docker_probe import probe_transcode_ca

    ca = tmp_path / "arm-ca.crt"
    ca.write_text(_pem(b"mine"))
    err = docker.errors.APIError("invalid mount config: bind source path does not exist: /host/certs/arm-ca.crt")
    ok, detail = probe_transcode_ca(_ca_client(err), _settings_for_ca(), ca_file=str(ca))
    assert ok is False and detail is not None and "/host/certs/arm-ca.crt" in detail


def test_ca_probe_skips_when_not_checkable(tmp_path) -> None:
    from arm_backend.docker_probe import probe_transcode_ca

    client = _ca_client(_pem(b"x").encode())
    # no CA file visible to the backend
    assert probe_transcode_ca(client, _settings_for_ca(), ca_file=str(tmp_path / "none")) == (True, None)
    ca = tmp_path / "arm-ca.crt"
    ca.write_text(_pem(b"mine"))
    # remote transcode: the host's certs are not this host's business here
    remote = _settings_for_ca(ARM_TRANSCODE_DOCKER_HOST="ssh://u@h")
    assert probe_transcode_ca(client, remote, ca_file=str(ca)) == (True, None)
    # the image is missing: probe_docker reports that
    client.containers.run.side_effect = docker.errors.ImageNotFound("nope")
    assert probe_transcode_ca(client, _settings_for_ca(), ca_file=str(ca)) == (True, None)
