from arm_common import MakemkvKeyState
from arm_common.schemas import ConfigView, MakemkvKeyStatusReport


def test_report_schema_roundtrip():
    r = MakemkvKeyStatusReport(state=MakemkvKeyState.VALID, detail="ok")
    assert r.state == MakemkvKeyState.VALID
    assert r.detail == "ok"
    # detail optional
    assert MakemkvKeyStatusReport(state=MakemkvKeyState.PROBE_FAILED).detail is None


def test_config_view_has_makemkv_status_fields():
    fields = ConfigView.model_fields
    assert "makemkv_key_valid" in fields
    assert "makemkv_key_state" in fields
    assert "makemkv_key_checked_at" in fields
