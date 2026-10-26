"""Log rotation for the containers the backend spawns over the docker socket.

Docker's default json-file driver never rotates, so a looping error in a
long-lived ripper fills the host disk. The compose services get the same limit
from the template's `x-logging` block; keep the two in step.
"""

from __future__ import annotations

from typing import Any

MAX_SIZE = "10m"
MAX_FILE = "3"


def log_config() -> dict[str, Any]:
    """`log_config` kwarg for `containers.run`: json-file, 3 x 10 MB. A fresh
    dict per call, so no caller can mutate another's spec."""
    return {"type": "json-file", "config": {"max-size": MAX_SIZE, "max-file": MAX_FILE}}
