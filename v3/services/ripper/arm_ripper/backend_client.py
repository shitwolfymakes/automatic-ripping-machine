from typing import Any

import httpx

from arm_common import Drive, Job
from arm_common.schemas import (
    IdentifyRequest,
    JobCompleteRequest,
    JobView,
    RegisterRequest,
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

    async def register(self, *, hostname: str, device_path: str, ripper_version: str) -> Drive:
        req = RegisterRequest(hostname=hostname, device_path=device_path, ripper_version=ripper_version)
        r = await self._client.post("/api/ripper/register", json=req.model_dump())
        r.raise_for_status()
        return Drive.model_validate(r.json())

    async def identify(self, *, drive_id: str, scan_result: ScanResult) -> Job:
        req = IdentifyRequest(drive_id=drive_id, scan_result=scan_result)
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
