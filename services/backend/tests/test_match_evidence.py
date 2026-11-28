from datetime import UTC, datetime

import pytest
from arm_common import DiscType
from arm_common.schemas import BdDiscMeta, ScanResult, ScanTitle

from arm_backend.metadata.match.evidence import DiscEvidence, build_evidence, evidence_from_scan

from tests.bd_structure_scans import br3d_structure_scan

NOW = datetime(2026, 11, 27, tzinfo=UTC)
BD_NAME = "Blade Runner 2049 - 3D Blu-ray™"
ISO_NAME = "Blade_Runner_2049_(2017)_[3D].iso"


def _title(index: int, minutes: float) -> ScanTitle:
    return ScanTitle(index=index, duration_seconds=round(minutes * 60))


def _build(
    *,
    bd_title: str | None = None,
    iso_name: str | None = None,
    label: str | None = None,
    titles: list[ScanTitle] | None = None,
    structured: bool = False,
    set_number: int | None = None,
    num_sets: int | None = None,
) -> DiscEvidence:
    return build_evidence(
        bd_title=bd_title,
        iso_name=iso_name,
        label=label,
        titles=titles or [],
        structured=structured,
        set_number=set_number,
        num_sets=num_sets,
        now=NOW,
    )


def _years(ev: DiscEvidence) -> list[tuple[int, float]]:
    return [(y.year, round(y.reliability, 4)) for y in ev.years]


def test_blade_runner_3d_structure_scan() -> None:
    scan = br3d_structure_scan().model_copy(update={"bd_meta": BdDiscMeta(name=BD_NAME)})
    ev = evidence_from_scan(scan, iso_name=ISO_NAME, now=NOW)
    assert [t.source for t in ev.titles] == ["bd_title", "iso_name", "label"]
    assert ev.titles[0].parsed.core == "Blade Runner 2049"
    assert set(ev.titles[0].parsed.optional) >= {"3d", "bluray", "tm"}
    assert ev.titles[1].parsed.core == "Blade Runner 2049"
    assert _years(ev) == [(2017, 0.9)]
    assert ev.runtime is not None
    assert ev.runtime.source == "structure"
    assert ev.runtime.reliability == 1.0
    assert ev.runtime.feature_minutes == (163.4,)
    assert ev.runtime.episode_minutes is None
    assert ev.p_tv == 0.15
    assert ev.kind_reasons == ("single 163-min feature",)
    assert ev.set_position == (None, None)


def test_2049_is_never_a_year_before_2027() -> None:
    ev = _build(bd_title="Blade Runner 2049", iso_name="Blade_Runner_2049_2049")
    assert ev.years == ()
    assert ev.titles[0].parsed.numbers == ("2049",)


def test_year_reliability_by_source_and_shape() -> None:
    assert _years(_build(iso_name="Movie (1999)")) == [(1999, 0.9)]
    assert _years(_build(bd_title="Movie (1999)")) == [(1999, 0.8)]
    assert _years(_build(iso_name="Movie 1999")) == [(1999, 0.5)]
    assert _years(_build(bd_title="Movie 1999")) == [(1999, 0.3)]
    assert _years(_build(label="MOVIE_1999")) == [(1999, 0.3)]
    assert _years(_build(iso_name="Movie 1999 Part Two")) == [(1999, 0.3)]


def test_same_year_from_two_sources_combines_reliabilities() -> None:
    ev = _build(bd_title="Movie (1999)", iso_name="Movie (1999)")
    assert _years(ev) == [(1999, 0.98)]
    assert ev.years[0].sources == ("bd_title", "iso_name")
    ev = _build(iso_name="Movie 1999", label="MOVIE_1999")
    assert _years(ev) == [(1999, 0.65)]


def test_different_years_stay_separate_strongest_first() -> None:
    ev = _build(iso_name="Movie (2001)", label="MOVIE_1999")
    assert _years(ev) == [(2001, 0.9), (1999, 0.3)]


def test_a_bare_year_is_marked_bare_so_a_candidate_title_can_consume_it() -> None:
    ev = _build(bd_title="Wonder Woman 1984", label="WONDER_WOMAN_1984")
    assert [(y.year, y.bare) for y in ev.years] == [(1984, True)]
    assert _build(iso_name="Movie (1999)").years[0].bare is False


def test_a_lone_bare_year_title_is_not_a_year_candidate() -> None:
    ev = _build(label="1917", titles=[_title(0, 119)])
    assert ev.years == ()
    assert ev.titles[0].parsed.required == ("1917",)


def test_empty_sources_are_skipped_and_a_label_with_no_words_gives_no_title() -> None:
    ev = _build(bd_title=" ", iso_name=None, label="___")
    assert ev.titles == ()


def test_long_volume_label_is_marked_truncated() -> None:
    label = "INDIANA_JONES_AND_THE_LAST_CRUSAD"
    assert len(label) >= 31
    ev = _build(label=label)
    assert ev.titles[0].parsed.truncated
    assert not _build(bd_title=label).titles[0].parsed.truncated
    assert not _build(label="THE_MATRIX").titles[0].parsed.truncated


def test_dvd_runtime_is_the_longest_title_at_lower_reliability() -> None:
    ev = _build(label="THE_MATRIX_NTSC", titles=[_title(0, 136), _title(1, 12), _title(2, 50)])
    assert ev.runtime is not None
    assert (ev.runtime.feature_minutes, ev.runtime.reliability, ev.runtime.source) == ((136.0,), 0.7, "titles")
    assert ev.p_tv == 0.15


def test_no_title_reaches_the_main_feature_floor() -> None:
    ev = _build(label="SHORTS", titles=[_title(0, 30), _title(1, 12)])
    assert ev.runtime is None
    assert ev.p_tv == 0.4
    assert ev.kind_reasons == ("no kind signal",)


def test_episodic_disc_has_an_episode_median_and_no_feature_runtime() -> None:
    titles = [_title(i, m) for i, m in enumerate([50, 51, 52, 51, 50])]
    ev = _build(
        label="KOLCHAK_THE_NIGHT_STALKER_DISC_1",
        iso_name="Kolchak The Night Stalker - Disc 1 of 4.iso",
        titles=titles,
    )
    assert ev.p_tv == 0.9
    assert ev.kind_reasons == ("5 episode-length titles",)
    assert ev.runtime is not None
    assert ev.runtime.feature_minutes == ()
    assert ev.runtime.episode_minutes == 51.0
    assert ev.set_position == (1, 4)
    assert {t.parsed.core for t in ev.titles} == {"Kolchak The Night Stalker", "KOLCHAK THE NIGHT STALKER"}


def test_season_marker_means_probably_tv() -> None:
    ev = _build(label="SHOW_S1D2", titles=[_title(0, 40), _title(1, 41)])
    assert (ev.p_tv, ev.kind_reasons) == (0.8, ("season marker in label",))
    assert ev.set_position == (2, None)


def test_two_disc_movie_set_is_still_a_movie() -> None:
    ev = _build(label="MOVIE_DISC_1_OF_2", titles=[_title(0, 120), _title(1, 9)])
    assert ev.p_tv == 0.15
    assert ev.set_position == (1, 2)


def test_disc_marker_alone_leans_tv() -> None:
    ev = _build(label="SHOW_DISC_1_OF_4", titles=[_title(0, 40), _title(1, 30)])
    assert (ev.p_tv, ev.kind_reasons) == (0.6, ("disc 1 of 4",))


def test_bd_set_numbers_win_and_count_as_a_disc_marker() -> None:
    ev = _build(bd_title="Show", label="SHOW_DISC_1", titles=[_title(0, 40)], set_number=2, num_sets=5)
    assert ev.set_position == (2, 5)
    assert ev.p_tv == 0.6
    assert ev.kind_reasons == ("disc 2 of 5",)
    assert _build(bd_title="Show", num_sets=3, titles=[_title(0, 40)]).kind_reasons == ("3-disc set",)


def test_a_part_marker_is_not_a_disc_marker() -> None:
    ev = _build(label="HARRY_POTTER_DEATHLY_HALLOWS_P2", titles=[_title(0, 40)])
    assert ev.set_position == (None, None)
    assert ev.p_tv == 0.4


def test_edition_hint_from_stripped_edition_words() -> None:
    assert _build(label="ALIEN_1979_DIRECTORS_CUT").edition_hint
    assert not _build(label="ALIEN").edition_hint


def test_structure_scan_keeps_every_edition_runtime() -> None:
    clip_a, clip_b = [1, 2], [1, 3]
    titles = [
        ScanTitle(index=0, duration_seconds=7200, segment_map=clip_a, source_file="00800.mpls"),
        ScanTitle(index=1, duration_seconds=7800, segment_map=clip_b, source_file="00801.mpls"),
        ScanTitle(index=2, duration_seconds=240, segment_map=[9], source_file="00900.mpls"),
    ]
    ev = _build(label="MOVIE", titles=titles, structured=True)
    assert ev.runtime is not None
    assert ev.runtime.feature_minutes == (120.0, 130.0)
    assert ev.runtime.source == "structure"


def test_a_long_extra_does_not_widen_the_feature_runtimes() -> None:
    # A 100-minute documentary extra is kept next to a 163-minute feature, but it is under 70% of the longest.
    titles = [
        ScanTitle(index=0, duration_seconds=163 * 60, segment_map=[1, 2], source_file="00800.mpls"),
        ScanTitle(index=1, duration_seconds=100 * 60, segment_map=[7], source_file="00801.mpls"),
    ]
    ev = _build(label="MOVIE", titles=titles, structured=True)
    assert ev.runtime is not None
    assert ev.runtime.feature_minutes == (163.0,)


def test_an_edition_within_seventy_percent_of_the_longest_is_still_kept() -> None:
    titles = [
        ScanTitle(index=0, duration_seconds=163 * 60, segment_map=[1, 2], source_file="00800.mpls"),
        ScanTitle(index=1, duration_seconds=120 * 60, segment_map=[1, 3], source_file="00801.mpls"),
    ]
    ev = _build(label="MOVIE", titles=titles, structured=True)
    assert ev.runtime is not None
    assert ev.runtime.feature_minutes == (120.0, 163.0)


def test_evidence_from_a_dvd_scan() -> None:
    scan = ScanResult(disc_type=DiscType.DVD, volume_label="THE_MATRIX_NTSC", titles=[_title(0, 136), _title(1, 5)])
    ev = evidence_from_scan(scan, iso_name=None, now=NOW)
    assert [t.source for t in ev.titles] == ["label"]
    assert ev.runtime is not None
    assert ev.runtime.source == "titles"


def test_build_is_deterministic() -> None:
    kwargs = {"bd_title": BD_NAME, "iso_name": ISO_NAME, "label": "BLADE_RUNNER_2049"}
    assert _build(**kwargs) == _build(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("year", [2026, 2027])
def test_next_year_is_still_a_year(year: int) -> None:
    assert _years(_build(iso_name=f"Movie {year}")) == [(year, 0.5)]


def test_a_disabled_hint_source_contributes_no_text() -> None:
    scan = br3d_structure_scan().model_copy(update={"bd_meta": BdDiscMeta(name=BD_NAME, set_number=1, num_sets=2)})
    both = evidence_from_scan(scan, iso_name=ISO_NAME, now=NOW)
    assert [t.source for t in both.titles][:2] == ["bd_title", "iso_name"]
    assert both.set_position == (1, 2)
    only_iso = evidence_from_scan(scan, iso_name=ISO_NAME, now=NOW, enabled=("iso_name",))
    assert [t.source for t in only_iso.titles] == ["iso_name"]
    nothing = evidence_from_scan(scan, iso_name=ISO_NAME, now=NOW, enabled=())
    assert nothing.titles == ()
    # A disabled BDMT name takes its disc set numbers with it.
    assert nothing.set_position == (None, None)
