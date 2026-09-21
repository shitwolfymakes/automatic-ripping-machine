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
