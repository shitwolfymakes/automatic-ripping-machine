# TheDiscDB Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Match scanned discs against a local snapshot of TheDiscDB and auto-apply the disc map (title labels, main-feature selection, episode numbering, suggested filenames, exact TMDb/IMDb identity).

**Architecture:** The ripper computes TheDiscDB's `ContentHash` (MD5 over stream-file sizes, read from the block device with pycdlib — no mount) and ships it as a `("thediscdb", <hash>)` fingerprint. The backend keeps a SQLite index built from the MIT-licensed `TheDiscDb/data` GitHub tarball, refreshed on a schedule; the identify flow looks up the fingerprint, stores the disc map in `job.metadata_json["thediscdb"]`, applies it to Track rows at both track-creation sites, and uses the release's IMDb ID for exact metadata identify.

**Tech Stack:** Python 3.14, FastAPI, SQLModel/Alembic, pycdlib (already present via `pydvdid_m`), httpx, sqlite3 (stdlib), pytest.

**Spec:** `docs/superpowers/specs/2026-08-06-thediscdb-design.md`

## Global Constraints

- Branch: `feat/media-identification`. Commit after each task; NO Claude attribution lines in commits.
- Gates that must stay green: `ruff check .`, `mypy`, backend+ripper pytest suites, single alembic head.
- Every failure mode falls through silently to current behavior (log info/debug) — TheDiscDB must never block a rip.
- Hash format: 32-hex UPPERCASE MD5. Fingerprint algo string: `"thediscdb"` (lowercase).
- File-set rule (confirmed from ImportBuddy `DiskContentHash.cs`): Blu-ray/UHD = `BDMV/STREAM/*.m2ts`; DVD = ALL files in `VIDEO_TS/`; sort by filename ascending; MD5 over each file's size packed as 8-byte little-endian (`struct.pack("<q", size)`).
- TheDiscDB JSON is PascalCase (`Titles`, `SourceFile`, `Item`, `Type`, `Season`, `Episode`, `Comment`).
- `Track.source_ref` for video titles is `str(ScanTitle.index)` (see `track_selection.py`); `ScanTitle.source_file` holds the mpls/vob name that joins to TheDiscDB `SourceFile`.

---

### Task 1: Ripper — ContentHash computation

**Files:**
- Create: `services/ripper/arm_ripper/scan/thediscdb_hash.py`
- Test: `services/ripper/tests/test_thediscdb_hash.py`

**Interfaces:**
- Produces: `compute_content_hash(sizes: Sequence[int]) -> str | None`; `collect_hash_files(source_path: str) -> list[tuple[str, int]] | None`; `probe_thediscdb_hash(source_path: str) -> str | None` (sync, exception-free).
- Consumes: nothing from other tasks. pycdlib is already an installed transitive dep (`pydvdid_m`); add it as a direct dependency of the ripper package.

- [ ] **Step 1: Write the failing tests**

```python
# services/ripper/tests/test_thediscdb_hash.py
"""ContentHash (TheDiscDB) unit coverage: MD5-over-sizes vectors, ISO name
cleaning, file-set selection (BDMV/STREAM/*.m2ts vs VIDEO_TS/*), soft-fail."""

from unittest import mock

from arm_ripper.scan.thediscdb_hash import (
    _clean_iso_name,
    _hash_from_listing,
    compute_content_hash,
    probe_thediscdb_hash,
)


def test_content_hash_known_vector() -> None:
    # MD5 over 8-byte little-endian sizes, uppercase hex.
    assert compute_content_hash([123, 456789, 9876543210]) == "D9041EE29C567CFF50030C5FD0DDDF68"


def test_content_hash_single_file_vector() -> None:
    assert compute_content_hash([36380633088]) == "51FA3253A72C8BA91430EBA8AA80AB3D"


def test_content_hash_empty_returns_none_marker() -> None:
    # No files -> no hash (never emit the MD5-of-nothing).
    assert compute_content_hash([]) is None


def test_clean_iso_name_strips_version_suffix() -> None:
    assert _clean_iso_name("VTS_01_1.VOB;1") == "VTS_01_1.VOB"
    assert _clean_iso_name("00003.m2ts") == "00003.m2ts"


def test_hash_from_listing_sorts_by_name() -> None:
    # Same files, shuffled input order -> same hash (ordering is by name).
    a = _hash_from_listing([("00002.m2ts", 20), ("00001.m2ts", 10)])
    b = _hash_from_listing([("00001.m2ts", 10), ("00002.m2ts", 20)])
    assert a == b == compute_content_hash([10, 20])


def test_hash_from_listing_bluray_filters_m2ts() -> None:
    # Filtering happens in collect_hash_files; _hash_from_listing hashes
    # exactly what it is given — assert it does NOT filter.
    with_extra = _hash_from_listing([("00001.m2ts", 10), ("index.bdmv", 5)])
    assert with_extra == compute_content_hash([5, 10])  # index.bdmv sorts first


def test_probe_soft_fails_on_unreadable_source() -> None:
    with mock.patch(
        "arm_ripper.scan.thediscdb_hash.collect_hash_files",
        side_effect=OSError("boom"),
    ):
        assert probe_thediscdb_hash("/dev/sr0") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/ripper && uv run pytest tests/test_thediscdb_hash.py -v`
Expected: FAIL — `ModuleNotFoundError: arm_ripper.scan.thediscdb_hash`

- [ ] **Step 3: Write the implementation**

```python
# services/ripper/arm_ripper/scan/thediscdb_hash.py
"""TheDiscDB ContentHash: MD5 over stream-file sizes, read via pycdlib.

Mirrors ImportBuddy's DiskContentHash.cs + HashingExtensions.cs exactly:
Blu-ray/UHD hashes `BDMV/STREAM/*.m2ts`; DVD hashes ALL files under
`VIDEO_TS/`; files are sorted by name ascending; each file's size is fed to
MD5 as 8 little-endian bytes. Reads the UDF/ISO tree straight from the block
device (or an ISO file) — same no-mount pattern as disc_probe's CRC64.

Soft-fail everywhere: any error returns None and the fingerprint is simply
absent (a TheDiscDB miss can only ever degrade to today's behavior).
"""
from __future__ import annotations

import hashlib
import logging
import struct
from collections.abc import Sequence

logger = logging.getLogger(__name__)


def compute_content_hash(sizes: Sequence[int]) -> str | None:
    """MD5 over each size as 8-byte little-endian, uppercase hex.

    Sizes must already be in filename order. Returns None for an empty list
    (never emit MD5-of-nothing — it would collide across all empty discs).
    """
    if not sizes:
        return None
    md5 = hashlib.md5()
    for size in sizes:
        md5.update(struct.pack("<q", size))
    return md5.hexdigest().upper()


def _clean_iso_name(name: str) -> str:
    """Strip ISO9660 `;1` version suffixes; UDF names pass through."""
    return name.split(";", 1)[0]


def _hash_from_listing(files: list[tuple[str, int]]) -> str | None:
    """Hash a (name, size) listing: sort by name, hash sizes. No filtering —
    the caller decides the file set."""
    ordered = sorted(files, key=lambda item: item[0])
    return compute_content_hash([size for _, size in ordered])


def collect_hash_files(source_path: str) -> list[tuple[str, int]] | None:
    """Read the hashable file set from a device or ISO path via pycdlib.

    Blu-ray/UHD: `/BDMV/STREAM/*.m2ts` (UDF). DVD: every file in `/VIDEO_TS`
    (ISO9660/UDF). Returns None when neither directory exists (CD, data disc).
    """
    from pycdlib import PyCdlib  # lazy: keep import cost off the hot path

    iso = PyCdlib()
    iso.open(source_path)
    try:
        # Blu-ray first: UDF filesystem, STREAM directory.
        try:
            listing = [
                (_clean_iso_name(child.file_identifier().decode("utf-8", "replace")), child.get_data_length())
                for child in iso.list_children(udf_path="/BDMV/STREAM")
                if child is not None and not child.is_dir()
            ]
            m2ts = [(n, s) for n, s in listing if n.lower().endswith(".m2ts")]
            if m2ts:
                return m2ts
        except Exception:  # noqa: BLE001 — no UDF / no BDMV: fall through to DVD
            pass

        for kwargs in ({"iso_path": "/VIDEO_TS"}, {"udf_path": "/VIDEO_TS"}):
            try:
                return [
                    (_clean_iso_name(child.file_identifier().decode("utf-8", "replace")), child.get_data_length())
                    for child in iso.list_children(**kwargs)  # type: ignore[arg-type]
                    if child is not None and not child.is_dir() and not child.is_dot() and not child.is_dotdot()
                ]
            except Exception:  # noqa: BLE001 — try next namespace
                continue
        return None
    finally:
        iso.close()


def probe_thediscdb_hash(source_path: str) -> str | None:
    """Compute the ContentHash for a device/ISO path. Never raises."""
    try:
        files = collect_hash_files(source_path)
    except Exception as e:  # noqa: BLE001 — pycdlib raises many flavors
        logger.debug("thediscdb hash probe failed for %s: %s", source_path, e)
        return None
    if not files:
        return None
    return _hash_from_listing(files)
```

Note: `is_dot()`/`is_dotdot()` exist on ISO9660 dir records; UDF children may
not have them — if mypy or runtime complains for the UDF branch, guard with
`getattr(child, "is_dot", lambda: False)()`. `get_data_length()` and
`file_identifier()` are the pycdlib child-record APIs (same ones `pydvdid_m`
relies on).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/ripper && uv run pytest tests/test_thediscdb_hash.py -v`
Expected: 7 PASS

- [ ] **Step 5: Add pycdlib as a direct ripper dependency**

In `services/ripper/pyproject.toml`, add `pycdlib` to `[project] dependencies`
(same style as the existing entries; it is already in `uv.lock` transitively
via `pydvdid_m`). Run `uv lock` from the repo root if the lockfile needs the
direct edge recorded.

- [ ] **Step 6: Lint, typecheck, commit**

```bash
ruff check services/ripper/arm_ripper/scan/thediscdb_hash.py services/ripper/tests/test_thediscdb_hash.py
cd services/ripper && uv run mypy arm_ripper/scan/thediscdb_hash.py
git add -A && git commit -m "feat(ripper): TheDiscDB ContentHash computation (MD5 over stream-file sizes)"
```

---

### Task 2: Ripper — emit the fingerprint from the disc probe

**Files:**
- Modify: `services/ripper/arm_ripper/scan/disc_probe.py` (DiscProbe dataclass + `probe_disc`)
- Modify: `services/ripper/arm_ripper/scan/makemkv.py:319-333` (fingerprint assembly)
- Test: `services/ripper/tests/test_disc_probe.py` (extend)

**Interfaces:**
- Consumes: `probe_thediscdb_hash(source_path) -> str | None` from Task 1.
- Produces: `DiscProbe` gains field `thediscdb: str | None`; `ScanResult.fingerprints` gains `DiscFingerprintInput(algo="thediscdb", value=<hash>)` when computed.

- [ ] **Step 1: Read the two modify-sites**

Read `services/ripper/arm_ripper/scan/disc_probe.py` fully (~150 lines): note
how `_compute_crc` is invoked from `probe_disc` (sync helper wrapped by the
async probe — mirror that pattern exactly for the new hash) and how `DiscProbe`
is constructed. Read `services/ripper/arm_ripper/scan/makemkv.py:315-335` for
the fingerprint list assembly.

- [ ] **Step 2: Write the failing test**

Extend `services/ripper/tests/test_disc_probe.py`, following its existing
mock style (it already mocks the CRC path — copy the established fixture
approach for device readiness):

```python
async def test_probe_disc_includes_thediscdb_hash(monkeypatch) -> None:
    from arm_ripper.scan import disc_probe

    monkeypatch.setattr(disc_probe, "_compute_crc", lambda _p: "AAAA000011112222")
    monkeypatch.setattr(
        disc_probe, "probe_thediscdb_hash", lambda _p: "D9041EE29C567CFF50030C5FD0DDDF68"
    )
    monkeypatch.setattr(disc_probe, "await_device_ready", _always_ready_async())  # reuse file's helper
    probe = await disc_probe.probe_disc("/dev/sr0")
    assert probe.thediscdb == "D9041EE29C567CFF50030C5FD0DDDF68"


async def test_probe_disc_thediscdb_none_on_failure(monkeypatch) -> None:
    from arm_ripper.scan import disc_probe

    monkeypatch.setattr(disc_probe, "_compute_crc", lambda _p: None)
    monkeypatch.setattr(disc_probe, "probe_thediscdb_hash", lambda _p: None)
    monkeypatch.setattr(disc_probe, "await_device_ready", _always_ready_async())
    probe = await disc_probe.probe_disc("/dev/sr0")
    assert probe.thediscdb is None
```

(`_always_ready_async` is illustrative — reuse whatever helper/fixture the
file already uses to fake `await_device_ready` returning True. If none
exists, add `async def _ready(_p): return True` and monkeypatch with it.)

- [ ] **Step 3: Run to verify failure**

Run: `cd services/ripper && uv run pytest tests/test_disc_probe.py -v -k thediscdb`
Expected: FAIL — `DiscProbe` has no field/attr `thediscdb`

- [ ] **Step 4: Implement**

In `disc_probe.py`:

```python
from arm_ripper.scan.thediscdb_hash import probe_thediscdb_hash  # top of file

@dataclass(frozen=True)
class DiscProbe:
    crc64: str | None
    thediscdb: str | None = None
```

In `probe_disc`, where `_compute_crc` runs (inside the same thread offload if
one is used), also compute `thediscdb = probe_thediscdb_hash(device_path)` and
pass it to the `DiscProbe(...)` constructor. Every return path that builds a
`DiscProbe` must set the field (failure paths pass `None`).

In `makemkv.py` (fingerprint assembly around line 325):

```python
    if probe.thediscdb:
        fingerprints.append(DiscFingerprintInput(algo="thediscdb", value=probe.thediscdb))
```

- [ ] **Step 5: Run the full ripper suite**

Run: `cd services/ripper && uv run pytest -q`
Expected: all pass (existing DiscProbe constructions in tests keep working
because the new field has a default).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(ripper): emit thediscdb fingerprint from disc probe"
```

---

### Task 3: Data model — Track.season, Config toggles, migration 0029

**Files:**
- Modify: `packages/arm_common/arm_common/models/track.py`
- Modify: `packages/arm_common/arm_common/models/config.py`
- Modify: `packages/arm_common/arm_common/config_metadata.py`
- Create: `services/backend/migrations/versions/0029_thediscdb.py`
- Test: existing suites + alembic single-head check

**Interfaces:**
- Produces: `Track.season: int | None`; `Config.thediscdb_enabled: bool` (default true), `Config.thediscdb_refresh_days: int` (default 7), `Config.thediscdb_refreshed_at: datetime | None`.

- [ ] **Step 1: Model fields**

`track.py` — next to `episode_number` (line ~35):

```python
    season: int | None = Field(default=None)
```

`config.py` — follow the `makemkv_sdf_*` block style (line ~48):

```python
    # TheDiscDB disc-map matching (docs/superpowers/specs/2026-08-06-thediscdb-design.md).
    thediscdb_enabled: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="true"))
    thediscdb_refresh_days: int = Field(sa_column=Column(Integer, nullable=False, server_default="7"))
    thediscdb_refreshed_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
```

- [ ] **Step 2: Migration**

```python
# services/backend/migrations/versions/0029_thediscdb.py
"""TheDiscDB integration: tracks.season + config toggle/refresh columns.

Pure additive, reversible. Mirrors 0026's config-columns pattern.

Revision ID: 0029_thediscdb
Revises: 0028_user_role_disabled
Create Date: 2026-08-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_thediscdb"
down_revision: Union[str, None] = "0028_user_role_disabled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tracks", sa.Column("season", sa.Integer(), nullable=True))
    op.add_column(
        "config",
        sa.Column("thediscdb_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "config",
        sa.Column("thediscdb_refresh_days", sa.Integer(), nullable=False, server_default=sa.text("7")),
    )
    op.add_column("config", sa.Column("thediscdb_refreshed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("config", "thediscdb_refreshed_at")
    op.drop_column("config", "thediscdb_refresh_days")
    op.drop_column("config", "thediscdb_enabled")
    op.drop_column("tracks", "season")
```

Check the exact tracks table name first: `grep -n '__tablename__' packages/arm_common/arm_common/models/track.py` — use what it says (expected `tracks`).

- [ ] **Step 3: Config metadata entries**

In `config_metadata.py`, append to the Metadata group (copy the
`ConfigFieldMeta` shape used by `metadata_provider`):

```python
    ConfigFieldMeta(
        key="thediscdb_enabled",
        group="Metadata",
        tier="operator",
        label="TheDiscDB disc matching",
        help="Match discs against the local TheDiscDB snapshot to label titles, pick the main feature, and name extras/episodes.",
        type="bool",
        editable=True,
    ),
    ConfigFieldMeta(
        key="thediscdb_refresh_days",
        group="Metadata",
        tier="operator",
        label="TheDiscDB refresh interval (days)",
        help="How often the backend refreshes its TheDiscDB snapshot from GitHub.",
        type="int",
        editable=True,
    ),
```

- [ ] **Step 4: Verify heads + suites**

```bash
cd services/backend && uv run alembic heads   # exactly one head: 0029_thediscdb
uv run pytest -q                              # config metadata/model tests still green
```

If a config-metadata completeness test exists (grep `CONFIG_FIELD_META` in
backend tests), it will fail until the entries match the model — fix per its
assertion message.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(db): thediscdb config + track.season (migration 0029)"
```

---

### Task 4: Backend — snapshot store and index builder

**Files:**
- Create: `services/backend/arm_backend/thediscdb/__init__.py` (empty)
- Create: `services/backend/arm_backend/thediscdb/snapshot.py`
- Modify: `services/backend/arm_backend/config.py` (Settings: add `ARM_THEDISCDB_PATH: str = "/data/cache/thediscdb"`)
- Test: `services/backend/tests/test_thediscdb_snapshot.py`

**Interfaces:**
- Produces:
  - `@dataclass DiscMatch: kind: str; title_slug: str; release_slug: str; disc: dict; metadata: dict; release: dict`
  - `class SnapshotStore: __init__(self, dir_path: Path)`, `lookup(self, content_hash: str) -> DiscMatch | None` (sync, sqlite3), `count(self) -> int`, `exists(self) -> bool`
  - `build_index(tarball: Path, dest_sqlite: Path) -> int` (returns disc count; atomic via `.new` + `os.replace`)
  - `async refresh(http: httpx.AsyncClient, dir_path: Path) -> int`
  - `TARBALL_URL = "https://codeload.github.com/TheDiscDb/data/tar.gz/refs/heads/main"`

- [ ] **Step 1: Write the failing tests**

```python
# services/backend/tests/test_thediscdb_snapshot.py
"""Snapshot index: tarball -> sqlite build, lookup, atomic replace."""
from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

from arm_backend.thediscdb.snapshot import SnapshotStore, build_index

DISC = {
    "Index": 1,
    "Slug": "blu-ray",
    "Format": "Blu-Ray",
    "ContentHash": "2D61282D8DA5EAC2CA87B451BCE9A055",
    "GlobalDiscId": "BDE5486DBE5FA6E7B9D66485CB9AA774C527D8EE",
    "Titles": [
        {
            "Index": 0,
            "Comment": "Main.mkv",
            "SourceFile": "00001.mpls",
            "Duration": "2:11:34",
            "Item": {"Title": "Round Midnight", "Type": "MainMovie"},
        }
    ],
}
METADATA = {"Title": "Round Midnight", "Year": 1986, "ExternalIds": {"Tmdb": "14670", "Imdb": "tt0090557"}}
RELEASE = {"Slug": "2022-criterion-blu-ray", "Title": "Criterion Blu-ray"}


def _mini_tarball(path: Path) -> Path:
    """data-main/data/movie/<title>/<release>/disc01.json + siblings."""
    tar_path = path / "data.tar.gz"
    base = "data-main/data/movie/Round Midnight (1986)"
    with tarfile.open(tar_path, "w:gz") as tar:
        for name, obj in [
            (f"{base}/metadata.json", METADATA),
            (f"{base}/2022-criterion-blu-ray/release.json", RELEASE),
            (f"{base}/2022-criterion-blu-ray/disc01.json", DISC),
        ]:
            raw = json.dumps(obj).encode()
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
    return tar_path


def test_build_and_lookup(tmp_path: Path) -> None:
    tarball = _mini_tarball(tmp_path)
    dest = tmp_path / "index.sqlite"
    count = build_index(tarball, dest)
    assert count == 1
    store = SnapshotStore(tmp_path)
    assert store.exists()
    assert store.count() == 1
    hit = store.lookup("2D61282D8DA5EAC2CA87B451BCE9A055")
    assert hit is not None
    assert hit.kind == "movie"
    assert hit.metadata["ExternalIds"]["Imdb"] == "tt0090557"
    assert hit.disc["Titles"][0]["SourceFile"] == "00001.mpls"
    assert store.lookup("00000000000000000000000000000000") is None


def test_lookup_is_case_insensitive(tmp_path: Path) -> None:
    build_index(_mini_tarball(tmp_path), tmp_path / "index.sqlite")
    store = SnapshotStore(tmp_path)
    assert store.lookup("2d61282d8da5eac2ca87b451bce9a055") is not None


def test_build_replaces_atomically(tmp_path: Path) -> None:
    dest = tmp_path / "index.sqlite"
    build_index(_mini_tarball(tmp_path), dest)
    before = dest.stat().st_mtime_ns
    build_index(_mini_tarball(tmp_path), dest)  # rebuild over live index
    assert dest.exists() and SnapshotStore(tmp_path).count() == 1
    assert dest.stat().st_mtime_ns != before
    assert not dest.with_suffix(".sqlite.new").exists()


def test_missing_store(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "nope")
    assert not store.exists()
    assert store.lookup("2D61282D8DA5EAC2CA87B451BCE9A055") is None
    assert store.count() == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `cd services/backend && uv run pytest tests/test_thediscdb_snapshot.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```python
# services/backend/arm_backend/thediscdb/snapshot.py
"""Local TheDiscDB snapshot: GitHub data tarball -> sqlite index -> lookups.

The data repo (github.com/TheDiscDb/data, MIT) lays out
`data/<movie|series|sets>/<Title (Year)>/[metadata.json + <release>/
(release.json + disc*.json)]`. We index every disc*.json by its ContentHash
(uppercased) with its sibling metadata/release JSON attached. `sets/` is
skipped in v1 (deferred; different grouping shape).

Refresh keeps the previous index on any failure (mirror philosophy: a
third-party outage must never break local operation). Build is atomic:
write `<dest>.new`, then os.replace over the live file.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TARBALL_URL = "https://codeload.github.com/TheDiscDb/data/tar.gz/refs/heads/main"
INDEX_FILENAME = "index.sqlite"

# <root>/data/(movie|series)/<title-dir>/<release-dir>/disc<NN>.json
_DISC_RE = re.compile(r"^[^/]+/data/(movie|series)/([^/]+)/([^/]+)/disc\d+\.json$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS discs (
    content_hash TEXT PRIMARY KEY,
    global_disc_id TEXT,
    kind TEXT NOT NULL,
    title_slug TEXT NOT NULL,
    release_slug TEXT NOT NULL,
    disc_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    release_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_discs_global ON discs(global_disc_id);
"""


@dataclass(slots=True)
class DiscMatch:
    kind: str
    title_slug: str
    release_slug: str
    disc: dict[str, Any]
    metadata: dict[str, Any]
    release: dict[str, Any]


def build_index(tarball: Path, dest_sqlite: Path) -> int:
    """Parse the data tarball into a fresh sqlite index; atomic replace."""
    # Pass 1: read everything grouped by directory.
    discs: list[tuple[str, str, str, dict[str, Any]]] = []  # (kind, title_dir, release_dir, disc)
    metadata_by_title: dict[str, dict[str, Any]] = {}
    release_by_dir: dict[str, dict[str, Any]] = {}

    def _load(tar: tarfile.TarFile, member: tarfile.TarInfo) -> dict[str, Any] | None:
        fh = tar.extractfile(member)
        if fh is None:
            return None
        try:
            loaded = json.load(fh)
            return loaded if isinstance(loaded, dict) else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.debug("thediscdb: skipping malformed %s", member.name)
            return None

    with tarfile.open(tarball, "r:gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            parts = member.name.split("/")
            m = _DISC_RE.match(member.name)
            if m:
                obj = _load(tar, member)
                if obj and obj.get("ContentHash"):
                    discs.append((m.group(1), m.group(2), m.group(3), obj))
            elif len(parts) >= 4 and parts[-1] == "metadata.json" and parts[1] == "data":
                obj = _load(tar, member)
                if obj is not None:
                    metadata_by_title["/".join(parts[2:4])] = obj  # "<kind>/<title-dir>"
            elif parts[-1] == "release.json" and len(parts) >= 5 and parts[1] == "data":
                obj = _load(tar, member)
                if obj is not None:
                    release_by_dir["/".join(parts[2:5])] = obj  # "<kind>/<title>/<release>"

    new_path = dest_sqlite.with_suffix(".sqlite.new")
    new_path.unlink(missing_ok=True)
    dest_sqlite.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(new_path)
    try:
        conn.executescript(_SCHEMA)
        rows = 0
        for kind, title_dir, release_dir, disc in discs:
            meta = metadata_by_title.get(f"{kind}/{title_dir}", {})
            release = release_by_dir.get(f"{kind}/{title_dir}/{release_dir}", {})
            conn.execute(
                "INSERT OR REPLACE INTO discs VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(disc["ContentHash"]).upper(),
                    (str(disc["GlobalDiscId"]).upper() if disc.get("GlobalDiscId") else None),
                    kind,
                    str(meta.get("Slug") or title_dir),
                    str(release.get("Slug") or release_dir),
                    json.dumps(disc),
                    json.dumps(meta),
                    json.dumps(release),
                ),
            )
            rows += 1
        conn.commit()
    finally:
        conn.close()
    os.replace(new_path, dest_sqlite)
    logger.info("thediscdb: index built with %d discs", rows)
    return rows


class SnapshotStore:
    """Read-side handle. sqlite3 opens are per-call (cheap, and immune to the
    os.replace swap under a running process)."""

    def __init__(self, dir_path: Path) -> None:
        self._path = Path(dir_path) / INDEX_FILENAME

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def count(self) -> int:
        if not self.exists():
            return 0
        with sqlite3.connect(f"file:{self._path}?mode=ro", uri=True) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM discs").fetchone()[0])

    def lookup(self, content_hash: str) -> DiscMatch | None:
        if not content_hash or not self.exists():
            return None
        with sqlite3.connect(f"file:{self._path}?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT kind, title_slug, release_slug, disc_json, metadata_json, release_json"
                " FROM discs WHERE content_hash = ?",
                (content_hash.upper(),),
            ).fetchone()
        if row is None:
            return None
        return DiscMatch(
            kind=row[0],
            title_slug=row[1],
            release_slug=row[2],
            disc=json.loads(row[3]),
            metadata=json.loads(row[4]),
            release=json.loads(row[5]),
        )


async def refresh(http: httpx.AsyncClient, dir_path: Path) -> int:
    """Download the tarball and rebuild the index. Raises on failure — the
    caller logs and keeps the previous index."""
    dir_path.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        async with http.stream("GET", TARBALL_URL, follow_redirects=True, timeout=300.0) as resp:
            resp.raise_for_status()
            with open(tmp_path, "wb") as out:
                async for chunk in resp.aiter_bytes():
                    out.write(chunk)
        return build_index(tmp_path, Path(dir_path) / INDEX_FILENAME)
    finally:
        tmp_path.unlink(missing_ok=True)
```

Add to `services/backend/arm_backend/config.py` Settings (next to
`ARM_IMAGE_CACHE_PATH`):

```python
    # TheDiscDB snapshot index (built from the GitHub data tarball).
    ARM_THEDISCDB_PATH: str = "/data/cache/thediscdb"
```

- [ ] **Step 4: Run tests**

Run: `cd services/backend && uv run pytest tests/test_thediscdb_snapshot.py -v`
Expected: 4 PASS. Note `test_build_replaces_atomically` asserts the `.new`
suffix path — `Path("index.sqlite").with_suffix(".sqlite.new")` yields
`index.sqlite.new`; adjust the test's suffix expression if needed to match.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(backend): TheDiscDB snapshot store + tarball index builder"
```

---

### Task 5: Backend — matcher (join, map, apply-to-tracks)

**Files:**
- Create: `services/backend/arm_backend/thediscdb/matcher.py`
- Test: `services/backend/tests/test_thediscdb_matcher.py`

**Interfaces:**
- Consumes: `DiscMatch` from Task 4; `ScanResult`/`ScanTitle` from `arm_common.schemas`; `Track` model.
- Produces:
  - `parse_duration(text: str) -> int | None` ("2:11:34" → 7894; "56:03" → 3363)
  - `build_map(match: DiscMatch, scan: ScanResult) -> dict[str, Any]` — JSON-safe record stored at `job.metadata_json["thediscdb"]`; shape:
    `{"release_slug", "title_slug", "kind", "matched": {"<source_ref>": {"type", "title", "season", "episode", "filename"}}}`
  - `async apply_map(session: AsyncSession, job: Job) -> int` — stamps Track rows from the stored map; idempotent; returns count updated.

- [ ] **Step 1: Write the failing tests**

```python
# services/backend/tests/test_thediscdb_matcher.py
"""Matcher: duration parse, SourceFile join, map build, track stamping."""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.thediscdb.matcher import build_map, parse_duration  # noqa: E402
from arm_backend.thediscdb.snapshot import DiscMatch  # noqa: E402
from arm_common.schemas import ScanResult, ScanTitle  # noqa: E402
from arm_common import DiscType  # noqa: E402


def _match(titles: list[dict], kind: str = "movie") -> DiscMatch:
    return DiscMatch(
        kind=kind,
        title_slug="round-midnight-1986",
        release_slug="2022-criterion-blu-ray",
        disc={"ContentHash": "2D61282D8DA5EAC2CA87B451BCE9A055", "Titles": titles},
        metadata={"Title": "Round Midnight", "Year": 1986, "ExternalIds": {"Imdb": "tt0090557", "Tmdb": "14670"}},
        release={"Slug": "2022-criterion-blu-ray"},
    )


def test_parse_duration() -> None:
    assert parse_duration("2:11:34") == 2 * 3600 + 11 * 60 + 34
    assert parse_duration("56:03") == 56 * 60 + 3
    assert parse_duration("") is None
    assert parse_duration("garbage") is None


def test_build_map_joins_by_source_file() -> None:
    match = _match(
        [
            {"SourceFile": "00001.mpls", "Duration": "2:11:34", "Comment": "Main.mkv",
             "Item": {"Title": "Round Midnight", "Type": "MainMovie"}},
            {"SourceFile": "00011.mpls", "Duration": "0:12:00", "Comment": "Making Of.mkv",
             "Item": {"Title": "The Making Of", "Type": "Featurette"}},
        ]
    )
    scan = ScanResult(
        disc_type=DiscType.BLURAY,
        titles=[
            ScanTitle(index=0, duration_seconds=7894, source_file="00001.mpls"),
            ScanTitle(index=1, duration_seconds=720, source_file="00011.mpls"),
            ScanTitle(index=2, duration_seconds=30, source_file="00029.mpls"),  # not in db
        ],
    )
    result = build_map(match, scan)
    assert result["release_slug"] == "2022-criterion-blu-ray"
    assert result["matched"]["0"] == {
        "type": "MainMovie", "title": "Round Midnight", "season": None, "episode": None,
        "filename": "Main.mkv",
    }
    assert result["matched"]["1"]["type"] == "Featurette"
    assert "2" not in result["matched"]  # unmatched scan title untouched


def test_build_map_series_episode_fields() -> None:
    match = _match(
        [{"SourceFile": "00800.mpls", "Duration": "1:06:55", "Comment": "1883 S01E01.mkv",
          "Item": {"Title": "1883", "Type": "Episode", "Season": "1", "Episode": "1"}}],
        kind="series",
    )
    scan = ScanResult(
        disc_type=DiscType.BLURAY,
        titles=[ScanTitle(index=5, duration_seconds=4015, source_file="00800.mpls")],
    )
    result = build_map(match, scan)
    assert result["matched"]["5"] == {
        "type": "Episode", "title": "1883", "season": 1, "episode": 1,
        "filename": "1883 S01E01.mkv",
    }


def test_build_map_duration_fallback_when_no_source_file() -> None:
    # DVD scans may lack source_file; duration within ±2s joins.
    match = _match(
        [{"SourceFile": "VTS_01_1.VOB", "Duration": "1:30:00", "Comment": "Movie.mkv",
          "Item": {"Title": "Movie", "Type": "MainMovie"}}]
    )
    scan = ScanResult(
        disc_type=DiscType.DVD,
        titles=[ScanTitle(index=0, duration_seconds=5401, source_file=None)],
    )
    result = build_map(match, scan)
    assert result["matched"]["0"]["type"] == "MainMovie"


def test_build_map_ambiguous_duration_no_join() -> None:
    # Two scan titles inside the window and no source_file -> ambiguous, skip.
    match = _match(
        [{"SourceFile": "VTS_01_1.VOB", "Duration": "1:30:00", "Comment": "Movie.mkv",
          "Item": {"Title": "Movie", "Type": "MainMovie"}}]
    )
    scan = ScanResult(
        disc_type=DiscType.DVD,
        titles=[
            ScanTitle(index=0, duration_seconds=5400, source_file=None),
            ScanTitle(index=1, duration_seconds=5401, source_file=None),
        ],
    )
    assert build_map(match, scan)["matched"] == {}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd services/backend && uv run pytest tests/test_thediscdb_matcher.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```python
# services/backend/arm_backend/thediscdb/matcher.py
"""Join a TheDiscDB disc map to a MakeMKV scan and stamp Track rows.

Join keys, in order: SourceFile == ScanTitle.source_file (case-insensitive);
else duration within ±2s IF exactly one scan title is in the window
(ambiguity -> no join; a wrong label is worse than no label).

The map is stored JSON-safe in job.metadata_json["thediscdb"] at identify
time, then applied to Track rows wherever tracks are created (identify's
review path and rip-start) — apply_map is idempotent and only fills
operator-empty fields, so re-running never clobbers operator edits.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.thediscdb.snapshot import DiscMatch
from arm_common import Job, Track
from arm_common.schemas import ScanResult

logger = logging.getLogger(__name__)

DURATION_WINDOW_SECONDS = 2
# TheDiscDB Item.Type values that should be selected (excluded=False).
_SELECT_TYPES = {"MainMovie", "Episode"}


def parse_duration(text: str) -> int | None:
    """"H:MM:SS" or "MM:SS" -> seconds; None on anything else."""
    if not text:
        return None
    parts = text.split(":")
    if not 2 <= len(parts) <= 3:
        return None
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return nums[0] * 3600 + nums[1] * 60 + nums[2]


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() != "" else None
    except (TypeError, ValueError):
        return None


def build_map(match: DiscMatch, scan: ScanResult) -> dict[str, Any]:
    """Produce the JSON-safe match record keyed by track source_ref."""
    by_source_file = {
        t.source_file.lower(): t for t in scan.titles if t.source_file
    }
    matched: dict[str, dict[str, Any]] = {}
    for entry in match.disc.get("Titles") or []:
        item = entry.get("Item") or {}
        source_file = str(entry.get("SourceFile") or "").lower()
        scan_title = by_source_file.get(source_file)
        if scan_title is None:
            # Duration fallback: unique scan title within ±2s.
            want = parse_duration(str(entry.get("Duration") or ""))
            if want is None:
                continue
            candidates = [
                t for t in scan.titles
                if t.source_file is None and abs(t.duration_seconds - want) <= DURATION_WINDOW_SECONDS
            ]
            if len(candidates) != 1:
                continue
            scan_title = candidates[0]
        ref = str(scan_title.index)
        if ref in matched:
            continue  # first disc entry wins; don't flip-flop on dupes
        matched[ref] = {
            "type": str(item.get("Type") or "Unknown"),
            "title": item.get("Title"),
            "season": _int_or_none(item.get("Season")),
            "episode": _int_or_none(item.get("Episode")),
            "filename": entry.get("Comment"),
        }
    return {
        "release_slug": match.release_slug,
        "title_slug": match.title_slug,
        "kind": match.kind,
        # Community credit (spec): who contributed this disc layout.
        "contributors": [
            str(c.get("Name")) for c in (match.release.get("Contributors") or []) if isinstance(c, dict) and c.get("Name")
        ],
        "matched": matched,
    }


def external_imdb_id(match: DiscMatch) -> str | None:
    ids = match.metadata.get("ExternalIds") or {}
    imdb = ids.get("Imdb")
    return str(imdb) if imdb else None


async def apply_map(session: AsyncSession, job: Job) -> int:
    """Stamp the stored map onto the job's Track rows. Idempotent; returns
    the number of tracks updated. Never raises on malformed map data."""
    record = (job.metadata_json or {}).get("thediscdb")
    if not isinstance(record, dict):
        return 0
    matched = record.get("matched")
    if not isinstance(matched, dict) or not matched:
        return 0
    tracks = (
        (await session.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all()
    )
    updated = 0
    for track in tracks:
        entry = matched.get(track.source_ref)
        if not isinstance(entry, dict):
            continue
        track.role = str(entry.get("type") or "Unknown")
        track.role_source = "thediscdb"
        if entry.get("title") and not track.episode_name:
            track.episode_name = str(entry["title"])
        if entry.get("season") is not None:
            track.season = int(entry["season"])
        if entry.get("episode") is not None and track.episode_number is None:
            track.episode_number = int(entry["episode"])
        if entry.get("filename") and not track.custom_filename:
            track.custom_filename = str(entry["filename"])
        if entry.get("type") in _SELECT_TYPES:
            track.excluded = False
        session.add(track)
        updated += 1
    if updated:
        await session.flush()
        logger.info("thediscdb: applied map to %d tracks job_id=%s", updated, job.id)
    return updated
```

Check `DiscType.BLURAY` member name before running (`grep -n 'BLURAY\|BLU_RAY' packages/arm_common/arm_common/enums.py`) and align the tests' constant.

- [ ] **Step 4: Run tests**

Run: `cd services/backend && uv run pytest tests/test_thediscdb_matcher.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(backend): TheDiscDB matcher — join disc map to scan, stamp tracks"
```

---

### Task 6: Backend — exact identify via matched IMDb ID

**Files:**
- Modify: `services/backend/arm_backend/metadata/dispatcher.py`
- Test: `services/backend/tests/test_metadata_dispatcher.py` (extend; if the file does not exist, create it with just this test using the same env-var preamble as other backend tests)

**Interfaces:**
- Consumes: existing `TMDBClient.find_by_imdb_id(imdb_id: str) -> MetadataResult` (`metadata/tmdb.py:153`), `MetadataDispatcher._call`.
- Produces: `async MetadataDispatcher.identify_from_imdb(self, imdb_id: str, cfg: Config) -> MetadataResult | None`.

- [ ] **Step 1: Write the failing test**

```python
async def test_identify_from_imdb_uses_tmdb_find(monkeypatch) -> None:
    import httpx
    from arm_backend.metadata import dispatcher as dispatcher_mod
    from arm_backend.metadata.base import MetadataResult

    class FakeTMDB:
        def __init__(self, api_key, http):  # matches TMDBClient signature
            pass

        async def find_by_imdb_id(self, imdb_id):
            assert imdb_id == "tt0090557"
            return MetadataResult(title="Round Midnight", year=1986, kind="movie")

    monkeypatch.setattr(dispatcher_mod, "TMDBClient", FakeTMDB)
    d = dispatcher_mod.MetadataDispatcher(httpx.AsyncClient())
    cfg = _cfg(tmdb_api_key="k")  # reuse/mirror the file's Config factory helper
    hit = await d.identify_from_imdb("tt0090557", cfg)
    assert hit is not None and hit.title == "Round Midnight"

    cfg_nokey = _cfg(tmdb_api_key=None)
    assert await d.identify_from_imdb("tt0090557", cfg_nokey) is None
```

(`_cfg` = however the surrounding test file constructs a `Config` — reuse it,
or construct `Config(id=..., ...)` minimally as sibling tests do.)

- [ ] **Step 2: Run to verify failure**

Run: `cd services/backend && uv run pytest tests -k identify_from_imdb -v`
Expected: FAIL — no attribute `identify_from_imdb`

- [ ] **Step 3: Implement** — add to `MetadataDispatcher` (after `_identify_video`):

```python
    async def identify_from_imdb(self, imdb_id: str, cfg: Config) -> MetadataResult | None:
        """Exact-ID identify for a TheDiscDB-matched disc. TMDb's /find
        endpoint resolves an IMDb id for both movies and TV; requires a TMDb
        key. Returns None (caller falls back to fuzzy identify) otherwise."""
        if not imdb_id or not cfg.tmdb_api_key:
            return None
        tmdb = TMDBClient(cfg.tmdb_api_key, self._http)
        return await self._call("tmdb_find_imdb", tmdb.find_by_imdb_id(imdb_id))
```

- [ ] **Step 4: Run tests, commit**

```bash
cd services/backend && uv run pytest -k identify_from_imdb -v   # PASS
git add -A && git commit -m "feat(backend): dispatcher.identify_from_imdb for exact TheDiscDB identity"
```

---

### Task 7: Backend — identify + rip-start integration

**Files:**
- Modify: `services/backend/arm_backend/routers/ripper.py` (identify endpoint ~298-460; rip_start track-creation site ~533)
- Modify: `services/backend/arm_backend/main.py` (lifespan: `app.state.thediscdb`)
- Test: `services/backend/tests/test_ripper_router.py` (extend)

**Interfaces:**
- Consumes: `SnapshotStore.lookup` (Task 4); `build_map`, `apply_map`, `external_imdb_id` (Task 5); `identify_from_imdb` (Task 6).
- Produces: `job.metadata_json["thediscdb"]` written on match; tracks stamped in both creation flows; `request.app.state.thediscdb: SnapshotStore`.

- [ ] **Step 1: Wire app.state**

In `main.py` lifespan, next to `app.state.dispatcher` (line ~149):

```python
    from arm_backend.thediscdb.snapshot import SnapshotStore

    app.state.thediscdb = SnapshotStore(Path(settings.ARM_THEDISCDB_PATH))
```

- [ ] **Step 2: Identify endpoint changes**

In `routers/ripper.py` identify(), AFTER the fingerprint-persist flush and
BEFORE the `if already_identified:` block, insert the lookup (new-job path
only — reuse guards forbid identity clobber):

```python
    thediscdb_match = None
    if not already_identified and cfg.thediscdb_enabled:
        store = getattr(request.app.state, "thediscdb", None)
        content_hash = next(
            (fp.value for fp in scan.fingerprints if fp.algo.lower() == "thediscdb" and fp.value),
            None,
        )
        if store is not None and content_hash:
            thediscdb_match = await asyncio.to_thread(store.lookup, content_hash)
            if thediscdb_match is not None:
                job.metadata_json = {
                    **(job.metadata_json or {}),
                    "thediscdb": {
                        **build_map(thediscdb_match, scan),
                        "matched_at": datetime.now(timezone.utc).isoformat(),
                    },
                }
                logger.info(
                    "thediscdb: matched job_id=%s release=%s", job.id, thediscdb_match.release_slug
                )
```

(The endpoint signature needs `request: Request` — it already imports
`Request` for the `_get_dispatcher`/`_get_hub` helpers; add `request: Request`
to the identify parameters and pass `request.app.state` as above. Imports:
`from arm_backend.thediscdb.matcher import apply_map, build_map, external_imdb_id`;
`MetadataResult` for the `_identify` annotation comes from
`arm_backend.metadata.base` — extend the existing import if it only brings in
`extract_poster_url`.)

In the `else:` (not already_identified) dispatch branch, try exact identity
first — replace the single `dispatcher.identify(...)` call inside the
`asyncio.wait_for` with:

```python
            async def _identify() -> MetadataResult | None:
                if thediscdb_match is not None:
                    imdb = external_imdb_id(thediscdb_match)
                    if imdb:
                        exact = await dispatcher.identify_from_imdb(imdb, cfg)
                        if exact is not None:
                            return exact
                return await dispatcher.identify(scan, cfg)

            result = await asyncio.wait_for(_identify(), timeout=DISPATCH_TIMEOUT_SECONDS)
```

After `_persist_review_tracks(session, job, scan)` (hold_for_review path),
add:

```python
                await apply_map(session, job)
```

Note the metadata_json merge later in the endpoint
(`job.metadata_json = {**(job.metadata_json or {}), "scan_result": ...}`)
preserves the `"thediscdb"` key — but the `result is not None` branch does
`job.metadata_json = result.payload` which would DROP it. Fix that line to
merge instead:

```python
            job.metadata_json = {**(job.metadata_json or {}), **result.payload}
```

- [ ] **Step 3: rip_start changes**

In `rip_start`, after `new_tracks = select_tracks(job.id, scan, preset)` and
the session.add/flush of those tracks, add:

```python
    await apply_map(session, job)
```

(Read the surrounding function first: the apply must run after the new
tracks are flushed and before the response is built. `apply_map` is a no-op
for jobs without a stored match, so the call is safe unconditionally.)

- [ ] **Step 4: Write the failing router test**

Extend `test_ripper_router.py` following its established fake-session +
dependency-override pattern (read the file's existing identify tests first
and mirror their setup exactly — drive row, config row, service-token header,
mocked dispatcher). New test, in outline with the file's idioms:

```python
def test_identify_thediscdb_match_stamps_map_and_uses_exact_identity() -> None:
    # Arrange per the file's existing identify-test fixture: fake session with
    # Drive + Config rows (set cfg.hold_for_review=True, cfg.thediscdb_enabled=True),
    # mocked dispatcher whose identify_from_imdb returns
    # MetadataResult(title="Round Midnight", year=1986, kind="movie")
    # and whose identify(...) fails the test if called (exact path must win).
    # app.state.thediscdb = FakeStore with:
    class FakeStore:
        def lookup(self, content_hash):
            assert content_hash == "2D61282D8DA5EAC2CA87B451BCE9A055"
            return DiscMatch(
                kind="movie", title_slug="round-midnight-1986",
                release_slug="2022-criterion-blu-ray",
                disc={"Titles": [{"SourceFile": "00001.mpls", "Duration": "2:11:34",
                                   "Comment": "Main.mkv",
                                   "Item": {"Title": "Round Midnight", "Type": "MainMovie"}}]},
                metadata={"ExternalIds": {"Imdb": "tt0090557"}},
                release={},
            )
    # Act: POST /api/ripper/identify with a ScanResult carrying
    # fingerprints=[{"algo": "thediscdb", "value": "2D61282D8DA5EAC2CA87B451BCE9A055"}]
    # and titles=[{"index": 0, "duration_seconds": 7894, "source_file": "00001.mpls"}].
    # Assert: response job title == "Round Midnight";
    #   job.metadata_json["thediscdb"]["matched"]["0"]["type"] == "MainMovie";
    #   the persisted Track with source_ref "0" has role == "MainMovie",
    #   role_source == "thediscdb", custom_filename == "Main.mkv", excluded is False.
```

Also add the negative test: `thediscdb_enabled=False` in config → FakeStore.lookup
must not be called (assert via a flag) and behavior is unchanged.

- [ ] **Step 5: Run backend suite**

Run: `cd services/backend && uv run pytest tests/test_ripper_router.py -v`
Expected: new tests PASS, all existing identify tests still PASS (the merge
fix in Step 2 changes `metadata_json` semantics: any existing test asserting
`job.metadata_json == result.payload` exactly must be updated to a superset
assertion — do that only where the test breaks, keeping its intent).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(backend): TheDiscDB match in identify — exact identity + track stamping"
```

---

### Task 8: Backend — refresh endpoint + startup/periodic refresh

**Files:**
- Modify: `services/backend/arm_backend/routers/system.py`
- Modify: `services/backend/arm_backend/main.py` (lifespan background task)
- Test: `services/backend/tests/test_system_router.py` (extend)

**Interfaces:**
- Consumes: `refresh(http, dir_path)`, `SnapshotStore` (Task 4); `Config.thediscdb_enabled/thediscdb_refresh_days/thediscdb_refreshed_at` (Task 3).
- Produces: `POST /api/system/thediscdb/refresh` (JWT-authed) → `{"discs": int, "refreshed_at": iso8601}`; lifespan task `_thediscdb_refresh_loop`.

- [ ] **Step 1: Endpoint (write test first)**

Extend `test_system_router.py` per its existing auth/fixture pattern:

Concrete steps (the file's local fixture names decide the exact spelling —
read its first existing POST-endpoint test and copy its client/session
setup verbatim):

1. Monkeypatch `arm_backend.routers.system.thediscdb_refresh` (the name as
   imported into `system.py`) with `async def _fake(http, path): return 4724`.
2. Issue an authed `POST /api/system/thediscdb/refresh` exactly as the
   sibling tests issue their authed requests.
3. Assert `resp.status_code == 200`, `resp.json()["discs"] == 4724`, and
   `datetime.fromisoformat(resp.json()["refreshed_at"])` parses.
4. Assert the config row's `thediscdb_refreshed_at` is now non-None.
5. Second test: monkeypatch the fake to `raise RuntimeError("down")` and
   assert the endpoint returns 502 (previous index untouched semantics).

Implementation in `system.py`:

```python
from arm_backend.thediscdb.snapshot import refresh as thediscdb_refresh
# `settings`, `Config`, `CONFIG_SINGLETON_ID`, `get_session` are already
# imported at the top of system.py — reuse them.


@router.post("/thediscdb/refresh", dependencies=[Depends(require_jwt)])
async def thediscdb_refresh_now(
    request: Request, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Rebuild the TheDiscDB snapshot index from GitHub, on demand."""
    try:
        count = await thediscdb_refresh(request.app.state.http, Path(settings.ARM_THEDISCDB_PATH))
    except Exception as e:  # noqa: BLE001 — network/tar/sqlite: report, keep old index
        raise HTTPException(status_code=502, detail=f"thediscdb refresh failed: {e}") from e
    now = datetime.now(timezone.utc)
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one()
    cfg.thediscdb_refreshed_at = now
    session.add(cfg)
    await session.commit()
    return {"discs": count, "refreshed_at": now.isoformat()}
```

(`HTTPException` import: the router file already uses FastAPI imports —
extend the existing import line.)

- [ ] **Step 2: Lifespan refresh loop**

In `main.py`, define near the other background helpers (`_refresh_gpu_inventory`):

```python
async def _thediscdb_refresh_loop(app: FastAPI) -> None:
    """Daily check; refresh the snapshot when absent or older than
    cfg.thediscdb_refresh_days. Failures keep the previous index."""
    from arm_backend.thediscdb.snapshot import refresh as thediscdb_refresh

    while True:
        try:
            async with async_session_factory() as session:  # use the module's existing session factory name
                cfg = (
                    await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))
                ).scalar_one_or_none()
                if cfg is not None and cfg.thediscdb_enabled:
                    stale_after = timedelta(days=max(1, cfg.thediscdb_refresh_days))
                    last = cfg.thediscdb_refreshed_at
                    store = app.state.thediscdb
                    if not store.exists() or last is None or datetime.now(UTC) - last > stale_after:
                        count = await thediscdb_refresh(app.state.http, Path(settings.ARM_THEDISCDB_PATH))
                        cfg.thediscdb_refreshed_at = datetime.now(UTC)
                        session.add(cfg)
                        await session.commit()
                        logger.info("thediscdb: snapshot refreshed (%d discs)", count)
        except Exception as e:  # noqa: BLE001 — never kill the loop
            logger.warning("thediscdb: refresh loop error: %s", e)
        await asyncio.sleep(24 * 3600)
```

Start/stop it in lifespan exactly like `notification_task` / `log_tailer_task`
(create after `app.state.thediscdb` is set; cancel in the shutdown section the
same way the neighbors are cancelled). Read the shutdown block first and
mirror it. Match the module's actual session-factory/import names (`grep -n
'session' services/backend/arm_backend/main.py | head`).

- [ ] **Step 3: Run backend suite, commit**

```bash
cd services/backend && uv run pytest -q
git add -A && git commit -m "feat(backend): TheDiscDB snapshot refresh — endpoint + daily lifespan loop"
```

---

### Task 9: Full gates + docs touch-up

**Files:**
- Modify: `docs/superpowers/specs/2026-08-06-thediscdb-design.md` (status line only)

- [ ] **Step 1: Repo-wide gates**

```bash
ruff check .
cd services/backend && uv run mypy arm_backend && uv run pytest -q && uv run alembic heads
cd ../ripper && uv run mypy arm_ripper && uv run pytest -q
```

Expected: clean; exactly one alembic head (`0029_thediscdb`). Fix anything
that surfaces (mypy on pycdlib may need a `# type: ignore[import-untyped]` on
the import, matching how `pydvdid_m` is imported in `disc_probe.py`).

- [ ] **Step 2: Mark spec implemented + commit**

Change the spec's `Status:` line to `implemented (see plan of the same date)`.

```bash
git add -A && git commit -m "docs: mark TheDiscDB spec implemented"
```

---

## Post-plan notes for the executor

- The two riskiest integration points are pycdlib's UDF listing on real
  Blu-rays (Task 1 — the unit tests can't cover a real disc; first manual
  validation is `python -c "from arm_ripper.scan.thediscdb_hash import probe_thediscdb_hash; print(probe_thediscdb_hash('/path/to/disc.iso'))"`
  against any BD ISO, compared with the hash TheDiscDB shows for that release)
  and the identify-endpoint guard interactions (Task 7 — reuse-job and
  timeout paths must remain byte-identical when there is no match).
- Deferred by design (do NOT implement): `aacs` fingerprint computation,
  live GraphQL fallback, `data/sets` parsing, contribution flow, ui-neu
  badges.
