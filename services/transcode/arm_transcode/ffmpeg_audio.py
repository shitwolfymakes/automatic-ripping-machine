"""ffmpeg-based audio re-encoder.

The ripper produces `track_NN.wav` files for CDs. The transcode tasks
attached to a music session re-encode each WAV into the target container
(`flac` / `mp3`). `preset_ref` selects the codec — we map the small set
of seeded values to ffmpeg flags rather than letting users pass arbitrary
encoder strings.

Progress is parsed from `-progress pipe:1`, which ffmpeg emits as
`key=value` lines roughly every second. `out_time_us` (microseconds) +
the source's `duration_seconds` → percent.

A music track's tags (`MusicTags`, from the Backend's register response)
go in as `-metadata key=value` pairs, one argv item each, so any title is
safe without shell quoting. FLAC gets Vorbis comment names; MP3 gets the
ffmpeg ID3v2 keys, written as ID3v2.3 for the widest player support.
The cover, when there is one, is a second input copied in untouched as
the front-cover picture (a FLAC PICTURE block, an ID3 APIC frame).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from pathlib import Path

from arm_common.schemas import MusicTags
from arm_transcode.ffmpeg_progress import ProgressCallback, consume_progress, drain_stderr

logger = logging.getLogger("arm_transcode.ffmpeg_audio")


# `-f <muxer>` is mandatory: the atomic-rename flow writes the output as
# `<final>.arm-inprogress`, and ffmpeg infers the container from the
# filename extension. Without `-f`, ffmpeg sees `.arm-inprogress` and
# bails with "Unable to find a suitable output format" before encoding
# anything. Same shape as engines/ffmpeg_vaapi.py.
_CODEC_FLAGS: dict[str, list[str]] = {
    "flac": ["-c:a", "flac", "-compression_level", "8", "-f", "flac"],
    "mp3": ["-c:a", "libmp3lame", "-q:a", "0", "-id3v2_version", "3", "-f", "mp3"],
}


def _flac_tags(tags: MusicTags) -> list[tuple[str, object]]:
    return [
        ("ARTIST", tags.artist),
        ("ALBUMARTIST", tags.artist),
        ("ALBUM", tags.album),
        ("TITLE", tags.title),
        ("TRACKNUMBER", tags.track_number),
        ("TRACKTOTAL", tags.track_total),
        ("DISCNUMBER", tags.disc_number),
        ("DATE", tags.year),
        ("MUSICBRAINZ_ALBUMID", tags.musicbrainz_release_id),
    ]


def _mp3_tags(tags: MusicTags) -> list[tuple[str, object]]:
    track: int | str | None = tags.track_number
    if track is not None and tags.track_total is not None:
        track = f"{track}/{tags.track_total}"
    return [
        ("artist", tags.artist),
        ("album_artist", tags.artist),
        ("album", tags.album),
        ("title", tags.title),
        ("track", track),
        ("disc", tags.disc_number),
        ("date", tags.year),
        # Not an ID3 frame name, so ffmpeg writes it as TXXX with this
        # description: the name Picard and beets read the release id from.
        ("MusicBrainz Album Id", tags.musicbrainz_release_id),
    ]


_TAG_MAPS: dict[str, Callable[[MusicTags], list[tuple[str, object]]]] = {"flac": _flac_tags, "mp3": _mp3_tags}


# The cover is the second input: map the WAV's audio and the image, copy the
# image as-is, and mark it as the front cover (picture type 3) both muxers read
# from the stream's `comment`.
_COVER_ARGS = [
    "-map",
    "0:a",
    "-map",
    "1:v",
    "-c:v",
    "copy",
    "-disposition:v",
    "attached_pic",
    "-metadata:s:v",
    "title=Album cover",
    "-metadata:s:v",
    "comment=Cover (front)",
]


def _metadata_args(codec: str, tags: MusicTags | None) -> list[str]:
    """`-metadata key=value` argv pairs for every known tag; [] without tags."""
    if tags is None:
        return []
    args: list[str] = []
    for key, value in _TAG_MAPS[codec](tags):
        if value is not None and value != "":
            args += ["-metadata", f"{key}={value}"]
    return args


def build_audio_command(
    *,
    input_path: Path,
    output_path: Path,
    preset_ref: str,
    tags: MusicTags | None = None,
    cover_path: Path | None = None,
) -> list[str]:
    """Build the ffmpeg argv that re-encodes `input_path` to the preset's codec,
    writing `tags` and the `cover_path` image into the output.

    Progress goes to stdout; raises `RuntimeError` for an unknown preset.
    """
    codec = preset_ref.lower()
    flags = _CODEC_FLAGS.get(codec)
    if flags is None:
        raise RuntimeError(f"unsupported audio preset_ref={preset_ref!r}")

    return [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-y",
        "-i",
        str(input_path),
        *(["-i", str(cover_path), *_COVER_ARGS] if cover_path is not None else []),
        *flags,
        *_metadata_args(codec, tags),
        str(output_path),
    ]


async def transcode_audio(
    *,
    input_path: Path,
    output_path: Path,
    preset_ref: str,
    duration_seconds: int | None,
    progress_callback: ProgressCallback,
    tags: MusicTags | None = None,
    cover_path: Path | None = None,
) -> int:
    """Run ffmpeg to re-encode `input_path` → `output_path`, tagged with `tags` and `cover_path`.

    Returns the final file size in bytes; raises `RuntimeError` on non-zero exit.
    """
    cmd = build_audio_command(
        input_path=input_path, output_path=output_path, preset_ref=preset_ref, tags=tags, cover_path=cover_path
    )
    logger.info("ffmpeg launching: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None

    stderr_buf: list[str] = []
    stderr_task = asyncio.create_task(drain_stderr(proc.stderr, stderr_buf))

    try:
        await consume_progress(proc.stdout, duration_seconds, progress_callback)
        rc = await proc.wait()
    finally:
        with contextlib.suppress(asyncio.CancelledError):
            await stderr_task

    if rc != 0:
        tail = "\n".join(stderr_buf[-30:])
        raise RuntimeError(f"ffmpeg exited rc={rc}\nstderr tail:\n{tail}")

    return output_path.stat().st_size
