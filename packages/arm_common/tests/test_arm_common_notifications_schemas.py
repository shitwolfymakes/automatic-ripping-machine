from arm_common.schemas import (
    AppriseChannelConfig,
    ChannelTemplate,
    ComposeUrlRequest,
    ComposeUrlResult,
    InAppChannelConfig,
    NotificationChannelCreateRequest,
    NotificationChannelTestRequest,
    NotificationChannelUpdateRequest,
    NotificationTestRequest,
    NotificationTestResult,
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
