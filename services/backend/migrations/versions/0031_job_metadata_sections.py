"""Restructure jobs.metadata_json into its typed sections.

Companion to 0030 (gap analysis §3.4): identify no longer merges provider
payloads into the top level of the bag — conclusions live under `identity`,
music naming under `music`, behaviour flags under `flags`, and raw payloads
under `provider_raw[<provider>]`. This migration lifts existing rows into
that shape so readers need their legacy fallbacks only for rows that never
migrate (non-Postgres tooling has none).

Per row (PostgreSQL only, in Python — the reshaping is not sane SQL):
- imdb_id / imdbID / tmdb_id / tvdb_id → identity.external_ids, with
  provider "legacy" (the merging writer never recorded which provider won).
- artist / album / tracks → music.
- unidentified / dispatch_timeout → flags.
- every remaining unknown top-level key → provider_raw["legacy"] (the old
  payload merge is exactly what those keys are).
- kept at top level: scan_result, thediscdb, the transitional
  pending_session_id mirror, and the section keys themselves.

Idempotent: an already-shaped row has no stray keys, so the loop rewrites
nothing. Downgrade is a no-op — the sections remain readable by the
pre-migration code's fallbacks except provider_raw, which older code never
read anyway.

Revision ID: 0031_job_metadata_sections
Revises: 0030_job_identity_columns
Create Date: 2026-09-13

"""

import json
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_job_metadata_sections"
down_revision: Union[str, None] = "0030_job_identity_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KEEP_TOP_LEVEL = {
    "scan_result",
    "thediscdb",
    "pending_session_id",
    "identity",
    "music",
    "flags",
    "provider_raw",
}
_EXTERNAL_ID_KEYS = (("imdb_id", "imdb"), ("imdbID", "imdb"), ("tmdb_id", "tmdb"), ("tvdb_id", "tvdb"))
_MUSIC_KEYS = ("artist", "album", "tracks")
_FLAG_KEYS = ("unidentified", "dispatch_timeout")


def _reshape(md: dict[str, Any]) -> dict[str, Any] | None:
    """Return the reshaped bag, or None when the row is already clean."""
    strays = [k for k in md if k not in _KEEP_TOP_LEVEL]
    if not strays:
        return None

    out = {k: v for k, v in md.items() if k in _KEEP_TOP_LEVEL}

    external: dict[str, str] = {}
    for src, dst in _EXTERNAL_ID_KEYS:
        v = md.get(src)
        if isinstance(v, str) and v and v != "N/A" and dst not in external:
            external[dst] = v
    if external and "identity" not in out:
        out["identity"] = {"provider": "legacy", "external_ids": external}

    music = {k: md[k] for k in _MUSIC_KEYS if md.get(k)}
    if music and "music" not in out:
        out["music"] = music

    flags = dict(out.get("flags") or {})
    for k in _FLAG_KEYS:
        if k in md:
            flags.setdefault(k, bool(md[k]))
    if flags:
        out["flags"] = flags

    handled = {src for src, _ in _EXTERNAL_ID_KEYS} | set(_MUSIC_KEYS) | set(_FLAG_KEYS)
    legacy_raw = {k: md[k] for k in strays if k not in handled}
    if legacy_raw:
        raw = dict(out.get("provider_raw") or {})
        raw["legacy"] = {**(raw.get("legacy") or {}), **legacy_raw}
        out["provider_raw"] = raw
    return out


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    rows = bind.execute(sa.text("SELECT id, metadata_json FROM jobs WHERE metadata_json::text <> '{}'"))
    for job_id, md in rows:
        if isinstance(md, str):  # JSON column may deliver text depending on driver
            md = json.loads(md)
        if not isinstance(md, dict):
            continue
        reshaped = _reshape(md)
        if reshaped is None:
            continue
        bind.execute(
            sa.text("UPDATE jobs SET metadata_json = :md WHERE id = :id"),
            {"md": json.dumps(reshaped), "id": job_id},
        )


def downgrade() -> None:
    pass
