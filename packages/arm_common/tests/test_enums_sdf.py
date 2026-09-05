from arm_common import MakemkvSdfState


def test_sdf_state_values():
    assert MakemkvSdfState.UPDATED == "updated"
    assert MakemkvSdfState.FRESH_KEPT == "fresh_kept"
    assert MakemkvSdfState.DISABLED == "disabled"
    assert MakemkvSdfState.DOWNLOAD_FAILED == "download_failed"
    assert MakemkvSdfState.PROBE_FAILED == "probe_failed"


def test_sdf_state_roundtrips_from_varchar():
    assert MakemkvSdfState("fresh_kept") is MakemkvSdfState.FRESH_KEPT
