from arm_common import MakemkvKeyState


def test_makemkv_key_state_members():
    assert MakemkvKeyState.VALID == "valid"
    assert MakemkvKeyState.UNREGISTERED_OR_EXPIRED == "unregistered_or_expired"
    assert MakemkvKeyState.BINARY_EXPIRED == "binary_expired"
    assert MakemkvKeyState.FORMAT_INVALID == "format_invalid"
    assert MakemkvKeyState.PROBE_FAILED == "probe_failed"
    # exactly these five — no stray members
    assert {m.value for m in MakemkvKeyState} == {
        "valid",
        "unregistered_or_expired",
        "binary_expired",
        "format_invalid",
        "probe_failed",
    }
