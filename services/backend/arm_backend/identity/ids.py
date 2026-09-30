"""Show-id resolution across episode-list providers (design spec 6.2).

Reads the show ids already known for a job (`metadata_json.identity.external_ids`)
and asks each episode-list provider whose own id field is still empty to
resolve it, then caches whatever is newly found back onto the job so a later
run does not re-query providers that already succeeded.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from pydantic import ValidationError

from arm_common import Job
from arm_common.schemas import ExternalIds

from arm_backend.identity.episodes.providers.base import EpisodeListProvider
from arm_backend.identity.http import SourceError, SourceMiss

logger = logging.getLogger(__name__)


def current_ids(job: Job) -> ExternalIds:
    """The show ids already known for a job, from
    `metadata_json.identity.external_ids`. Empty `ExternalIds()` when the
    identity section is absent, not a dict, or its `external_ids` fail to
    validate."""
    identity = (job.metadata_json or {}).get("identity")
    if not isinstance(identity, dict):
        return ExternalIds()
    raw = identity.get("external_ids")
    if not isinstance(raw, dict):
        return ExternalIds()
    try:
        return ExternalIds.model_validate(raw)
    except ValidationError as e:
        logger.warning("external_ids invalid job_id=%s; treating as empty: %s", job.id, e)
        return ExternalIds()


async def resolve_show_ids(
    job: Job, providers: Sequence[EpisodeListProvider], *, persist: bool = True, raise_errors: bool = False
) -> ExternalIds:
    """Resolve each provider's own show id and cache the merged result.

    Providers are tried in the given order. Each is asked at most once, and
    only when its `id_field` is still empty in the ids known so far; ids
    resolved by an earlier provider are visible to later ones. A provider
    raising `SourceError` or `SourceMiss` is logged and its field stays
    empty; a provider returning `None` likewise leaves its field empty.

    Newly found ids are merged into `metadata_json["identity"]["external_ids"]`
    (every other key of both `metadata_json` and `identity` is kept), but only
    when at least one new id was found and the job already has a dict
    `identity` section — otherwise the resolved ids are returned without
    writing anything back. With `persist=False` (a preview run) the ids are
    resolved the same way but never written back.
    """
    ids = current_ids(job)
    found = False
    for provider in providers:
        if getattr(ids, provider.id_field, None):
            continue
        try:
            show_id = await provider.resolve_show_id(ids)
        except (SourceError, SourceMiss) as e:
            if raise_errors and isinstance(e, SourceError):
                raise
            logger.warning("resolve_show_id failed source=%s job_id=%s: %s", provider.source_id, job.id, e)
            continue
        if show_id is None:
            continue
        ids = ids.model_copy(update={provider.id_field: show_id})
        found = True

    if found and persist:
        identity = (job.metadata_json or {}).get("identity")
        if isinstance(identity, dict):
            job.metadata_json = {
                **(job.metadata_json or {}),
                "identity": {
                    **identity,
                    "external_ids": ids.model_dump(mode="json", exclude_none=True),
                },
            }

    return ids


def merge_new_ids(target_job: Job, found: ExternalIds) -> bool:
    """Merge every id set on `found` that `target_job` doesn't already have
    into `target_job.metadata_json["identity"]["external_ids"]`. Never
    overwrites a field `target_job` already has. Returns whether anything
    changed.

    `found` is typically `current_ids` of a detached compute-phase snapshot
    job, taken after `resolve_show_ids` ran against it (see
    `EpisodeStageRunner`): that snapshot's session is closed once the
    network phase finishes, so any show id it newly resolved would
    otherwise be silently discarded along with it. This folds just those
    new fields into the fresh, just-re-selected job the apply phase writes
    to — never a field a concurrent edit may have set in the meantime."""
    existing = current_ids(target_job)
    new_values = {
        field: value
        for field, value in found.model_dump(exclude_none=True).items()
        if getattr(existing, field, None) is None
    }
    if not new_values:
        return False
    identity = (target_job.metadata_json or {}).get("identity")
    if not isinstance(identity, dict):
        return False
    merged = existing.model_copy(update=new_values)
    target_job.metadata_json = {
        **(target_job.metadata_json or {}),
        "identity": {
            **identity,
            "external_ids": merged.model_dump(mode="json", exclude_none=True),
        },
    }
    return True
