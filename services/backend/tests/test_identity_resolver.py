"""Resolver: tier > pin > rank; presence semantics; provenance; resets."""

from arm_common import DiscType, Job, JobStatus, Track, TrackKind
from arm_common.enums import TrackRole
from arm_common.schemas.identity import IdentityClaims, JobClaim, SourceClaims, TrackClaim

from arm_backend.identity.resolver import Winner, apply_resolution, resolve

TIERS = {"manual": 1, "thediscdb": 2, "ep_a": 3, "ep_b": 3, "preset": 5}


def _claims(**sources: SourceClaims) -> IdentityClaims:
    return IdentityClaims(sources=sources)


def _job() -> Job:
    return Job(id="job_1", drive_id="d", disc_type=DiscType.BLURAY, status=JobStatus.IDENTIFIED, metadata_json={})


def _track(ref: str = "1", **kw) -> Track:
    return Track(id=f"trk_{ref}", job_id="job_1", kind=TrackKind.VIDEO_TITLE, index=int(ref), source_ref=ref, **kw)


def test_higher_tier_wins() -> None:
    res = resolve(
        _claims(
            thediscdb=SourceClaims(tracks={"1": TrackClaim(episode=2)}),
            ep_a=SourceClaims(tracks={"1": TrackClaim(episode=9)}),
        ),
        tiers=TIERS,
    )
    assert res.tracks["1"]["episode"] == Winner(2, "thediscdb")


def test_rank_breaks_ties_within_tier_and_pin_beats_rank() -> None:
    both = dict(
        ep_a=SourceClaims(tracks={"1": TrackClaim(episode=1)}),
        ep_b=SourceClaims(tracks={"1": TrackClaim(episode=2)}),
    )
    ranked = resolve(_claims(**both), tiers=TIERS, ranks={"ep_b": 0, "ep_a": 1})
    assert ranked.tracks["1"]["episode"].source == "ep_b"
    pinned = resolve(IdentityClaims(sources=both, pin={"episode": "ep_a"}), tiers=TIERS, ranks={"ep_b": 0, "ep_a": 1})
    assert pinned.tracks["1"]["episode"].source == "ep_a"


def test_unranked_sorts_after_ranked_then_by_id() -> None:
    both = dict(
        ep_b=SourceClaims(tracks={"1": TrackClaim(episode=2)}),
        ep_a=SourceClaims(tracks={"1": TrackClaim(episode=1)}),
    )
    assert resolve(_claims(**both), tiers=TIERS).tracks["1"]["episode"].source == "ep_a"
    assert resolve(_claims(**both), tiers=TIERS, ranks={"ep_b": 0}).tracks["1"]["episode"].source == "ep_b"


def test_manual_null_wins_and_absent_is_no_opinion() -> None:
    res = resolve(
        _claims(
            manual=SourceClaims(tracks={"1": TrackClaim(title=None)}),
            thediscdb=SourceClaims(tracks={"1": TrackClaim(title="Pilot", episode=1)}),
        ),
        tiers=TIERS,
    )
    assert res.tracks["1"]["title"] == Winner(None, "manual")
    assert res.tracks["1"]["episode"] == Winner(1, "thediscdb")


def test_non_ok_and_unknown_sources_are_ignored() -> None:
    res = resolve(
        _claims(
            thediscdb=SourceClaims(status="error", tracks={"1": TrackClaim(episode=2)}),
            mystery=SourceClaims(tracks={"1": TrackClaim(episode=7)}),
        ),
        tiers=TIERS,
    )
    assert res.tracks == {}


def test_job_fields_resolve() -> None:
    res = resolve(
        _claims(
            manual=SourceClaims(job=JobClaim(season=3)), thediscdb=SourceClaims(job=JobClaim(season=1, disc_total=4))
        ),
        tiers=TIERS,
    )
    assert res.job == {"season": Winner(3, "manual"), "disc_total": Winner(4, "thediscdb")}


def test_apply_sets_values_and_provenance() -> None:
    job, track = _job(), _track()
    res = resolve(
        _claims(thediscdb=SourceClaims(tracks={"1": TrackClaim(role=TrackRole.EPISODE, episode=1, selected=True)})),
        tiers=TIERS,
    )
    changed = apply_resolution(job, [track], res)
    assert (track.role, track.episode_number, track.excluded) == (TrackRole.EPISODE, 1, False)
    assert track.identity_provenance == {"role": "thediscdb", "episode_number": "thediscdb", "excluded": "thediscdb"}
    assert changed == 2  # role and episode_number changed; excluded was already False


def test_apply_selected_false_excludes() -> None:
    track = _track()
    apply_resolution(
        _job(), [track], resolve(_claims(preset=SourceClaims(tracks={"1": TrackClaim(selected=False)})), tiers=TIERS)
    )
    assert track.excluded is True


def test_apply_resets_owned_field_when_no_winner() -> None:
    track = _track(episode_number=4, identity_provenance={"episode_number": "manual"})
    apply_resolution(_job(), [track], resolve(IdentityClaims(), tiers=TIERS))
    assert track.episode_number is None
    assert track.identity_provenance is None


def test_apply_leaves_unowned_field_when_no_winner() -> None:
    track = _track(episode_name="Operator typed this")
    apply_resolution(_job(), [track], resolve(IdentityClaims(), tiers=TIERS))
    assert track.episode_name == "Operator typed this"


def test_apply_drops_provenance_without_change_when_reset_value_already_current() -> None:
    # excluded is already at its default (False); losing its only proposer
    # still drops the stale provenance entry, but there is no value to write
    # back, so this contributes 0 to the changed count.
    track = _track(identity_provenance={"excluded": "manual"})
    changed = apply_resolution(_job(), [track], resolve(IdentityClaims(), tiers=TIERS))
    assert track.excluded is False
    assert track.identity_provenance is None
    assert changed == 0


def test_apply_leaves_unowned_nonempty_field_when_only_lower_tier_proposes() -> None:
    track = _track(episode_name="Operator typed this")
    res = resolve(_claims(thediscdb=SourceClaims(tracks={"1": TrackClaim(episode_name="Pilot")})), tiers=TIERS)
    apply_resolution(_job(), [track], res)
    assert track.episode_name == "Operator typed this"
    assert track.identity_provenance is None


def test_apply_role_and_excluded_are_not_guarded() -> None:
    track = _track(role=TrackRole.OTHER, excluded=True)
    res = resolve(
        _claims(thediscdb=SourceClaims(tracks={"1": TrackClaim(role=TrackRole.MAIN, selected=True)})), tiers=TIERS
    )
    apply_resolution(_job(), [track], res)
    assert (track.role, track.excluded) == (TrackRole.MAIN, False)


def test_manual_selected_false_beats_thediscdb_selected_on_unguarded_field() -> None:
    """Migration 0039 seeds a manual `selected=False` for a legacy operator
    exclusion; it must outrank the disc map's `selected=True` even though
    `excluded` is unguarded."""
    track = _track(role=TrackRole.MAIN, excluded=True)
    res = resolve(
        _claims(
            thediscdb=SourceClaims(tracks={"1": TrackClaim(role=TrackRole.MAIN, selected=True)}),
            manual=SourceClaims(tracks={"1": TrackClaim(selected=False)}),
        ),
        tiers=TIERS,
    )
    assert res.tracks["1"]["selected"] == Winner(False, "manual")
    apply_resolution(_job(), [track], res)
    assert track.excluded is True
    assert track.identity_provenance == {"role": "thediscdb", "excluded": "manual"}


def test_apply_manual_overrides_unowned_value() -> None:
    track = _track(episode_name="old")
    res = resolve(_claims(manual=SourceClaims(tracks={"1": TrackClaim(episode_name="new")})), tiers=TIERS)
    apply_resolution(_job(), [track], res)
    assert track.episode_name == "new"
    assert track.identity_provenance == {"episode_name": "manual"}


def test_apply_is_idempotent() -> None:
    job, track = _job(), _track()
    res = resolve(
        _claims(
            thediscdb=SourceClaims(tracks={"1": TrackClaim(episode=1)}), manual=SourceClaims(job=JobClaim(season=2))
        ),
        tiers=TIERS,
    )
    apply_resolution(job, [track], res)
    assert apply_resolution(job, [track], res) == 0
    assert job.season == 2 and job.identity_provenance == {"season": "manual"}


def test_apply_skips_claims_for_missing_tracks() -> None:
    res = resolve(_claims(thediscdb=SourceClaims(tracks={"9": TrackClaim(episode=1)})), tiers=TIERS)
    assert apply_resolution(_job(), [_track("1")], res) == 0


def test_unranked_sorts_after_sparse_ranks() -> None:
    both = dict(
        ep_a=SourceClaims(tracks={"1": TrackClaim(episode=1)}),
        ep_b=SourceClaims(tracks={"1": TrackClaim(episode=2)}),
    )
    # A sparse rank (10) must still beat an unranked source.
    assert resolve(_claims(**both), tiers=TIERS, ranks={"ep_b": 10}).tracks["1"]["episode"].source == "ep_b"


def test_hint_does_not_overwrite_unowned_job_season() -> None:
    """Review Focus 4 (resolver guard): a job-level season set before this PR
    (no provenance) is not overwritten by a lower-tier disc-hint claim."""
    job = _job()
    job.season = 7
    res = resolve(_claims(label=SourceClaims(job=JobClaim(season=2))), tiers={**TIERS, "label": 4})
    apply_resolution(job, [], res)
    assert job.season == 7 and job.identity_provenance is None


def test_tier_beats_pin() -> None:
    res = resolve(
        IdentityClaims(
            sources={
                "thediscdb": SourceClaims(tracks={"1": TrackClaim(episode=2)}),
                "ep_a": SourceClaims(tracks={"1": TrackClaim(episode=9)}),
            },
            pin={"episode": "ep_a"},
        ),
        tiers=TIERS,
    )
    assert res.tracks["1"]["episode"].source == "thediscdb"
