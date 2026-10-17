"""Track selection on a 99-title "decoy playlist" disc.

Some DVDs (Disney, Sony, Lionsgate and others) carry structure protection:
99 titles, most of them decoys whose length is within seconds of the real
feature, some of them longer than it. ARM v2 detected these (`lsdvd` reporting
exactly 99 tracks) and by default refused the disc (PREVENT_99). v3 has no
such handling yet.

MakeMKV drops some decoys itself ("assuming fake title", "Title X is equal to
title Y and was skipped"), so what reaches us can be fewer than 99 titles. This
fixture is the worst case: every decoy survives the scan, with the same
chapter count as the feature, as on reported discs where nine titles were all
"8 chapter(s) 0:49:10 14 cell(s)".

These are characterisation tests: they pin what the presets do with such a
disc TODAY so a future fix is a deliberate, visible change. The tests marked
`xfail(strict=True)` state the behaviour we want; they fail now, and when the
handling lands they start passing and strict mode makes the suite flag them so
they can be promoted to plain tests.

The scan mirrors the ripper's fixture
(services/ripper/tests/fixtures/makemkvcon_dvd_99_titles.txt): the real
feature is title 37 (6201s, 28 chapters), 92 decoys sit within 5s of it with
the same chapter count, the longest decoy is 6206s, and 6 short titles
(warnings, menus, trailers) fill the rest.
"""

import pytest

from arm_backend.track_selection import (
    ALL_TRACKS_MIN_SECONDS,
    select_tracks,
    select_tracks_for_review,
)
from arm_common import (
    DiscType,
    IdentificationMode,
    MediaType,
    OutputMode,
    RipPreset,
    TrackSelection,
)
from arm_common.schemas import ScanResult, ScanTitle

JOB_ID = "job_01JZXR7K3M5Q8N4VWA00000099"
FEATURE_INDEX = 37
FEATURE_SECONDS = 6201
SHORT = {0: 21, 1: 44, 2: 95, 96: 137, 97: 151, 98: 302}
OFFSETS = [0, -1, 2, -3, 1, 5, -2, 0, 3, -4, 1, -1]


def _decoy_disc() -> ScanResult:
    titles = []
    k = 0
    for i in range(99):
        if i == FEATURE_INDEX:
            secs = FEATURE_SECONDS
        elif i in SHORT:
            secs = SHORT[i]
        else:
            secs = FEATURE_SECONDS + OFFSETS[k % len(OFFSETS)]
            k += 1
        titles.append(ScanTitle(index=i, duration_seconds=secs, chapter_count=1 if i in SHORT else 28))
    return ScanResult(disc_type=DiscType.DVD, titles=titles)


def _preset(rule: TrackSelection, filters: dict | None = None) -> RipPreset:
    return RipPreset(
        id="rpr_test",
        name="test",
        media_type=MediaType.MOVIE,
        is_builtin=False,
        track_selection=rule,
        identification_mode=IdentificationMode.REQUIRED,
        output_mode=OutputMode.TRACKS,
        track_filters_json=filters,
    )


def test_fixture_shape():
    scan = _decoy_disc()
    assert len(scan.titles) == 99
    near = [t for t in scan.titles if abs(t.duration_seconds - FEATURE_SECONDS) <= 5]
    assert len(near) == 93
    longest = max(scan.titles, key=lambda t: t.duration_seconds)
    assert longest.duration_seconds == FEATURE_SECONDS + 5
    assert longest.index != FEATURE_INDEX


# --- what happens today -----------------------------------------------------


def test_main_feature_picks_the_longest_decoy_today():
    """MAIN_FEATURE takes the single longest title, so a decoy a few seconds
    longer than the real feature wins and nothing flags the disc."""
    tracks = select_tracks(JOB_ID, _decoy_disc(), _preset(TrackSelection.MAIN_FEATURE))
    assert len(tracks) == 1
    assert tracks[0].index != FEATURE_INDEX
    assert tracks[0].expected_duration_seconds == FEATURE_SECONDS + 5


def test_main_feature_breaks_a_tie_by_lowest_index_today():
    """With every candidate exactly the same length, max() keeps the first,
    so the pick is purely positional."""
    scan = ScanResult(
        disc_type=DiscType.DVD,
        titles=[ScanTitle(index=i, duration_seconds=FEATURE_SECONDS) for i in range(99)],
    )
    tracks = select_tracks(JOB_ID, scan, _preset(TrackSelection.MAIN_FEATURE))
    assert [t.index for t in tracks] == [0]


def test_all_tracks_queues_every_title_over_a_minute_today():
    """ALL_TRACKS keeps all 93 near-feature titles plus the menus/trailers over
    a minute: 97 rips (and transcodes), 93 of them essentially one movie."""
    tracks = select_tracks(JOB_ID, _decoy_disc(), _preset(TrackSelection.ALL_TRACKS))
    assert len(tracks) == 97
    assert all(t.expected_duration_seconds >= ALL_TRACKS_MIN_SECONDS for t in tracks)


def test_archive_queues_all_99_titles_today():
    tracks = select_tracks(JOB_ID, _decoy_disc(), _preset(TrackSelection.ARCHIVE))
    assert [t.index for t in tracks] == list(range(99))


def test_custom_duration_window_cannot_separate_the_feature_from_decoys():
    """A tight duration window around the feature still lets the decoys in:
    length alone does not identify the real title."""
    filters = {"min_duration_seconds": FEATURE_SECONDS - 10, "max_duration_seconds": FEATURE_SECONDS + 10}
    tracks = select_tracks(JOB_ID, _decoy_disc(), _preset(TrackSelection.CUSTOM, filters))
    assert len(tracks) == 93


def test_custom_index_allowlist_is_the_manual_escape_hatch():
    """Knowing the real title number (e.g. from MakeMKV's GUI or a forum),
    a CUSTOM allowlist rips exactly that title."""
    filters = {"title_indices": [FEATURE_INDEX]}
    tracks = select_tracks(JOB_ID, _decoy_disc(), _preset(TrackSelection.CUSTOM, filters))
    assert [t.index for t in tracks] == [FEATURE_INDEX]


def test_review_persists_all_99_with_one_decoy_kept_today():
    """The review gate stores every title (99 rows for the review card) and
    pre-selects only MAIN_FEATURE's pick, which is a decoy."""
    tracks = select_tracks_for_review(JOB_ID, _decoy_disc(), _preset(TrackSelection.MAIN_FEATURE))
    assert [t.index for t in tracks] == list(range(99))
    kept = [t.index for t in tracks if not t.excluded]
    assert len(kept) == 1
    assert kept != [FEATURE_INDEX]


# --- what we want -----------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="no decoy-playlist handling yet: MAIN_FEATURE picks the longest decoy")
def test_main_feature_does_not_pick_a_decoy():
    tracks = select_tracks(JOB_ID, _decoy_disc(), _preset(TrackSelection.MAIN_FEATURE))
    assert [t.index for t in tracks] == [FEATURE_INDEX]


@pytest.mark.xfail(strict=True, reason="no decoy-playlist handling yet: ALL_TRACKS queues every decoy")
def test_all_tracks_does_not_queue_the_decoys():
    tracks = select_tracks(JOB_ID, _decoy_disc(), _preset(TrackSelection.ALL_TRACKS))
    near = [t for t in tracks if abs((t.expected_duration_seconds or 0) - FEATURE_SECONDS) <= 5]
    assert len(near) <= 1
