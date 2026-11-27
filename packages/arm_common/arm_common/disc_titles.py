"""Candidate titles from the disc's playlist structure (no MakeMKV): one per playlist and angle.

`titles_from_structure` turns the Blu-ray structure read (`BdPlaylist`, `BdClip`) into `ScanTitle`s;
`title_ref` / `parse_title_ref` are the one place that writes and reads the title reference
(`00334.mpls`, or `00334.mpls:2` for angle 2 of a multi-angle playlist). Pure; no I/O.

Dependent views. `BdPlaylist.mvc_clips` is flat, in play order across every angle: one clip per play
item and angle for a multi-clip SubPlayItem, one per item otherwise. A play item's angle count is
1 plus the extra angles whose clip differs from the base (an item without that angle repeats its own
clip in `angle_clips`), so the list splits into one chunk per play item and angle `a` of an item takes
chunk entry `a`, or the first when the item has fewer angles. A list that is neither that length nor
one clip per item cannot be paired; its title stays 3D (when CLPI marks a clip of it as a dependent
view) but has no known size. A clip counts as a dependent view only through `BdClip.mvc`: extras
carry a stereoscopic SubPath block too.
"""

from __future__ import annotations

from collections.abc import Sequence

from arm_common.schemas import BdClip, BdPlaylist, ScanTitle

_ANGLE_SEPARATOR = ":"


def title_ref(source_file: str, angle: int | None) -> str:
    """`00334.mpls` for a single-angle playlist, `00334.mpls:2` for angle 2 of a multi-angle one."""
    return source_file if angle is None else f"{source_file}{_ANGLE_SEPARATOR}{angle}"


def parse_title_ref(ref: str) -> tuple[str, int | None]:
    """(source file, angle or None) of a title ref; ValueError for a malformed ref."""
    source, sep, angle_text = ref.partition(_ANGLE_SEPARATOR)
    if not source or (sep and (not angle_text.isdigit() or int(angle_text) < 1)):
        raise ValueError(f"malformed title ref {ref!r}")
    return source, (int(angle_text) if sep else None)


def _item_angle_counts(playlist: BdPlaylist) -> list[int]:
    """Angles per play item: the base plus each extra angle whose clip differs from the base."""
    return [1 + sum(1 for extra in playlist.angle_clips if extra[i] != clip) for i, clip in enumerate(playlist.clips)]


def _dependents_by_item(playlist: BdPlaylist) -> list[list[int]] | None:
    """The dependent clips of each play item, one per angle of the item; None when the flat list cannot be paired."""
    flat = playlist.mvc_clips
    counts = _item_angle_counts(playlist)
    if len(flat) == sum(counts):
        sizes = counts
    elif len(flat) == len(counts):
        sizes = [1] * len(counts)
    else:
        return None
    chunks: list[list[int]] = []
    pos = 0
    for size in sizes:
        chunks.append(flat[pos : pos + size])
        pos += size
    return chunks


def _is_dependent_view(number: int, clips: dict[int, BdClip]) -> bool:
    clip = clips.get(number)
    return clip is not None and clip.mvc


def _angle_dependents(chunks: list[list[int]], angle: int, clips: dict[int, BdClip]) -> list[int | None]:
    """Per play item, the confirmed dependent-view clip of `angle` (0-based), or None."""
    picked = [chunk[angle] if angle < len(chunk) else chunk[0] for chunk in chunks]
    return [number if _is_dependent_view(number, clips) else None for number in picked]


def _used_bytes(clip: BdClip | None, seconds: float) -> int | None:
    """The part of the clip's file a play item of `seconds` reads; None when the size is unknown."""
    if clip is None or clip.size_bytes is None:
        return None
    if clip.seconds <= 0:
        return clip.size_bytes
    return round(clip.size_bytes * min(1.0, seconds / clip.seconds))


def _title_size(
    base: Sequence[int], dependents: Sequence[int | None], seconds: Sequence[float], clips: dict[int, BdClip]
) -> int | None:
    """Sum of the played share of every base and dependent clip; None when any is unsized."""
    total = 0
    for number, dependent, item_seconds in zip(base, dependents, seconds, strict=True):
        parts = [_used_bytes(clips.get(number), item_seconds)]
        if dependent is not None:
            parts.append(_used_bytes(clips.get(dependent), item_seconds))
        if any(part is None for part in parts):
            return None
        total += sum(part for part in parts if part is not None)
    return total


def _angle_title(playlist: BdPlaylist, angle: int, clips: dict[int, BdClip]) -> ScanTitle:
    """The title of angle `angle` (0-based) of `playlist`; `index` is set by the caller."""
    base = [playlist.clips, *playlist.angle_clips][angle]
    chunks = _dependents_by_item(playlist)
    if chunks is None:
        dependents: list[int | None] = [None] * len(base)
        stereo = any(_is_dependent_view(number, clips) for number in playlist.mvc_clips)
        size = None if stereo else _title_size(base, dependents, playlist.clip_seconds, clips)
    else:
        dependents = _angle_dependents(chunks, angle, clips)
        stereo = any(number is not None for number in dependents)
        size = _title_size(base, dependents, playlist.clip_seconds, clips)
    return ScanTitle(
        index=0,
        duration_seconds=playlist.duration_seconds,
        chapter_count=playlist.chapter_count,
        size_bytes=size,
        source_file=playlist.name,
        segment_count=len(base),
        segment_map=list(base),
        angle=angle + 1 if playlist.angle_clips else None,
        stereo_3d=stereo,
    )


def titles_from_structure(
    playlists: Sequence[BdPlaylist], clips: Sequence[BdClip], min_length_seconds: int
) -> list[ScanTitle]:
    """One title per playlist and angle at least `min_length_seconds` long.

    Playlist name ascending, a playlist's angles adjacent; `index` is the position in the result.
    `segment_map` is the angle's base clips; `size_bytes` adds the dependent views of a 3D title
    and scales a partly played clip by the played share (None when a clip is unsized).
    """
    by_number = {clip.number: clip for clip in clips}
    titles: list[ScanTitle] = []
    for playlist in sorted(playlists, key=lambda p: p.name):
        if playlist.duration_seconds < min_length_seconds:
            continue
        for angle in range(1 + len(playlist.angle_clips)):
            title = _angle_title(playlist, angle, by_number)
            titles.append(title.model_copy(update={"index": len(titles)}))
    return titles
