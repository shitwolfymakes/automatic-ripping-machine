"""HTTPS client for the transcoder ↔ Backend REST surface.

The Backend issues a self-signed cert chained to the install's internal CA;
the entrypoint merges that CA into the system trust store, so plain
`verify=...` against `/etc/ssl/certs/ca-certificates.crt` works end-to-end
without per-call SSL fiddling.
"""

from __future__ import annotations

import httpx

from arm_common.schemas import (
    ClaimTaskResponse,
    CompleteTaskRequest,
    FailTaskRequest,
    HardwareCaps,
    HeartbeatRequest,
    RegisterTranscoderRequest,
    RegisterTranscoderResponse,
    TranscodeTaskView,
)


class BackendClient:
    def __init__(
        self,
        *,
        base_url: str,
        service_token: str,
        hostname: str,
        timeout: float = 30.0,
    ) -> None:
        self._hostname = hostname
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
        self,
        *,
        task_id: str,
        hw_caps: HardwareCaps,
    ) -> RegisterTranscoderResponse:
        req = RegisterTranscoderRequest(task_id=task_id, hostname=self._hostname, hw_caps=hw_caps)
        r = await self._client.post("/api/transcoder/register", json=req.model_dump())
        r.raise_for_status()
        return RegisterTranscoderResponse.model_validate(r.json())

    async def claim(self, task_id: str) -> ClaimTaskResponse:
        r = await self._client.post(f"/api/transcoder/tasks/{task_id}/claim")
        r.raise_for_status()
        return ClaimTaskResponse.model_validate(r.json())

    async def heartbeat(
        self,
        task_id: str,
        *,
        progress_pct: int,
        current_pass: str | None = None,
        eta_seconds: int | None = None,
    ) -> TranscodeTaskView:
        req = HeartbeatRequest(progress_pct=progress_pct, current_pass=current_pass, eta_seconds=eta_seconds)
        r = await self._client.patch(
            f"/api/transcoder/tasks/{task_id}/heartbeat",
            json=req.model_dump(),
        )
        r.raise_for_status()
        return TranscodeTaskView.model_validate(r.json())

    async def complete(
        self,
        task_id: str,
        *,
        output_path: str,
        size_bytes: int | None = None,
        duration_seconds: int | None = None,
        sha256: str | None = None,
    ) -> TranscodeTaskView:
        req = CompleteTaskRequest(
            output_path=output_path,
            size_bytes=size_bytes,
            duration_seconds=duration_seconds,
            sha256=sha256,
        )
        r = await self._client.patch(
            f"/api/transcoder/tasks/{task_id}/complete",
            json=req.model_dump(),
        )
        r.raise_for_status()
        return TranscodeTaskView.model_validate(r.json())

    async def fail(self, task_id: str, *, last_error: str) -> TranscodeTaskView:
        req = FailTaskRequest(last_error=last_error)
        r = await self._client.patch(
            f"/api/transcoder/tasks/{task_id}/fail",
            json=req.model_dump(),
        )
        r.raise_for_status()
        return TranscodeTaskView.model_validate(r.json())
