import asyncio
import logging
from typing import NamedTuple

from arm_common import DiscType
from arm_common.schemas import DiscFingerprintInput, ScanResult, ScanTitle
from arm_ripper.scan.disc_probe import DiscProbe, probe_disc
from arm_ripper.scan.makemkv_info import parse_makemkvcon_info
from arm_ripper.source import makemkv_source_url

logger = logging.getLogger("arm_ripper.scan.makemkv")

SCAN_TIMEOUT_SECONDS = 300.0

# MakeMKV emits this when its hard-coded 60-day beta kill-switch has fired.
# No registration key overrides it; the binary refuses all protected-disc
# work and the only fix is rebuilding against a fresher upstream tarball.
# See docs/user/MakeMKV-Ripper.md § Failure modes.
MAKEMKV_EXPIRED_PREFIX = b"MSG:5021,"


class ScanError(Exception):
    pass


class MakemkvBinaryExpiredError(ScanError):
    """Distinct subtype so callers / operators can match this specifically
    and route to the upstream-blocked playbook instead of a generic retry."""


def _classify_from_titles(titles: list[ScanTitle]) -> DiscType:
    """Last-resort fallback used only when MakeMKV's CINFO:1 disc-type
    string was missing. Title size > 4.7GB is unreliable (DVD-9s exceed it
    routinely) but better than UNKNOWN.
    """
    if not titles:
        return DiscType.UNKNOWN
    longest = max(t.duration_seconds for t in titles)
    return (
        DiscType.BLURAY
        if longest >= 60 * 60 * 1.5 and any(t.size_bytes is not None and t.size_bytes > 4_700_000_000 for t in titles)
        else DiscType.DVD
    )


async def _read_info_stdout(proc: asyncio.subprocess.Process) -> tuple[bytes, bool]:
    """Read makemkvcon's stdout to EOF; return it and whether MSG:5021 (expired binary) appeared.

    The first MSG:5021 line kills makemkvcon; the pipe is still drained to EOF.
    """
    assert proc.stdout is not None
    chunks: list[bytes] = []
    expired = False
    async for raw in proc.stdout:
        chunks.append(raw)
        if not expired and raw.startswith(MAKEMKV_EXPIRED_PREFIX):
            expired = True
            proc.kill()
            # Keep draining the pipe so the kernel doesn't block on
            # buffered writes between SIGKILL and process teardown.
    return b"".join(chunks), expired


async def _read_info_stderr(proc: asyncio.subprocess.Process) -> bytes:
    """Read makemkvcon's stderr to EOF."""
    assert proc.stderr is not None
    chunks: list[bytes] = []
    async for chunk in proc.stderr:
        chunks.append(chunk)
    return b"".join(chunks)


async def _read_makemkvcon_stream(proc: asyncio.subprocess.Process) -> tuple[bytes, bytes, bool]:
    """Drain stdout + stderr concurrently. Returns (stdout, stderr, expired).

    Watches stdout line-by-line; on `MSG:5021,` (binary kill-switch fired)
    kills the subprocess so the caller short-circuits the SCAN_TIMEOUT_SECONDS
    ceiling. With an expired binary makemkvcon can either exit instantly
    (`info disc:9999`) or spin against the ISO/disc structure for the full
    5 minutes (`info iso:/big.iso`) — the early-kill turns the slow path
    into a deterministic ~few-second failure.
    """
    assert proc.stdout is not None
    assert proc.stderr is not None
    stdout_task = asyncio.create_task(_read_info_stdout(proc))
    stderr_task = asyncio.create_task(_read_info_stderr(proc))
    stdout_bytes, expired = await stdout_task
    stderr_bytes = await stderr_task
    return stdout_bytes, stderr_bytes, expired


class _InfoRun(NamedTuple):
    """What one `makemkvcon info` run printed, and how it exited."""

    stdout: bytes
    stderr: bytes
    expired: bool
    returncode: int | None


async def _run_info(device_path: str) -> _InfoRun:
    """Run `makemkvcon info` on the device under the scan timeout.

    Raises ScanError when makemkvcon is not on PATH or times out.
    """
    cmd = ["makemkvcon", "-r", "--cache=1", "info", makemkv_source_url(device_path)]
    logger.info("makemkvcon info device=%s", device_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise ScanError("makemkvcon binary not found on PATH") from e

    try:
        stdout, stderr, expired = await asyncio.wait_for(_read_makemkvcon_stream(proc), timeout=SCAN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise ScanError(f"makemkvcon timed out after {SCAN_TIMEOUT_SECONDS}s") from None

    await proc.wait()
    return _InfoRun(stdout, stderr, expired, proc.returncode)


def _raise_for_failure(run: _InfoRun) -> None:
    """Raise when the info run failed.

    MakemkvBinaryExpiredError for an expired binary, else ScanError on a non-zero exit.
    """
    if run.expired:
        raise MakemkvBinaryExpiredError(
            "makemkvcon refused: binary is past its hard-coded expiry "
            "(MSG:5021 'application version is too old'). MakeMKV beta "
            "binaries carry a 60-day kill-switch from release date that "
            "no registration key overrides; the only fix is rebuilding the "
            "ripper image after upstream ships a fresher tarball. See "
            "docs/user/MakeMKV-Ripper.md § Failure modes."
        )

    if run.returncode != 0:
        msg = run.stderr.decode(errors="replace").strip() or run.stdout.decode(errors="replace")[:200]
        raise ScanError(f"makemkvcon exited {run.returncode}: {msg}")


def _fingerprints(probe: DiscProbe) -> list[DiscFingerprintInput]:
    """The disc fingerprints the probe found, in the order crc64, thediscdb, matrix256; empty values are skipped."""
    fingerprints: list[DiscFingerprintInput] = []
    if probe.crc64:
        fingerprints.append(DiscFingerprintInput(algo="crc64", value=probe.crc64))
    if probe.thediscdb:
        fingerprints.append(DiscFingerprintInput(algo="thediscdb", value=probe.thediscdb))
    if probe.matrix256:
        fingerprints.append(DiscFingerprintInput(algo="matrix256", value=probe.matrix256))
    return fingerprints


async def scan_disc(device_path: str) -> ScanResult:
    run = await _run_info(device_path)

    _raise_for_failure(run)

    lines = run.stdout.decode(errors="replace").splitlines()
    volume_label, titles, mkv_disc_type = parse_makemkvcon_info(lines)

    # MakeMKV's CINFO:1 is the authoritative disc-type signal — works on
    # region-locked discs that the kernel refuses to mount, and on UDF
    # quirks; when CINFO:1 is missing we fall back to a title-size heuristic.
    # Classify before probing so the probe knows whether to bother opening
    # the disc a third time for the Blu-ray-only BDMT read.
    if mkv_disc_type is not None:
        disc_type = mkv_disc_type
    else:
        disc_type = _classify_from_titles(titles)
    probe = await probe_disc(device_path, bluray=disc_type == DiscType.BLURAY)

    return ScanResult(
        disc_type=disc_type,
        volume_label=volume_label,
        titles=titles,
        fingerprints=_fingerprints(probe),
        bd_meta=probe.bd_meta,
    )
