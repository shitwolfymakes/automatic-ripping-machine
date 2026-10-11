"""The episode stage: match a TV disc's titles against provider episode lists
and turn the result into identity claims (design spec 5, 6.3, 9; plan Task 7)."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from typing import Any  # noqa: E402

import pytest  # noqa: E402

from arm_common import Config, DiscType, Job, JobStatus, Track, TrackKind  # noqa: E402
from arm_common.enums import MediaType, TrackRole  # noqa: E402
from arm_common.schemas import ExternalIds  # noqa: E402

from arm_backend.identity import episode_stage  # noqa: E402
from arm_backend.identity.episode_stage import (  # noqa: E402
    StageOptions,
    compute_episode_claims,
    is_tv_candidate,
    run_episode_stage,
)
from arm_backend.identity.episodes.continuity import SiblingDisc  # noqa: E402
from arm_backend.identity.episodes.model import Episode  # noqa: E402
from arm_backend.identity.http import SourceError, SourceMiss  # noqa: E402
from arm_backend.identity.proposals import claims_of, forget_episode_show_ids, set_pin  # noqa: E402
from tests._fakes import FakeSession  # noqa: E402

CFG = Config(id=1)

# A season whose runtimes are distinct enough that a 4-title disc fits one place only.
DISTINCT = [1320, 2580, 1500, 2880, 1800, 2220, 3060, 1980, 2400, 1680]
# The disc: E3-E6 of DISTINCT.
DISC = [1500, 2880, 1800, 2220]


def _season(number: int, runtimes: list[int], *, names: dict[int, str | None] | None = None) -> list[Episode]:
    names = names or {}
    return [
        Episode(season=number, number=i, name=names.get(i, f"Name {i}"), runtime_s=rt)
        for i, rt in enumerate(runtimes, start=1)
    ]


class FakeHttp:
    def __init__(self, backing_off: bool = False) -> None:
        self._backing_off = backing_off

    def backing_off(self) -> bool:
        return self._backing_off


class FakeProvider:
    """In-memory EpisodeListProvider: canned seasons, records every call."""

    def __init__(
        self,
        source_id: str = "episodes_tmdb",
        id_field: str = "tmdb",
        *,
        seasons: dict[int, list[Episode]] | None = None,
        season_list: list[int] | None = None,
        show_id: str | None = "100",
        reason: str | None = None,
        backing_off: bool = False,
        error: Exception | None = None,
    ) -> None:
        self.source_id = source_id
        self.id_field = id_field
        self.http = FakeHttp(backing_off)
        self._seasons = seasons or {}
        self._season_list = season_list
        self._show_id = show_id
        self._reason = reason
        self.error = error
        self.resolve_error: Exception | None = None
        self.calls: list[tuple[str, Any]] = []

    def configured(self, cfg: Config) -> str | None:
        self.calls.append(("configured", None))
        return self._reason

    async def resolve_show_id(self, ids: ExternalIds) -> str | None:
        self.calls.append(("resolve_show_id", ids))
        if self.resolve_error is not None:
            raise self.resolve_error
        return self._show_id

    async def seasons(self, show_id: str) -> list[int]:
        self.calls.append(("seasons", show_id))
        return self._season_list if self._season_list is not None else sorted(self._seasons)

    async def season(self, show_id: str, number: int) -> list[Episode]:
        self.calls.append(("season", number))
        if self.error is not None:
            raise self.error
        if number not in self._seasons:
            raise SourceMiss(f"no season {number}")
        return self._seasons[number]

    def network_calls(self) -> list[str]:
        return [name for name, _ in self.calls if name != "configured"]


def _job(
    job_id: str = "job_1",
    *,
    season: int | None = 1,
    disc_number: int | None = None,
    disc_total: int | None = None,
    ids: dict[str, str] | None = None,
    title: str | None = "Show",
) -> Job:
    return Job(
        id=job_id,
        drive_id="d",
        disc_type=DiscType.DVD,
        status=JobStatus.IDENTIFIED,
        title=title,
        media_type=MediaType.TV,
        season=season,
        disc_number=disc_number,
        disc_total=disc_total,
        metadata_json={"identity": {"external_ids": ids if ids is not None else {"imdb": "tt1"}}},
    )


def _track(job_id: str, index: int, seconds: int | None, **kw: Any) -> Track:
    return Track(
        id=f"{job_id}_trk_{index}",
        job_id=job_id,
        kind=kw.pop("kind", TrackKind.VIDEO_TITLE),
        index=index,
        source_ref=str(index),
        duration_seconds=seconds,
        **kw,
    )


def _db(job: Job, lengths: list[int], *extra_jobs: Job, extra_tracks: list[Track] | None = None) -> FakeSession:
    db = FakeSession()
    db.rows["jobs"] = [job, *extra_jobs]
    db.rows["tracks"] = [_track(job.id, i, s) for i, s in enumerate(lengths)] + (extra_tracks or [])
    return db


def _tracks(db: FakeSession, job: Job) -> dict[str, Track]:
    return {t.source_ref: t for t in db.rows["tracks"] if t.job_id == job.id}


# ---------------------------------------------------------------------------
# Applying a confident match
# ---------------------------------------------------------------------------


async def test_applies_a_confident_match() -> None:
    job = _job()
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    outcomes, resolved = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    [outcome] = outcomes
    claims = outcome.claims
    assert claims.status == "ok"
    assert claims.suggestion is False
    assert claims.inputs == {
        "show_id": "100",
        "season": 1,
        "disc_number": None,
        "tolerance": 300,
        "nominal_runtimes": False,
    }
    assert {ref: (c.role, c.season, c.episode, c.episode_name) for ref, c in claims.tracks.items()} == {
        "0": (TrackRole.EPISODE, 1, 3, "Name 3"),
        "1": (TrackRole.EPISODE, 1, 4, "Name 4"),
        "2": (TrackRole.EPISODE, 1, 5, "Name 5"),
        "3": (TrackRole.EPISODE, 1, 6, "Name 6"),
    }
    assert "season" not in claims.job.model_fields_set  # season came from the job, not a scan
    assert claims.extra == {
        "coverage": 1.0,
        "ambiguous": False,
        "near_tie": False,
        "sibling_conflict": False,
        "play_all": [],
        "skipped": [],
    }
    tracks = _tracks(db, job)
    assert [tracks[r].episode_number for r in "0123"] == [3, 4, 5, 6]
    assert tracks["0"].role == TrackRole.EPISODE
    assert tracks["0"].episode_name == "Name 3"
    assert tracks["0"].identity_provenance is not None
    assert tracks["0"].identity_provenance["episode_number"] == "episodes_tmdb"
    assert resolved.track_ids == frozenset(t.id for t in tracks.values())
    assert db.flushed >= 1
    assert claims_of(job).sources["episodes_tmdb"].status == "ok"


async def test_unnamed_episode_gets_placeholder_name_c8() -> None:
    job = _job()
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT, names={3: None})})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.tracks["0"].episode_name == "Episode 3"
    assert outcome.claims.tracks["1"].episode_name == "Name 4"


async def test_extra_and_play_all_titles_get_role_extra_c5() -> None:
    job = _job()
    # 300 s trailer between episodes; the last title is a play-all of E3-E6.
    db = _db(job, [1500, 300, 2880, 1800, 2220, 8400])
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    tracks = outcome.claims.tracks
    assert tracks["1"].role == TrackRole.EXTRA
    assert tracks["5"].role == TrackRole.EXTRA
    assert tracks["1"].model_fields_set == {"role"}
    assert outcome.claims.extra["skipped"] == ["1"]
    assert outcome.claims.extra["play_all"] == ["5"]
    assert [tracks[r].episode for r in "0234"] == [3, 4, 5, 6]


async def test_anchor_counts_only_eligible_titles_c6(monkeypatch) -> None:
    job = _job(disc_number=2, disc_total=4)
    db = _db(
        job,
        DISC,
        extra_tracks=[_track(job.id, 10, 1500, excluded=True), _track(job.id, 11, 2880, excluded=True)],
    )
    seen: list[int] = []
    real = episode_stage.start_anchor

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs["n_titles"])
        return real(*args, **kwargs)

    monkeypatch.setattr(episode_stage, "start_anchor", spy)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert seen == [4]
    assert outcome.claims.inputs["disc_number"] == 2
    assert [outcome.claims.tracks[r].episode for r in "0123"] == [3, 4, 5, 6]


async def test_eligibility_rules(monkeypatch) -> None:
    job = _job()
    extra = [
        _track(job.id, 4, 3000, kind=TrackKind.AUDIO_TRACK),
        _track(job.id, 5, 5400, role=TrackRole.MAIN, identity_provenance={"role": "thediscdb"}),
        # A role this stage set on an earlier run does not make the title ineligible.
        _track(job.id, 6, 1980, role=TrackRole.EXTRA, identity_provenance={"role": "episodes_tmdb"}),
        _track(job.id, 7, 1980, role=TrackRole.EXTRA, identity_provenance={"role": "manual"}),
        _track(job.id, 8, None),
        _track(job.id, 9, None, expected_duration_seconds=2400),
    ]
    db = _db(job, DISC, extra_tracks=extra)
    seen: list[list[str]] = []
    real = episode_stage.align_runs

    def spy(titles: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append([t.ref for t in titles])
        return real(titles, *args, **kwargs)

    monkeypatch.setattr(episode_stage, "align_runs", spy)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert seen == [["0", "1", "2", "3", "6", "9"]]


# ---------------------------------------------------------------------------
# Uncertain results are suggestions (C2, C4, C1)
# ---------------------------------------------------------------------------


async def test_identical_runtimes_are_a_suggestion_and_not_applied_c2() -> None:
    job = _job()
    db = _db(job, [2580] * 4)
    provider = FakeProvider(seasons={1: _season(1, [2580] * 10)})

    [outcome], resolved = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.status == "ok"
    assert outcome.claims.suggestion is True
    assert outcome.claims.extra["ambiguous"] is True
    assert resolved.changed == 0
    assert all(t.episode_number is None and t.role is None for t in _tracks(db, job).values())


async def test_auto_apply_off_makes_every_result_a_suggestion(monkeypatch) -> None:
    monkeypatch.setattr(episode_stage, "EPISODE_AUTO_APPLY", False)
    job = _job()
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.suggestion is True


# ---------------------------------------------------------------------------
# The pin rule (Task 9 F4/F8): a pinned source's stored claims stay
# non-suggestion, and applied, across later runs -- until unpinned.
# ---------------------------------------------------------------------------


async def test_pin_rule_applies_despite_computed_suggestion(monkeypatch) -> None:
    """A pinned source whose own computed result would be a suggestion
    (EPISODE_AUTO_APPLY off) still gets applied -- the RESOLVER (Task 9 F4
    round 2) lets a pinned "ok" source's suggestion through. The STORED
    claims keep the computed `suggestion=True` unchanged (nothing rewrites
    it); only the resolver's own usable-source selection treats it as
    applicable while the pin holds."""
    monkeypatch.setattr(episode_stage, "EPISODE_AUTO_APPLY", False)
    job = _job()
    set_pin(job, "episode", "episodes_tmdb")
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    outcomes, resolved = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcomes[0].claims.suggestion is True  # the computed value
    stored = claims_of(job).sources["episodes_tmdb"]
    assert stored.status == "ok"
    assert stored.suggestion is True  # unchanged -- nothing forces it
    assert resolved.changed > 0  # yet the resolver applied it, because it's pinned
    assert all(t.episode_number is not None for t in _tracks(db, job).values())


async def test_pin_rule_noop_when_unpinned_keeps_computed_suggestion(monkeypatch) -> None:
    """Without a pin, the pin rule is a no-op: the stored `suggestion` is
    exactly what was computed, and the resolver never applies it."""
    monkeypatch.setattr(episode_stage, "EPISODE_AUTO_APPLY", False)
    job = _job()  # no pin
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    outcomes, resolved = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcomes[0].claims.suggestion is True
    assert claims_of(job).sources["episodes_tmdb"].suggestion is True
    assert resolved.changed == 0
    assert all(t.episode_number is None for t in _tracks(db, job).values())


async def test_pin_rule_keeps_prior_entry_applied_across_a_same_inputs_error(monkeypatch) -> None:
    """F8: `put_source`'s same-inputs-error "keep the last good claims"
    behavior composes with the resolver's pin rule -- the kept entry is
    still `status="ok"` and still named by the pin, so it stays applicable
    (and applied) even though its `suggestion` (forced True here via
    EPISODE_AUTO_APPLY off) was never touched."""
    monkeypatch.setattr(episode_stage, "EPISODE_AUTO_APPLY", False)
    job = _job()
    set_pin(job, "episode", "episodes_tmdb")
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]
    assert claims_of(job).sources["episodes_tmdb"].status == "ok"

    provider.error = SourceError("timeout")  # same inputs: season/show_id/tolerance unchanged
    await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    stored = claims_of(job).sources["episodes_tmdb"]
    assert stored.status == "ok"  # kept the prior good entry, not "error"
    assert stored.suggestion is True  # the computed value, unchanged
    assert stored.extra["last_error"]["detail"] == "SourceError: timeout"
    assert all(t.episode_number is not None for t in _tracks(db, job).values())  # stays applied under the pin


async def test_nominal_runtimes_are_not_applied_c4() -> None:
    # TVmaze-style: every episode listed at 60 min, real episodes run ~44 min.
    job = _job()
    db = _db(job, [2640, 2700, 2580, 2660])
    provider = FakeProvider("episodes_tvmaze", "tvmaze", seasons={1: _season(1, [3600] * 10)})

    [outcome], resolved = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.inputs["nominal_runtimes"] is True
    assert outcome.claims.suggestion is True
    assert resolved.changed == 0
    assert all(t.episode_number is None for t in _tracks(db, job).values())


async def test_slot_runtimes_that_fit_are_not_nominal() -> None:
    job = _job()
    db = _db(job, [1800, 2700, 1200, 2400])
    provider = FakeProvider(seasons={1: _season(1, [600, 1800, 2700, 1200, 2400, 3000])})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.inputs["nominal_runtimes"] is False
    assert outcome.claims.suggestion is False


async def test_sibling_held_episodes_are_never_crossed_c1(monkeypatch) -> None:
    pattern = [1320, 2580, 1500, 2880, 1800] * 3
    job = _job(disc_number=3)
    sibling = _job("job_2", disc_number=2)
    stranger = _job("job_3", disc_number=1, ids={"imdb": "tt999"})  # same title, different show
    other_season = _job("job_4", season=2, disc_number=1)
    sibling_tracks = [
        _track("job_2", 0, 2580, episode_number=6, episode_number_end=7),
        _track("job_2", 1, 1500, episode_number=8),
        _track("job_2", 2, 2880, episode_number=9),
        _track("job_2", 3, 1800, episode_number=10, season=1),
        _track("job_2", 4, 1800, episode_number=11, season=2),
        _track("job_2", 5, 1800),
        _track("job_3", 0, 1320, episode_number=11),
        _track("job_4", 0, 1320, episode_number=12),
    ]
    db = _db(job, [1320, 2580, 1500, 2880], sibling, stranger, other_season, extra_tracks=sibling_tracks)
    seen: list[list[SiblingDisc]] = []
    real = episode_stage.start_anchor

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(list(kwargs["siblings"]))
        return real(*args, **kwargs)

    monkeypatch.setattr(episode_stage, "start_anchor", spy)
    provider = FakeProvider(seasons={1: _season(1, pattern)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert seen == [[SiblingDisc(2, frozenset({6, 7, 8, 9, 10}))]]
    episodes = sorted(c.episode for c in outcome.claims.tracks.values() if c.episode is not None)
    assert not any(6 <= e <= 10 for e in episodes)
    assert outcome.claims.suggestion or all(e >= 11 for e in episodes)


async def test_sibling_in_season_by_track_season_only() -> None:
    job = _job()
    sibling = _job("job_2", season=None, disc_number=1)
    sibling_tracks = [_track("job_2", 0, 1320, episode_number=1, season=1)]
    db = _db(job, DISC, sibling, extra_tracks=sibling_tracks)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert [outcome.claims.tracks[r].episode for r in "0123"] == [3, 4, 5, 6]
    # This disc's number is unknown, so the sibling may be this very disc.
    assert outcome.claims.extra["sibling_conflict"] is True
    assert outcome.claims.suggestion is True


async def test_job_without_title_has_no_siblings() -> None:
    job = _job(title=None)
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.status == "ok"


# ---------------------------------------------------------------------------
# Provider failures (C7, spec 9)
# ---------------------------------------------------------------------------


async def test_provider_error_after_good_run_keeps_last_claims_c7() -> None:
    job = _job()
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]
    good_inputs = claims_of(job).sources["episodes_tmdb"].inputs

    provider.error = SourceError("timeout")
    [outcome], _ = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.status == "error"
    assert outcome.claims.detail == "SourceError: timeout"
    assert outcome.claims.inputs == good_inputs
    stored = claims_of(job).sources["episodes_tmdb"]
    assert stored.status == "ok"
    assert stored.tracks["0"].episode == 3
    assert stored.extra["last_error"]["detail"] == "SourceError: timeout"
    assert [_tracks(db, job)[r].episode_number for r in "0123"] == [3, 4, 5, 6]


async def test_backoff_after_good_run_keeps_applied_episodes_i2() -> None:
    """I2: a provider in backoff reports an error carrying the stored entry's
    inputs, so put_source keeps the last good claims and records last_error
    instead of a skipped entry wiping the applied episodes."""
    job = _job()
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]
    good_inputs = claims_of(job).sources["episodes_tmdb"].inputs

    provider.http = FakeHttp(backing_off=True)
    provider.calls.clear()
    [outcome], _ = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert (outcome.claims.status, outcome.claims.detail) == ("error", "backing off")
    assert outcome.claims.inputs == good_inputs
    assert provider.network_calls() == []
    stored = claims_of(job).sources["episodes_tmdb"]
    assert stored.status == "ok"
    assert stored.extra["last_error"]["detail"] == "backing off"
    assert [_tracks(db, job)[r].episode_number for r in "0123"] == [3, 4, 5, 6]


async def test_show_id_source_error_after_good_run_keeps_last_claims_m3() -> None:
    """M3: a SourceError while resolving the show id is an error, not a miss,
    so a good run's claims survive when the request is otherwise unchanged.
    No `identity` section on the job, so the show id is resolved every run."""
    job = _job()
    job.metadata_json = {}
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]
    good_inputs = claims_of(job).sources["episodes_tmdb"].inputs

    provider.resolve_error = SourceError("HTTP 503")
    [outcome], _ = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.status == "error"
    assert outcome.claims.detail == "SourceError: HTTP 503"
    assert outcome.claims.inputs == good_inputs
    stored = claims_of(job).sources["episodes_tmdb"]
    assert stored.status == "ok"
    assert stored.extra["last_error"]["detail"] == "SourceError: HTTP 503"
    assert [_tracks(db, job)[r].episode_number for r in "0123"] == [3, 4, 5, 6]


async def test_show_id_source_error_without_previous_claims_m3() -> None:
    job = _job()
    db = _db(job, DISC)
    provider = FakeProvider(show_id=None)
    provider.resolve_error = SourceError("HTTP 503")

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.status == "error"
    assert outcome.claims.inputs == {}  # R2: no known previous show id, nothing to keep


async def test_backoff_with_a_new_season_does_not_keep_the_old_season_r2() -> None:
    """R2: the backoff keep-path uses this request's season, so a `/match`
    for a different season during backoff replaces the old season's claims
    instead of keeping them."""
    job = _job()
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]
    assert _tracks(db, job)["0"].episode_number == 3

    provider.http = FakeHttp(backing_off=True)
    [outcome], _ = await run_episode_stage(db, job, [provider], CFG, StageOptions(season=2))  # type: ignore[arg-type]

    assert outcome.claims.inputs["season"] == 2
    stored = claims_of(job).sources["episodes_tmdb"]
    assert (stored.status, stored.detail) == ("error", "backing off")
    assert all(t.episode_number is None for t in _tracks(db, job).values())


@pytest.mark.parametrize("failure", ["backoff", "show_id_error"])
async def test_forgotten_show_id_keeps_nothing_r2(failure: str) -> None:
    """R2: after /resolve names a different show (`forget_episode_show_ids`),
    neither keep-path can hold the previous show's claims."""
    job = _job()
    job.metadata_json = {}  # the show id is resolved on every run
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]
    forget_episode_show_ids(job)

    if failure == "backoff":
        provider.http = FakeHttp(backing_off=True)
    else:
        provider.resolve_error = SourceError("HTTP 503")
    [outcome], _ = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.inputs == {}
    assert claims_of(job).sources["episodes_tmdb"].status == "error"
    assert all(t.episode_number is None for t in _tracks(db, job).values())


async def test_show_id_miss_is_still_a_miss_m3() -> None:
    job = _job()
    db = _db(job, DISC)
    provider = FakeProvider()
    provider.resolve_error = SourceMiss("no such show")

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert (outcome.claims.status, outcome.claims.detail) == ("miss", "show not found")


async def test_provider_error_without_previous_claims() -> None:
    job = _job()
    db = _db(job, DISC)
    provider = FakeProvider(error=SourceError("HTTP 503"))

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.status == "error"
    assert outcome.claims.inputs["nominal_runtimes"] is None
    assert outcome.claims.inputs["show_id"] == "100"


async def test_unexpected_exception_is_an_error_and_next_provider_runs(caplog) -> None:
    job = _job()
    db = _db(job, DISC)
    broken = FakeProvider(error=RuntimeError("boom"))
    good = FakeProvider("episodes_tvmaze", "tvmaze", seasons={1: _season(1, DISTINCT)})

    outcomes = await compute_episode_claims(db, job, [broken, good], CFG, StageOptions())  # type: ignore[arg-type]

    assert [o.source_id for o in outcomes] == ["episodes_tmdb", "episodes_tvmaze"]
    assert outcomes[0].claims.status == "error"
    assert outcomes[0].claims.detail == "RuntimeError: boom"
    assert outcomes[0].result is None
    assert outcomes[1].claims.status == "ok"
    assert "Traceback" in caplog.text


async def test_exception_before_show_id_has_empty_inputs() -> None:
    job = _job()
    db = _db(job, DISC)
    provider = FakeProvider()

    def boom(cfg: Config) -> str | None:
        raise ValueError("bad config")

    provider.configured = boom  # type: ignore[method-assign]

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.status == "error"
    assert outcome.claims.detail == "ValueError: bad config"
    assert outcome.claims.inputs == {}


async def test_no_eligible_titles_makes_no_provider_call_and_stores_nothing_c1() -> None:
    """C1: a job with no Track rows yet (identify without the review hold)
    returns no outcomes before any provider or network call, so nothing is
    stored and `sweep_startup` can retry the job later."""
    job = _job()
    db = _db(job, [])
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    outcomes, _ = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcomes == []
    assert provider.calls == []
    assert claims_of(job).sources == {}


async def test_no_episodes_matched_is_a_miss() -> None:
    job = _job()
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, [6010] * 10)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.status == "miss"
    assert outcome.claims.detail == "no episodes matched"
    assert outcome.claims.inputs["show_id"] == "100"
    assert outcome.result is not None


# ---------------------------------------------------------------------------
# Provider order, stop rule, skips, pin, narrowing
# ---------------------------------------------------------------------------


async def test_stop_after_confident_provider() -> None:
    job = _job()
    db = _db(job, DISC)
    first = FakeProvider(seasons={1: _season(1, DISTINCT)})
    second = FakeProvider("episodes_tvmaze", "tvmaze", seasons={1: _season(1, DISTINCT)})

    outcomes = await compute_episode_claims(db, job, [second, first], CFG, StageOptions())  # type: ignore[arg-type]

    assert [o.source_id for o in outcomes] == ["episodes_tmdb"]
    assert second.calls == []


async def test_suggestion_does_not_stop_the_next_provider() -> None:
    job = _job()
    db = _db(job, [2580] * 4)
    first = FakeProvider(seasons={1: _season(1, [2580] * 10)})
    second = FakeProvider("episodes_tvmaze", "tvmaze", seasons={1: _season(1, [2580] * 10)})

    outcomes = await compute_episode_claims(db, job, [first, second], CFG, StageOptions())  # type: ignore[arg-type]

    assert [o.source_id for o in outcomes] == ["episodes_tmdb", "episodes_tvmaze"]
    assert outcomes[0].claims.suggestion is True
    assert ("season", 1) in second.calls


async def test_skipped_reasons() -> None:
    job = _job()
    db = _db(job, DISC)
    no_key = FakeProvider(reason="no TMDb key")
    backing_off = FakeProvider("episodes_tvmaze", "tvmaze", backing_off=True)
    not_found = FakeProvider("episodes_tvdb", "tvdb", show_id=None)

    outcomes = await compute_episode_claims(
        db,  # type: ignore[arg-type]
        job,
        [no_key, backing_off, not_found],  # type: ignore[list-item]
        CFG,
        StageOptions(),
    )

    assert [(o.source_id, o.claims.status, o.claims.detail) for o in outcomes] == [
        ("episodes_tmdb", "skipped", "no TMDb key"),
        ("episodes_tvmaze", "error", "backing off"),
        ("episodes_tvdb", "miss", "show not found"),
    ]
    assert no_key.network_calls() == []
    assert backing_off.network_calls() == []
    assert [name for name, _ in not_found.calls] == ["configured", "resolve_show_id"]


async def test_unknown_season_scans_and_proposes_the_best() -> None:
    job = _job(season=None)
    db = _db(job, DISC)
    provider = FakeProvider(
        seasons={
            1: _season(1, [6010] * 10),
            2: _season(2, DISTINCT),
            3: _season(3, [1500, 2880, 6010, 6010, 6010]),
        },
        season_list=[1, 2, 3, 4],
    )

    [outcome], _ = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    claims = outcome.claims
    assert claims.job.season == 2
    assert claims.inputs["season"] is None
    assert claims.tracks["0"].season == 2
    assert claims.alternatives == [{"season": 3, "coverage": 0.5, "matches": 2}]
    assert claims.extra["near_tie"] is False
    assert ("season", 4) in provider.calls  # SourceMiss skipped that season
    assert job.season == 2
    assert _tracks(db, job)["0"].episode_number == 3


async def test_season_scan_is_capped() -> None:
    job = _job(season=None)
    db = _db(job, DISC)
    provider = FakeProvider(season_list=list(range(1, 13)))

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert [n for name, n in provider.calls if name == "season"] == list(range(1, 11))
    assert outcome.claims.status == "miss"
    assert outcome.result is None


async def test_near_tied_seasons_are_a_suggestion() -> None:
    job = _job(season=None)
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT), 2: _season(2, DISTINCT)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.extra["near_tie"] is True
    assert outcome.claims.suggestion is True
    assert outcome.claims.job.season == 1
    assert outcome.claims.alternatives == [{"season": 2, "coverage": 1.0, "matches": 4}]


async def test_options_override_job_season_and_disc() -> None:
    job = _job(season=5, disc_number=9)
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    [outcome] = await compute_episode_claims(
        db,  # type: ignore[arg-type]
        job,
        [provider],  # type: ignore[list-item]
        CFG,
        StageOptions(season=1, disc_number=1, tolerance=200),
    )

    assert outcome.claims.inputs == {
        "show_id": "100",
        "season": 1,
        "disc_number": 1,
        "tolerance": 200,
        "nominal_runtimes": False,
    }
    assert "season" not in outcome.claims.job.model_fields_set


async def test_pinned_source_reuses_its_stored_tolerance_i3() -> None:
    """I3: with default options the pinned source runs at the tolerance the
    operator's `/match` stored in its inputs; an unpinned source, or an
    explicit option, does not."""
    job = _job()
    set_pin(job, "episode", "episodes_tmdb")
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    await run_episode_stage(db, job, [provider], CFG, StageOptions(tolerance=400))  # type: ignore[arg-type]

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]
    assert outcome.claims.inputs["tolerance"] == 400

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions(tolerance=200))  # type: ignore[arg-type]
    assert outcome.claims.inputs["tolerance"] == 200

    other = FakeProvider("episodes_tvmaze", "tvmaze", seasons={1: _season(1, DISTINCT)})
    await run_episode_stage(db, job, [other], CFG, StageOptions(tolerance=400))  # type: ignore[arg-type]
    [outcome] = await compute_episode_claims(db, job, [other], CFG, StageOptions())  # type: ignore[arg-type]
    assert outcome.claims.inputs["tolerance"] == 300


async def test_pinned_source_without_a_stored_tolerance_uses_the_default() -> None:
    job = _job()
    set_pin(job, "episode", "episodes_tmdb")
    db = _db(job, DISC)
    provider = FakeProvider(show_id=None)
    await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]
    assert claims_of(job).sources["episodes_tmdb"].inputs == {}

    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]
    assert outcome.claims.inputs["tolerance"] == 300


async def test_pinned_source_is_tried_first() -> None:
    job = _job()
    job.metadata_json = {**job.metadata_json, "identity_claims": {"pin": {"episode": "episodes_tvmaze"}}}
    db = _db(job, DISC)
    tmdb = FakeProvider(seasons={1: _season(1, DISTINCT)})
    tvmaze = FakeProvider("episodes_tvmaze", "tvmaze", seasons={1: _season(1, DISTINCT)})

    outcomes = await compute_episode_claims(db, job, [tmdb, tvmaze], CFG, StageOptions())  # type: ignore[arg-type]

    assert [o.source_id for o in outcomes] == ["episodes_tvmaze"]
    assert tmdb.calls == []


async def test_unknown_pin_is_ignored() -> None:
    job = _job()
    job.metadata_json = {**job.metadata_json, "identity_claims": {"pin": {"episode": "episodes_nope"}}}
    db = _db(job, DISC)
    tmdb = FakeProvider(seasons={1: _season(1, DISTINCT)})

    outcomes = await compute_episode_claims(db, job, [tmdb], CFG, StageOptions())  # type: ignore[arg-type]

    assert [o.source_id for o in outcomes] == ["episodes_tmdb"]


async def test_only_source_narrows_and_unknown_providers_are_ignored() -> None:
    job = _job()
    db = _db(job, DISC)
    tmdb = FakeProvider()
    tvdb = FakeProvider("episodes_tvdb", "tvdb", seasons={1: _season(1, DISTINCT)})
    anidb = FakeProvider("episodes_anidb", "anidb")
    providers = [anidb, tmdb, tvdb]

    outcomes = await compute_episode_claims(
        db,  # type: ignore[arg-type]
        job,
        providers,  # type: ignore[arg-type]
        CFG,
        StageOptions(only_source="episodes_tvdb"),
    )
    assert [o.source_id for o in outcomes] == ["episodes_tvdb"]
    assert tmdb.calls == []

    none = await compute_episode_claims(
        db,  # type: ignore[arg-type]
        job,
        providers,  # type: ignore[arg-type]
        CFG,
        StageOptions(only_source="episodes_nope"),
    )
    assert none == []
    assert anidb.calls == []


async def test_preview_writes_nothing() -> None:
    job = _job(ids={"imdb": "tt1"})
    before = job.metadata_json
    db = _db(job, DISC)
    provider = FakeProvider("episodes_tvmaze", "tvmaze", show_id="77", seasons={1: _season(1, DISTINCT)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions(apply=False))  # type: ignore[arg-type]

    assert outcome.claims.status == "ok"
    assert outcome.claims.inputs["show_id"] == "77"
    assert job.metadata_json is before
    assert job.metadata_json["identity"]["external_ids"] == {"imdb": "tt1"}
    assert db.added == []
    assert db.flushed == 0
    assert all(t.episode_number is None for t in _tracks(db, job).values())


async def test_applied_run_caches_the_resolved_show_id() -> None:
    job = _job(ids={"imdb": "tt1"})
    db = _db(job, DISC)
    provider = FakeProvider("episodes_tvmaze", "tvmaze", show_id="77", seasons={1: _season(1, DISTINCT)})

    await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert job.metadata_json["identity"]["external_ids"] == {"imdb": "tt1", "tvmaze": "77"}


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_is_tv_candidate() -> None:
    movie = _job()
    movie.media_type = MediaType.MOVIE
    plain = _track(movie.id, 0, 5400)
    episode = _track(movie.id, 1, 2600, role=TrackRole.EPISODE)

    assert is_tv_candidate(_job(), []) is True
    assert is_tv_candidate(movie, [plain]) is False
    assert is_tv_candidate(movie, [plain, episode]) is True


# ---------------------------------------------------------------------------
# Fix round 1
# ---------------------------------------------------------------------------

# Realistic 44-minute episodes, close enough together that a shifted mapping still fits.
REALISTIC = [2640, 2610, 2700, 2580, 2655, 2620, 2690, 2600, 2670, 2630]


def _scan_provider() -> FakeProvider:
    return FakeProvider(seasons={1: _season(1, [6010] * 10), 2: _season(2, DISTINCT)})


async def test_scan_picked_season_is_stable_across_runs_f1() -> None:
    job = _job(season=None)
    db = _db(job, DISC)
    provider = _scan_provider()

    await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]
    assert job.season == 2
    assert job.identity_provenance == {"season": "episodes_tmdb"}

    [outcome], resolved = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.inputs["season"] is None
    assert outcome.claims.job.season == 2
    assert resolved.changed == 0
    assert job.season == 2
    assert job.identity_provenance == {"season": "episodes_tmdb"}
    assert [_tracks(db, job)[r].episode_number for r in "0123"] == [3, 4, 5, 6]


async def test_scan_picked_season_survives_an_error_rerun_f1() -> None:
    job = _job(season=None)
    db = _db(job, DISC)
    provider = _scan_provider()
    await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]
    await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    provider.error = SourceError("timeout")
    [outcome], _ = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.status == "error"
    stored = claims_of(job).sources["episodes_tmdb"]
    assert stored.status == "ok"
    assert stored.job.season == 2
    assert stored.extra["last_error"]["detail"] == "SourceError: timeout"
    assert job.season == 2
    assert [_tracks(db, job)[r].episode_number for r in "0123"] == [3, 4, 5, 6]


async def test_operator_season_is_not_rescanned_f1() -> None:
    job = _job(season=1)
    job.identity_provenance = {"season": "manual"}
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.inputs["season"] == 1
    assert "season" not in outcome.claims.job.model_fields_set
    assert ("seasons", "100") not in provider.calls


async def test_rerip_of_the_same_disc_is_a_suggestion_f2() -> None:
    earlier = _job("job_0", disc_number=1)
    job = _job(disc_number=1)
    earlier_tracks = [_track("job_0", i, rt, episode_number=i + 1) for i, rt in enumerate(REALISTIC[:4])]
    db = _db(job, REALISTIC[:4], earlier, extra_tracks=earlier_tracks)
    provider = FakeProvider(seasons={1: _season(1, REALISTIC)})

    [outcome], resolved = await run_episode_stage(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.suggestion is True
    assert outcome.claims.extra["sibling_conflict"] is True
    assert resolved.changed == 0
    assert all(t.episode_number is None for t in _tracks(db, job).values())


async def test_sibling_with_unknown_disc_number_forces_a_suggestion_f2(monkeypatch) -> None:
    sibling = _job("job_2", disc_number=None)
    job = _job(disc_number=2)
    db = _db(job, DISC, sibling, extra_tracks=[_track("job_2", 0, 1320, episode_number=1)])
    seen: list[list[SiblingDisc]] = []
    real = episode_stage.start_anchor

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(list(kwargs["siblings"]))
        return real(*args, **kwargs)

    monkeypatch.setattr(episode_stage, "start_anchor", spy)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert seen == [[]]  # an unknown disc number claims nothing
    assert outcome.claims.extra["sibling_conflict"] is True
    assert outcome.claims.suggestion is True


@pytest.mark.parametrize("status", [JobStatus.FAILED, JobStatus.ABANDONED])
async def test_failed_or_abandoned_sibling_is_ignored_f2(monkeypatch, status: JobStatus) -> None:
    sibling = _job("job_2", disc_number=1)
    sibling.status = status
    job = _job(disc_number=2)
    db = _db(job, DISC, sibling, extra_tracks=[_track("job_2", 0, 1320, episode_number=1)])
    seen: list[list[SiblingDisc]] = []
    real = episode_stage.start_anchor

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(list(kwargs["siblings"]))
        return real(*args, **kwargs)

    monkeypatch.setattr(episode_stage, "start_anchor", spy)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert seen == [[]]
    assert outcome.claims.extra["sibling_conflict"] is False
    assert outcome.claims.suggestion is False


async def test_seasons_miss_is_show_not_found_f3() -> None:
    job = _job(season=None)
    db = _db(job, DISC)
    provider = FakeProvider()

    async def gone(show_id: str) -> list[int]:
        raise SourceMiss("show 100 not found")

    provider.seasons = gone  # type: ignore[method-assign]

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.status == "miss"
    assert outcome.claims.detail == "show not found"
    assert outcome.result is None


def _tie_season(number: int, first_runtime: int) -> list[Episode]:
    # DISC fits E1-E4 exactly except E1, whose delta sets the mean cost.
    return _season(number, [first_runtime, 2880, 1800, 2220, 6010, 6010])


async def test_near_tie_ratio_about_five_percent_is_a_tie_f5() -> None:
    job = _job(season=None)
    db = _db(job, DISC)
    # Mean costs 100/4 = 25 vs 105/4 = 26.25: 4.8% apart.
    provider = FakeProvider(seasons={1: _tie_season(1, 1600), 2: _tie_season(2, 1605)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.job.season == 1
    assert outcome.claims.extra["near_tie"] is True
    assert outcome.claims.suggestion is True


async def test_near_tie_ratio_about_twenty_percent_is_not_a_tie_but_a_thin_win_i5() -> None:
    """Not a near tie (20% apart), but the runner-up is only 6.25 s worse on
    mean cost, under the 30 s floor (I5): a thin scan win is a suggestion."""
    job = _job(season=None)
    db = _db(job, DISC)
    # Mean costs 100/4 = 25 vs 125/4 = 31.25: 20% apart.
    provider = FakeProvider(seasons={1: _tie_season(1, 1600), 2: _tie_season(2, 1625)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.job.season == 1
    assert outcome.claims.extra["near_tie"] is False
    assert outcome.claims.extra["thin_win"] is True
    assert outcome.claims.suggestion is True
    assert outcome.claims.alternatives == [{"season": 2, "coverage": 1.0, "matches": 4}]


async def test_clear_scan_win_applies_i5() -> None:
    job = _job(season=None)
    db = _db(job, DISC)
    # Mean costs 100/4 = 25 vs 250/4 = 62.5: 37.5 s apart, over both floors.
    provider = FakeProvider(seasons={1: _tie_season(1, 1600), 2: _tie_season(2, 1750)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.job.season == 1
    assert "thin_win" not in outcome.claims.extra
    assert outcome.claims.suggestion is False


async def test_known_season_is_never_a_thin_win_i5() -> None:
    job = _job(season=1)
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _tie_season(1, 1600), 2: _tie_season(2, 1625)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.suggestion is False


async def test_truncated_season_scan_is_a_suggestion_i5() -> None:
    """More seasons than MAX_SEASON_SCAN: the best of the scanned ones may
    not be the true best, so the win is a suggestion (I5)."""
    job = _job(season=None)
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)}, season_list=list(range(1, 12)))

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.job.season == 1
    assert outcome.claims.extra["scan_truncated"] is True
    assert outcome.claims.suggestion is True


async def test_sibling_holding_no_episodes_is_no_conflict_f2() -> None:
    sibling = _job("job_2", disc_number=None)
    job = _job(disc_number=None)
    db = _db(job, DISC, sibling, extra_tracks=[_track("job_2", 0, 1320)])
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})

    [outcome] = await compute_episode_claims(db, job, [provider], CFG, StageOptions())  # type: ignore[arg-type]

    assert outcome.claims.extra["sibling_conflict"] is False
    assert outcome.claims.suggestion is False
