from arm_backend.notifications.message import Message


def test_message_is_frozen_dataclass() -> None:
    m = Message(
        event_id="evt_1",
        event_type="rip.completed",
        job_id="job_1",
        default_title="ARM: rip completed",
        default_body="disc",
        job=None,
        payload={},
    )
    assert m.event_id == "evt_1"
    assert m.event_type == "rip.completed"
    assert m.default_title == "ARM: rip completed"
    # frozen
    import dataclasses

    try:
        m.event_id = "x"  # type: ignore[misc]
        raised = False
    except dataclasses.FrozenInstanceError:
        raised = True
    assert raised


def test_message_carries_payload() -> None:
    m = Message(
        event_id="evt_1",
        event_type="rip.completed",
        job_id="job_1",
        default_title="t",
        default_body="b",
        job=None,
        payload={"drive_id": "sr0", "tracks_total": 3},
    )
    assert m.payload["drive_id"] == "sr0"
    assert m.payload["tracks_total"] == 3
