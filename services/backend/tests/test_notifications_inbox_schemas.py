from arm_common.schemas import (
    InAppChannelConfig,
    NotificationInboxCountView,
    NotificationInboxUpdateRequest,
)


def test_inapp_config_defaults() -> None:
    c = InAppChannelConfig()
    assert c.type == "inapp"


def test_inbox_update_request_optional() -> None:
    r = NotificationInboxUpdateRequest()
    assert r.seen is None
    assert r.cleared is None
    r2 = NotificationInboxUpdateRequest(seen=True)
    assert r2.seen is True and r2.cleared is None


def test_inbox_count_view() -> None:
    v = NotificationInboxCountView(unseen=2, seen=1, cleared=0, total=3)
    assert v.total == 3
