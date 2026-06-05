import asyncio
import logging
import re
from typing import Iterable

from arm_common import DiscType
from arm_common.schemas import DiscFingerprintInput, ScanResult, ScanTitle
from arm_ripper.scan.disc_probe import probe_disc
from arm_ripper.source import makemkv_source_url

logger = logging.getLogger("arm_ripper.scan.makemkv")

SCAN_TIMEOUT_SECONDS = 300.0

# MakeMKV emits this when its hard-coded 60-day beta kill-switch has fired.
# No registration key overrides it; the binary refuses all protected-disc
# work and the only fix is rebuilding against a fresher upstream tarball.
# See docs/ops/makemkv.md § Failure modes.
_MAKEMKV_EXPIRED_PREFIX = b"MSG:5021,"

_DURATION_RE = re.compile(r"^(\d+):(\d{1,2}):(\d{1,2})$")
_QUOTED_RE = re.compile(r'^"(.*)"$')


class ScanError(Exception):
    pass


class MakemkvBinaryExpiredError(ScanError):
    """Distinct subtype so callers / operators can match this specifically
    and route to the upstream-blocked playbook instead of a generic retry."""


def _strip_quotes(value: str) -> str:
    m = _QUOTED_RE.match(value.strip())
    return m.group(1) if m else value.strip()


def _parse_duration(value: str) -> int | None:
    m = _DURATION_RE.match(value.strip())
    if not m:
        return None
    h, mn, s = (int(g) for g in m.groups())
    return h * 3600 + mn * 60 + s


def _classify_from_cinfo(disc_type_text: str) -> DiscType | None:
    """Map MakeMKV's `CINFO:1` text value to our DiscType enum.

    Observed values vary across MakeMKV versions:
      - "DVD" (v1.17.x) and "DVD disc" (v1.18.x) for DVD-Video
      - "Blu-ray disc" for BD-Video
      - "Audio CD" for CDDA
      - "HD-DVD" / "HD DVD" for HD-DVD (no v3 enum yet — return None)
    Match HD-DVD before DVD because "hd-dvd" contains "dvd".
    """
    s = disc_type_text.strip().lower()
    if "blu-ray" in s or "bluray" in s or s == "bd":
        return DiscType.BLURAY
    if "hd-dvd" in s or "hd dvd" in s:
        return None
    if "dvd" in s:
        return DiscType.DVD
    if "audio cd" in s or s == "cd":
        return DiscType.CD
    return None


def parse_makemkvcon_info(
    lines: Iterable[str],
) -> tuple[str | None, list[ScanTitle], DiscType | None]:
    """Parse the robot-mode output of `makemkvcon -r info`.

    Returns (volume_label, titles, mkv_disc_type).

    MakeMKV codes used:
    - CINFO:1,...    — disc-type text ("DVD" / "Blu-ray disc" / "HD-DVD" /
                       "Audio CD") — authoritative signal regardless of
                       region-locks or kernel-mount failures
    - CINFO:2,...    — disc name (volume label)
    - CINFO:30,...   — disc tree info (sometimes the only place with the label)
    - TINFO:t,9,...  — title duration (HH:MM:SS)
    - TINFO:t,8,...  — chapter count
    - TINFO:t,11,... — title size in bytes
    - TINFO:t,27,... — source filename (e.g. title_t00.mkv)

    Reference: https://github.com/automatic-ripping-machine/automatic-ripping-machine/wiki/MakeMKV-Codes
    """
    volume_label: str | None = None
    mkv_disc_type: DiscType | None = None
    titles: dict[int, dict[str, object]] = {}

    for raw in lines:
        line = raw.strip()
        if not line or ":" not in line:
            continue
        msg_type, _, rest = line.partition(":")
        fields = [f.strip() for f in rest.split(",")]

        if msg_type == "CINFO" and len(fields) >= 3:
            try:
                code = int(fields[0])
            except ValueError:
                continue
            if code == 1 and mkv_disc_type is None:
                mkv_disc_type = _classify_from_cinfo(_strip_quotes(",".join(fields[2:])))
            elif code in (2, 30) and not volume_label:
                volume_label = _strip_quotes(",".join(fields[2:]))

        elif msg_type == "TINFO" and len(fields) >= 4:
            try:
                track_idx = int(fields[0])
                code = int(fields[1])
            except ValueError:
                continue
            value = _strip_quotes(",".join(fields[3:]))
            entry = titles.setdefault(track_idx, {})
            if code == 8:
                try:
                    entry["chapter_count"] = int(value)
                except ValueError:
                    pass
            elif code == 9:
                duration = _parse_duration(value)
                if duration is not None:
                    entry["duration_seconds"] = duration
            elif code == 11:
                try:
                    entry["size_bytes"] = int(value)
                except ValueError:
                    pass
            elif code == 27:
                entry["source_file"] = value

    parsed: list[ScanTitle] = []
    for idx in sorted(titles):
        entry = titles[idx]
        duration_obj = entry.get("duration_seconds")
        if not isinstance(duration_obj, int):
            continue
        chapter_obj = entry.get("chapter_count")
        size_obj = entry.get("size_bytes")
        source_obj = entry.get("source_file")
        parsed.append(
            ScanTitle(
                index=idx,
                duration_seconds=duration_obj,
                chapter_count=chapter_obj if isinstance(chapter_obj, int) else None,
                size_bytes=size_obj if isinstance(size_obj, int) else None,
                source_file=source_obj if isinstance(source_obj, str) else None,
            )
        )

    return volume_label, parsed, mkv_disc_type


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
    stdout_chunks: list[bytes] = []
    expired = False

    async def _read_stdout() -> None:
        nonlocal expired
        assert proc.stdout is not None
        async for raw in proc.stdout:
            stdout_chunks.append(raw)
            if not expired and raw.startswith(_MAKEMKV_EXPIRED_PREFIX):
                expired = True
                proc.kill()
                # Keep draining the pipe so the kernel doesn't block on
                # buffered writes between SIGKILL and process teardown.

    async def _drain_stderr() -> bytes:
        assert proc.stderr is not None
        chunks: list[bytes] = []
        async for chunk in proc.stderr:
            chunks.append(chunk)
        return b"".join(chunks)

    stdout_task = asyncio.create_task(_read_stdout())
    stderr_task = asyncio.create_task(_drain_stderr())
    await stdout_task
    stderr_bytes = await stderr_task
    return b"".join(stdout_chunks), stderr_bytes, expired


async def scan_disc(device_path: str) -> ScanResult:
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

    if expired:
        raise MakemkvBinaryExpiredError(
            "makemkvcon refused: binary is past its hard-coded expiry "
            "(MSG:5021 'application version is too old'). MakeMKV beta "
            "binaries carry a 60-day kill-switch from release date that "
            "no registration key overrides; the only fix is rebuilding the "
            "ripper image after upstream ships a fresher tarball. See "
            "docs/ops/makemkv.md § Failure modes."
        )

    if proc.returncode != 0:
        msg = stderr.decode(errors="replace").strip() or stdout.decode(errors="replace")[:200]
        raise ScanError(f"makemkvcon exited {proc.returncode}: {msg}")

    lines = stdout.decode(errors="replace").splitlines()
    volume_label, titles, mkv_disc_type = parse_makemkvcon_info(lines)

    # MakeMKV's CINFO:1 is the authoritative disc-type signal — works on
    # region-locked discs that the kernel refuses to mount, and on UDF
    # quirks. The probe's only job is the CRC64 fingerprint (read off the
    # device, no mount); when CINFO:1 is missing we fall back to a title-size
    # heuristic rather than any layout probe.
    probe = await probe_disc(device_path)
    if mkv_disc_type is not None:
        disc_type = mkv_disc_type
    else:
        disc_type = _classify_from_titles(titles)

    fingerprints: list[DiscFingerprintInput] = []
    if probe.crc64:
        fingerprints.append(DiscFingerprintInput(algo="crc64", value=probe.crc64))

    return ScanResult(
        disc_type=disc_type,
        volume_label=volume_label,
        titles=titles,
        fingerprints=fingerprints,
    )
