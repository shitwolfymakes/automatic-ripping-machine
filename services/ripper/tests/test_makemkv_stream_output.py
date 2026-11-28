"""Characterization tests for `makemkv_stream.stream_output` and its emit helpers."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import Any, cast

import pytest

from arm_ripper.rip import makemkv_stream
from arm_ripper.rip.makemkv_stream import ParserState

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


async def _run(lines: list[bytes], state: ParserState | None = None, **kwargs: Any) -> ParserState:
    state = state or ParserState()
    names = ("on_title_start", "on_disc_progress", "on_title_done")
    callbacks = makemkv_stream.RipCallbacks(**{n: kwargs.pop(n) for n in names if n in kwargs})
    await makemkv_stream.stream_output(cast(Any, _Proc(lines)), state, callbacks, **kwargs)
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
        on_disc_progress=cb,
        on_title_done=cb,
    )
    assert state == ParserState()
    assert cb.calls == []
    assert caplog.records == []


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


async def test_disc_progress_reports_the_disc_wide_total_while_a_title_is_saving() -> None:
    """PRGV's `total/max` (0.5 here) is reported, not the per-title `current/max` (0.1), which resets each title."""
    disc = _Recorder()
    state = ParserState(current_title=3, save_phase_started=True)
    await _run([PRGV], state, on_disc_progress=disc)
    assert disc.calls == [(0.5,)]


async def test_a_title_announced_before_the_5024_milestone_counts_as_the_save_phase() -> None:
    disc = _Recorder()
    await _run([PRGV], ParserState(current_title=3), on_disc_progress=disc)
    assert disc.calls == [(0.5,)]


async def test_disc_progress_gated_before_5024_and_ungated_when_disabled() -> None:
    gated, ungated = _Recorder(), _Recorder()
    await _run([PRGV], on_disc_progress=gated)
    await _run([PRGV], on_disc_progress=ungated, gate_disc_progress=False)
    assert gated.calls == []
    assert ungated.calls == [(0.5,)]


def _title_events(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) == event]


def _prgv(current_pct: int) -> bytes:
    return f"PRGV:{current_pct * 100},{current_pct * 50},10000".encode()


_PRGC = 'PRGC:5017,{},"Saving to MKV file"'


async def test_each_title_logs_its_start_and_its_quarter_steps(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    disc = _Recorder()
    lines = [b'PRGT:5024,0,"Saving all titles to MKV files"', _PRGC.format(0).encode()]
    lines += [_prgv(p) for p in (10, 30, 80, 100)]
    lines += [_PRGC.format(1).encode(), _prgv(60)]
    await _run(lines, on_disc_progress=disc, eligible_source_indexes=[3, 7])
    started = _title_events(caplog, "title.started")
    assert [(r.getMessage(), r.fields) for r in started] == [  # type: ignore[attr-defined]
        ("saving title 3 (file 1 of 2)", {"title_index": 3, "file_position": 1, "file_count": 2}),
        ("saving title 7 (file 2 of 2)", {"title_index": 7, "file_position": 2, "file_count": 2}),
    ]
    progress = _title_events(caplog, "title.progress")
    assert [(r.getMessage(), r.fields) for r in progress] == [  # type: ignore[attr-defined]
        ("title 3: 25%", {"title_index": 3, "percent": 25}),
        ("title 3: 75%", {"title_index": 3, "percent": 75}),
        ("title 3: 100%", {"title_index": 3, "percent": 100}),
        ("title 7: 50%", {"title_index": 7, "percent": 50}),
    ]
    assert [c[0] for c in disc.calls] == [0.05, 0.15, 0.4, 0.5, 0.3]


async def test_a_repeated_prgc_for_the_same_title_logs_one_start(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    await _run([_PRGC.format(0).encode()] * 2, eligible_source_indexes=[3])
    assert len(_title_events(caplog, "title.started")) == 1


async def test_a_title_announced_by_prgt_logs_its_start_and_restarts_its_quarters(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    lines = [b'PRGT:5024,0,"Saving all titles to MKV files"', _PRGC.format(0).encode(), _prgv(80)]
    lines += [b'PRGT:5011,0,"Saving title #5 to MKV file"', _prgv(30)]
    await _run(lines, eligible_source_indexes=[3, 5])
    started = _title_events(caplog, "title.started")
    assert [r.getMessage() for r in started] == ["saving title 3 (file 1 of 2)", "saving title 5 (file 2 of 2)"]
    progress = _title_events(caplog, "title.progress")
    assert [r.getMessage() for r in progress] == ["title 3: 75%", "title 5: 25%"]


async def test_a_late_prgt_for_an_open_title_keeps_its_quarters(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    lines = [_PRGC.format(0).encode(), _prgv(30), b'PRGT:5011,0,"Saving title #3 to MKV file"', _prgv(40)]
    await _run(lines, eligible_source_indexes=[3])
    assert len(_title_events(caplog, "title.started")) == 1
    assert [r.getMessage() for r in _title_events(caplog, "title.progress")] == ["title 3: 25%"]


async def test_a_prgt_title_outside_the_eligible_list_starts_without_a_file_position(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    state = await _run([b'PRGT:5011,0,"Saving title #9 to MKV file"', _prgv(60)], eligible_source_indexes=[3])
    assert state.current_title == 9
    assert _title_events(caplog, "title.started") == []
    assert [r.getMessage() for r in _title_events(caplog, "title.progress")] == ["title 9: 50%"]


async def test_nothing_is_logged_before_the_save_phase(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    await _run([_prgv(10), _prgv(60)], eligible_source_indexes=[3])
    assert _title_events(caplog, "title.progress") == []


async def test_progress_with_no_announced_title_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    await _run([_prgv(10), _prgv(60)], ParserState(save_phase_started=True))
    assert _title_events(caplog, "title.progress") == []


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
    state = ParserState()
    done = _Recorder()
    await makemkv_stream._emit_title_done(state, 1, done)
    await makemkv_stream._emit_title_done(state, 1, done)
    assert done.calls == [(1,)]
    assert state.titles[1].done_emitted is True


async def test_emit_title_done_without_callback_marks_done() -> None:
    state = ParserState()
    await makemkv_stream._emit_title_done(state, 1, None)
    assert state.titles[1].done_emitted is True


async def test_emit_title_done_callback_raising_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    state = ParserState()
    await makemkv_stream._emit_title_done(state, 1, _Recorder(RuntimeError("oops")))
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
    assert state == ParserState()
    assert [r.getMessage() for r in caplog.records] == [f"makemkv-raw: {line.decode()}"]


async def test_unparseable_msg_only_logs_debug(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    state = await _run([b"MSG:abc"])
    assert state == ParserState()
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
    await makemkv_stream._call_safely("lbl", rec, 1, 0.5)
    assert rec.calls == [(1, 0.5)]
    assert caplog.records == []


async def test_call_safely_swallows_exception_and_logs_debug(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    await makemkv_stream._call_safely("lbl", _Recorder(RuntimeError("boom")), 7)
    assert [(r.name, r.levelno, r.getMessage()) for r in caplog.records] == [
        (LOGGER, logging.DEBUG, "lbl callback raised: boom")
    ]


async def test_call_safely_propagates_base_exception() -> None:
    cb = cast(Any, _Recorder(cast(Any, asyncio.CancelledError())))
    with pytest.raises(asyncio.CancelledError):
        await makemkv_stream._call_safely("lbl", cb)


def test_rip_callbacks_default_to_none_and_are_frozen() -> None:
    cbs = makemkv_stream.RipCallbacks()
    assert (cbs.on_title_start, cbs.on_disc_progress, cbs.on_title_done) == (None,) * 3
    with pytest.raises(dataclasses.FrozenInstanceError):
        cbs.on_title_start = _Recorder()  # type: ignore[misc]


class _KillProc:
    def __init__(self) -> None:
        self.kills = 0

    def kill(self) -> None:
        self.kills += 1


def _parser(
    state: ParserState, proc: _KillProc | None = None, eligible: list[int] | None = None
) -> makemkv_stream._LineParser:
    return makemkv_stream._LineParser(
        cast(Any, proc or _KillProc()), state, makemkv_stream.RipCallbacks(), eligible or [], True
    )


_EXPIRED = 'MSG:5021,0,1,"evaluation period has expired","%1","x"'


async def test_feed_first_binary_expired_msg_flags_records_and_kills_once() -> None:
    state, proc = ParserState(), _KillProc()
    await _parser(state, proc).feed(_EXPIRED)
    assert state.binary_expired is True
    assert state.diagnostics == [_EXPIRED]
    assert proc.kills == 1


async def test_feed_second_binary_expired_msg_does_not_kill_again_and_falls_through(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    state, proc = ParserState(), _KillProc()
    parser = _parser(state, proc)
    await parser.feed(_EXPIRED)
    assert _records(caplog, "makemkvcon: ") == []
    await parser.feed(_EXPIRED)
    assert proc.kills == 1
    assert state.diagnostics == [_EXPIRED]
    # Fell through to the generic MSG branch, which logs the line.
    _assert_one(caplog, logging.DEBUG, f"makemkvcon: {_EXPIRED}")


async def test_feed_prgc_position_maps_through_eligible_to_current_title() -> None:
    state = ParserState()
    await _parser(state, eligible=[4, 9]).feed('PRGC:5017,1,"Saving to MKV file"')
    assert state.current_title == 9


# --- _LineParser handlers: True when the line was their kind, else False --------------------------------------------


async def test_apply_expiry_true_on_first_5021_false_once_expired_or_other_line() -> None:
    state, proc = ParserState(), _KillProc()
    parser = _parser(state, proc)
    assert await parser._apply_expiry("PRGV:1,2,3") is False
    assert await parser._apply_expiry(_EXPIRED) is True
    assert await parser._apply_expiry(_EXPIRED) is False
    assert proc.kills == 1


async def test_apply_progress_true_for_prgv_false_otherwise() -> None:
    parser = _parser(ParserState())
    assert await parser._apply_progress(PRGV.decode()) is True
    assert await parser._apply_progress('PRGC:5017,0,"x"') is False


async def test_apply_save_position_true_in_range_and_out_of_range_false_otherwise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    state = ParserState()
    parser = _parser(state, eligible=[4])
    assert await parser._apply_save_position("PRGV:1,2,3") is False
    assert await parser._apply_save_position('PRGC:5017,0,"Saving to MKV file"') is True
    assert state.current_title == 4
    assert await parser._apply_save_position('PRGC:5017,5,"Saving to MKV file"') is True
    _assert_one(caplog, logging.WARNING, "PRGC:5017 output position 5 out of range (eligible has 1 entries)")
    assert state.current_title == 4


async def test_apply_title_line_true_for_saving_title_false_otherwise() -> None:
    state = ParserState()
    parser = _parser(state)
    assert await parser._apply_title_line("PRGV:1,2,3") is False
    assert await parser._apply_title_line('PRGT:5011,0,"Saving title #5 to MKV file"') is True
    assert state.current_title == 5


async def test_apply_milestone_true_for_other_prgt_and_marks_save_phase(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    state = ParserState()
    parser = _parser(state)
    assert await parser._apply_milestone("PRGV:1,2,3") is False
    assert await parser._apply_milestone('PRGT:5024,0,"Saving all titles"') is True
    assert state.save_phase_started is True
    _assert_one(caplog, logging.INFO, "makemkvcon milestone: Saving all titles")


async def test_apply_msg_true_for_msg_false_for_non_msg(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    state = ParserState()
    parser = _parser(state)
    assert await parser._apply_msg("PRGV:1,2,3") is False
    assert caplog.records == []
    line = 'MSG:5003,0,2,"Failed to save title 2 to file x","Failed to save title %1 to file %2","2","x"'
    assert await parser._apply_msg(line) is True
    assert state.diagnostics == ["Failed to save title 2 to file x"]
    assert state.titles[2].fail_reason == "Failed to save title 2 to file x"
    _assert_one(caplog, logging.DEBUG, f"makemkvcon: {line}")


def test_record_title_failure_with_index_stores_unescaped_reason() -> None:
    state = ParserState()
    line = r'MSG:5003,0,2,"Failed \"x\" to save","fmt","3","y"'
    _parser(state)._record_title_failure(line, ["3", "y"])
    assert state.titles[3].fail_reason == 'Failed "x" to save'


def test_record_title_failure_without_index_warns_and_leaves_state(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    state = ParserState()
    line = 'MSG:5003,0,2,"nope","fmt"'
    _parser(state)._record_title_failure(line, [])
    assert state == ParserState()
    _assert_one(caplog, logging.WARNING, f"MSG:5003 without parseable title index: {line}")


async def test_feed_tries_handlers_in_order_and_stops_at_the_first_taker(monkeypatch: pytest.MonkeyPatch) -> None:
    names = ["expiry", "progress", "save_position", "title_line", "milestone", "msg"]
    calls: list[str] = []

    def install(parser: makemkv_stream._LineParser, take: str | None) -> None:
        for name in names:

            async def handler(line: str, name: str = name) -> bool:
                calls.append(f"{name}:{line}")
                return name == take

            monkeypatch.setattr(parser, f"_apply_{name}", handler)

    parser = _parser(ParserState())
    install(parser, None)
    await parser.feed("L")
    assert calls == [f"{n}:L" for n in names]

    calls.clear()
    install(parser, "title_line")
    await parser.feed("M")
    assert calls == [f"{n}:M" for n in names[:4]]


class _TickClock:
    """A clock that reads 1.0, 2.0, 3.0 ... one tick per call."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


_COPY_COMPLETE = b'MSG:5036,0,1,"Copy complete. 1 titles saved.","Copy complete. %1 titles saved.","1"'


@pytest.mark.asyncio
async def test_copy_complete_is_recorded_with_its_arrival_and_wakes_the_waiter():
    state = ParserState(clock=_TickClock())
    await _run([b"PRGV:1,1,100", _COPY_COMPLETE, b'MSG:1005,0,1,"x","y"'], state)
    assert state.copy_complete == makemkv_stream.CopyComplete(saved=1, failed=0)
    assert state.copy_complete_at == 2.0
    assert state.last_line_at == 3.0
    assert state.completed.is_set()


@pytest.mark.asyncio
async def test_a_second_copy_complete_keeps_the_first_arrival():
    state = ParserState(clock=_TickClock())
    await _run([_COPY_COMPLETE, _COPY_COMPLETE], state)
    assert state.copy_complete_at == 1.0


@pytest.mark.asyncio
async def test_copy_complete_5037_still_lands_in_the_diagnostics():
    state = await _run([b'MSG:5037,0,2,"Copy complete. 1 titles saved, 1 failed.","f","1","1"'])
    assert state.copy_complete == makemkv_stream.CopyComplete(saved=1, failed=1)
    assert state.diagnostics == ["Copy complete. 1 titles saved, 1 failed."]


@pytest.mark.asyncio
async def test_full_save_progress_is_recorded_in_the_save_phase():
    state = ParserState(clock=_TickClock())
    await _run([b'PRGT:5024,0,"Saving all titles to MKV files"', b"PRGV:50,50,100", b"PRGV:100,100,100"], state)
    assert state.save_full_at == 3.0
    assert state.completed.is_set()
    assert state.copy_complete is None


@pytest.mark.asyncio
async def test_full_save_progress_is_recorded_once_a_title_is_current():
    state = ParserState(clock=_TickClock())
    await _run(
        [b'PRGC:5017,0,"Saving to MKV file"', b"PRGV:100,100,100", b"PRGV:100,100,100"],
        state,
        eligible_source_indexes=[0],
    )
    assert state.save_full_at == 2.0


@pytest.mark.asyncio
async def test_full_progress_before_the_save_phase_is_not_a_completion():
    state = await _run([b"PRGV:100,100,100"])
    assert state.save_full_at is None
    assert not state.completed.is_set()


@pytest.mark.asyncio
async def test_partial_save_progress_is_not_a_completion():
    state = await _run([b'PRGT:5024,0,"Saving all titles to MKV files"', b"PRGV:99,99,100"])
    assert state.save_full_at is None
    assert not state.completed.is_set()
