"""Discovery contract (settings audit Tier-2): every operator-relevant backend
env key must be documented in .env.example. Required secrets (compose-set) are
exempt; container-internal paths are documented as a COMMENTED advanced block,
so they ARE present (commented) in .env.example. Keep the allowlists honest: a
NEW operator-tunable Settings key fails this test until it's documented."""

from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.config import Settings  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"

# Required secrets / bootstrap — set in compose, never as plain in .env.example.
_SECRET_OR_REQUIRED = {"DATABASE_URL", "ARM_SERVICE_TOKEN"}

# Container-internal: documented as a COMMENTED advanced block in .env.example.
# Listed here as the canonical set that block must cover.
_CONTAINER_INTERNAL = {
    "BIND_HOST",
    "BIND_PORT",
    "MEDIA_ROOT",
    "RAW_ROOT",
    "ARM_SCRIPTS_ROOT",
    "ISO_INGRESS_ROOT",
    "ARM_IMAGE_CACHE_PATH",
    "ARM_THEMES_PATH",
    "TLS_CERT_PATH",
    "TLS_KEY_PATH",
    "ARM_TRANSCODE_IMAGE",
}


def _documented_keys(text: str) -> set[str]:
    # match `KEY=...` and commented `# KEY=...` (advanced block) — the KEY token.
    keys: set[str] = set()
    for line in text.splitlines():
        m = re.match(r"\s*#?\s*([A-Z][A-Z0-9_]+)=", line)
        if m:
            keys.add(m.group(1))
    return keys


def test_every_backend_env_key_is_documented() -> None:
    documented = _documented_keys(_ENV_EXAMPLE.read_text())
    for name in Settings.model_fields:
        if name in _SECRET_OR_REQUIRED:
            continue
        assert name in documented, (
            f"{name} is a backend Settings env key but is undocumented in "
            f".env.example (add it — operator-tunable to the active block, "
            f"container-internal to the commented advanced block)"
        )


def test_container_internal_keys_are_documented_at_least_commented() -> None:
    documented = _documented_keys(_ENV_EXAMPLE.read_text())
    missing = _CONTAINER_INTERNAL - documented
    assert not missing, f"container-internal keys missing from .env.example advanced block: {missing}"
