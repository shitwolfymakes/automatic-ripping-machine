"""Cleanup for a ripper subprocess (makemkvcon or dd) that may still be running."""

import asyncio


async def kill_if_running(proc: asyncio.subprocess.Process) -> None:
    """Kill the subprocess and reap it if it is still running."""
    # Cancel-safe cleanup: if the parent task was cancelled (abandon flow), the
    # subprocess is still running. Kill and reap it before CancelledError
    # propagates, so the /raw/<id>/ wipe finds no open files.
    if proc.returncode is not None:
        return
    proc.kill()
    try:
        await proc.wait()
    except BaseException:
        pass
