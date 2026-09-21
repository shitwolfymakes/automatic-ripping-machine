"""Unit tests for arm_transcode.main helpers."""

from __future__ import annotations

from arm_transcode.main import _MAX_ERROR_CHARS, _clip_error


def test_clip_error_passes_short_messages_through() -> None:
    msg = "HandBrakeCLI exited rc=3\nstderr tail:\nDriver does not support nvenc"
    assert _clip_error(msg) == msg


def test_clip_error_keeps_the_tail_not_the_head() -> None:
    # The decisive encoder error is the LAST line; the historical str(exc)[:500]
    # kept the head and dropped exactly this line. Verify we keep the tail.
    head = "x" * (_MAX_ERROR_CHARS * 2)
    msg = head + "\nDriver does not support the required nvenc API version"
    clipped = _clip_error(msg)
    assert len(clipped) <= _MAX_ERROR_CHARS + len("…(truncated)…\n")
    assert clipped.startswith("…(truncated)…\n")
    assert "Driver does not support the required nvenc API version" in clipped


def test_clip_error_at_exact_boundary_is_unchanged() -> None:
    msg = "y" * _MAX_ERROR_CHARS
    assert _clip_error(msg) == msg


def test_probe_encoders_mode_prints_json(monkeypatch, capsys) -> None:
    import json

    import arm_transcode.main as m

    monkeypatch.setattr(m.sys, "argv", ["arm_transcode", "--probe-encoders"])
    monkeypatch.setattr(m, "probe_encoders", lambda: {"qsv": ["h264"]})
    rc = m.main()
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert json.loads(out) == {"qsv": ["h264"]}
    assert "\n" not in out  # exactly one JSON line
