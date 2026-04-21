import httpx

from arm_common import DiscType
from arm_common.schemas import (
    IdentifyRequest,
    IdentifyResponse,
    RegisterRequest,
    RegisterResponse,
)


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

    async def register(self, *, hostname: str, device_path: str, ripper_version: str) -> RegisterResponse:
        req = RegisterRequest(hostname=hostname, device_path=device_path, ripper_version=ripper_version)
        r = await self._client.post("/api/ripper/register", json=req.model_dump())
        r.raise_for_status()
        return RegisterResponse.model_validate(r.json())

    async def identify(
        self,
        *,
        drive_id: str,
        disc_type: DiscType,
        volume_label: str | None = None,
        scan_result: dict | None = None,
    ) -> IdentifyResponse:
        req = IdentifyRequest(
            drive_id=drive_id,
            disc_type=disc_type,
            volume_label=volume_label,
            scan_result=scan_result or {},
        )
        r = await self._client.post("/api/ripper/identify", json=req.model_dump(mode="json"))
        r.raise_for_status()
        return IdentifyResponse.model_validate(r.json())
