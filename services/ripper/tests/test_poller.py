"""Poller: steps on an interval, survives a failing step, and stops after the step in flight."""

from __future__ import annotations

import asyncio

from arm_ripper.rip.poller import Poller


async def test_runs_the_step_on_each_interval_until_stopped() -> None:
    calls: list[int] = []

    async def step() -> None:
        calls.append(1)

    poller = Poller(0.01, step)
    poller.start()
    await asyncio.sleep(0.055)
    await poller.stop()
    seen = len(calls)
    assert seen >= 2
    await asyncio.sleep(0.03)
    assert len(calls) == seen


async def test_a_failing_step_is_logged_and_polling_goes_on(caplog) -> None:
    calls: list[int] = []

    async def step() -> None:
        calls.append(1)
        raise OSError("not there yet")

    caplog.set_level("DEBUG", logger="arm_ripper.rip.poller")
    poller = Poller(0.01, step)
    poller.start()
    await asyncio.sleep(0.045)
    await poller.stop()
    assert len(calls) >= 2
    assert "poll step failed" in caplog.text


async def test_stop_lets_the_step_in_flight_finish() -> None:
    started = asyncio.Event()
    finished: list[bool] = []

    async def step() -> None:
        started.set()
        await asyncio.sleep(0.03)
        finished.append(True)

    poller = Poller(0.001, step)
    poller.start()
    await started.wait()
    await poller.stop()
    assert finished == [True]


async def test_stop_before_the_first_interval_runs_no_step() -> None:
    calls: list[int] = []

    async def step() -> None:
        calls.append(1)

    poller = Poller(60, step)
    poller.start()
    await poller.stop()
    assert calls == []


async def test_stop_without_start_returns() -> None:
    async def step() -> None:
        raise AssertionError("never runs")

    await Poller(0.01, step).stop()
