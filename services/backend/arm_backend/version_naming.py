"""Names for the versions of one film that a job keeps: the `{edition?}` and `{plex_edition?}` tokens.

A version set is a kept title and the alternates that point at it (angles, a 2D/3D twin, a shorter cut,
every edition). A set with one kept member needs no name; with two or more, each kept member is named so
the files differ and Plex can group them. The name is the operator's edition when there is one, else one
derived from the title's class: "Angle 2", "3D", "2D", "Shorter Cut".
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from arm_backend.path_sanitize import sanitize_path_component
from arm_common.disc_titles import parse_title_ref
from arm_common.enums import TitleClass
from arm_common.models import Track
from arm_common.title_classes import TitleVerdict, version_sets

_BRACES = str.maketrans("", "", "{}")


def track_version_sets(tracks: Sequence[Track]) -> list[tuple[Track, ...]]:
    """The version sets of the job's tracks, derived from the classifier columns (a track without a
    `title_class` is in none)."""
    by_ref = {t.source_ref: t for t in tracks if t.title_class is not None}
    verdicts = [
        TitleVerdict(t.index, t.title_class, by_ref[t.title_class_ref].index if t.title_class_ref in by_ref else None)
        for t in by_ref.values()
        if t.title_class is not None
    ]
    by_index = {t.index: t for t in by_ref.values()}
    return [tuple(by_index[i] for i in members) for members in version_sets(verdicts)]


def _angle(track: Track) -> int:
    """The angle a track plays: the number in its ref, 1 for the base angle."""
    try:
        return parse_title_ref(track.source_ref)[1] or 1
    except ValueError:
        return 1


def _has_angles(members: Collection[Track]) -> bool:
    return any(t.title_class is TitleClass.ANGLE for t in members)


def _has_views(members: Collection[Track]) -> bool:
    return any(t.title_class is TitleClass.VIEW for t in members)


def _view_name(track: Track, stereo_3d: Collection[str]) -> str:
    return "3D" if track.source_ref in stereo_3d else "2D"


def _generated_name(track: Track, members: Collection[Track], stereo_3d: Collection[str]) -> str:
    """The name a title takes from its place in the set: its view, its angle, or what it is a cut of."""
    parts: list[str] = []
    if _has_views(members):
        parts.append(_view_name(track, stereo_3d))
    if _has_angles(members):
        parts.append(f"Angle {_angle(track)}")
    if parts:
        return " ".join(parts)
    if track.title_class is TitleClass.SUBSET:
        return "Shorter Cut"
    if track.title_class is TitleClass.VARIANT:
        return "With Intro"
    return f"Edition {track.index}" if track.title_class is TitleClass.EDITION else "Main"


def version_names(tracks: Sequence[Track], stereo_3d: Collection[str] = ()) -> dict[str, str]:
    """track id -> name, for every kept (not excluded) track of a version set with two or more kept members.
    A track that is not named has no entry. `stereo_3d` holds the `source_ref`s that play a 3D view."""
    names: dict[str, str] = {}
    for members in track_version_sets(tracks):
        kept = [t for t in members if not t.excluded]
        if len(kept) < 2:
            continue
        for t in kept:
            raw = t.edition or _generated_name(t, members, stereo_3d)
            names[t.id] = sanitize_path_component(raw.translate(_BRACES))
    return names


def plex_edition(name: str) -> str:
    """Plex's edition tag for a name: `{edition-Director's Cut}`; empty for no name."""
    return f"{{edition-{name}}}" if name else ""
