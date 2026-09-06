import pytest
from pydantic import ValidationError

from arm_common.schemas import (
    AppriseChannelConfig,
    BashChannelConfig,
    BashPreviewRequest,
    BashPreviewResult,
    BashRunResult,
    BashScriptInfo,
    BashScriptSummary,
    ChannelTemplate,
    ComposeUrlRequest,
    ComposeUrlResult,
    InAppChannelConfig,
    NotificationChannelCreateRequest,
    NotificationChannelTestRequest,
    NotificationChannelUpdateRequest,
    NotificationTestRequest,
    NotificationTestResult,
    ScriptInput,
    ServiceCatalog,
)


def test_event_type_info_shape():
    from arm_common.schemas import EventTypeInfo

    e = EventTypeInfo(
        key="rip.completed",
        label="Rip completed",
        variables=["job_title", "drive_id"],
        default_title="t",
        default_body="b",
    )
    assert e.key == "rip.completed" and e.variables[0] == "job_title"


def test_apprise_channel_config_defaults():
    cfg = AppriseChannelConfig()
    assert cfg.type == "apprise"
    assert cfg.url == ""
    assert cfg.service_id is None
    assert cfg.fields is None


def test_inapp_channel_config():
    cfg = InAppChannelConfig()
    assert cfg.type == "inapp"


def test_channel_template_optional_fields():
    t = ChannelTemplate()
    assert t.title is None and t.body is None
    t2 = ChannelTemplate(title="hi", body="there")
    assert t2.title == "hi"


def test_notification_test_result():
    ok = NotificationTestResult(ok=True)
    assert ok.ok is True and ok.error is None
    fail = NotificationTestResult(ok=False, error="bad")
    assert fail.error == "bad"


def test_compose_url_request_and_result():
    req = ComposeUrlRequest(required={"a": 1}, advanced={"b": 2})
    assert req.required == {"a": 1}
    result = ComposeUrlResult(url="discord://x/y")
    assert result.url == "discord://x/y"


def test_notification_channel_create_request_defaults():
    req = NotificationChannelCreateRequest(
        type="apprise",
        name="Test",
        config=AppriseChannelConfig(url="json://localhost/x"),
    )
    assert req.enabled is True
    assert req.subscribed_events == []
    assert req.templates == {}


def test_notification_channel_update_request_all_optional():
    req = NotificationChannelUpdateRequest()
    assert req.name is None and req.enabled is None and req.config is None


def test_notification_test_request():
    req = NotificationTestRequest(config=AppriseChannelConfig(url="json://localhost/x"))
    assert req.event_type is None


def test_notification_channel_test_request_defaults():
    req = NotificationChannelTestRequest()
    assert req.fields == {}
    assert req.event_type is None


def test_service_catalog_shape():
    catalog = ServiceCatalog(featured=["discord"], services=[])
    assert catalog.featured == ["discord"]


def test_bash_config_defaults() -> None:
    cfg = BashChannelConfig(script="send-email.sh")
    assert (cfg.type, cfg.timeout_seconds, cfg.inputs, cfg.secret_keys) == ("bash", 30, {}, [])


@pytest.mark.parametrize("timeout", [0, 601])
def test_bash_config_timeout_bounds(timeout: int) -> None:
    with pytest.raises(ValidationError):
        BashChannelConfig(script="x.sh", timeout_seconds=timeout)


def test_channel_template_inputs_optional() -> None:
    assert ChannelTemplate().inputs is None
    assert ChannelTemplate(inputs={"TO": "x"}).inputs == {"TO": "x"}


def test_requests_accept_bash() -> None:
    body = {"type": "bash", "script": "p.sh", "inputs": {"TO": "a@b"}}
    c = NotificationChannelCreateRequest.model_validate(
        {"type": "bash", "name": "P", "config": body, "subscribed_events": []}
    )
    u = NotificationChannelUpdateRequest.model_validate({"config": body})
    t = NotificationTestRequest.model_validate({"config": body})
    assert all(isinstance(r.config, BashChannelConfig) for r in (c, u, t))


def test_script_shapes() -> None:
    inp = ScriptInput(key="TO", label="Recipient", required=True)
    assert (inp.secret, inp.default, inp.values) == (False, "", None)
    assert BashScriptSummary(name="a.sh", executable=True).description == ""
    info = BashScriptInfo(
        name="a.sh",
        executable=True,
        description="",
        size_bytes=1,
        modified_at="2026-09-06T00:00:00Z",
        inputs=[inp],
        preview="#!",
    )
    assert info.inputs[0].key == "TO"


def test_preview_shapes() -> None:
    req = BashPreviewRequest(config=BashChannelConfig(script="a.sh"), event_type="rip.completed")
    assert req.run is False and req.template is None and req.channel_id is None
    res = BashPreviewResult(
        title="t",
        body="b",
        inputs={},
        env={},
        argv=["bash"],
        result=BashRunResult(ok=True, exit_code=0, duration_ms=1, stdout="", stderr="", error=None),
    )
    assert res.error is None and res.result is not None and res.result.ok
