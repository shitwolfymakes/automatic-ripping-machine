import asyncio

import arm_backend.disk_refresh as dr


def test_refresher_refreshes_each_path_then_stops(monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(dr, "refresh_path", lambda p: called.append(p))
    monkeypatch.setattr(dr, "REFRESH_INTERVAL", 0.01)

    async def go():
        r = dr.DiskRefresher(["/raw", "/media"])
        task = asyncio.create_task(r.run())
        await asyncio.sleep(0.05)
        r.stop()
        await asyncio.wait_for(task, timeout=1.0)

    asyncio.run(go())
    assert "/raw" in called and "/media" in called
