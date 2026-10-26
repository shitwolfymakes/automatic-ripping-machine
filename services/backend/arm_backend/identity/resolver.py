"""Pick one value per identity field from every source's proposals and apply
it with provenance (design spec section 6.1). Pure: no I/O, no session."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from arm_common import Job, Track
from arm_common.schemas.identity import JOB_CLAIM_FIELDS, TRACK_CLAIM_FIELDS, IdentityClaims

from arm_backend.identity.proposals import MANUAL
from arm_backend.identity.sources.base import TIER_BY_CAPABILITY, Capability

logger = logging.getLogger(__name__)

# Old apply_map forced these two regardless of the current value; every other
# field was fill-if-empty. Kept so pre-provenance rows behave as before.
_UNGUARDED_ATTRS = {"role", "excluded"}
_DEFAULTS: dict[str, Any] = {"excluded": False}
# Episode matches are winner-takes-all: two providers' placements of the same
# disc are alternatives, never parts to merge field by field.
_EPISODE_TIER = TIER_BY_CAPABILITY[Capability.EPISODE_MATCH]


@dataclass(frozen=True)
class Winner:
    value: Any
    source: str


@dataclass
class Resolution:
    job: dict[str, Winner] = field(default_factory=dict)
    tracks: dict[str, dict[str, Winner]] = field(default_factory=dict)
    # Every source this run knew about (regardless of ok/error/skipped), so
    # _apply_one can tell "no winner because a still-live source stayed
    # silent" (reset to default) from "no winner because the owning source
    # was rolled back / removed" (leave the value alone).
    known_sources: frozenset[str] = frozenset()
    # The episode source whose placement won, and whether its result was held
    # (a guess). A held result is applied like a clean one; `episode_unsure`
    # is what tells the UI and the ripper to treat it as a guess.
    episode_source: str | None = None
    episode_unsure: bool = False


def resolve(
    claims: IdentityClaims,
    *,
    tiers: Mapping[str, int],
    ranks: Mapping[str, int] | None = None,
    disabled: frozenset[str] = frozenset(),
) -> Resolution:
    ranks = ranks or {}
    pinned = set(claims.pin.values())
    # A held result (`suggestion`) is applied like a clean one and reported
    # through `episode_unsure`; within a tier a clean result outranks a held
    # one, and a pin outranks both, so a source the operator chose in Fix
    # match keeps its placement until the match is cleared or re-run.
    usable = []
    for source_id, source in claims.sources.items():
        if source_id not in tiers:
            logger.debug("identity resolver: ignoring unknown source %s", source_id)
            continue
        # PR 4: a source the operator unchecked contributes nothing unless
        # pinned; it stays in `known_sources` (via `tiers`), so fields it
        # owned still reset to default when nothing else claims them.
        if source_id in disabled and source_id not in pinned:
            continue
        if source.status != "ok":
            continue
        usable.append(source_id)
    usable.sort(
        key=lambda s: (
            tiers[s],
            0 if s in pinned else 1,
            1 if claims.sources[s].suggestion else 0,
            s not in ranks,
            ranks.get(s, 0),
            s,
        )
    )
    # Keep only the first usable episode-match source (the pin sorts first);
    # every other one contributes nothing, so a lower-ranked provider can
    # never fill a track the winner called an extra with a duplicate number.
    episode_sources = [s for s in usable if tiers[s] == _EPISODE_TIER]
    usable = [s for s in usable if tiers[s] != _EPISODE_TIER or s == episode_sources[0]]

    res = Resolution(known_sources=frozenset(tiers))
    for source_id in usable:
        source = claims.sources[source_id]
        for name in source.job.model_fields_set & JOB_CLAIM_FIELDS.keys():
            res.job.setdefault(name, Winner(getattr(source.job, name), source_id))
        for ref, claim in source.tracks.items():
            slot = res.tracks.setdefault(ref, {})
            for name in claim.model_fields_set & TRACK_CLAIM_FIELDS.keys():
                slot.setdefault(name, Winner(getattr(claim, name), source_id))
    res.tracks = {ref: slot for ref, slot in res.tracks.items() if slot}
    if episode_sources:
        winner = episode_sources[0]
        res.episode_source = winner
        # A guess the operator has overridden on every track is no guess any
        # more: the flag follows the placements that are actually on the tracks.
        owns_a_track = any(w.source == winner for slot in res.tracks.values() for w in slot.values())
        res.episode_unsure = owns_a_track and claims.sources[winner].suggestion
    return res


def _to_attr_value(claim_field: str, value: Any) -> Any:
    if claim_field == "selected":
        return False if value is None else not value
    return value


def _apply_one(obj: Any, attr: str, winner: Winner | None, prov: dict[str, str], known_sources: frozenset[str]) -> int:
    default = _DEFAULTS.get(attr)
    current = getattr(obj, attr)
    if winner is None:
        owner = prov.get(attr)
        if owner is None or owner not in known_sources:
            # No current proposer, and either nothing ever owned this field or
            # the field's owner was rolled back / removed this run: leave the
            # value and its stale provenance alone rather than resetting it.
            return 0
        del prov[attr]
        if current != default:
            setattr(obj, attr, default)
            return 1
        return 0
    if (
        winner.source != MANUAL
        and attr not in prov
        and attr not in _UNGUARDED_ATTRS
        and current not in (None, "")
        and current != winner.value
    ):
        return 0
    prov[attr] = winner.source
    if current != winner.value:
        setattr(obj, attr, winner.value)
        return 1
    return 0


def apply_resolution(
    job: Job,
    tracks: Sequence[Track],
    resolution: Resolution,
    *,
    changed_track_ids: set[str] | None = None,
) -> int:
    changed = 0
    job_prov = dict(job.identity_provenance or {})
    for claim_field, attr in JOB_CLAIM_FIELDS.items():
        changed += _apply_one(job, attr, resolution.job.get(claim_field), job_prov, resolution.known_sources)
    job.identity_provenance = job_prov or None

    for track in tracks:
        prov = dict(track.identity_provenance or {})
        winners = resolution.tracks.get(track.source_ref, {})
        track_changed = 0
        for claim_field, attr in TRACK_CLAIM_FIELDS.items():
            w = winners.get(claim_field)
            if w is not None:
                w = Winner(_to_attr_value(claim_field, w.value), w.source)
            track_changed += _apply_one(track, attr, w, prov, resolution.known_sources)
        track.identity_provenance = prov or None
        changed += track_changed
        if track_changed and changed_track_ids is not None:
            changed_track_ids.add(track.id)
    return changed
