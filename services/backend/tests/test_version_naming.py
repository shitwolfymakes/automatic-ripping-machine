"""`{edition?}` / `{plex_edition?}`: the names of the versions of one film a job keeps."""

from __future__ import annotations

import asyncio
import secrets
from pathlib import PurePosixPath

import pytest
from fastapi.testclient import TestClient

from arm_backend.identity.pipeline import resolve_job
from arm_backend.path_template import TemplateValidationError, expand_template, validate_template
from arm_backend.seeders import SESSIONS
from arm_backend.title_map_service import job_stereo_3d_refs
from arm_backend.transcode_apply import compute_outputs
from arm_backend.version_naming import plex_edition, version_names
from arm_common import (
    ContainerFormat,
    DiscType,
    Job,
    JobStatus,
    MediaType,
    Session,
    Track,
    TrackKind,
    TranscodePreset,
    TranscodeTool,
)
from arm_common.enums import TitleClass
from tests._fakes import FakeSession
from tests.test_naming_router import _auth, _make_app, _seed


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


_TEMPLATE = "{title} ({year?})/{title} ({year?}) {plex_edition?} - Track {track} - {transcode_slug}.{ext}"
_EDITION_TEMPLATE = "{title} ({year?}) - {edition?} - Track {track}.{ext}"


def _track(
    index: int,
    ref: str,
    cls: TitleClass | None = TitleClass.PRIMARY,
    of: str | None = None,
    *,
    excluded: bool = False,
    edition: str | None = None,
) -> Track:
    return Track(
        id=f"trk_{index:026d}",
        job_id="job_00000000000000000000000001",
        kind=TrackKind.VIDEO_TITLE,
        index=index,
        source_ref=ref,
        title_class=cls,
        title_class_ref=of,
        excluded=excluded,
        edition=edition,
    )


def _job() -> Job:
    return Job(
        id="job_00000000000000000000000001",
        drive_id="drv_x",
        disc_type=DiscType.BLURAY,
        status=JobStatus.RIPPED,
        title="Blade Runner",
        year=1982,
        metadata_json={},
    )


def _session(template: str = _TEMPLATE) -> Session:
    return Session(
        id="ses_x",
        name="s",
        media_type=MediaType.MOVIE,
        rip_preset_id="rpr_x",
        transcode_preset_id="tpr_x",
        output_path_template=template,
    )


_PRESET = TranscodePreset(
    id="tpr_x",
    name="Plex 1080p H.265",
    media_type=MediaType.MOVIE,
    tool=TranscodeTool.HANDBRAKE,
    container=ContainerFormat.MKV,
    encoder="preset",
)


def _names(tracks: list[Track], stereo: tuple[str, ...] = ()) -> dict[int, str]:
    by_id = {t.id: t.index for t in tracks}
    return {by_id[k]: v for k, v in version_names(tracks, stereo).items()}


def _paths(tracks: list[Track], template: str = _TEMPLATE, stereo: tuple[str, ...] = ()) -> list[str]:
    return [r.output_path for r in compute_outputs(_job(), tracks, _session(template), _PRESET, stereo)]


def test_one_version_kept_has_no_edition_text() -> None:
    tracks = [
        _track(0, "00800.mpls"),
        _track(1, "00801.mpls", TitleClass.VIEW, "00800.mpls", excluded=True),
    ]
    assert version_names(tracks, ("00800.mpls",)) == {}
    (path,) = _paths(tracks)
    assert path == "Blade Runner (1982)/Blade Runner (1982) - Track 01 - plex-1080p-h-265.mkv"


def test_a_film_with_no_version_set_has_no_edition_text() -> None:
    assert version_names([_track(0, "1")]) == {}


def test_3d_and_2d_kept_get_distinct_names() -> None:
    tracks = [_track(0, "00800.mpls"), _track(1, "00801.mpls", TitleClass.VIEW, "00800.mpls")]
    assert _names(tracks, ("00800.mpls",)) == {0: "3D", 1: "2D"}
    paths = _paths(tracks, stereo=("00800.mpls",))
    assert paths == [
        "Blade Runner (1982)/Blade Runner (1982) {edition-3D} - Track 01 - plex-1080p-h-265.mkv",
        "Blade Runner (1982)/Blade Runner (1982) {edition-2D} - Track 02 - plex-1080p-h-265.mkv",
    ]


def test_3d_pick_when_the_alternate_is_the_3d_twin() -> None:
    tracks = [_track(0, "00800.mpls"), _track(1, "00801.mpls", TitleClass.VIEW, "00800.mpls")]
    assert _names(tracks, ("00801.mpls",)) == {0: "2D", 1: "3D"}


def test_two_angles_kept_are_angle_1_and_angle_2() -> None:
    tracks = [_track(0, "00800.mpls"), _track(1, "00800.mpls:2", TitleClass.ANGLE, "00800.mpls")]
    assert _names(tracks) == {0: "Angle 1", 1: "Angle 2"}
    assert _paths(tracks, _EDITION_TEMPLATE) == [
        "Blade Runner (1982) - Angle 1 - Track 01.mkv",
        "Blade Runner (1982) - Angle 2 - Track 02.mkv",
    ]


def test_angle_not_kept_leaves_the_other_unnamed() -> None:
    tracks = [_track(0, "00800.mpls"), _track(1, "00800.mpls:2", TitleClass.ANGLE, "00800.mpls", excluded=True)]
    assert version_names(tracks) == {}


def test_named_edition_wins_over_the_generated_name() -> None:
    tracks = [
        _track(0, "00800.mpls", TitleClass.EDITION, edition="Theatrical"),
        _track(1, "00801.mpls", TitleClass.EDITION, edition="Director's Cut"),
    ]
    assert _names(tracks) == {0: "Theatrical", 1: "Director's Cut"}
    assert _paths(tracks)[1] == (
        "Blade Runner (1982)/Blade Runner (1982) {edition-Director's Cut} - Track 02 - plex-1080p-h-265.mkv"
    )


def test_shorter_cut_and_unnamed_editions() -> None:
    tracks = [_track(0, "a.mpls"), _track(1, "b.mpls", TitleClass.SUBSET, "a.mpls")]
    assert _names(tracks) == {0: "Main", 1: "Shorter Cut"}
    editions = [_track(0, "a.mpls", TitleClass.EDITION), _track(1, "b.mpls", TitleClass.EDITION)]
    assert _names(editions) == {0: "Edition 0", 1: "Edition 1"}


def test_view_and_angle_axes_combine() -> None:
    tracks = [
        _track(0, "a.mpls"),
        _track(1, "a.mpls:2", TitleClass.ANGLE, "a.mpls"),
        _track(2, "b.mpls", TitleClass.VIEW, "a.mpls"),
    ]
    assert _names(tracks, ("a.mpls", "a.mpls:2")) == {0: "3D Angle 1", 1: "3D Angle 2", 2: "2D Angle 1"}


def test_name_is_safe_in_a_path() -> None:
    tracks = [
        _track(0, "a.mpls", TitleClass.EDITION, edition="Final/Cut {x}"),
        _track(1, "b.mpls", TitleClass.EDITION, edition="Other"),
    ]
    assert _names(tracks)[0] == "Final - Cut x"


def test_plex_edition_form() -> None:
    assert plex_edition("Director's Cut") == "{edition-Director's Cut}"
    assert plex_edition("") == ""


def test_plain_edition_token_renders_the_name_only() -> None:
    assert expand_template("{title} {edition?}", {"title": "X", "edition": "3D"}) == "X 3D"
    assert expand_template("{title} {edition?}", {"title": "X", "edition": ""}) == "X"


def test_tokens_validate_for_movies_only() -> None:
    assert "{edition-Director's Cut}" in validate_template(_TEMPLATE, MediaType.MOVIE, True)
    with pytest.raises(TemplateValidationError):
        validate_template("{show} {plex_edition?} {track}.{ext}", MediaType.TV, True)


def test_built_in_movie_templates_carry_plex_edition() -> None:
    movie = [s for s in SESSIONS if s["media_type"] == MediaType.MOVIE]
    assert movie
    assert all("{plex_edition?}" in s["output_path_template"] for s in movie)


def test_job_without_a_scan_has_no_3d_refs() -> None:
    assert job_stereo_3d_refs(_job()) == frozenset()


def test_preview_and_apply_agree(signing_key: bytes) -> None:
    tracks = [_track(0, "00800.mpls"), _track(1, "00800.mpls:2", TitleClass.ANGLE, "00800.mpls")]
    job = _job()
    job.pending_session_id = "ses_x"
    session = _session()
    session.transcode_preset_id = None
    session.output_path_template = "{title}/{title} {plex_edition?} - Track {track}.mkv"
    db = FakeSession()
    _seed(db)
    db.rows["sessions"] = [session]
    db.rows["jobs"] = [job]
    db.rows["tracks"] = tracks
    db.rows["transcode_presets"] = []
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/jobs/job_00000000000000000000000001/naming-preview", headers=_auth(token))
    assert r.status_code == 200, r.text
    preview = [i["output_path"] for i in r.json()["items"]]
    applied = [x.output_path for x in compute_outputs(job, tracks, session, None, job_stereo_3d_refs(job))]
    assert preview == applied
    assert PurePosixPath(preview[1]).name == "Blade Runner {edition-Angle 2} - Track 02.mkv"


def test_an_edited_edition_reaches_apply_and_preview(signing_key: bytes) -> None:
    from arm_backend.identity.manual_edits import _apply_track_edit
    from arm_common.schemas import TrackEditRequest

    tracks = [_track(0, "00800.mpls"), _track(1, "00800.mpls:2", TitleClass.ANGLE, "00800.mpls")]
    job = _job()
    job.pending_session_id = "ses_x"
    session = _session()
    session.transcode_preset_id = None
    session.output_path_template = "{title}/{title} {plex_edition?} - {edition?} - Track {track}.mkv"
    db = FakeSession()
    _seed(db)
    db.rows["sessions"] = [session]
    db.rows["jobs"] = [job]
    db.rows["tracks"] = tracks
    db.rows["transcode_presets"] = []
    # The edition is a manual identity proposal: the PATCH route resolves the job after recording it.
    _apply_track_edit(job, tracks[1], TrackEditRequest(track_id=tracks[1].id, edition="Director's Cut"))
    asyncio.run(resolve_job(db, job))
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{job.id}/naming-preview", headers=_auth(token))
    preview = [i["output_path"] for i in r.json()["items"]]
    applied = [x.output_path for x in compute_outputs(job, tracks, session, None)]
    assert preview == applied
    assert applied[1] == "Blade Runner/Blade Runner {edition-Director's Cut} - Director's Cut - Track 02.mkv"
    _apply_track_edit(job, tracks[1], TrackEditRequest(track_id=tracks[1].id, revert_fields=["edition"]))
    asyncio.run(resolve_job(db, job))
    assert compute_outputs(job, tracks, session, None)[1].output_path.endswith(
        "{edition-Angle 2} - Angle 2 - Track 02.mkv"
    )
