from arm_common.schemas.job_metadata import flag_is_set, without_flags


def test_without_flags_removes_the_flag_and_its_legacy_key() -> None:
    md = {"unidentified": True, "flags": {"unidentified": True, "dispatch_timeout": True}, "title": "X"}
    out = without_flags(md, "unidentified")
    assert out == {"flags": {"dispatch_timeout": True}, "title": "X"}
    assert not flag_is_set(out, "unidentified")
    # The input bag is left as it was.
    assert md["flags"] == {"unidentified": True, "dispatch_timeout": True}
    assert md["unidentified"] is True


def test_without_flags_adds_no_flags_section_when_there_is_none() -> None:
    assert without_flags({"unidentified": True}, "unidentified") == {}
    assert without_flags(None, "unidentified") == {}
