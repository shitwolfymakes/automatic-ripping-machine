import asyncio
import hashlib
from pathlib import Path

_CHUNK = 1024 * 1024


def _sha256_blocking(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


async def sha256_file(path: Path) -> str:
    return await asyncio.to_thread(_sha256_blocking, path)
