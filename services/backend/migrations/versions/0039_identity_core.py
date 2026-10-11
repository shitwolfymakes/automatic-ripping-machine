"""Identity core: provenance columns, two-episode titles, role enum values;
drop role_source (provenance supersedes it) and video_type (role supersedes
it); move the stored TheDiscDB map into metadata_json.identity_claims.

Revision ID: 0039_identity_core
Revises: 0038_encoder_first
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039_identity_core"
down_revision: Union[str, None] = "0038_encoder_first"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_NEW_ROLES = "('main', 'episode', 'extra', 'trailer', 'other')"
_EXTRA_TYPES = "('Extra', 'Featurette', 'DeletedScene', 'Interview', 'BehindTheScenes', 'Short')"

# TheDiscDB Item.Type -> TrackRole value, as a SQL CASE over <expr>.
_DISC_TYPE_TO_ROLE = (
    """CASE {expr}
    WHEN 'MainMovie' THEN 'main'
    WHEN 'Episode' THEN 'episode'
    WHEN 'Trailer' THEN 'trailer'
    ELSE CASE WHEN {expr} IN """
    + _EXTRA_TYPES
    + """ THEN 'extra' ELSE 'other' END
END"""
)


def upgrade() -> None:
    op.add_column("tracks", sa.Column("episode_number_end", sa.Integer(), nullable=True))
    op.add_column("tracks", sa.Column("identity_provenance", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("identity_provenance", sa.JSON(), nullable=True))

    # 1. video_type -> role where role is empty (only operator PATCH ever set it).
    op.execute("""
        UPDATE tracks SET role = CASE video_type WHEN 'series' THEN 'episode' WHEN 'movie' THEN 'main' END
        WHERE role IS NULL AND video_type IN ('series', 'movie');
    """)
    # 2. legacy TheDiscDB free-text roles -> TrackRole values.
    op.execute(f"""
        UPDATE tracks SET role = CASE
            WHEN role IN {_NEW_ROLES} THEN role
            ELSE {_DISC_TYPE_TO_ROLE.format(expr="role")}
        END
        WHERE role IS NOT NULL;
    """)
    op.drop_column("tracks", "role_source")
    op.drop_column("tracks", "video_type")

    # 3. metadata_json.thediscdb -> metadata_json.identity_claims.sources.thediscdb,
    #    converting each matched entry to the TrackClaim shape. jsonb_strip_nulls
    #    turns JSON nulls into ABSENT fields (= no opinion), matching the schema's
    #    presence semantics; an empty title / filename is no opinion either.
    role_case = _DISC_TYPE_TO_ROLE.format(expr="m.value ->> 'type'")
    op.execute(f"""
        UPDATE jobs SET metadata_json = (
            (metadata_json::jsonb - 'thediscdb')
            || jsonb_build_object('identity_claims', jsonb_build_object(
                'pin', '{{}}'::jsonb,
                'sources', jsonb_build_object('thediscdb', jsonb_strip_nulls(jsonb_build_object(
                    'status', 'ok',
                    'run_at', metadata_json::jsonb -> 'thediscdb' -> 'matched_at',
                    'extra', jsonb_strip_nulls(jsonb_build_object(
                        'release_slug', metadata_json::jsonb -> 'thediscdb' -> 'release_slug',
                        'title_slug', metadata_json::jsonb -> 'thediscdb' -> 'title_slug',
                        'kind', metadata_json::jsonb -> 'thediscdb' -> 'kind',
                        'contributors', metadata_json::jsonb -> 'thediscdb' -> 'contributors'
                    )),
                    'tracks', CASE
                        WHEN jsonb_typeof(metadata_json::jsonb -> 'thediscdb' -> 'matched') = 'object' THEN COALESCE((
                            SELECT jsonb_object_agg(m.key, jsonb_strip_nulls(jsonb_build_object(
                                'role', {role_case},
                                'episode_name', to_jsonb(NULLIF(m.value ->> 'title', '')),
                                'season', m.value -> 'season',
                                'episode', m.value -> 'episode',
                                'filename', to_jsonb(NULLIF(m.value ->> 'filename', '')),
                                'selected', CASE WHEN m.value ->> 'type' IN ('MainMovie', 'Episode') THEN true END
                            )))
                            FROM jsonb_each(metadata_json::jsonb -> 'thediscdb' -> 'matched') AS m
                            WHERE jsonb_typeof(m.value) = 'object'
                        ), '{{}}'::jsonb)
                        ELSE '{{}}'::jsonb
                    END
                )))
            ))
        )::json
        WHERE jsonb_typeof(metadata_json::jsonb -> 'thediscdb') = 'object';
    """)

    # 4. Keep pre-upgrade operator choices. The resolver lets thediscdb set
    #    `excluded` (via `selected`) and `role` even over a value without
    #    provenance, so a legacy track the operator excluded, or re-roled,
    #    would be flipped back on the first PATCH / resolve. Where a moved
    #    thediscdb claim disagrees with the stored column, seed a `manual`
    #    claim holding the column's value (merged into any manual claim
    #    already there). Agreeing values get no manual claim. Compared as
    #    jsonb so a malformed claim value never raises a cast error.
    op.execute("""
        UPDATE jobs SET metadata_json = jsonb_set(
            metadata_json::jsonb,
            '{identity_claims,sources,manual}',
            COALESCE(metadata_json::jsonb #> '{identity_claims,sources,manual}', '{}'::jsonb)
            || jsonb_build_object('tracks',
                COALESCE(metadata_json::jsonb #> '{identity_claims,sources,manual,tracks}', '{}'::jsonb) || d.claims)
        )::json
        FROM (
            SELECT t.job_id, jsonb_object_agg(
                t.source_ref,
                COALESCE(j.metadata_json::jsonb #> ARRAY['identity_claims', 'sources', 'manual', 'tracks', t.source_ref],
                    '{}'::jsonb) || f.fields
            ) AS claims
            FROM tracks t
            JOIN jobs j ON j.id = t.job_id
            CROSS JOIN LATERAL (
                SELECT j.metadata_json::jsonb #> ARRAY['identity_claims', 'sources', 'thediscdb', 'tracks', t.source_ref]
                    AS claim
            ) c
            CROSS JOIN LATERAL (
                SELECT jsonb_strip_nulls(jsonb_build_object(
                    'selected', CASE WHEN c.claim -> 'selected' = to_jsonb(t.excluded) THEN NOT t.excluded END,
                    'role', CASE
                        WHEN t.role IS NOT NULL AND c.claim -> 'role' IS NOT NULL
                            AND c.claim -> 'role' <> to_jsonb(t.role) THEN t.role
                    END
                )) AS fields
            ) f
            WHERE jsonb_typeof(c.claim) = 'object' AND f.fields <> '{}'::jsonb
            GROUP BY t.job_id
        ) AS d
        WHERE jobs.id = d.job_id;
    """)


def downgrade() -> None:
    op.add_column("tracks", sa.Column("video_type", sa.String(), nullable=True))
    op.add_column("tracks", sa.Column("role_source", sa.String(), nullable=True))
    op.execute("""
        UPDATE tracks SET role = CASE role
            WHEN 'main' THEN 'MainMovie' WHEN 'episode' THEN 'Episode'
            WHEN 'extra' THEN 'Extra' WHEN 'trailer' THEN 'Trailer' ELSE NULL END
        WHERE role IS NOT NULL;
    """)
    op.execute("""
        UPDATE tracks SET role_source = 'thediscdb'
        WHERE identity_provenance IS NOT NULL
          AND (identity_provenance::jsonb ->> 'role') = 'thediscdb';
    """)
    # identity_claims is dropped, not reverse-converted to the old `thediscdb`
    # section. Accepted trade-off: after a downgrade, a job identified but not
    # yet ripped loses its TheDiscDB labels at rip-start (the pre-0039 code
    # read that section there). Rows already ripped keep their column values.
    op.execute("""
        UPDATE jobs SET metadata_json = (metadata_json::jsonb - 'identity_claims')::json
        WHERE metadata_json::jsonb ? 'identity_claims';
    """)
    op.drop_column("jobs", "identity_provenance")
    op.drop_column("tracks", "identity_provenance")
    op.drop_column("tracks", "episode_number_end")
