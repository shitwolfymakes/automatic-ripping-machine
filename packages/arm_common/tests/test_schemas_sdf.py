from arm_common import MakemkvSdfState
from arm_common.schemas import RipperConfigView, SdfStatusReport


def test_sdf_status_report_defaults():
    r = SdfStatusReport(state=MakemkvSdfState.UPDATED)
    assert r.state is MakemkvSdfState.UPDATED
    assert r.age_days is None


def test_sdf_status_report_with_age():
    r = SdfStatusReport(state=MakemkvSdfState.FRESH_KEPT, age_days=3)
    assert r.age_days == 3


def test_ripper_config_view_sdf_enabled_defaults_true():
    v = RipperConfigView(auto_rip_on_insert=False, makemkv_key=None)
    assert v.makemkv_sdf_enabled is True
