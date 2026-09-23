"""Scrub the lifted-to-column mirror keys out of jobs.metadata_json.

Step 2 lockdown slice (docs/plans/AUTOMATION_GAP_ANALYSIS.md §3.4): 0030
lifted `pending_session_id` (and `season`/`disc`) into real columns but kept
the metadata_json copies around "until both UIs read the column." They do
now (`JobView.pending_session_id` is exposed; both UIs prefer the column),
so identify no longer writes the mirror and this migration removes the
stray top-level `pending_session_id`, `season`, and `disc` keys from
existing rows. In practice, 0030 already dropped `season`/`disc` from any
row it touched during its own lift, so on an already-migrated database this
migration's only real scrub target is `pending_session_id`; the other two
keys are covered defensively in case a row reached this point without going
through 0030's lift (e.g. written between 0030 and 0032 by code that still
had a mirror write path).

Per row (PostgreSQL only, in Python — same as 0030/0031, not sane SQL):
strip any of MIRROR_KEYS found at the top level of metadata_json and
rewrite the row only when something changed.

Idempotent: a row with none of the mirror keys is left untouched (the loop
rewrites nothing). Downgrade is a no-op — this is a data-only scrub, and the
dropped keys are not restored (they are redundant with the columns).

Revision ID: 0032_drop_metadata_mirrors
Revises: 0031_job_metadata_sections
Create Date: 2026-09-22

"""

import json
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_drop_metadata_mirrors"
down_revision: Union[str, None] = "0031_job_metadata_sections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MIRROR_KEYS = ("pending_session_id", "season", "disc")


def strip_mirror_keys(md: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Remove lifted-to-column top-level keys. Returns (new_md, changed)."""
    changed = False
    out = dict(md)
    for k in MIRROR_KEYS:
        if k in out:
            out.pop(k)
            changed = True
    return out, changed


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
        reshaped, changed = strip_mirror_keys(md)
        if not changed:
            continue
        bind.execute(
            sa.text("UPDATE jobs SET metadata_json = :md WHERE id = :id"),
            {"md": json.dumps(reshaped), "id": job_id},
        )


def downgrade() -> None:
    pass
