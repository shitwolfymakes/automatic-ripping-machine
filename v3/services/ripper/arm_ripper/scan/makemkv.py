import asyncio
import logging
import re
from typing import Iterable

from arm_common import DiscType
from arm_common.schemas import DiscFingerprintInput, ScanResult, ScanTitle
from arm_ripper.scan.disc_probe import probe_disc

logger = logging.getLogger("arm_ripper.scan.makemkv")

SCAN_TIMEOUT_SECONDS = 300.0

_DURATION_RE = re.compile(r"^(\d+):(\d{1,2}):(\d{1,2})$")
_QUOTED_RE = re.compile(r'^"(.*)"$')


class ScanError(Exception):
    pass


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

    MakeMKV emits one of (case-sensitive in practice but we lowercase for
    safety): "DVD", "Blu-ray disc", "HD-DVD", "Audio CD". Anything else
    is treated as None so callers fall back to other signals.
    """
    s = disc_type_text.strip().lower()
    if "blu-ray" in s or s == "bd":
        return DiscType.BLURAY
    if s == "dvd" or "dvd-video" in s:
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
    string was missing AND the mount-probe couldn't read VIDEO_TS / BDMV.
    Title size > 4.7GB is unreliable (DVD-9s exceed it routinely) but
    better than UNKNOWN.
    """
    if not titles:
        return DiscType.UNKNOWN
    longest = max(t.duration_seconds for t in titles)
    return (
        DiscType.BLURAY
        if longest >= 60 * 60 * 1.5 and any(t.size_bytes is not None and t.size_bytes > 4_700_000_000 for t in titles)
        else DiscType.DVD
    )


async def scan_disc(device_path: str) -> ScanResult:
    cmd = ["makemkvcon", "-r", "--cache=1", "info", f"dev:{device_path}"]
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
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=SCAN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise ScanError(f"makemkvcon timed out after {SCAN_TIMEOUT_SECONDS}s") from None

    if proc.returncode != 0:
        msg = stderr.decode(errors="replace").strip() or stdout.decode(errors="replace")[:200]
        raise ScanError(f"makemkvcon exited {proc.returncode}: {msg}")

    lines = stdout.decode(errors="replace").splitlines()
    volume_label, titles, mkv_disc_type = parse_makemkvcon_info(lines)

    # MakeMKV's CINFO:1 is the authoritative disc-type signal — works on
    # region-locked discs that the kernel refuses to mount, and on UDF
    # quirks where blkid reads the FS but mount returns "cannot mount
    # read-only". The mount-probe is still useful for computing CRC64 (and
    # for catching the rare case where MakeMKV doesn't emit CINFO:1), but
    # it doesn't override what MakeMKV says.
    probe = await probe_disc(device_path)
    if mkv_disc_type is not None:
        disc_type = mkv_disc_type
    elif probe.disc_type is not None:
        disc_type = probe.disc_type
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
