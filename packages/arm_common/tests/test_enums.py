from arm_common import KeydbState, MakemkvKeyState


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


def test_keydb_state_members_are_lowercase_strings():
    assert KeydbState.OK.value == "ok"
    assert KeydbState.DISABLED.value == "disabled"
    assert KeydbState.FRESH_KEPT.value == "fresh_kept"
    assert KeydbState.DOWNLOAD_FAILED.value == "download_failed"
    assert KeydbState.EMPTY.value == "empty"
    assert KeydbState.PROBE_FAILED.value == "probe_failed"
    # Round-trips from the wire string the script emits.
    assert KeydbState("fresh_kept") is KeydbState.FRESH_KEPT
    assert {m.value for m in KeydbState} == {
        "ok",
        "disabled",
        "fresh_kept",
        "download_failed",
        "empty",
        "probe_failed",
    }
