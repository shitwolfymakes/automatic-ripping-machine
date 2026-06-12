import pytest
from pydantic import ValidationError

from arm_common.schemas import (
    AppriseChannelConfig,
    NotificationChannelCreateRequest,
    NotificationTestRequest,
)


def test_apprise_config_defaults() -> None:
    c = AppriseChannelConfig()
    assert c.type == "apprise"
    assert c.url == ""
    assert c.service_id is None
    assert c.fields is None


def test_create_request_requires_apprise_type() -> None:
    req = NotificationChannelCreateRequest(name="D", config=AppriseChannelConfig(url="discord://1/2"))
    assert req.type == "apprise"
    assert req.enabled is True
    assert req.subscribed_events == []


def test_create_request_rejects_non_apprise_type() -> None:
    with pytest.raises(ValidationError):
        NotificationChannelCreateRequest(name="D", type="webhook", config=AppriseChannelConfig())


def test_test_request_shape() -> None:
    r = NotificationTestRequest(config=AppriseChannelConfig(service_id="discord", fields={"webhook_id": "1"}))
    assert r.event_type is None


def test_apprise_config_accepts_typed_field_values() -> None:
    c = AppriseChannelConfig(service_id="discord", fields={"webhook_id": "1", "tts": True, "flags": 4, "ratio": 0.5})
    assert c.fields == {"webhook_id": "1", "tts": True, "flags": 4, "ratio": 0.5}
