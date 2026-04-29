"""HandBrakeCLI JSON progress parser."""

from __future__ import annotations

from arm_transcode.handbrake import _extract_progress


def test_extract_progress_from_working_block() -> None:
    obj = {
        "Working": {
            "Progress": 0.4275,
            "ETASeconds": 1234,
            "PassID": "main",
            "Pass": 1,
            "PassCount": 1,
        }
    }
    pct, eta, current = _extract_progress(obj)
    assert pct == 43
    assert eta == 1234
    assert current == "main"


def test_extract_progress_handles_zero() -> None:
    obj = {"Working": {"Progress": 0.0, "ETASeconds": 0, "PassID": "subtitle scan"}}
    pct, eta, _ = _extract_progress(obj)
    assert pct == 0
    assert eta == 0


def test_extract_progress_handles_one_hundred() -> None:
    obj = {"Working": {"Progress": 1.0}}
    pct, _, _ = _extract_progress(obj)
    assert pct == 100


def test_extract_progress_empty_when_no_working_block() -> None:
    assert _extract_progress({}) == (None, None, None)
    assert _extract_progress({"WorkDone": {"Error": 0}}) == (None, None, None)


def test_extract_progress_handles_missing_eta() -> None:
    obj = {"Working": {"Progress": 0.5}}
    pct, eta, _ = _extract_progress(obj)
    assert pct == 50
    assert eta is None
