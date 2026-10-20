import pytest

from arm_common import JobStatus
from arm_common.models._columns import _StrEnumString, enum_value_str


def test_enum_value_str_known_member_returns_value():
    assert enum_value_str(JobStatus.AWAITING_REVIEW) == "awaiting_review"


def test_enum_value_str_raw_string_returns_string():
    # A forward-incompatible status loaded as a raw str by _StrEnumString has no
    # `.value`; the helper must return it unchanged instead of raising.
    assert enum_value_str("some_future_status") == "some_future_status"


def test_str_enum_string_round_trips_known_value():
    col = _StrEnumString(JobStatus)
    assert col.process_bind_param(JobStatus.RIPPING, None) == "ripping"
    assert col.process_result_value("ripping", None) is JobStatus.RIPPING


def test_str_enum_string_tolerates_unknown_value_on_load():
    # An enum member written by a NEWER build must load as the raw string, not raise.
    col = _StrEnumString(JobStatus)
    loaded = col.process_result_value("some_future_status", None)
    assert loaded == "some_future_status"
    assert not isinstance(loaded, JobStatus)


def test_str_enum_string_passes_none_through():
    col = _StrEnumString(JobStatus)
    assert col.process_bind_param(None, None) is None
    assert col.process_result_value(None, None) is None


def test_str_enum_string_accepts_exact_string_value_on_bind():
    col = _StrEnumString(JobStatus)
    assert col.process_bind_param("ripping", None) == "ripping"


def test_str_enum_string_rejects_unknown_value_on_bind():
    # D-187: enums are VARCHAR in the DB, so the bind processor is the write-time
    # guardrail. A non-member must raise instead of being written verbatim.
    col = _StrEnumString(JobStatus)
    with pytest.raises(ValueError, match="not a valid JobStatus value"):
        col.process_bind_param("bogus", None)


def test_str_enum_string_cache_key_includes_enum_class():
    # D-188: cache_ok types are keyed on __init__ args stored under the same
    # name; otherwise every enum column type shares one compilation cache key.
    from sqlalchemy import literal, select

    from arm_common import DriveStatus

    job_t, drive_t = _StrEnumString(JobStatus), _StrEnumString(DriveStatus)
    assert job_t._static_cache_key != drive_t._static_cache_key
    assert _StrEnumString(JobStatus)._static_cache_key == job_t._static_cache_key

    job_stmt = select(literal(JobStatus.RIPPING, type_=job_t))
    drive_stmt = select(literal(DriveStatus.ONLINE, type_=drive_t))
    job_key, drive_key = job_stmt._generate_cache_key(), drive_stmt._generate_cache_key()
    assert job_key is not None and drive_key is not None
    assert job_key.key != drive_key.key
