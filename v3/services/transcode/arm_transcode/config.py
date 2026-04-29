"""Transcoder env-var binding.

The dispatcher passes everything we need at spawn time:
- `ARM_TRANSCODE_TASK_ID` — the row to register/claim/run.
- `ARM_BACKEND_URL` — e.g. `https://arm-backend:8443`.
- `ARM_SERVICE_TOKEN` — for both REST `Authorization: Bearer` and the
  WS auth-message token.
- `HOSTNAME` — set by docker (`hostname=arm-transcode-...` in the spawn
  call); the transcoder echoes it on register so the Backend can stamp
  `claimed_by`.
"""

from __future__ import annotations

import os
import socket


class TranscoderConfig:
    def __init__(self) -> None:
        self.task_id = _required("ARM_TRANSCODE_TASK_ID")
        self.backend_url = _required("ARM_BACKEND_URL").rstrip("/")
        self.service_token = _required("ARM_SERVICE_TOKEN")
        self.log_level = os.environ.get("ARM_LOG_LEVEL", "info").upper()
        self.hostname = os.environ.get("HOSTNAME") or socket.gethostname()

    @property
    def ws_url(self) -> str:
        # Convert https:// → wss:// — same host, same port, /ws path.
        if self.backend_url.startswith("https://"):
            return "wss://" + self.backend_url[len("https://") :] + "/ws"
        if self.backend_url.startswith("http://"):
            return "ws://" + self.backend_url[len("http://") :] + "/ws"
        return self.backend_url + "/ws"


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing required env var: {name}")
    return value
