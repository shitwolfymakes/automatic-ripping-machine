# TheDiscDB integration — design

Date: 2026-08-06
Branch: `feat/media-identification` (off the Tier-33 chain tip)
Status: approved (design), pending implementation plan

## Problem

ARM identifies *what a disc is* (OMDb/TMDb/TVDb/MusicBrainz via
`MetadataDispatcher`) but nothing identifies *which title on the disc is
what*. Blu-ray playlists are unlabeled (`00003.mpls`, `00800.mpls`, …), so
main-feature selection is heuristic and extras/episodes come out unnamed.

[TheDiscDB](https://thediscdb.com) is a community database (MIT-licensed data,
`github.com/TheDiscDb/data`, ~4.7k discs / 1.4k movies / 166 series) that maps
each disc release's playlists to typed content — MainMovie / Extra /
Featurette / Trailer / Episode (with season+episode) — including suggested
output filenames, chapter names, and TMDb/IMDb external IDs.

## Scope (v1)

- Full disc map: label every scanned title, auto-select the main feature
  (or all episodes), apply suggested filenames — operator can override via
  the existing review card + timed review gate.
- Movies **and** series discs.
- Local snapshot of the data repo as the only runtime source (no live
  thediscdb.com dependency). Hybrid live-API fallback is an explicit
  non-goal for v1 but the module boundary allows it later.
- Contribution (uploading unmatched discs) is out of scope.

## Matching keys

- **`ContentHash`** (primary, full coverage in the dataset): MD5 over each
  stream file's size as 8 little-endian bytes, files in ordinal filename
  order. Mirrors `TheDiscDb.Core/DiscHash/HashingExtensions.cs`
  (`files.OrderBy(Name).CalculateHash()`); their browser flow feeds it
  `BDMV/STREAM` listings. The exact DVD file-set rule must be pinned against
  their ImportBuddy tool during implementation.
- **`GlobalDiscId`** (secondary, sparse/backfilling): AACS Disc ID =
  `SHA1(AACS/Unit_Key_RO.inf)`. Indexed when present; the ripper does not
  compute it in v1 (the `aacs` fingerprint algo name is already reserved in
  `DiscFingerprintInput` for when it does).

## Architecture

```
disc inserted
  → ripper scan (makemkvcon robot info)
  → disc_probe: fingerprints += ("thediscdb", <ContentHash>)
  → IdentifyRequest → backend identify
      → thediscdb matcher: hash in local snapshot index?
          hit  → stamp disc map on tracks; auto-select; external IDs → MetadataDispatcher
          miss → unchanged current flow
```

### Ripper: content hash (`services/ripper/arm_ripper/scan/`)

New `thediscdb_hash.py` + a call from `disc_probe.py`, following the existing
no-mount pattern (pycdlib reads the UDF/ISO tree straight from the block
device; pycdlib is already in the tree via `pydvdid_m`):

- Blu-ray/UHD: list `BDMV/STREAM/*`, collect (name, size), ordinal sort by
  name, MD5 over sizes as above.
- DVD: same hash over the ImportBuddy-pinned file set (expected: `VIDEO_TS`
  contents; verify during implementation).
- Emits `DiscFingerprintInput(algo="thediscdb", value=<32-hex-uppercase>)`.
- Any failure (unreadable fs, ISO source quirks) → no fingerprint, logged at
  debug. CDs: not applicable, skipped.

### Backend: snapshot manager (`services/backend/arm_backend/thediscdb/snapshot.py`)

- Source: `https://codeload.github.com/TheDiscDb/data/tar.gz/refs/heads/main`.
- Parses every `data/**/disc*.json` with its sibling `metadata.json` and
  `release.json` into a SQLite index in the backend data dir:
  - `discs(content_hash PK, global_disc_id, title_slug, release_slug,
    kind movie|series|set, disc_json, metadata_json, release_json)`
  - lookup by `content_hash` (and `global_disc_id` where present).
- Refresh lifecycle: build on startup when missing or older than
  `thediscdb_refresh_days`; scheduled re-check daily; manual
  `POST /api/system/thediscdb/refresh`. A failed refresh keeps the previous
  index and logs a warning (same philosophy as the MakeMKV mirror work:
  third-party outages must never break local operation).
- Index build is atomic: write `index.sqlite.new`, rename over.

### Backend: matcher + apply (`services/backend/arm_backend/thediscdb/matcher.py`)

Called from the identify flow where scan fingerprints are already in hand
(alongside `disc_dedupe`):

- Look up the `thediscdb` fingerprint in the index. Miss → return None,
  caller proceeds unchanged.
- Join matched disc titles to scanned titles: primary key `SourceFile`
  (mpls/vob name from the MakeMKV scan), secondary `SegmentMap`, duration
  (±2s) as tiebreak. Unjoined titles on either side are left untouched.
- Per joined track: set `item_type` (MainMovie/Extra/Featurette/Trailer/
  Episode/…), `season`, `episode`, and the suggested output filename via the
  existing track operator-fields path (so review card display + override
  work with zero UI changes).
- Selection: movie discs → select the MainMovie track; series discs →
  select all Episode tracks. Existing operator/config selection logic keeps
  priority; the timed review gate remains the override point.
- Record `{release_slug, title_slug, contributor, matched_at}` in
  `job.metadata_json["thediscdb"]`.
- Feed `ExternalIds.Tmdb`/`Imdb` into `MetadataDispatcher` so the metadata
  lookup is exact (by-ID) instead of title-string guessing; on provider
  failure the normal fallback chain still applies.

### Data model

Migration `0029` (chains on `0028_user_role_disabled`): three nullable track
columns — `item_type: str | None`, `season: int | None`,
`episode: int | None`. Suggested filenames reuse existing operator fields; no
job-table changes (`metadata_json` carries the match record).

### Config

Via the existing `config_metadata` pattern:
- `thediscdb_enabled: bool = true`
- `thediscdb_refresh_days: int = 7`

## Error handling

Every failure mode — no fingerprint, index absent/stale, no match, malformed
entry, join ambiguity — logs (info for match/miss, debug for detail) and
falls through to current behavior. TheDiscDB can only improve a rip; it must
never block or degrade one.

## Testing

- Hash unit vectors: synthetic (name, size) lists with known MD5s; ordering
  and 8-byte little-endian encoding pinned.
- Snapshot builder: fixture mini-tarball (one movie, one series) → index
  rows asserted; atomic-replace behavior; failed-download keeps old index.
- Matcher: real `disc*.json` fixtures from the data repo (one movie with
  extras, one series disc) joined against synthetic ScanResults — labels,
  selection, S/E, filename application, and miss/ambiguity fallthrough.
- Router: refresh endpoint auth + happy path.
- Migration: single-alembic-head check (repo standard).

## Follow-ups (explicitly deferred)

- `aacs` fingerprint computation in the ripper (second match key).
- Hybrid live-GraphQL fallback on snapshot miss.
- Contribution flow (upload MakeMKV logs for unmatched discs).
- Box-set (`data/sets`) awareness beyond what disc-level matching gives.
- UI badges for item types in ui-neu beyond existing track fields.
