"""Pure classifier for scanned Blu-ray titles.

MakeMKV lists every playlist and raw stream on a disc. Many are not distinct
content: exact copies, raw streams a playlist already covers, decoy playlists
that replay the feature's clips in another order, and variants that are the
feature plus a disclaimer. `classify_titles` gives every title a verdict; the
kept ones (`KEPT_CLASSES`) are the distinct titles worth selecting.

No I/O. Each step is its own function over `classed`, the verdicts of the
titles demoted so far; a step returns an extended copy and never mutates its
argument.
"""

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

from arm_common.enums import TitleClass
from arm_common.schemas.ripper import ScanTitle

# MakeMKV durations are whole seconds; allow for rounding.
SAME_RUNTIME_SECONDS = 2
# A variant is a kept title's clips plus one or two short extras.
VARIANT_MAX_EXTRA_CLIPS = 2
VARIANT_MAX_EXTRA_SECONDS = 180
# Feature-length: at least this share of the longest kept title.
EDITION_MIN_SHARE = 0.6
# At least half of the shorter cut's clips are shared.
EDITION_MIN_OVERLAP = 0.5
# Cuts closer than this are not called editions.
EDITION_MIN_DELTA_SECONDS = 180
MAIN_FEATURE_MIN_SECONDS = 45 * 60


@dataclass(frozen=True)
class TitleVerdict:
    index: int
    title_class: TitleClass
    # The kept title this one copies (DUPLICATE/DECOY/VARIANT), else None.
    of_index: int | None


KEPT_CLASSES = frozenset({TitleClass.PRIMARY, TitleClass.EDITION})

_Classed = dict[int, TitleVerdict]


def _clips(title: ScanTitle) -> frozenset[int]:
    return frozenset(title.segment_map or ())


def _m2ts_clip_number(source_file: str | None) -> int | None:
    """`00294.m2ts` -> 294; None for anything that is not a raw stream."""
    if source_file is None:
        return None
    stem, _, extension = source_file.rpartition(".")
    if extension.lower() != "m2ts" or not stem.isdecimal():
        return None
    return int(stem)


def _is_playlist(title: ScanTitle) -> bool:
    return (title.source_file or "").lower().endswith(".mpls")


def pick_representative(group: Sequence[ScanTitle], preferred: Collection[int]) -> ScanTitle:
    """The title of a group that stays kept: the only one with a comment, else
    the only preferred one, else the lowest index (MakeMKV lists its own pick
    first; never order by playlist number)."""
    for narrowed in (
        [t for t in group if t.comment],
        [t for t in group if t.index in preferred],
    ):
        if len(narrowed) == 1:
            return narrowed[0]
    return min(group, key=lambda t: t.index)


def _repoint(classed: _Classed, old: int, new: int) -> _Classed:
    """Copy of `classed` where verdicts that pointed at `old` point at `new`."""
    return {index: TitleVerdict(index, v.title_class, new) if v.of_index == old else v for index, v in classed.items()}


def _demote(classed: _Classed, title: int, title_class: TitleClass, of_index: int) -> _Classed:
    """Copy of `classed` with `title` demoted to a copy of `of_index`; whatever
    was a copy of `title` becomes a copy of `of_index`."""
    moved = _repoint(classed, title, of_index)
    moved[title] = TitleVerdict(title, title_class, of_index)
    return moved


def _demote_groups(
    classed: _Classed,
    groups: Iterable[Sequence[ScanTitle]],
    title_class: TitleClass,
    preferred: Collection[int],
) -> _Classed:
    """Keep each group's representative of the groups with >= 2 members; every
    other member becomes `title_class` of it."""
    result = dict(classed)
    for group in groups:
        if len(group) < 2:
            continue
        keeper = pick_representative(group, preferred)
        for member in group:
            if member is not keeper:
                result[member.index] = TitleVerdict(member.index, title_class, keeper.index)
    return result


def _exact_duplicates(titles: Sequence[ScanTitle], preferred: Collection[int]) -> _Classed:
    """Step 1: structured titles with the identical clip sequence."""
    groups: dict[tuple[int, ...], list[ScanTitle]] = {}
    for title in titles:
        groups.setdefault(tuple(title.segment_map or ()), []).append(title)
    return _demote_groups({}, groups.values(), TitleClass.DUPLICATE, preferred)


def _playlist_covers_raw(
    playlist: ScanTitle,
    raw: ScanTitle,
    clip: int,
    clip_seconds: Mapping[int, float] | None,
) -> bool:
    if not _is_playlist(playlist) or clip not in _clips(playlist):
        return False
    known = None if clip_seconds is None else clip_seconds.get(clip)
    if known is not None:
        return known >= raw.duration_seconds - SAME_RUNTIME_SECONDS
    return 0 <= playlist.duration_seconds - raw.duration_seconds <= VARIANT_MAX_EXTRA_SECONDS


def _raw_stream_duplicates(
    titles: Sequence[ScanTitle],
    classed: _Classed,
    preferred: Collection[int],
    clip_seconds: Mapping[int, float] | None,
) -> _Classed:
    """Step 2: a raw .m2ts a kept playlist already plays is a duplicate of it."""
    result = dict(classed)
    for raw in titles:
        clip = _m2ts_clip_number(raw.source_file)
        if clip is None or raw.index in result:
            continue
        covering = [p for p in titles if p.index not in result and _playlist_covers_raw(p, raw, clip, clip_seconds)]
        if covering:
            keeper = pick_representative(covering, preferred)
            result[raw.index] = TitleVerdict(raw.index, TitleClass.DUPLICATE, keeper.index)
    return result


def _decoy_groups(titles: Sequence[ScanTitle], classed: _Classed, preferred: Collection[int]) -> _Classed:
    """Step 3: titles with the same clip set (>= 2 distinct clips), different order."""
    groups: dict[frozenset[int], list[ScanTitle]] = {}
    for title in titles:
        if title.index not in classed and len(_clips(title)) >= 2:
            groups.setdefault(_clips(title), []).append(title)
    return _demote_groups(classed, groups.values(), TitleClass.DECOY, preferred)


def _extra_seconds(base: ScanTitle, candidate: ScanTitle, clip_seconds: Mapping[int, float] | None) -> float:
    """Runtime `candidate` adds over `base`: the extra clips' own lengths when
    all are known, else the difference in title durations."""
    extra = _clips(candidate) - _clips(base)
    if clip_seconds is not None and extra.issubset(clip_seconds):
        return sum(clip_seconds[c] for c in extra)
    return candidate.duration_seconds - base.duration_seconds


def _is_variant_of(base: ScanTitle, candidate: ScanTitle, clip_seconds: Mapping[int, float] | None) -> bool:
    if not _clips(base) < _clips(candidate):
        return False
    if len(_clips(candidate) - _clips(base)) > VARIANT_MAX_EXTRA_CLIPS:
        return False
    return 0 < _extra_seconds(base, candidate, clip_seconds) <= VARIANT_MAX_EXTRA_SECONDS


def _best_base(
    candidate: ScanTitle,
    bases: Iterable[ScanTitle],
    clip_seconds: Mapping[int, float] | None,
) -> ScanTitle | None:
    """The base `candidate` is a variant of: largest clip set, then lowest index."""
    fits = [b for b in bases if _is_variant_of(b, candidate, clip_seconds)]
    return min(fits, key=lambda b: (-len(_clips(b)), b.index), default=None)


def _variants(
    titles: Sequence[ScanTitle],
    classed: _Classed,
    clip_seconds: Mapping[int, float] | None,
) -> _Classed:
    """Step 4: a kept title's clips plus one or two short extras."""
    result = dict(classed)
    for candidate in titles:
        if candidate.index in result:
            continue
        kept = [t for t in titles if t.index not in result]
        base = _best_base(candidate, kept, clip_seconds)
        if base is not None:
            result = _demote(result, candidate.index, TitleClass.VARIANT, base.index)
    return result


def _is_edition_pair(a: ScanTitle, b: ScanTitle) -> bool:
    shared = len(_clips(a) & _clips(b)) / min(len(_clips(a)), len(_clips(b)))
    apart = abs(a.duration_seconds - b.duration_seconds) > EDITION_MIN_DELTA_SECONDS
    return shared >= EDITION_MIN_OVERLAP and apart


def _edition_members(kept: Sequence[ScanTitle]) -> set[int]:
    """Step 5: indexes of feature-length kept titles that are distinct cuts of
    one another (a member of any pair belongs to a component of size >= 2)."""
    longest = max((t.duration_seconds for t in kept), default=0)
    floor = max(MAIN_FEATURE_MIN_SECONDS, EDITION_MIN_SHARE * longest)
    features = [t for t in kept if t.segment_map and t.duration_seconds >= floor]
    return {t.index for pair in combinations(features, 2) if _is_edition_pair(*pair) for t in pair}


def _kept_verdict(title: ScanTitle, editions: Collection[int]) -> TitleVerdict:
    title_class = TitleClass.EDITION if title.index in editions else TitleClass.PRIMARY
    return TitleVerdict(title.index, title_class, None)


def classify_titles(
    titles: Sequence[ScanTitle],
    *,
    preferred: frozenset[int] = frozenset(),
    clip_seconds: Mapping[int, float] | None = None,
) -> dict[int, TitleVerdict]:
    """A verdict for every title. Call only for Blu-ray scans. A title without
    a segment map takes part in no step and stays PRIMARY."""
    ordered = sorted(titles, key=lambda t: t.index)
    structured = [t for t in ordered if t.segment_map]
    classed = _exact_duplicates(structured, preferred)
    classed = _raw_stream_duplicates(ordered, classed, preferred, clip_seconds)
    classed = _decoy_groups(structured, classed, preferred)
    classed = _variants(structured, classed, clip_seconds)
    editions = _edition_members([t for t in ordered if t.index not in classed])
    return {t.index: classed.get(t.index) or _kept_verdict(t, editions) for t in ordered}
