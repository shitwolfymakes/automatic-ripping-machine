"""Track-selection rule unit tests."""

import json
from pathlib import Path

import pytest

from arm_backend.track_selection import (
    _clip_seconds,
    ALL_TRACKS_MIN_SECONDS,
    select_tracks,
    select_tracks_for_review,
)
from arm_common.title_classes import MAIN_FEATURE_MIN_SECONDS, TitleClass
from arm_common import (
    DiscType,
    IdentificationMode,
    MediaType,
    OutputMode,
    RipPreset,
    TrackKind,
    TrackSelection,
)
from arm_common.schemas import BdPlaylist, ScanResult, ScanTitle


def _preset(rule: TrackSelection) -> RipPreset:
    return RipPreset(
        id="rpr_test",
        name="test",
        media_type=MediaType.MOVIE,
        is_builtin=False,
        track_selection=rule,
        identification_mode=IdentificationMode.REQUIRED,
        output_mode=OutputMode.TRACKS,
    )


def _scan(*durations: int) -> ScanResult:
    return ScanResult(
        disc_type=DiscType.DVD,
        titles=[ScanTitle(index=i, duration_seconds=d) for i, d in enumerate(durations)],
    )


def test_archive_returns_every_title():
    scan = _scan(120, 90 * 60, 30, 60 * 60)
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ARCHIVE))
    assert [t.index for t in tracks] == [0, 1, 2, 3]
    assert all(t.kind == TrackKind.VIDEO_TITLE for t in tracks)


def test_all_tracks_filters_below_minimum():
    short = ALL_TRACKS_MIN_SECONDS - 1
    scan = _scan(short, ALL_TRACKS_MIN_SECONDS, 5 * 60, short)
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ALL_TRACKS))
    assert [t.index for t in tracks] == [1, 2]


def test_main_feature_returns_longest_above_threshold():
    scan = _scan(60 * 30, 90 * 60, 60 * 60, 45 * 60)
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.MAIN_FEATURE))
    assert len(tracks) == 1
    assert tracks[0].index == 1
    assert tracks[0].expected_duration_seconds == 90 * 60


def test_main_feature_falls_back_to_longest_when_no_threshold_match():
    short = MAIN_FEATURE_MIN_SECONDS - 1
    scan = _scan(short, short - 100, short - 50)
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.MAIN_FEATURE))
    assert len(tracks) == 1
    assert tracks[0].index == 0  # longest of the shorts
    assert tracks[0].expected_duration_seconds == short


def test_custom_without_filters_raises():
    from arm_backend.track_selection import TrackSelectionError

    with pytest.raises(TrackSelectionError):
        select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", _scan(60), _preset(TrackSelection.CUSTOM))


def test_empty_scan_returns_empty():
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", _scan(), _preset(TrackSelection.ARCHIVE))
    assert tracks == []


def test_data_disc_emits_single_dump():
    scan = ScanResult(disc_type=DiscType.DATA, volume_label="DATA_DISC")
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ALL_TRACKS))
    assert len(tracks) == 1
    assert tracks[0].kind == TrackKind.DATA_DUMP
    assert tracks[0].source_ref == "full"


def test_cd_emits_audio_tracks():
    scan = ScanResult(
        disc_type=DiscType.CD,
        titles=[ScanTitle(index=i, duration_seconds=180) for i in range(1, 4)],
    )
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ALL_TRACKS))
    assert [t.kind for t in tracks] == [TrackKind.AUDIO_TRACK] * 3
    assert [t.index for t in tracks] == [1, 2, 3]


# --- select_tracks_for_review (timed review gate: persist ALL, default excluded) ---


def test_review_persists_all_titles_with_main_feature_defaults():
    """MAIN_FEATURE keeps only the longest title; review persists ALL of them,
    marking the non-kept ones excluded by default."""
    scan = _scan(120, 90 * 60, 30, 60 * 60)  # indices 0..3; longest = index 1
    tracks = select_tracks_for_review("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.MAIN_FEATURE))
    assert [t.index for t in tracks] == [0, 1, 2, 3]  # every title persisted
    kept = {t.index for t in tracks if not t.excluded}
    assert kept == {1}  # only the longest is kept by default
    assert all(t.excluded for t in tracks if t.index != 1)


def test_review_archive_keeps_all_unexcluded():
    """ARCHIVE keeps every title -> none excluded by default."""
    scan = _scan(120, 5400, 30)
    tracks = select_tracks_for_review("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ARCHIVE))
    assert len(tracks) == 3
    assert all(not t.excluded for t in tracks)


def test_review_all_tracks_excludes_below_minlength():
    """ALL_TRACKS drops titles under the min-length -> those persist excluded."""
    short = ALL_TRACKS_MIN_SECONDS - 1
    scan = _scan(short, 3600, short)
    tracks = select_tracks_for_review("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ALL_TRACKS))
    assert len(tracks) == 3  # all persisted
    kept = {t.index for t in tracks if not t.excluded}
    assert kept == {1}  # only the above-threshold one kept by default


def test_review_data_disc_delegates_to_single_dump():
    scan = ScanResult(disc_type=DiscType.DATA, volume_label="DATA_DISC")
    tracks = select_tracks_for_review("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ALL_TRACKS))
    assert len(tracks) == 1
    assert tracks[0].kind == TrackKind.DATA_DUMP


# --- ISO output mode: a full-disc dump whatever the disc holds ---


def _iso_preset() -> RipPreset:
    return RipPreset(
        id="rpr_builtin_iso_dump",
        name="ISO: Full-disc dump",
        media_type=MediaType.ISO,
        is_builtin=True,
        track_selection=TrackSelection.ALL_TRACKS,
        identification_mode=IdentificationMode.SKIP,
        output_mode=OutputMode.ISO,
    )


@pytest.mark.parametrize("disc_type", [DiscType.BLURAY, DiscType.DVD])
def test_iso_preset_dumps_a_video_disc_that_has_titles(disc_type: DiscType):
    """The ISO preset copies the disc whole. Titles in the scan must not turn
    it into a MakeMKV rip of those titles."""
    scan = ScanResult(
        disc_type=disc_type,
        titles=[ScanTitle(index=i, duration_seconds=d) for i, d in enumerate([7200, 1800, 300])],
    )
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _iso_preset())
    assert [(t.kind, t.source_ref) for t in tracks] == [(TrackKind.DATA_DUMP, "full")]


def test_iso_preset_dumps_a_video_disc_without_titles():
    scan = ScanResult(disc_type=DiscType.BLURAY)
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _iso_preset())
    assert [t.kind for t in tracks] == [TrackKind.DATA_DUMP]


def test_review_iso_preset_persists_the_single_dump():
    """The review gate shows the one dump, not every title marked excluded."""
    scan = _scan(7200, 1800)
    tracks = select_tracks_for_review("job_01JZXR7K3M5Q8N4VWA00000001", scan, _iso_preset())
    assert [(t.kind, t.excluded) for t in tracks] == [(TrackKind.DATA_DUMP, False)]


# --- FOLDER output mode: one decrypted-backup track, Blu-ray only ---


def _backup_preset() -> RipPreset:
    return RipPreset(
        id="rpr_builtin_bd_backup",
        name="Blu-ray: Decrypted backup",
        media_type=MediaType.ISO,
        is_builtin=True,
        track_selection=TrackSelection.ALL_TRACKS,
        identification_mode=IdentificationMode.SKIP,
        output_mode=OutputMode.FOLDER,
    )


def test_folder_preset_backs_up_a_bluray_with_titles():
    scan = ScanResult(
        disc_type=DiscType.BLURAY,
        titles=[ScanTitle(index=i, duration_seconds=d) for i, d in enumerate([7200, 1800])],
    )
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _backup_preset())
    assert [(t.kind, t.index, t.source_ref) for t in tracks] == [(TrackKind.DISC_BACKUP, 0, "full")]


def test_folder_preset_backs_up_a_bluray_without_titles():
    """A backup copies the disc structure; it does not need MakeMKV's title list."""
    scan = ScanResult(disc_type=DiscType.BLURAY)
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _backup_preset())
    assert [t.kind for t in tracks] == [TrackKind.DISC_BACKUP]


@pytest.mark.parametrize("disc_type", [DiscType.DVD, DiscType.DATA, DiscType.CD])
def test_folder_preset_refuses_anything_but_a_bluray(disc_type: DiscType):
    from arm_backend.track_selection import DiscBackupNeedsBluray

    scan = ScanResult(disc_type=disc_type, titles=[ScanTitle(index=1, duration_seconds=3600)])
    with pytest.raises(DiscBackupNeedsBluray, match=f"disc backup needs a Blu-ray, not disc_type={disc_type.value}"):
        select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _backup_preset())


def test_review_folder_preset_persists_the_single_backup():
    scan = ScanResult(disc_type=DiscType.BLURAY, titles=[ScanTitle(index=0, duration_seconds=7200)])
    tracks = select_tracks_for_review("job_01JZXR7K3M5Q8N4VWA00000001", scan, _backup_preset())
    assert [(t.kind, t.excluded) for t in tracks] == [(TrackKind.DISC_BACKUP, False)]


# --- Blu-ray title classification (#705) ---

_JOB = "job_01JZXR7K3M5Q8N4VWA00000001"
_DECOY_JSON = (
    Path(__file__).resolve().parents[3] / "packages/arm_common/tests/fixtures/scan_titles/bd_decoy_playlists.json"
)


def _decoy_scan(disc_type: DiscType = DiscType.BLURAY) -> ScanResult:
    titles = [ScanTitle.model_validate(t) for t in json.loads(_DECOY_JSON.read_text())]
    return ScanResult(disc_type=disc_type, titles=titles)


def _bd_title(index: int, duration: int, clips: list[int]) -> ScanTitle:
    return ScanTitle(
        index=index,
        duration_seconds=duration,
        source_file=f"{index:05d}.mpls",
        segment_map=clips,
        segment_count=len(clips),
    )


def _edition_scan() -> ScanResult:
    theatrical = list(range(1, 21))
    return ScanResult(
        disc_type=DiscType.BLURAY,
        titles=[
            _bd_title(0, 100 * 60, theatrical),
            _bd_title(1, 117 * 60, theatrical + [30, 31, 32, 33]),
            _bd_title(2, 100 * 60, theatrical[::-1]),
        ],
    )


def test_decoy_disc_main_feature_picks_real_feature_not_copy_disclaimer():
    tracks = select_tracks(_JOB, _decoy_scan(), _preset(TrackSelection.MAIN_FEATURE))
    assert [t.index for t in tracks] == [0]


def test_decoy_disc_all_tracks_drops_decoys_and_variant():
    tracks = select_tracks(_JOB, _decoy_scan(), _preset(TrackSelection.ALL_TRACKS))
    assert [t.index for t in tracks] == [0, 1, 3, 4, 5, 6, 7, 8, 9, 10]


def test_decoy_disc_archive_honours_classification():
    tracks = select_tracks(_JOB, _decoy_scan(), _preset(TrackSelection.ARCHIVE))
    assert len(tracks) == 10
    assert 2 not in {t.index for t in tracks}


def test_decoy_disc_review_persists_all_and_excludes_non_kept():
    tracks = select_tracks_for_review(_JOB, _decoy_scan(), _preset(TrackSelection.ALL_TRACKS))
    assert len(tracks) == 309
    assert sum(1 for t in tracks if t.excluded) == 299


def test_decoy_disc_as_dvd_is_unclassified():
    tracks = select_tracks(_JOB, _decoy_scan(DiscType.DVD), _preset(TrackSelection.ALL_TRACKS))
    assert len(tracks) == 309


def test_preferred_breaks_the_tie_when_no_title_has_a_comment():
    scan = _decoy_scan()
    for t in scan.titles:
        t.playlist_name = None
    tracks = select_tracks(_JOB, scan, _preset(TrackSelection.MAIN_FEATURE), preferred=frozenset({"11"}))
    assert [t.index for t in tracks] == [11]


def test_preferred_reaches_the_review_defaults():
    scan = _decoy_scan()
    for t in scan.titles:
        t.playlist_name = None
    tracks = select_tracks_for_review(_JOB, scan, _preset(TrackSelection.MAIN_FEATURE), preferred=frozenset({"11"}))
    assert {t.index for t in tracks if not t.excluded} == {11}


def test_custom_allowlist_keeps_a_decoy():
    preset = _preset(TrackSelection.CUSTOM)
    preset.track_filters_json = {"title_indices": [11]}
    tracks = select_tracks(_JOB, _decoy_scan(), preset)
    assert [t.index for t in tracks] == [11]


def test_custom_without_allowlist_filters_the_candidates():
    preset = _preset(TrackSelection.CUSTOM)
    preset.track_filters_json = {"min_duration_seconds": 3600}
    tracks = select_tracks(_JOB, _decoy_scan(), preset)
    assert [t.index for t in tracks] == [0]


def test_main_feature_ticks_every_edition():
    tracks = select_tracks(_JOB, _edition_scan(), _preset(TrackSelection.MAIN_FEATURE))
    assert [t.index for t in tracks] == [0, 1]


def test_all_tracks_ticks_every_edition_but_not_its_decoy():
    tracks = select_tracks(_JOB, _edition_scan(), _preset(TrackSelection.ALL_TRACKS))
    assert [t.index for t in tracks] == [0, 1]


def test_review_tracks_carry_scan_fields_and_verdicts():
    tracks = {t.index: t for t in select_tracks_for_review(_JOB, _decoy_scan(), _preset(TrackSelection.ALL_TRACKS))}
    feature, variant, decoy = tracks[0], tracks[2], tracks[20]
    assert (feature.source_file, feature.playlist_name) == ("00202.mpls", "FPL_MainFeature")
    assert (feature.title_class, feature.title_class_ref) == (TitleClass.PRIMARY, None)
    assert (variant.title_class, variant.title_class_ref) == (TitleClass.VARIANT, "0")
    assert (decoy.title_class, decoy.title_class_ref) == (TitleClass.DECOY, "0")


def test_selected_tracks_carry_verdicts_too():
    tracks = select_tracks(_JOB, _decoy_scan(), _preset(TrackSelection.ARCHIVE))
    assert {t.title_class for t in tracks} == {TitleClass.PRIMARY}
    assert all(t.title_class_ref is None and t.source_file for t in tracks)


def test_dvd_tracks_keep_source_file_but_have_no_verdict():
    tracks = select_tracks(_JOB, _decoy_scan(DiscType.DVD), _preset(TrackSelection.ARCHIVE))
    assert all(t.title_class is None and t.title_class_ref is None for t in tracks)
    assert tracks[0].source_file == "00202.mpls"
    assert tracks[0].playlist_name == "FPL_MainFeature"


def _playlist(name: str, clips: list[int], seconds: list[float]) -> BdPlaylist:
    return BdPlaylist(name=name, clips=clips, clip_seconds=seconds, duration_seconds=int(sum(seconds)), chapter_count=0)


def test_clip_seconds_empty_without_playlists():
    assert _clip_seconds(_edition_scan()) == {}


def test_clip_seconds_one_playlist():
    scan = _edition_scan().model_copy(update={"playlists": [_playlist("1.mpls", [1, 2], [10.0, 20.5])]})
    assert _clip_seconds(scan) == {1: 10.0, 2: 20.5}


def test_clip_seconds_first_playlist_wins_for_a_shared_clip():
    playlists = [_playlist("1.mpls", [1, 2], [10.0, 20.0]), _playlist("2.mpls", [2, 3], [99.0, 30.0])]
    scan = _edition_scan().model_copy(update={"playlists": playlists})
    assert _clip_seconds(scan) == {1: 10.0, 2: 20.0, 3: 30.0}


def test_clip_seconds_skips_a_playlist_with_mismatched_lists():
    playlists = [_playlist("1.mpls", [1, 2, 3], [10.0, 20.0]), _playlist("2.mpls", [4], [40.0])]
    scan = _edition_scan().model_copy(update={"playlists": playlists})
    assert _clip_seconds(scan) == {4: 40.0}


def _disclaimer_scan(playlists: list[BdPlaylist]) -> ScanResult:
    # Title durations say the disclaimer cut adds 500 s; clip 9 is really 60 s.
    titles = [_bd_title(0, 6000, [1, 2, 3]), _bd_title(1, 6500, [1, 2, 3, 9])]
    return ScanResult(disc_type=DiscType.BLURAY, titles=titles, playlists=playlists)


def test_clip_durations_turn_a_long_looking_cut_into_a_variant():
    preset = _preset(TrackSelection.ARCHIVE)
    without = select_tracks(_JOB, _disclaimer_scan([]), preset)
    assert {t.index: t.title_class for t in without} == {0: TitleClass.EDITION, 1: TitleClass.EDITION}
    playlist = _playlist("00001.mpls", [1, 2, 3, 9], [2000.0, 2000.0, 1940.0, 60.0])
    with_clips = select_tracks(_JOB, _disclaimer_scan([playlist]), preset)
    assert [(t.index, t.title_class) for t in with_clips] == [(0, TitleClass.PRIMARY)]
