from typing import Any

import httpx

from arm_common import Drive, DriveMediaStatus, Job, KeydbState, MakemkvKeyState
from arm_common.schemas import (
    HeldJobView,
    IdentifyRequest,
    JobCompleteRequest,
    JobView,
    KeydbStatusReport,
    MakemkvKeyStatusReport,
    RegisterRequest,
    RipperConfigView,
    RipperHeartbeatRequest,
    RipStartResponse,
    ScanResult,
    TrackUpdateRequest,
    TrackView,
)


class BackendClient:
    def __init__(
        self,
        base_url: str,
        service_token: str,
        hostname: str,
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {service_token}",
                "X-ARM-Hostname": hostname,
            },
            timeout=timeout,
            verify="/etc/ssl/certs/ca-certificates.crt",
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def register(
        self, *, hostname: str, device_path: str, ripper_version: str, serial: str | None = None
    ) -> Drive:
        req = RegisterRequest(hostname=hostname, device_path=device_path, ripper_version=ripper_version, serial=serial)
        r = await self._client.post("/api/ripper/register", json=req.model_dump())
        r.raise_for_status()
        return Drive.model_validate(r.json())

    async def heartbeat(self, *, drive_id: str, media_status: DriveMediaStatus) -> None:
        req = RipperHeartbeatRequest(drive_id=drive_id, media_status=media_status)
        r = await self._client.post("/api/ripper/heartbeat", json=req.model_dump(mode="json"))
        r.raise_for_status()

    async def identify(
        self,
        *,
        drive_id: str,
        scan_result: ScanResult,
        pending_session_id: str | None = None,
    ) -> Job:
        req = IdentifyRequest(
            drive_id=drive_id,
            scan_result=scan_result,
            pending_session_id=pending_session_id,
        )
        r = await self._client.post("/api/ripper/identify", json=req.model_dump(mode="json"))
        r.raise_for_status()
        return Job.model_validate(r.json())

    async def get_job(self, job_id: str) -> JobView:
        r = await self._client.get(f"/api/ripper/jobs/{job_id}")
        r.raise_for_status()
        return JobView.model_validate(r.json())

    async def rip_start(self, job_id: str) -> RipStartResponse:
        r = await self._client.post(f"/api/ripper/jobs/{job_id}/rip-start")
        r.raise_for_status()
        return RipStartResponse.model_validate(r.json())

    async def update_track(self, track_id: str, **fields: Any) -> TrackView:
        req = TrackUpdateRequest(**fields)
        r = await self._client.patch(
            f"/api/ripper/tracks/{track_id}",
            json=req.model_dump(mode="json", exclude_none=True),
        )
        r.raise_for_status()
        return TrackView.model_validate(r.json())

    async def rip_complete(self, job_id: str) -> JobView:
        req = JobCompleteRequest()
        r = await self._client.post(
            f"/api/ripper/jobs/{job_id}/rip-complete",
            json=req.model_dump(mode="json"),
        )
        r.raise_for_status()
        return JobView.model_validate(r.json())

    async def get_in_flight_job(self, drive_id: str) -> JobView | None:
        """Phase 9 — boot-probe lookup. Returns None on 404."""
        r = await self._client.get(f"/api/ripper/drives/{drive_id}/in-flight-job")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return JobView.model_validate(r.json())

    async def get_held_job(self, drive_id: str) -> HeldJobView | None:
        """Boot-probe lookup for a disc held in AWAITING_REVIEW (timed review
        gate). Returns the held job + its paused flag, or None on 404."""
        r = await self._client.get(f"/api/ripper/drives/{drive_id}/held-job")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return HeldJobView.model_validate(r.json())

    async def recovery_abandon(self, job_id: str) -> JobView:
        """Abandon a counting-down held job on reboot recovery (review gate §6.3)."""
        r = await self._client.post(f"/api/ripper/jobs/{job_id}/recovery-abandon")
        r.raise_for_status()
        return JobView.model_validate(r.json())

    async def get_ripper_config(self) -> RipperConfigView:
        """Tiny config snapshot polled before each disc-insert pipeline.

        On any HTTP error, callers should fail-open (treat as `auto_rip=True`)
        — a flapping backend should not silently disable ripping.
        """
        r = await self._client.get("/api/ripper/config")
        r.raise_for_status()
        return RipperConfigView.model_validate(r.json())

    async def resume(self, job_id: str) -> RipStartResponse:
        """Phase 9 — per-job crash-recovery reset. Same response shape as
        rip-start so the ripper's existing flow continues unchanged.
        """
        r = await self._client.post(f"/api/ripper/jobs/{job_id}/resume")
        r.raise_for_status()
        return RipStartResponse.model_validate(r.json())

    async def report_makemkv_key_status(self, *, state: MakemkvKeyState, detail: str | None = None) -> None:
        req = MakemkvKeyStatusReport(state=state, detail=detail)
        r = await self._client.post("/api/ripper/makemkv-key-status", json=req.model_dump(mode="json"))
        r.raise_for_status()

    async def report_keydb_status(
        self, *, state: KeydbState, vuk_count: int | None = None, age_days: int | None = None
    ) -> None:
        req = KeydbStatusReport(state=state, vuk_count=vuk_count, age_days=age_days)
        r = await self._client.post("/api/ripper/keydb-status", json=req.model_dump(mode="json"))
        r.raise_for_status()
