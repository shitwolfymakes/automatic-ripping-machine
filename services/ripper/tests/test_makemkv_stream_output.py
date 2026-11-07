"""Characterization tests for `makemkv_rip._stream_output` and its emit helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

import pytest

from arm_ripper.rip import makemkv_rip
from arm_ripper.rip.makemkv_rip import _ParserState

LOGGER = "arm_ripper.rip.makemkv"
PRGV = b"PRGV:10,50,100"  # current 0.1, total 0.5


class _Stream:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = [ln + b"\n" for ln in lines]

    async def readline(self) -> bytes:
        return self._lines.pop(0) if self._lines else b""


class _Proc:
    def __init__(self, lines: list[bytes]) -> None:
        self.stdout = _Stream(lines)


class _Recorder:
    """Async callback recording its calls; optionally raising."""

    def __init__(self, exc: Exception | None = None) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self._exc = exc

    async def __call__(self, *args: Any) -> None:
        self.calls.append(args)
        if self._exc is not None:
            raise self._exc


async def _run(lines: list[bytes], state: _ParserState | None = None, **kwargs: Any) -> _ParserState:
    state = state or _ParserState()
    kwargs.setdefault("on_title_start", None)
    kwargs.setdefault("on_title_progress", None)
    kwargs.setdefault("on_disc_progress", None)
    await makemkv_rip._stream_output(cast(Any, _Proc(lines)), state, **kwargs)
    return state


def _records(caplog: pytest.LogCaptureFixture, prefix: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage().startswith(prefix)]


def _assert_one(caplog: pytest.LogCaptureFixture, level: int, message: str) -> None:
    matches = [r for r in caplog.records if r.getMessage() == message]
    assert len(matches) == 1
    assert matches[0].name == LOGGER
    assert matches[0].levelno == level


async def test_blank_lines_skipped(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    cb = _Recorder()
    state = await _run(
        [b"", b"   ", b"\t "],
        on_title_start=cb,
        on_title_progress=cb,
        on_disc_progress=cb,
        on_title_done=cb,
    )
    assert state == _ParserState()
    assert cb.calls == []
    assert caplog.records == []


async def test_title_progress_callback_raising_is_logged_and_stream_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    state = _ParserState(current_title=4)
    cb = _Recorder(RuntimeError("boom"))
    await _run([PRGV, b'PRGT:5024,0,"Saving all titles"'], state, on_title_progress=cb)
    assert cb.calls == [(4, 0.1)]
    _assert_one(caplog, logging.DEBUG, "title progress callback raised: boom")
    assert state.save_phase_started is True


async def test_disc_progress_callback_raising_is_logged_and_stream_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    cb = _Recorder(ValueError("bad"))
    state = await _run(
        [b'PRGT:5024,0,"Saving all titles"', PRGV, PRGV, b'PRGC:5017,0,"Saving"'],
        on_disc_progress=cb,
        eligible_source_indexes=[7],
    )
    assert cb.calls == [(0.5,), (0.5,)]
    assert len(_records(caplog, "disc progress callback raised: bad")) == 2
    _assert_one(caplog, logging.INFO, "makemkvcon milestone: Saving all titles")
    assert state.current_title == 7


async def test_disc_progress_callback_raising_record_fields(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    await _run(
        [b'PRGT:5024,0,"x"', PRGV],
        on_disc_progress=_Recorder(ValueError("bad")),
    )
    _assert_one(caplog, logging.DEBUG, "disc progress callback raised: bad")


async def test_current_title_without_title_callback_falls_through_to_disc_progress() -> None:
    disc = _Recorder()
    state = _ParserState(current_title=3, save_phase_started=True)
    await _run([PRGV], state, on_title_progress=None, on_disc_progress=disc)
    assert disc.calls == [(0.5,)]


async def test_current_title_without_title_callback_still_gated_before_save_phase() -> None:
    disc = _Recorder()
    await _run([PRGV], _ParserState(current_title=3), on_disc_progress=disc)
    assert disc.calls == []


async def test_title_progress_preferred_over_disc_progress_when_title_known() -> None:
    title, disc = _Recorder(), _Recorder()
    state = _ParserState(current_title=3, save_phase_started=True)
    await _run([PRGV], state, on_title_progress=title, on_disc_progress=disc)
    assert title.calls == [(3, 0.1)]
    assert disc.calls == []


async def test_disc_progress_gated_before_5024_and_ungated_when_disabled() -> None:
    gated, ungated = _Recorder(), _Recorder()
    await _run([PRGV], on_disc_progress=gated)
    await _run([PRGV], on_disc_progress=ungated, gate_disc_progress=False)
    assert gated.calls == []
    assert ungated.calls == [(0.5,)]


async def test_title_start_callback_raising_via_prgc(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    cb = _Recorder(RuntimeError("nope"))
    state = await _run([b'PRGC:5017,0,"Saving to MKV file"'], on_title_start=cb, eligible_source_indexes=[2])
    assert cb.calls == [(2,)]
    _assert_one(caplog, logging.DEBUG, "title start callback raised: nope")
    assert state.titles[2].started_emitted is True
    assert state.current_title == 2


async def test_title_start_callback_raising_via_prgt(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    cb = _Recorder(RuntimeError("nope"))
    state = await _run([b'PRGT:5011,0,"Saving title #5 to MKV file"'], on_title_start=cb)
    assert cb.calls == [(5,)]
    _assert_one(caplog, logging.DEBUG, "title start callback raised: nope")
    assert state.titles[5].started_emitted is True


async def test_title_done_fires_once_via_prgc_transition() -> None:
    done = _Recorder()
    state = await _run(
        [
            b'PRGC:5017,0,"s"',
            b'PRGC:5017,1,"s"',
            b'PRGC:5017,1,"s"',
        ],
        on_title_done=done,
        eligible_source_indexes=[10, 11],
    )
    assert done.calls == [(10,)]
    assert state.titles[10].done_emitted is True
    assert state.titles[11].done_emitted is False


async def test_emit_title_done_second_call_does_not_refire() -> None:
    state = _ParserState()
    done = _Recorder()
    await makemkv_rip._emit_title_done(state, 1, done)
    await makemkv_rip._emit_title_done(state, 1, done)
    assert done.calls == [(1,)]
    assert state.titles[1].done_emitted is True


async def test_emit_title_done_without_callback_marks_done() -> None:
    state = _ParserState()
    await makemkv_rip._emit_title_done(state, 1, None)
    assert state.titles[1].done_emitted is True


async def test_emit_title_done_callback_raising_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    state = _ParserState()
    await makemkv_rip._emit_title_done(state, 1, _Recorder(RuntimeError("oops")))
    _assert_one(caplog, logging.DEBUG, "title done callback raised: oops")
    assert state.titles[1].done_emitted is True


async def test_prgt_other_milestone_logs_info_and_keeps_save_phase_false(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    state = await _run([b'PRGT:5011,0,"Analyzing seamless segments"'])
    assert state.save_phase_started is False
    _assert_one(caplog, logging.INFO, "makemkvcon milestone: Analyzing seamless segments")


async def test_prgt_5024_sets_save_phase(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    state = await _run([b'PRGT:5024,0,"Saving all titles to MKV files"'])
    assert state.save_phase_started is True
    _assert_one(caplog, logging.INFO, "makemkvcon milestone: Saving all titles to MKV files")


@pytest.mark.parametrize("line", [b'DRV:0,2,999,1,"DVD","LABEL","/dev/sr0"', b"TCOUNT:3"])
async def test_non_msg_unmatched_lines_change_nothing(line: bytes, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    state = await _run([line])
    assert state == _ParserState()
    assert [r.getMessage() for r in caplog.records] == [f"makemkv-raw: {line.decode()}"]


async def test_unparseable_msg_only_logs_debug(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    state = await _run([b"MSG:abc"])
    assert state == _ParserState()
    _assert_one(caplog, logging.DEBUG, "makemkvcon: MSG:abc")
    assert [r.levelno for r in caplog.records if r.levelno > logging.DEBUG] == []


async def test_msg_5003_without_title_index_warns(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    line = 'MSG:5003,0,1,"Failed to save","Failed to save %1","abc"'
    state = await _run([line.encode()])
    assert state.titles == {}
    _assert_one(caplog, logging.WARNING, f"MSG:5003 without parseable title index: {line}")
    _assert_one(caplog, logging.DEBUG, f"makemkvcon: {line}")
    assert state.diagnostics == ["Failed to save"]


async def test_msg_5003_without_any_args_warns(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    line = "MSG:5003,0,0,bare"
    state = await _run([line.encode()])
    assert state.titles == {}
    assert state.diagnostics == []
    _assert_one(caplog, logging.WARNING, f"MSG:5003 without parseable title index: {line}")


async def test_msg_5003_with_index_sets_unescaped_fail_reason() -> None:
    line = r'MSG:5003,0,2,"Failed to save \"weird\" title","Failed %1","2","/raw/x.mkv"'
    state = await _run([line.encode()])
    assert state.titles[2].fail_reason == 'Failed to save "weird" title'


async def test_call_safely_awaits_callback_with_args(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    rec = _Recorder()
    await makemkv_rip._call_safely("lbl", rec, 1, 0.5)
    assert rec.calls == [(1, 0.5)]
    assert caplog.records == []


async def test_call_safely_swallows_exception_and_logs_debug(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    await makemkv_rip._call_safely("lbl", _Recorder(RuntimeError("boom")), 7)
    assert [(r.name, r.levelno, r.getMessage()) for r in caplog.records] == [
        (LOGGER, logging.DEBUG, "lbl callback raised: boom")
    ]


async def test_call_safely_propagates_base_exception() -> None:
    cb = cast(Any, _Recorder(cast(Any, asyncio.CancelledError())))
    with pytest.raises(asyncio.CancelledError):
        await makemkv_rip._call_safely("lbl", cb)
