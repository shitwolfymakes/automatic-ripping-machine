from arm_common import KeydbState
from arm_common.schemas import KeydbStatusReport, RipperConfigView


def test_keydb_status_report_roundtrip():
    r = KeydbStatusReport(state=KeydbState.OK, vuk_count=4200, age_days=0)
    dumped = r.model_dump(mode="json")
    assert dumped == {"state": "ok", "vuk_count": 4200, "age_days": 0}
    assert KeydbStatusReport.model_validate(dumped).state is KeydbState.OK


def test_keydb_status_report_optional_fields_default_none():
    r = KeydbStatusReport(state=KeydbState.DOWNLOAD_FAILED)
    assert r.vuk_count is None and r.age_days is None


def test_ripper_config_view_carries_keydb_toggle_defaulted_true():
    v = RipperConfigView(auto_rip_on_insert=True, makemkv_key=None)
    assert v.community_keydb_enabled is True
    v2 = RipperConfigView(auto_rip_on_insert=True, makemkv_key=None, community_keydb_enabled=False)
    assert v2.community_keydb_enabled is False
