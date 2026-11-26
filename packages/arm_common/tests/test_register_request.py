from __future__ import annotations

import pytest
from pydantic import ValidationError

from arm_common.schemas import RegisterRequest


def test_register_request_is_keyed_on_drive_id() -> None:
    req = RegisterRequest(drive_id="drv_1", hostname="arm-ripper-abc", device_path="/dev/sr0", ripper_version="3")
    assert req.drive_id == "drv_1" and req.by_id_name is None and req.hw_caps == {}


def test_register_request_requires_drive_id() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(hostname="h", device_path="/dev/sr0", ripper_version="3")  # type: ignore[call-arg]


def test_register_request_has_no_serial_field() -> None:
    assert "serial" not in RegisterRequest.model_fields


def test_transcoder_register_request_schema_hash_is_optional() -> None:
    from arm_common.schemas import RegisterTranscoderRequest

    base = {"task_id": "txt_1", "hostname": "h", "hw_caps": {"cpu_count": 4}}
    assert RegisterTranscoderRequest.model_validate(base).schema_hash is None
    assert RegisterTranscoderRequest.model_validate({**base, "schema_hash": "abc"}).schema_hash == "abc"
