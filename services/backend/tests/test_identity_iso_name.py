"""ISO file-name disc hints: title, season / disc and year from the ripped file's name."""

from datetime import datetime, timezone

import pytest
from arm_common import Drive, DriveKind, DiscType, Job, JobStatus
from arm_common.schemas import ScanResult

from arm_backend.identity.pipeline import source_name_of
from arm_backend.identity.sources.base import JobContext
from arm_backend.identity.sources.iso_name import ISO_NAME, parse_iso_name

NOW = datetime(2026, 11, 28, tzinfo=timezone.utc)


def _ctx(source_name: str | None, disc_type: DiscType = DiscType.BLURAY) -> JobContext:
    job = Job(id="job_1", drive_id="d", disc_type=disc_type, status=JobStatus.CREATED, metadata_json={})
    return JobContext(job=job, scan=ScanResult(disc_type=disc_type), now=NOW, source_name=source_name)


@pytest.mark.parametrize(
    ("name", "title", "year"),
    [
        ("Blade_Runner_2049_(2017)_[3D]", "blade runner 2049", 2017),
        ("Alien [1979]", "alien", 1979),
        ("The Matrix (1999)", "the matrix", 1999),
        ("Arrival", "arrival", None),
        # A bare year is ambiguous (a release year or part of the title): it stays in the title, never a year claim.
        ("ALIEN_1979", "alien 1979", None),
        ("WONDER_WOMAN_1984", "wonder woman 1984", None),
        ("1917", "1917", None),
        # A bracketed number past next year is not a year.
        ("Blade_Runner_(2049)", "blade runner", None),
        ("Dune (2021) [UHD]", "dune", 2021),
    ],
)
def test_parse_iso_name_title_and_year(name: str, title: str, year: int | None) -> None:
    hints, found = parse_iso_name(name, max_year=2027)
    assert (hints.title, found) == (title, year)


def test_parse_iso_name_season_and_disc() -> None:
    hints, year = parse_iso_name("West_Wing_(1999)_S3D2", max_year=2027)
    assert (hints.title, hints.season, hints.disc_number, year) == ("west wing", 3, 2, 1999)


def test_run_proposes_title_year_and_markers() -> None:
    claims = ISO_NAME.run(_ctx("Blade_Runner_2049_(2017)_[3D]"))
    assert claims.status == "ok"
    assert claims.job.model_dump(exclude_unset=True) == {"title": "blade runner 2049", "year": 2017}
    assert claims.inputs == {"source_name": "Blade_Runner_2049_(2017)_[3D]"}


def test_run_proposes_season_and_disc() -> None:
    claims = ISO_NAME.run(_ctx("LOST_S2D3"))
    assert claims.job.model_dump(exclude_unset=True) == {"season": 2, "disc_number": 3, "title": "lost"}


def test_run_drops_a_part_marker_only_title() -> None:
    claims = ISO_NAME.run(_ctx("LOTR_FELLOWSHIP_P1"))
    assert claims.job.model_dump(exclude_unset=True) == {"disc_number": 1}


def test_skips_without_a_source_name() -> None:
    assert ISO_NAME.applies_to(_ctx(None)) is not None
    assert ISO_NAME.applies_to(_ctx("")) is not None
    assert ISO_NAME.applies_to(_ctx("Arrival")) is None


def test_applies_to_dvd_too() -> None:
    assert ISO_NAME.applies_to(_ctx("Arrival", DiscType.DVD)) is None


def _drive(kind: DriveKind, source_path: str | None) -> Drive:
    return Drive(id="d", kind=kind, source_path=source_path)


@pytest.mark.parametrize(
    ("drive", "expected"),
    [
        (_drive(DriveKind.VIRTUAL, "Blade_Runner_2049_(2017)_[3D].iso"), "Blade_Runner_2049_(2017)_[3D]"),
        (_drive(DriveKind.VIRTUAL, "movies/Arrival.iso"), "Arrival"),
        (_drive(DriveKind.VIRTUAL, "Some Disc Folder"), "Some Disc Folder"),
        (_drive(DriveKind.VIRTUAL, None), None),
        (_drive(DriveKind.OPTICAL, "Arrival.iso"), None),
    ],
)
def test_source_name_of_drive(drive: Drive, expected: str | None) -> None:
    assert source_name_of(drive) == expected
