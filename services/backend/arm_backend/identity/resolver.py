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

logger = logging.getLogger(__name__)

# Old apply_map forced these two regardless of the current value; every other
# field was fill-if-empty. Kept so pre-provenance rows behave as before.
_UNGUARDED_ATTRS = {"role", "excluded"}
_DEFAULTS: dict[str, Any] = {"excluded": False}


@dataclass(frozen=True)
class Winner:
    value: Any
    source: str


@dataclass
class Resolution:
    job: dict[str, Winner] = field(default_factory=dict)
    tracks: dict[str, dict[str, Winner]] = field(default_factory=dict)


def resolve(claims: IdentityClaims, *, tiers: Mapping[str, int], ranks: Mapping[str, int] | None = None) -> Resolution:
    ranks = ranks or {}
    pinned = set(claims.pin.values())
    usable = []
    for source_id, source in claims.sources.items():
        if source_id not in tiers:
            logger.debug("identity resolver: ignoring unknown source %s", source_id)
            continue
        if source.status == "ok":
            usable.append(source_id)
    usable.sort(key=lambda s: (tiers[s], 0 if s in pinned else 1, ranks.get(s, len(ranks) + 1), s))

    res = Resolution()
    for source_id in usable:
        source = claims.sources[source_id]
        for name in source.job.model_fields_set & JOB_CLAIM_FIELDS.keys():
            res.job.setdefault(name, Winner(getattr(source.job, name), source_id))
        for ref, claim in source.tracks.items():
            slot = res.tracks.setdefault(ref, {})
            for name in claim.model_fields_set & TRACK_CLAIM_FIELDS.keys():
                slot.setdefault(name, Winner(getattr(claim, name), source_id))
    res.tracks = {ref: slot for ref, slot in res.tracks.items() if slot}
    return res


def _to_attr_value(claim_field: str, value: Any) -> Any:
    if claim_field == "selected":
        return False if value is None else not value
    return value


def _apply_one(obj: Any, attr: str, winner: Winner | None, prov: dict[str, str]) -> int:
    default = _DEFAULTS.get(attr)
    current = getattr(obj, attr)
    if winner is None:
        if attr in prov:
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


def apply_resolution(job: Job, tracks: Sequence[Track], resolution: Resolution) -> int:
    changed = 0
    job_prov = dict(job.identity_provenance or {})
    for claim_field, attr in JOB_CLAIM_FIELDS.items():
        changed += _apply_one(job, attr, resolution.job.get(claim_field), job_prov)
    job.identity_provenance = job_prov or None

    for track in tracks:
        prov = dict(track.identity_provenance or {})
        winners = resolution.tracks.get(track.source_ref, {})
        for claim_field, attr in TRACK_CLAIM_FIELDS.items():
            w = winners.get(claim_field)
            if w is not None:
                w = Winner(_to_attr_value(claim_field, w.value), w.source)
            changed += _apply_one(track, attr, w, prov)
        track.identity_provenance = prov or None
    return changed
