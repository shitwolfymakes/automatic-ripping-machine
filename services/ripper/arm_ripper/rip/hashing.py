import asyncio
import hashlib
from collections.abc import Callable
from pathlib import Path

_CHUNK = 1024 * 1024

# Called from the hashing thread with the byte count of each chunk read.
OnBytes = Callable[[int], None]


def _sha256_blocking(path: Path, on_bytes: OnBytes | None = None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
            if on_bytes is not None:
                on_bytes(len(chunk))
    return h.hexdigest()


async def sha256_file(path: Path, on_bytes: OnBytes | None = None) -> str:
    return await asyncio.to_thread(_sha256_blocking, path, on_bytes)
