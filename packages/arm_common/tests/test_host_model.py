from datetime import datetime, timezone

from arm_common import Host


def test_host_row_fields():
    now = datetime.now(timezone.utc)
    h = Host(hostname="ripper-sr0", role="ripper", version="1.2.3", first_seen=now, last_seen=now)
    assert h.hostname == "ripper-sr0"
    assert h.role == "ripper"
    assert h.version == "1.2.3"
    assert h.first_seen == now
    assert h.last_seen == now


def test_host_tablename():
    assert Host.__tablename__ == "hosts"
