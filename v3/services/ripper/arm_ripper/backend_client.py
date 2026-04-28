import httpx

from arm_common import Drive, Job
from arm_common.schemas import IdentifyRequest, JobView, RegisterRequest, ScanResult


class BackendClient:
    def __init__(self, base_url: str, service_token: str, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {service_token}"},
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
