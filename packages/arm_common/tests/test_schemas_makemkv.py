from datetime import datetime, timezone

from arm_common import MakemkvKeyState
from arm_common.schemas import ConfigView, MakemkvKeyStatusReport, MetadataKeyTestResponse


def test_report_schema_roundtrip():
    r = MakemkvKeyStatusReport(state=MakemkvKeyState.VALID, detail="ok")
    assert r.state == MakemkvKeyState.VALID
    assert r.detail == "ok"
    # detail optional
    assert MakemkvKeyStatusReport(state=MakemkvKeyState.PROBE_FAILED).detail is None


def test_test_key_response_valid_is_tristate_and_has_checked_at():
    now = datetime.now(timezone.utc)
    ok = MetadataKeyTestResponse(provider="makemkv", valid=None, detail="unknown", checked_at=now)
    assert ok.valid is None
    assert ok.checked_at == now
    # back-compat: valid bool + no checked_at still constructs
    assert MetadataKeyTestResponse(provider="omdb", valid=True).checked_at is None


def test_config_view_has_makemkv_status_fields():
    fields = ConfigView.model_fields
    assert "makemkv_key_valid" in fields
    assert "makemkv_key_state" in fields
    assert "makemkv_key_checked_at" in fields
