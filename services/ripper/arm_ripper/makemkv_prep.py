"""Gets MakeMKV ready for a disc: key refresh now, community KEYDB and SDF refreshes in the background."""

import asyncio
import logging

from arm_ripper.backend_client import BackendClient
from arm_ripper.background_tasks import spawn_tracked
from arm_ripper.community_keydb import refresh_community_keydb
from arm_ripper.makemkv_key import refresh_makemkv_key
from arm_ripper.makemkv_sdf import refresh_makemkv_sdf
from arm_ripper.ripper_config import ripper_config_or_none

# The moved code keeps the job controller's logger name so existing log filters and log text stay the same.
logger = logging.getLogger("arm_ripper.job_controller")


class MakeMKVPrep:
    """Refreshes MakeMKV's key and starts the background KEYDB and SDF refreshes before a disc is read."""

    def __init__(self, client: BackendClient) -> None:
        self._client = client
        self._keydb_tasks: set[asyncio.Task[None]] = set()
        self._sdf_tasks: set[asyncio.Task[None]] = set()

    async def prepare(self) -> None:
        """Get MakeMKV ready for a disc: refresh its key now, and start the KEYDB and SDF
        refreshes in the background."""
        await refresh_makemkv_key(key=await self._configured_makemkv_key())
        self._spawn_keydb_refresh(enabled=await self._community_keydb_enabled())
        self._spawn_sdf_refresh(enabled=await self._makemkv_sdf_enabled())

    async def _configured_makemkv_key(self) -> str | None:
        """The operator's UI-set MakeMKV key, or None to fall back to the
        MAKEMKV_KEY env var / forum scrape.

        Fail-open: a flapping backend must not block ripping. On any lookup
        error we return None, which leaves the legacy env/scrape behaviour
        intact rather than wiping a key the operator already configured.
        """
        cfg = await ripper_config_or_none(self._client, "makemkv key lookup", "using env/scrape fallback")
        return None if cfg is None else cfg.makemkv_key

    async def _community_keydb_enabled(self) -> bool:
        """Whether the operator has the community-keydb auto-fetch enabled.
        Fail-open to True (the default) so a flapping backend doesn't silently
        disable the feature."""
        cfg = await ripper_config_or_none(self._client, "community keydb toggle lookup", "defaulting enabled")
        return True if cfg is None else cfg.community_keydb_enabled

    def _spawn_keydb_refresh(self, *, enabled: bool) -> None:
        """Fire-and-forget community-keydb refresh. The rip proceeds immediately
        with the on-disk keydb; a fresh keydb benefits the next rip. Errors are
        swallowed — a keydb hiccup must never abort a rip."""
        spawn_tracked(self._keydb_refresh_and_report(enabled=enabled), self._keydb_tasks)

    async def _keydb_refresh_and_report(self, *, enabled: bool) -> None:
        try:
            result = await refresh_community_keydb(enabled=enabled)
            if result is not None:
                await self._client.report_keydb_status(
                    state=result.state, vuk_count=result.vuk_count, age_days=result.age_days
                )
        except Exception as exc:  # noqa: BLE001 — fire-and-forget, never propagate
            logger.warning("community keydb refresh failed (non-fatal): %s", exc)

    async def _drain_keydb_tasks(self) -> None:
        """Await any outstanding keydb refreshes. Used by tests to synchronise
        on the fire-and-forget tasks. Not wired into production shutdown by
        design: a keydb refresh is best-effort, so on SIGTERM the tasks are
        abandoned (their bodies swallow Exception, and CancelledError —
        BaseException — propagates cleanly to the event loop)."""
        if self._keydb_tasks:
            await asyncio.gather(*self._keydb_tasks, return_exceptions=True)

    async def _makemkv_sdf_enabled(self) -> bool:
        """Whether the operator has the MakeMKV SDF auto-refresh enabled.
        Fail-open to True so a flapping backend doesn't silently disable it."""
        cfg = await ripper_config_or_none(self._client, "makemkv sdf toggle lookup", "defaulting enabled")
        return True if cfg is None else cfg.makemkv_sdf_enabled

    def _spawn_sdf_refresh(self, *, enabled: bool) -> None:
        """Fire-and-forget MakeMKV SDF refresh. The rip proceeds immediately
        with the on-disk SDF; a fresh SDF benefits the next rip. Errors are
        swallowed — an SDF hiccup must never abort a rip."""
        spawn_tracked(self._sdf_refresh_and_report(enabled=enabled), self._sdf_tasks)

    async def _sdf_refresh_and_report(self, *, enabled: bool) -> None:
        try:
            result = await refresh_makemkv_sdf(enabled=enabled)
            if result is not None:
                await self._client.report_sdf_status(state=result.state, age_days=result.age_days)
        except Exception as exc:  # noqa: BLE001 — fire-and-forget, never propagate
            logger.warning("makemkv sdf refresh failed (non-fatal): %s", exc)

    async def _drain_sdf_tasks(self) -> None:
        """Await any outstanding SDF refreshes. Test-only synchronisation."""
        while self._sdf_tasks:
            await asyncio.gather(*list(self._sdf_tasks), return_exceptions=True)
