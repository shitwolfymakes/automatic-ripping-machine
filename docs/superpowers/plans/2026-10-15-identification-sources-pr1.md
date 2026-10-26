# Identification Sources PR 1: Columns, Schema and UI Compatibility — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Identification settings columns from the spec, drop `metadata_provider`, expose the new fields through the config API and the UI's existing schema-driven Metadata tab, and keep every current behaviour working, so that PR 2 only has to make the dispatcher read the columns.

**Architecture:** One Alembic migration (0045) adds eight columns to `config` and seeds them from the old `metadata_provider` before dropping it. `arm_common` gains the matching model fields, `ConfigFieldMeta` entries and view/update schema fields. The backend registry gains settings readers for the new columns and `search_source` reads `search_provider_*` instead of `metadata_provider`. The config router validates the new ranked lists and enum fields (including the "needs a key" rule) and re-resolves identities when the new lists change. The UI only follows the schema: its hand-written readers of `metadata_provider` switch to the new fields; the v4.2 Identification tab itself is the next PR.

**Tech Stack:** Python 3.14, SQLModel/Alembic (Postgres, enums as VARCHAR), FastAPI, pytest; SvelteKit 5 + vitest; `uv run …` from the repo root; ruff 0.15.11 via pre-commit; `bash devtools/regen-openapi-snapshot.sh` and `bash services/ui-neu/scripts/codegen.sh` for the wire contract.

**Spec:** `docs/superpowers/specs/2026-10-14-identification-sources-design.md` (§5.2, §5.4, D-2, D-7, D-8, D-9, D-10, §6 "PR 1", §8 criteria 7 and 8). Branch: `feat/identification-sources-pr1`, created from `feat/identification-sources-pr0` (PR #359) so PR 0's registry is present.

## Global Constraints

- Migration file: `services/backend/migrations/versions/0045_identification_sources.py`, revision `0045_identification_sources`, down revision `0044_previously_ripped` (0044 is taken on `main`; the spec's "0044" is superseded).
- New `config` columns, all `NOT NULL` with server defaults: `movie_sources` `ARRAY(String)` default `{tmdb,omdb}`; `music_sources` `ARRAY(String)` default `{musicbrainz}`; `search_provider_movie` `String` default `tmdb`; `search_provider_tv` `String` default `tmdb`; `search_provider_music` `String` default `musicbrainz`; `movie_auto_apply` `Boolean` default `true`; `music_auto_apply` `Boolean` default `true`; `crc64service_enabled` `Boolean` default `true`. `metadata_provider` is dropped.
- Seeding (D-8): `movie_sources` = `{omdb,tmdb}` when `metadata_provider = 'omdb'`, else `{tmdb,omdb}`; `search_provider_movie` = `metadata_provider` when it is `tmdb` or `omdb`, else `tmdb`; `search_provider_tv` = `episode_sources[1]` when present, else `tmdb`. Downgrade restores `metadata_provider` from `movie_sources[1]` when it is `tmdb` or `omdb`, else `tmdb`.
- Enum values: `movie_sources` `["tmdb", "omdb"]`; `music_sources` `["musicbrainz"]`; `search_provider_movie` `["tmdb", "omdb"]`; `search_provider_tv` `["tmdb", "tvmaze", "tvdb"]` (the owner's #258 note: offered from PR 1, falls back to the first usable ranked source with a log line until PR 2b adds their title search); `search_provider_music` `["musicbrainz"]`. Labels: `tmdb` "TMDb", `omdb` "OMDb", `tvmaze` "TVmaze", `tvdb` "TVDB", `musicbrainz` "MusicBrainz". `enum_requires`: `tmdb → tmdb_api_key`, `omdb → omdb_api_key`, `tvdb → tvdb_api_key`.
- No enum is a Postgres type; everything is VARCHAR validated in the app layer.
- No new field carries a `setup_step` (D-9: the wizard shows keys only). `metadata_provider`'s `setup_step="metadata", setup_order=4` disappears with it; `thediscdb_enabled` keeps `setup_order=5`.
- `search_source(cfg, media_type, registry)` prefers `search_provider_<media_type>` when that id is among `sources_for(...)`; otherwise the first ranked source, logging at INFO `search provider %s is not available for %s; using %s` when a preference was set and skipped. `online_source_ids` keeps its built-in defaults (PR 2 reads `movie_sources` / `episode_sources` / `music_sources`).
- Config PATCH validation: ranked lists via the existing `_RANKED_META` loop; every `type == "enum"` field via a new `_ENUM_META` loop: `None` or a value outside `enum_values` → 400 `{key} must be one of {a, b}`; a value whose `enum_requires` key is blank on the merged row (request fields override the stored row) → 400 `{key}: {label} needs its API key`. `on_previously_ripped` keeps its own check.
- `_IDENTITY_SOURCE_KEYS` gains `movie_sources` and `music_sources` (#219 re-resolve hook).
- ConfigView and ConfigUpdateRequest gain the eight fields and lose `metadata_provider`. OpenAPI snapshot and `api.gen.ts` are regenerated and committed in the same PR (the `openapi-drift` job).
- UI: no new tab or card. Hand-written readers switch from `metadata_provider` to `search_provider_movie` / `search_provider_tv`; the Metadata tab's section map lists the new keys so they render through `SchemaConfigForm`.
- Error strings elsewhere unchanged. Tests stay zero-infra. Commits carry no `Co-Authored-By` or "Generated with" trailers.

## Review Focus

1. An upgrade of a row with `metadata_provider = 'omdb'` must come out `movie_sources = {omdb,tmdb}` and `search_provider_movie = omdb` (Task 1 renders the UPDATE and asserts it).
2. A PATCH that sets `search_provider_movie = omdb` while also sending `omdb_api_key` in the same body must pass the needs-a-key check using the new key, not the stored blank one (Task 3 test).
3. A PATCH `search_provider_tv = tvmaze` must be accepted even though no adapter serves it yet, and `/search?type=tv` must then fall back to TMDb with the INFO log line (Task 3 tests on the router and the registry).
4. A legacy in-memory `Config()` with the new columns at `None` (fixtures predating them) must render through `/api/config` with the defaults, not 500 (Task 3 view test).
5. The job page's provider badge must follow the search type: TV search shows the TV provider's label (Task 4 UI test).

---

### Task 1: Model fields and migration 0045

**Files:**
- Modify: `packages/arm_common/arm_common/models/config.py` (the identity-settings block and the `metadata_provider` field)
- Create: `services/backend/migrations/versions/0045_identification_sources.py`
- Modify: `services/backend/tests/test_migration_chain.py` (append)
- Modify: `packages/arm_common/tests/test_config_metadata.py::test_config_model_defaults_for_identity_settings`

**Interfaces:**
- Produces: `Config.movie_sources: list[str]`, `Config.music_sources: list[str]`, `Config.search_provider_movie: str`, `Config.search_provider_tv: str`, `Config.search_provider_music: str`, `Config.movie_auto_apply: bool`, `Config.music_auto_apply: bool`, `Config.crc64service_enabled: bool`; `Config.metadata_provider` no longer exists.

- [ ] **Step 1: Write the failing tests**

Append to `services/backend/tests/test_migration_chain.py`:

```python
_IDENT_PARENT = "0044_previously_ripped"
_IDENT_REV = "0045_identification_sources"


def test_0045_upgrade_adds_the_identification_columns_and_seeds_them() -> None:
    sql = _render_sql(_IDENT_PARENT, _IDENT_REV)
    assert "ALTER TABLE config ADD COLUMN movie_sources VARCHAR[] DEFAULT '{tmdb,omdb}'::text[] NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN music_sources VARCHAR[] DEFAULT '{musicbrainz}'::text[] NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN search_provider_movie VARCHAR DEFAULT 'tmdb' NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN search_provider_tv VARCHAR DEFAULT 'tmdb' NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN search_provider_music VARCHAR DEFAULT 'musicbrainz' NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN movie_auto_apply BOOLEAN DEFAULT true NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN music_auto_apply BOOLEAN DEFAULT true NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN crc64service_enabled BOOLEAN DEFAULT true NOT NULL" in sql
    # D-8: the old choice goes first in the movie order and stays the search provider.
    assert "WHEN metadata_provider = 'omdb' THEN '{omdb,tmdb}'::text[]" in sql
    assert "WHEN metadata_provider IN ('tmdb', 'omdb') THEN metadata_provider" in sql
    assert "COALESCE(episode_sources[1], 'tmdb')" in sql
    assert sql.index("UPDATE config SET") < sql.index("ALTER TABLE config DROP COLUMN metadata_provider")


def test_0045_downgrade_restores_metadata_provider_from_the_movie_order() -> None:
    sql = _render_sql(_IDENT_REV, _IDENT_PARENT, downgrade=True)
    assert "ALTER TABLE config ADD COLUMN metadata_provider VARCHAR DEFAULT 'tmdb' NOT NULL" in sql
    assert "WHEN movie_sources[1] IN ('tmdb', 'omdb') THEN movie_sources[1]" in sql
    for name in (
        "crc64service_enabled",
        "music_auto_apply",
        "movie_auto_apply",
        "search_provider_music",
        "search_provider_tv",
        "search_provider_movie",
        "music_sources",
        "movie_sources",
    ):
        assert f"ALTER TABLE config DROP COLUMN {name}" in sql


def test_0045_matches_the_config_model() -> None:
    from arm_common import Config as ConfigModel

    sql = _render_sql(_IDENT_PARENT, _IDENT_REV)
    for name in (
        "movie_sources",
        "music_sources",
        "search_provider_movie",
        "search_provider_tv",
        "search_provider_music",
        "movie_auto_apply",
        "music_auto_apply",
        "crc64service_enabled",
    ):
        column = ConfigModel.__table__.columns[name]
        assert f"ADD COLUMN {name} " in sql, f"0045 does not add config.{name}"
        assert not column.nullable, f"Config.{name} is nullable but 0045 declares NOT NULL"
        assert column.server_default is not None, f"Config.{name} has no server_default to match 0045's"
    assert "metadata_provider" not in ConfigModel.__table__.columns
```

Replace `test_config_model_defaults_for_identity_settings` in `packages/arm_common/tests/test_config_metadata.py` with:

```python
def test_config_model_defaults_for_identity_settings() -> None:
    cfg = Config()
    assert cfg.episode_sources == ["tmdb", "tvmaze", "tvdb"]
    assert cfg.disc_hint_sources == ["bd_title", "label"]
    assert cfg.episode_match_tolerance_seconds == 300
    assert cfg.episode_auto_apply is True
    assert cfg.movie_sources == ["tmdb", "omdb"]
    assert cfg.music_sources == ["musicbrainz"]
    assert (cfg.search_provider_movie, cfg.search_provider_tv, cfg.search_provider_music) == (
        "tmdb",
        "tmdb",
        "musicbrainz",
    )
    assert cfg.movie_auto_apply is True
    assert cfg.music_auto_apply is True
    assert cfg.crc64service_enabled is True
    assert not hasattr(cfg, "metadata_provider")
    assert Config().episode_sources is not cfg.episode_sources  # no shared mutable default
    assert Config().movie_sources is not cfg.movie_sources
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest services/backend/tests/test_migration_chain.py packages/arm_common/tests/test_config_metadata.py -q -p no:cacheprovider -k "0045 or identity_settings"`
Expected: FAIL — `_render_sql` raises because revision `0045_identification_sources` does not exist; the model test fails on `movie_sources`.

- [ ] **Step 3: Add the model fields**

In `packages/arm_common/arm_common/models/config.py`, after the `episode_auto_apply` field and before `musicbrainz_user_agent`, add:

```python
    # Identification settings (spec 2026-10-14 D-7). Ranked online sources per
    # media type, the job page's search provider per type, per-type auto-apply
    # gates, and the ARM community CRC64 database switch (D-2). The TV list is
    # `episode_sources` above.
    movie_sources: list[str] = Field(
        default_factory=lambda: ["tmdb", "omdb"],
        sa_column=Column(ARRAY(String), nullable=False, server_default="{tmdb,omdb}"),
    )
    music_sources: list[str] = Field(
        default_factory=lambda: ["musicbrainz"],
        sa_column=Column(ARRAY(String), nullable=False, server_default="{musicbrainz}"),
    )
    search_provider_movie: str = Field(default="tmdb", sa_column=Column(String, nullable=False, server_default="tmdb"))
    search_provider_tv: str = Field(default="tmdb", sa_column=Column(String, nullable=False, server_default="tmdb"))
    search_provider_music: str = Field(
        default="musicbrainz", sa_column=Column(String, nullable=False, server_default="musicbrainz")
    )
    movie_auto_apply: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, server_default="true"))
    music_auto_apply: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, server_default="true"))
    crc64service_enabled: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, server_default="true"))
```

Delete the `metadata_provider` field and its three comment lines ("Persisted metadata provider …" through "… not search providers.").

- [ ] **Step 4: Write the migration**

Create `services/backend/migrations/versions/0045_identification_sources.py`:

```python
"""Identification settings (spec 2026-10-14 §5.4).

Adds the per-media-type online-source lists, the job page's search provider
per type, the per-type auto-apply gates and the ARM community CRC64 database
switch to the config singleton, seeds the movie order and search providers
from the old `metadata_provider` choice (D-8), then drops that column.

Revision ID: 0045_identification_sources
Revises: 0044_previously_ripped
Create Date: 2026-10-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045_identification_sources"
down_revision: Union[str, None] = "0044_previously_ripped"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    "movie_sources",
    "music_sources",
    "search_provider_movie",
    "search_provider_tv",
    "search_provider_music",
    "movie_auto_apply",
    "music_auto_apply",
    "crc64service_enabled",
)


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column(
            "movie_sources",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{tmdb,omdb}'::text[]"),
        ),
    )
    op.add_column(
        "config",
        sa.Column(
            "music_sources",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{musicbrainz}'::text[]"),
        ),
    )
    op.add_column(
        "config", sa.Column("search_provider_movie", sa.String(), nullable=False, server_default=sa.text("'tmdb'"))
    )
    op.add_column(
        "config", sa.Column("search_provider_tv", sa.String(), nullable=False, server_default=sa.text("'tmdb'"))
    )
    op.add_column(
        "config",
        sa.Column("search_provider_music", sa.String(), nullable=False, server_default=sa.text("'musicbrainz'")),
    )
    op.add_column(
        "config", sa.Column("movie_auto_apply", sa.Boolean(), nullable=False, server_default=sa.text("true"))
    )
    op.add_column(
        "config", sa.Column("music_auto_apply", sa.Boolean(), nullable=False, server_default=sa.text("true"))
    )
    op.add_column(
        "config", sa.Column("crc64service_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true"))
    )
    # D-8: no install changes behaviour on upgrade. The old choice leads the
    # movie order and stays the job page's movie search provider; the TV
    # search provider is the first episode source.
    op.execute(
        sa.text(
            "UPDATE config SET "
            "movie_sources = CASE WHEN metadata_provider = 'omdb' THEN '{omdb,tmdb}'::text[] "
            "ELSE '{tmdb,omdb}'::text[] END, "
            "search_provider_movie = CASE WHEN metadata_provider IN ('tmdb', 'omdb') THEN metadata_provider "
            "ELSE 'tmdb' END, "
            "search_provider_tv = COALESCE(episode_sources[1], 'tmdb')"
        )
    )
    op.drop_column("config", "metadata_provider")


def downgrade() -> None:
    op.add_column(
        "config", sa.Column("metadata_provider", sa.String(), nullable=False, server_default=sa.text("'tmdb'"))
    )
    op.execute(
        sa.text(
            "UPDATE config SET metadata_provider = CASE WHEN movie_sources[1] IN ('tmdb', 'omdb') "
            "THEN movie_sources[1] ELSE 'tmdb' END"
        )
    )
    for name in reversed(_COLUMNS):
        op.drop_column("config", name)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest services/backend/tests/test_migration_chain.py packages/arm_common/tests/test_config_metadata.py -q -p no:cacheprovider`
Expected: all passed (the chain tests `test_every_down_revision_resolves` and `test_single_linear_head` included). If an ADD COLUMN assertion fails on the exact rendering of the ARRAY type or default, print the rendered SQL with `pytest -s` once, adjust the assertion to the dialect's literal rendering, and say so in the report — the semantics (name, type, default, NOT NULL) are what matter.

- [ ] **Step 6: Commit**

```bash
git add packages/arm_common/arm_common/models/config.py services/backend/migrations/versions/0045_identification_sources.py services/backend/tests/test_migration_chain.py packages/arm_common/tests/test_config_metadata.py
git commit -m "feat(config): identification settings columns; migration 0045 seeds them from metadata_provider"
```

(Other suites fail until Tasks 2 and 3 land; that is expected between commits of this plan.)

---

### Task 2: Field metadata and wire schemas

**Files:**
- Modify: `packages/arm_common/arm_common/config_metadata.py` (replace the `metadata_provider` entry; add eight entries after `episode_auto_apply`)
- Modify: `packages/arm_common/arm_common/schemas/auth.py` (`ConfigView`, `ConfigUpdateRequest`)
- Modify: `packages/arm_common/tests/test_config_metadata.py` (`test_identity_settings_meta`, `test_setup_step_tagging_matches_spec`)

**Interfaces:**
- Produces: `ConfigFieldMeta` entries keyed `movie_sources`, `music_sources`, `search_provider_movie`, `search_provider_tv`, `search_provider_music`, `movie_auto_apply`, `music_auto_apply`, `crc64service_enabled`; `ConfigView` and `ConfigUpdateRequest` fields of the same names (`list[str]`, `str`, `bool`; optional on the update request).

- [ ] **Step 1: Write the failing tests**

In `packages/arm_common/tests/test_config_metadata.py`, extend `test_identity_settings_meta` by appending:

```python
    movies = by_key["movie_sources"]
    assert (movies.group, movies.tier, movies.type, movies.editable) == ("Metadata", "operator", "ranked", True)
    assert movies.enum_values == ["tmdb", "omdb"]
    assert movies.enum_labels == {"tmdb": "TMDb", "omdb": "OMDb"}
    assert movies.enum_requires == {"tmdb": "tmdb_api_key", "omdb": "omdb_api_key"}
    music = by_key["music_sources"]
    assert (music.type, music.enum_values, music.enum_requires) == ("ranked", ["musicbrainz"], None)
    assert music.enum_labels == {"musicbrainz": "MusicBrainz"}
    movie_sp = by_key["search_provider_movie"]
    assert (movie_sp.type, movie_sp.enum_values) == ("enum", ["tmdb", "omdb"])
    assert movie_sp.enum_requires == {"tmdb": "tmdb_api_key", "omdb": "omdb_api_key"}
    tv_sp = by_key["search_provider_tv"]
    assert (tv_sp.type, tv_sp.enum_values) == ("enum", ["tmdb", "tvmaze", "tvdb"])
    assert tv_sp.enum_requires == {"tmdb": "tmdb_api_key", "tvdb": "tvdb_api_key"}
    music_sp = by_key["search_provider_music"]
    assert (music_sp.type, music_sp.enum_values, music_sp.enum_requires) == ("enum", ["musicbrainz"], None)
    assert by_key["movie_auto_apply"].type == "bool"
    assert by_key["music_auto_apply"].type == "bool"
    assert by_key["crc64service_enabled"].type == "bool"
    assert "metadata_provider" not in by_key
    for key in (
        "movie_sources",
        "music_sources",
        "search_provider_movie",
        "search_provider_tv",
        "search_provider_music",
        "movie_auto_apply",
        "music_auto_apply",
        "crc64service_enabled",
    ):
        assert by_key[key].setup_step is None, key
```

In `test_setup_step_tagging_matches_spec`, change the `keys("metadata")` expectation to:

```python
    assert keys("metadata") == ["tmdb_api_key", "omdb_api_key", "tvdb_api_key", "thediscdb_enabled"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/arm_common/tests/test_config_metadata.py -q -p no:cacheprovider`
Expected: FAIL with `KeyError: 'movie_sources'` and the metadata-step list mismatch. (`test_every_editable_config_field_has_metadata` also fails until Step 3: the new model fields have no metadata yet.)

- [ ] **Step 3: Replace and add the metadata entries**

In `packages/arm_common/arm_common/config_metadata.py`, delete the whole `ConfigFieldMeta(key="metadata_provider", …)` entry. After the `episode_auto_apply` entry, add:

```python
    ConfigFieldMeta(
        key="movie_sources",
        group="Metadata",
        tier="operator",
        label="Movie sources",
        help="Tried top to bottom when a disc looks like a movie. ARM stops at the first confident match.",
        type="ranked",
        editable=True,
        enum_values=["tmdb", "omdb"],
        enum_labels={"tmdb": "TMDb", "omdb": "OMDb"},
        enum_requires={"tmdb": "tmdb_api_key", "omdb": "omdb_api_key"},
    ),
    ConfigFieldMeta(
        key="music_sources",
        group="Metadata",
        tier="operator",
        label="Music sources",
        help="Tried top to bottom for audio CDs, matched by the disc's track layout. MusicBrainz needs no key.",
        type="ranked",
        editable=True,
        enum_values=["musicbrainz"],
        enum_labels={"musicbrainz": "MusicBrainz"},
    ),
    ConfigFieldMeta(
        key="search_provider_movie",
        group="Metadata",
        tier="operator",
        label="Search movies with",
        help="The service behind the job page's search box for movies.",
        type="enum",
        editable=True,
        enum_values=["tmdb", "omdb"],
        enum_labels={"tmdb": "TMDb", "omdb": "OMDb"},
        enum_requires={"tmdb": "tmdb_api_key", "omdb": "omdb_api_key"},
    ),
    ConfigFieldMeta(
        key="search_provider_tv",
        group="Metadata",
        tier="operator",
        label="Search TV with",
        help="The service behind the job page's search box for TV. TVmaze needs no key.",
        type="enum",
        editable=True,
        enum_values=["tmdb", "tvmaze", "tvdb"],
        enum_labels={"tmdb": "TMDb", "tvmaze": "TVmaze", "tvdb": "TVDB"},
        enum_requires={"tmdb": "tmdb_api_key", "tvdb": "tvdb_api_key"},
    ),
    ConfigFieldMeta(
        key="search_provider_music",
        group="Metadata",
        tier="operator",
        label="Search music with",
        help="The service behind the job page's search box for audio CDs.",
        type="enum",
        editable=True,
        enum_values=["musicbrainz"],
        enum_labels={"musicbrainz": "MusicBrainz"},
    ),
    ConfigFieldMeta(
        key="movie_auto_apply",
        group="Metadata",
        tier="operator",
        label="Apply movie matches automatically",
        help="Off: a confident movie match is stored as a suggestion for you to confirm. Ripping › Review first still applies either way.",
        type="bool",
        editable=True,
    ),
    ConfigFieldMeta(
        key="music_auto_apply",
        group="Metadata",
        tier="operator",
        label="Apply music matches automatically",
        help="Off: a confident CD match is stored as a suggestion for you to confirm. Ripping › Review first still applies either way.",
        type="bool",
        editable=True,
    ),
    ConfigFieldMeta(
        key="crc64service_enabled",
        group="Metadata",
        tier="operator",
        label="ARM community database (CRC64)",
        help="Send a DVD's CRC64 fingerprint to the ARM project's community database and take its title when it has one. DVDs only; no key needed.",
        type="bool",
        editable=True,
    ),
```

- [ ] **Step 4: Update the wire schemas**

In `packages/arm_common/arm_common/schemas/auth.py`, in `ConfigView`, replace the line `metadata_provider: str` with:

```python
    movie_sources: list[str]
    music_sources: list[str]
    search_provider_movie: str
    search_provider_tv: str
    search_provider_music: str
    movie_auto_apply: bool
    music_auto_apply: bool
    crc64service_enabled: bool
```

In `ConfigUpdateRequest`, replace `metadata_provider: str | None = None` with:

```python
    movie_sources: list[str] | None = None
    music_sources: list[str] | None = None
    search_provider_movie: str | None = None
    search_provider_tv: str | None = None
    search_provider_music: str | None = None
    movie_auto_apply: bool | None = None
    music_auto_apply: bool | None = None
    crc64service_enabled: bool | None = None
```

- [ ] **Step 5: Run the arm_common suite**

Run: `uv run pytest packages/arm_common/tests -q -p no:cacheprovider`
Expected: all passed, including `test_every_editable_config_field_has_metadata`, `test_operator_and_secret_keys_are_real_config_view_fields`, `test_enum_labels_cover_exactly_the_enum_values`, `test_enum_requires_names_real_secret_keys`.

- [ ] **Step 6: Commit**

```bash
git add packages/arm_common/arm_common/config_metadata.py packages/arm_common/arm_common/schemas/auth.py packages/arm_common/tests/test_config_metadata.py
git commit -m "feat(config): metadata and view schema for the identification settings"
```

---

### Task 3: Registry readers, config router, backend tests

**Files:**
- Modify: `services/backend/arm_backend/identity/sources/registry.py` (settings readers; `search_source`)
- Modify: `services/backend/arm_backend/routers/config.py` (`_to_view`, validation, `_IDENTITY_SOURCE_KEYS`)
- Modify: `services/backend/tests/test_identity_registry_online.py`
- Create: `services/backend/tests/test_config_identification_settings.py` (replaces `test_config_metadata_provider.py`, which is deleted; its `test_patch_config_rejects_non_editable_key` and `test_config_view_exposes_makemkv_status` move over unchanged)
- Modify: `services/backend/tests/test_config_identity_settings.py`, `test_config_secret_masking.py`, `test_config_iso_rips.py`, `test_settings_router.py`, `test_metadata_search_router.py` (seed kwargs and one assertion)

**Interfaces:**
- Consumes: Task 1 columns; `sources_for`, `lookup_sources`, `known_source_ids` (PR 0).
- Produces in `registry.py`: `DEFAULT_MOVIE_SOURCES = ("tmdb", "omdb")`, `DEFAULT_MUSIC_SOURCES = ("musicbrainz",)`, `DEFAULT_SEARCH_PROVIDERS = {"movie": "tmdb", "tv": "tmdb", "music": "musicbrainz"}`, `movie_sources_setting(cfg) -> tuple[str, ...]`, `music_sources_setting(cfg) -> tuple[str, ...]`, `search_provider_setting(cfg, media_type) -> str`, `movie_auto_apply(cfg) -> bool`, `music_auto_apply(cfg) -> bool`, `crc64service_enabled(cfg) -> bool`.

- [ ] **Step 1: Write the failing registry tests**

In `services/backend/tests/test_identity_registry_online.py`, replace `test_search_source_honours_legacy_metadata_provider` with:

```python
def test_search_source_reads_the_search_provider_setting(caplog):
    reg = _registry(
        FakeSource("tmdb", {"movie", "tv"}),
        FakeSource("omdb", {"movie", "tv"}),
        FakeSource("musicbrainz", {"music"}),
    )
    assert search_source(_cfg(search_provider_movie="omdb"), "movie", reg).id == "omdb"
    assert search_source(_cfg(search_provider_tv="tmdb"), "tv", reg).id == "tmdb"
    assert search_source(_cfg(), "music", reg).id == "musicbrainz"
    reg["omdb"]._reason = "no omdb key"
    with caplog.at_level("INFO", logger="arm_backend.identity.sources.registry"):
        assert search_source(_cfg(search_provider_movie="omdb"), "movie", reg).id == "tmdb"
    assert "search provider omdb is not available for movie; using tmdb" in caplog.text


def test_search_source_falls_back_for_a_provider_with_no_adapter_yet(caplog):
    """`search_provider_tv = tvmaze` is a valid setting before PR 2b adds the
    adapter: the job page falls back to the first usable ranked source."""
    reg = _registry(FakeSource("tmdb", {"movie", "tv"}), FakeSource("omdb", {"movie", "tv"}))
    with caplog.at_level("INFO", logger="arm_backend.identity.sources.registry"):
        assert search_source(_cfg(search_provider_tv="tvmaze"), "tv", reg).id == "tmdb"
    assert "search provider tvmaze is not available for tv; using tmdb" in caplog.text


def test_settings_readers_default_for_legacy_rows():
    from arm_backend.identity.sources.registry import (
        crc64service_enabled,
        movie_auto_apply,
        movie_sources_setting,
        music_auto_apply,
        music_sources_setting,
        search_provider_setting,
    )

    assert movie_sources_setting(None) == ("tmdb", "omdb")
    assert music_sources_setting(None) == ("musicbrainz",)
    assert search_provider_setting(None, "movie") == "tmdb"
    assert search_provider_setting(None, "tv") == "tmdb"
    assert search_provider_setting(None, "music") == "musicbrainz"
    assert search_provider_setting(None, "data") == ""
    assert movie_auto_apply(None) is True
    assert music_auto_apply(None) is True
    assert crc64service_enabled(None) is True
    cfg = _cfg(movie_sources=["omdb", "bogus", "omdb"], music_sources=[], movie_auto_apply=False, crc64service_enabled=False)
    assert movie_sources_setting(cfg) == ("omdb",)
    assert music_sources_setting(cfg) == ()
    assert movie_auto_apply(cfg) is False
    assert crc64service_enabled(cfg) is False
```

- [ ] **Step 2: Write the failing config router tests**

Create `services/backend/tests/test_config_identification_settings.py`:

```python
"""Identification settings on the Config singleton (spec 2026-10-14 PR 1)."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import config as config_router  # noqa: E402
from arm_backend.seeders import CONFIG_SINGLETON_ID  # noqa: E402
from arm_common import Config, RetentionPolicy, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession, **overrides: object) -> Config:
    row = Config(
        id=CONFIG_SINGLETON_ID,
        tmdb_api_key=None,
        omdb_api_key=None,
        musicbrainz_user_agent=None,
        auto_transcode_on_idle=False,
        auto_rip_on_insert=True,
        block_on_miss=True,
        default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
        notification_apprise_urls=[],
        notifications_enabled=False,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    db.rows["config"] = [row]
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    return row


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(config_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_config_view_exposes_the_identification_settings(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        body = client.get("/api/config", headers=_auth(token)).json()
    assert body["movie_sources"] == ["tmdb", "omdb"]
    assert body["music_sources"] == ["musicbrainz"]
    assert body["search_provider_movie"] == "tmdb"
    assert body["search_provider_tv"] == "tmdb"
    assert body["search_provider_music"] == "musicbrainz"
    assert body["movie_auto_apply"] is True
    assert body["music_auto_apply"] is True
    assert body["crc64service_enabled"] is True
    assert "metadata_provider" not in body


def test_config_view_defaults_when_the_new_columns_are_none(signing_key: bytes) -> None:
    db = FakeSession()
    row = _seed(db)
    for key in (
        "movie_sources",
        "music_sources",
        "search_provider_movie",
        "search_provider_tv",
        "search_provider_music",
        "movie_auto_apply",
        "music_auto_apply",
        "crc64service_enabled",
    ):
        setattr(row, key, None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/config", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["movie_sources"] == ["tmdb", "omdb"]
    assert body["search_provider_music"] == "musicbrainz"
    assert body["crc64service_enabled"] is True


def test_patch_ranked_lists_and_toggles(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="k", omdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/config",
            json={"movie_sources": ["omdb", "tmdb"], "music_sources": [], "movie_auto_apply": False, "crc64service_enabled": False},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["movie_sources"] == ["omdb", "tmdb"]
    assert body["music_sources"] == []
    assert body["movie_auto_apply"] is False
    assert body["crc64service_enabled"] is False
    row = db.rows["config"][0]
    assert row.movie_sources == ["omdb", "tmdb"] and row.crc64service_enabled is False


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"movie_sources": ["tmdb", "netflix"]}, "movie_sources: unknown value(s) netflix"),
        ({"movie_sources": ["tmdb", "tmdb"]}, "movie_sources: duplicate values"),
        ({"music_sources": None}, "music_sources must be a list"),
        ({"search_provider_movie": "netflix"}, "search_provider_movie must be one of tmdb, omdb"),
        ({"search_provider_movie": None}, "search_provider_movie must be one of tmdb, omdb"),
        ({"search_provider_music": "spotify"}, "search_provider_music must be one of musicbrainz"),
        ({"movie_auto_apply": None}, "movie_auto_apply must be true or false"),
        ({"crc64service_enabled": None}, "crc64service_enabled must be true or false"),
    ],
)
def test_patch_rejects_bad_identification_settings(signing_key: bytes, body: dict, detail: str) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="k", omdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/config", json=body, headers=_auth(token))
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == detail


def test_patch_search_provider_needs_its_key(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="k", omdb_api_key=None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/config", json={"search_provider_movie": "omdb"}, headers=_auth(token))
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "search_provider_movie: OMDb needs its API key"
        # The key sent in the same body counts (review focus 2).
        r = client.patch(
            "/api/config", json={"search_provider_movie": "omdb", "omdb_api_key": "new-k"}, headers=_auth(token)
        )
        assert r.status_code == 200, r.text
        assert r.json()["search_provider_movie"] == "omdb"
        # A keyless choice needs no key even when no key is stored.
        r = client.patch("/api/config", json={"search_provider_tv": "tvmaze"}, headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["search_provider_tv"] == "tvmaze"


def test_patch_ranked_lists_do_not_require_keys(signing_key: bytes) -> None:
    """A ranked list may name an unkeyed source: the registry skips it at run
    time and the UI shows the "Needs key" chip (same rule as episode_sources)."""
    db = FakeSession()
    _seed(db, tmdb_api_key=None, omdb_api_key=None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/config", json={"movie_sources": ["omdb", "tmdb"]}, headers=_auth(token))
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("key", ["movie_sources", "music_sources"])
def test_changing_the_new_lists_re_resolves_live_jobs(signing_key: bytes, monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    db = FakeSession()
    _seed(db)
    resolved: list[str] = []
    stage_scheduled: list[str] = []

    async def fake_reresolve(session, request):  # type: ignore[no-untyped-def]
        resolved.append(key)

    monkeypatch.setattr(config_router, "_reresolve_identity", fake_reresolve)
    app, token = _make_app(signing_key, db)
    body = {key: ["omdb"] if key == "movie_sources" else []}
    with TestClient(app) as client:
        r = client.patch("/api/config", json=body, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert resolved == [key]
    del stage_scheduled


def test_patch_config_rejects_non_editable_key(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/config", json={"MEDIA_ROOT": "/x"}, headers=_auth(token))
    assert r.status_code in (400, 422)


def test_config_view_exposes_makemkv_status(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, makemkv_key_valid=True, makemkv_key_state="ok")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        body = client.get("/api/config", headers=_auth(token)).json()
    assert body["makemkv_key_valid"] is True
    assert body["makemkv_key_state"] == "ok"
```

Before writing the last two tests, read the originals in `services/backend/tests/test_config_metadata_provider.py` (lines 107–130) and copy their bodies verbatim instead of the sketches above if they differ; the point is to keep their coverage, not to rewrite them. Then delete `test_config_metadata_provider.py`.

Mechanical seed edits: remove the `metadata_provider="tmdb",` kwarg from `_seed`/row builders in `test_config_identity_settings.py` (line 43), `test_config_secret_masking.py` (line 48; its line 86 assertion changes to `assert body["search_provider_movie"] != HIDDEN_SECRET`), `test_config_iso_rips.py` (line 42). In `test_settings_router.py` line 63 assert `by_key["search_provider_movie"]["type"] == "enum"` instead. In `test_metadata_search_router.py`, every `_seed(db, metadata_provider="omdb", …)` becomes `_seed(db, search_provider_movie="omdb", …)` and every `metadata_provider="tmdb"` becomes `search_provider_movie="tmdb"`; rename `test_search_default_provider_honours_metadata_provider` → `test_search_default_provider_honours_search_provider_movie` and `test_lookup_prefers_metadata_provider_when_both_keyed` → `test_lookup_prefers_search_provider_movie_when_both_keyed`, updating their docstrings. Add one router test:

```python
@respx.mock
def test_tv_search_falls_back_when_the_tv_provider_has_no_adapter(signing_key: bytes) -> None:
    """search_provider_tv=tvmaze is valid before PR 2b; the box uses the first usable ranked source."""
    tmdb_route = respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=httpx.Response(200, json={"results": [{"name": "Lost", "first_air_date": "2004-09-22", "id": 4607}]})
    )
    db = FakeSession()
    _seed(db, tmdb_api_key="k", search_provider_tv="tvmaze")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "lost", "type": "tv"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Lost"
    assert tmdb_route.called
```

(If the TMDb TV candidates path issues a follow-up `external_ids` request in this test, mock `https://api.themoviedb.org/3/tv/4607/external_ids` with `httpx.Response(200, json={})` as the sibling `test_search_tmdb_tv_candidates` does — copy its mocks.)

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest services/backend/tests/test_identity_registry_online.py services/backend/tests/test_config_identification_settings.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError` for the new readers; `/api/config` 500s on the missing view fields.

- [ ] **Step 4: Registry readers and `search_source`**

In `services/backend/arm_backend/identity/sources/registry.py`, add `import logging` and `logger = logging.getLogger("arm_backend.identity.sources.registry")` after the imports. Below `DEFAULT_FINGERPRINT_SOURCES`, add:

```python
DEFAULT_MOVIE_SOURCES: tuple[str, ...] = ("tmdb", "omdb")
DEFAULT_MUSIC_SOURCES: tuple[str, ...] = ("musicbrainz",)
DEFAULT_SEARCH_PROVIDERS: dict[str, str] = {"movie": "tmdb", "tv": "tmdb", "music": "musicbrainz"}
# Every id a ranked online list may name, by media type (the Config field
# metadata's enum_values mirror these; a test pins them together).
ONLINE_SOURCE_VALUES: dict[str, tuple[str, ...]] = {
    "movie": ("tmdb", "omdb"),
    "tv": ("tmdb", "tvmaze", "tvdb"),
    "music": ("musicbrainz",),
}
_MOVIE_KNOWN = {sid: sid for sid in ONLINE_SOURCE_VALUES["movie"]}
_MUSIC_KNOWN = {sid: sid for sid in ONLINE_SOURCE_VALUES["music"]}


def movie_sources_setting(cfg: Config | None) -> tuple[str, ...]:
    return _ranked(getattr(cfg, "movie_sources", None), _MOVIE_KNOWN, DEFAULT_MOVIE_SOURCES)


def music_sources_setting(cfg: Config | None) -> tuple[str, ...]:
    return _ranked(getattr(cfg, "music_sources", None), _MUSIC_KNOWN, DEFAULT_MUSIC_SOURCES)


def search_provider_setting(cfg: Config | None, media_type: str) -> str:
    """The job page's search provider for `media_type` ("" for an unknown type)."""
    default = DEFAULT_SEARCH_PROVIDERS.get(media_type, "")
    value = getattr(cfg, f"search_provider_{media_type}", None)
    return str(value) if value else default


def movie_auto_apply(cfg: Config | None) -> bool:
    value = getattr(cfg, "movie_auto_apply", None)
    return True if value is None else bool(value)


def music_auto_apply(cfg: Config | None) -> bool:
    value = getattr(cfg, "music_auto_apply", None)
    return True if value is None else bool(value)


def crc64service_enabled(cfg: Config | None) -> bool:
    value = getattr(cfg, "crc64service_enabled", None)
    return True if value is None else bool(value)
```

Replace `search_source` with:

```python
def search_source(cfg: Config | None, media_type: str, registry: Mapping[str, "OnlineSource"]) -> "OnlineSource | None":
    """The source behind the job page's search box for `media_type`: the
    operator's `search_provider_<type>` when it is listed, registered and
    configured, else the first usable listed source (logged, so a provider
    chosen before its adapter exists — TVmaze/TVDB until PR 2b — is visible)."""
    ranked = sources_for(cfg, media_type, registry)
    preferred = search_provider_setting(cfg, media_type)
    for source in ranked:
        if source.id == preferred:
            return source
    fallback = ranked[0] if ranked else None
    if preferred and fallback is not None:
        logger.info("search provider %s is not available for %s; using %s", preferred, media_type, fallback.id)
    return fallback
```

- [ ] **Step 5: Config router**

In `services/backend/arm_backend/routers/config.py`:

1. Import the new readers alongside `episode_sources_setting`: `crc64service_enabled, movie_auto_apply, movie_sources_setting, music_auto_apply, music_sources_setting, search_provider_setting`.
2. Next to `_RANKED_META`, add `_ENUM_META = {m.key: m for m in CONFIG_FIELD_META if m.type == "enum" and m.key != "on_previously_ripped"}`.
3. In `_to_view`, replace `metadata_provider=cfg.metadata_provider or "tmdb",` with:

```python
        movie_sources=list(movie_sources_setting(cfg)),
        music_sources=list(music_sources_setting(cfg)),
        search_provider_movie=search_provider_setting(cfg, "movie"),
        search_provider_tv=search_provider_setting(cfg, "tv"),
        search_provider_music=search_provider_setting(cfg, "music"),
        movie_auto_apply=movie_auto_apply(cfg),
        music_auto_apply=music_auto_apply(cfg),
        crc64service_enabled=crc64service_enabled(cfg),
```

4. Delete the `if "metadata_provider" in fields …` block. In its place add:

```python
    for key, meta in _ENUM_META.items():
        if key not in fields:
            continue
        value = fields[key]
        allowed = meta.enum_values or []
        if value is None or value not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} must be one of {', '.join(allowed)}"
            )
        required = (meta.enum_requires or {}).get(value)
        if required:
            # The key sent in this body counts; otherwise the stored one.
            present = fields[required] if required in fields else getattr(cfg, required, None)
            if not (present or "").strip():
                label = (meta.enum_labels or {}).get(value, value)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key}: {label} needs its API key"
                )
    for key in ("movie_auto_apply", "music_auto_apply", "crc64service_enabled"):
        if key in fields and fields[key] is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} must be true or false")
```

5. `_IDENTITY_SOURCE_KEYS = ("episode_sources", "disc_hint_sources", "movie_sources", "music_sources")`.

`identity_sources_changed` (line 242) already compares `fields[key] != getattr(cfg, key)` for every key in `_IDENTITY_SOURCE_KEYS`, so extending the tuple is the whole change.

- [ ] **Step 6: Run the backend suites**

Run: `uv run pytest services/backend/tests -q -p no:cacheprovider`
Expected: all passed (about 3255). Typical casualties and their fixes: a `_seed` still passing `metadata_provider` (remove it); `test_config_secret_masking` asserting on the removed key (updated in Step 2); the drift test `test_search_provider_literal_matches_registry` (unchanged: `known_source_ids("movie"/"tv", registry)` still yields `tmdb, omdb` because TVmaze/TVDB have no adapter yet).

- [ ] **Step 7: Lint, types, commit**

Run: `uv run pre-commit run ruff --all-files && uv run pre-commit run ruff-format --all-files && uv run mypy services/backend/arm_backend/identity/sources/registry.py services/backend/arm_backend/routers/config.py`
Expected: clean.

```bash
git add services/backend/arm_backend/identity/sources/registry.py services/backend/arm_backend/routers/config.py services/backend/tests
git rm services/backend/tests/test_config_metadata_provider.py
git commit -m "feat(config): read and validate the identification settings; search providers replace metadata_provider"
```

---

### Task 4: Wire contract regeneration and UI compatibility

**Files:**
- Regenerate: `services/ui-neu/openapi.snapshot.json`, `services/ui-neu/frontend/src/lib/types/api.gen.ts`
- Modify: `services/ui-neu/frontend/src/lib/api/config.ts`, `src/lib/stores/config.ts`, `src/lib/components/TitleSearch.svelte`, `src/lib/components/setup/steps/FinishStep.svelte`, `src/lib/utils/settings-sections.ts`
- Modify tests: `src/lib/utils/__tests__/settings-sections.test.ts`, `src/routes/settings/__tests__/settings-page.test.ts`, `src/lib/components/settings/__tests__/SchemaConfigForm.test.ts`, `src/lib/components/settings/__tests__/ConfigSchemaField.test.ts`; add a `TitleSearch` badge test if a `TitleSearch` test file exists (`ls src/lib/components/__tests__ | grep -i title`), else add `src/lib/components/__tests__/TitleSearch.provider.test.ts`.

**Interfaces:**
- Consumes: `ConfigView.search_provider_movie`, `.search_provider_tv` (Task 2).
- Produces: `AppConfig.search_provider_movie: string | null`, `AppConfig.search_provider_tv: string | null`; store `searchProviders` (readable `{ movie: string | null; tv: string | null }`); `metadataProvider` store removed.

- [ ] **Step 1: Regenerate the contract**

Run from the repo root: `bash devtools/regen-openapi-snapshot.sh && bash services/ui-neu/scripts/codegen.sh && git diff --stat services/ui-neu/openapi.snapshot.json services/ui-neu/frontend/src/lib/types/api.gen.ts`
Expected: both files change; `ConfigView` in `api.gen.ts` has the eight new fields and no `metadata_provider`.

- [ ] **Step 2: Update the UI tests first**

In `settings-sections.test.ts`, replace `meta('metadata_provider', 'enum')` with `meta('search_provider_movie', 'enum')` (three places) and the expectation `['metadata_provider']` with `['search_provider_movie']`. In `settings-page.test.ts`, the schema field `key: 'metadata_provider'` becomes `key: 'search_provider_movie'` with label `'Search movies with'`, and `mockConfig.metadata_provider: 'omdb'` becomes `search_provider_movie: 'omdb'`. In `SchemaConfigForm.test.ts`, `key: 'metadata_provider'` → `'search_provider_movie'`, `CONFIG.metadata_provider` → `search_provider_movie`, and the three `payload.metadata_provider` / `{ metadata_provider: … }` expectations → `search_provider_movie`. In `ConfigSchemaField.test.ts`, the field key → `'search_provider_movie'`.

Add the badge test (in the existing TitleSearch test file if there is one, else the new file):

```ts
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import { writable } from 'svelte/store';

vi.mock('$lib/stores/config', () => ({
	searchProviders: writable({ movie: 'omdb', tv: 'tvmaze' })
}));
vi.mock('$lib/api/jobs', () => ({
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn(),
	updateJobTitle: vi.fn(),
	resolveJob: vi.fn()
}));

import TitleSearch from '$lib/components/TitleSearch.svelte';

describe('TitleSearch provider badge', () => {
	it('follows the search type', async () => {
		const job = { id: 'job_1', media_type: 'movie', looks_episodic: false, title: null } as never;
		render(TitleSearch, { props: { job } });
		expect(screen.getByTitle(/default metadata provider/i)).toHaveTextContent('OMDb');
		await fireEvent.click(screen.getByRole('button', { name: /^tv$/i }));
		expect(screen.getByTitle(/default metadata provider/i)).toHaveTextContent('TVmaze');
	});
});
```

Adjust the `job` literal and the button query to the component's real props and markup (read `TitleSearch.svelte` lines 17–60 and 205–232 first); the assertion that matters is the badge text per search type.

- [ ] **Step 3: Run the UI tests to verify they fail**

Run: `cd services/ui-neu/frontend && npx vitest run src/lib/utils src/routes/settings src/lib/components/settings src/lib/components/__tests__/TitleSearch.provider.test.ts`
Expected: the settings tests pass already (they only rename mock keys); the badge test fails because `searchProviders` does not exist.

- [ ] **Step 4: Update the UI readers**

`src/lib/api/config.ts`:

```ts
export interface AppConfig {
	transcoder_capable: boolean;
	transcoder_enabled: boolean;
	// The job page's search provider per media type; null when unset.
	search_provider_movie: string | null;
	search_provider_tv: string | null;
}

export async function fetchConfig(): Promise<AppConfig> {
	const cfg = await get<ConfigView>('/api/config');
	return {
		transcoder_capable: cfg.transcode_capable ?? true,
		transcoder_enabled: cfg.transcode_enabled ?? true,
		search_provider_movie: cfg.search_provider_movie ?? null,
		search_provider_tv: cfg.search_provider_tv ?? null
	};
}
```

(keep the comments on the first two fields and `fetchConfigView` as they are).

`src/lib/stores/config.ts`: replace `_metadataProvider` / `metadataProvider` with:

```ts
// The job page's search provider per media type; nulls until hydrated.
const _searchProviders = writable<{ movie: string | null; tv: string | null }>({ movie: null, tv: null });
export const searchProviders = { subscribe: _searchProviders.subscribe };
```

and in `hydrateConfig` set `_searchProviders.set({ movie: cfg.search_provider_movie, tv: cfg.search_provider_tv })`, with `{ movie: null, tv: null }` in the `catch`.

`src/lib/components/TitleSearch.svelte` lines 8–13:

```ts
	import { searchProviders } from '$lib/stores/config';

	// Pretty label for the configured search provider of the current search
	// type; generic until the config store hydrates.
	const PROVIDER_LABELS: Record<string, string> = { tmdb: 'TMDb', omdb: 'OMDb', tvmaze: 'TVmaze', tvdb: 'TVDB' };
	let providerLabel = $derived(
		PROVIDER_LABELS[(searchType === 'tv' ? $searchProviders.tv : $searchProviders.movie) ?? ''] ?? 'OMDb/TMDb'
	);
```

(`searchType` is declared below at line 26 today; move this `$derived` below that declaration so it reads an initialised state.)

`FinishStep.svelte` line 65: `Titles looked up with ${config.search_provider_movie === 'omdb' ? 'OMDb' : 'TMDb'}.`

`settings-sections.ts`, the `Metadata` sections become:

```ts
	Metadata: [
		{
			title: 'Lookup',
			blurb: 'Which services identify a disc and answer the job page search box, and the disc databases ARM consults.',
			keys: [
				'search_provider_movie',
				'search_provider_tv',
				'search_provider_music',
				'thediscdb_enabled',
				'crc64service_enabled',
				'thediscdb_refresh_days'
			],
			columns: [['search_provider_movie', 'search_provider_tv', 'search_provider_music'], ['thediscdb_enabled', 'crc64service_enabled']],
			advanced: ['thediscdb_refresh_days']
		},
		{
			title: 'Movies and music',
			blurb: 'Online sources tried in order for movie discs and audio CDs.',
			keys: ['movie_sources', 'music_sources', 'movie_auto_apply', 'music_auto_apply'],
			columns: [['movie_sources', 'movie_auto_apply'], ['music_sources', 'music_auto_apply']]
		},
		{
			title: 'TV episodes',
			blurb: 'How ARM works out season and episode numbers for TV discs.',
			summary: 'tv-episodes',
			keys: ['disc_hint_sources', 'episode_sources', 'episode_auto_apply', 'episode_match_tolerance_seconds'],
			columns: [['disc_hint_sources'], ['episode_sources']],
			advanced: ['episode_match_tolerance_seconds']
		},
		{
			title: 'API keys',
			blurb: 'Stored on the server. A key that is already set shows as hidden; leave it blank to keep it.',
			keys: ['tmdb_api_key', 'omdb_api_key', 'tvdb_api_key', 'makemkv_key']
		}
	],
```

The `settings-sections.test.ts` test "returns empty columns and advanced for a section that declares neither" now targets a Lookup section that declares both; change that test to use the `'API keys'` section with `meta('tmdb_api_key', 'string')` and expect `fields` `['tmdb_api_key']`, keeping its intent.

- [ ] **Step 5: Run the UI checks**

Run: `cd services/ui-neu/frontend && npm run check && npx vitest run && npm run lint`
Expected: svelte-check clean (no remaining reference to `metadata_provider` or `metadataProvider`: confirm with `grep -rn "metadata_provider\|metadataProvider" src | grep -v api.gen.ts` → no output); all vitest suites pass; lint clean. Run `npm run format` if Prettier reports changes, and include them.

- [ ] **Step 6: Full pre-commit and commit**

Run from the repo root: `uv run pre-commit run --all-files` (eslint/prettier hooks now run because `node_modules` is installed).
Expected: all hooks pass.

```bash
git add services/ui-neu/openapi.snapshot.json services/ui-neu/frontend/src
git commit -m "feat(ui): search providers replace metadata_provider; identification settings on the Metadata tab"
```

---

### Task 5: Spec and tracking updates

**Files:**
- Modify: `docs/superpowers/specs/2026-10-14-identification-sources-design.md` (§5.4 heading "migration 0044" → "migration 0045"; the `metadata_provider` row of the column table; §6 PR 1 bullet; §10)

- [ ] **Step 1: Edit the spec**

- Change the §5.4 heading to `### 5.4 Data model (migration 0045)` and the §6 PR 1 bullet's "Migration 0044" to "Migration 0045".
- Append to §10:

```markdown
- Resolved in PR 1: `search_provider_tv` offers `tmdb, tvmaze, tvdb` (no OMDb row, matching the
  v4.2 TV list); a choice with no adapter yet falls back to the first usable ranked source with an
  INFO log until PR 2b lands. Consequence for PR 2: once the dispatcher's TV order reads
  `episode_sources`, OMDb series search is gone, so PR 2b (keyless TVmaze title search) must land
  before PR 2, or an OMDb-only install loses TV title search.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-10-14-identification-sources-design.md docs/superpowers/plans/2026-10-15-identification-sources-pr1.md
git commit -m "docs: identification spec follows PR 1 (migration 0045, TV search providers)"
```

---

## Self-review notes

- **Spec coverage.** §5.4 columns and seeding: Task 1. Field metadata and schemas: Task 2. §5.2 `search_source` on `search_provider_*`: Task 3. Validation incl. criterion 7 ("needs its API key"): Task 3. #219 re-resolve on the new lists: Task 3. Regen and UI readers: Task 4. D-9 wizard: no new field is tagged; the step rename to "Identification" is deferred with the UI redesign PR. D-2 Step 2 row: the toggle exists and renders on the Metadata tab; the card layout is the UI PR.
- **Deviations recorded.** Migration number 0045 (0044 taken). `search_provider_tv` values follow the owner's #258 note rather than the registry's current adapters; the registry's `ONLINE_SOURCE_VALUES` table mirrors the metadata enum values and Task 3's suite plus the existing `test_search_provider_literal_matches_registry` keep movie/music pinned; a test pinning `ONLINE_SOURCE_VALUES` to `CONFIG_FIELD_META` is worth adding in Task 3 if time allows (`for key, mt in (("movie_sources","movie"),("episode_sources","tv"),("music_sources","music")): assert tuple(meta[key].enum_values) == ONLINE_SOURCE_VALUES[mt]`).
- **Type consistency.** `search_provider_setting(cfg, media_type)` is used in `_to_view` and `search_source`; readers return tuples, the view converts with `list(...)`. UI store name `searchProviders` is used in `TitleSearch.svelte` and the badge test.
- **Review Focus** items 1–5 each have a named test above.
