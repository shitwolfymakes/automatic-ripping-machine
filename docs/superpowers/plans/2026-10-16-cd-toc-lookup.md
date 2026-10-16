# CD Track-Layout Fallback (MusicBrainz TOC Lookup) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an audio CD's exact MusicBrainz disc ID is not listed, look the disc up by its table of contents (track count and lengths) so other pressings of a listed album still identify; when several releases fit, hold the best one as a suggestion instead of applying it.

**Architecture:** The ripper already reads the disc with libdiscid; it now also sends the TOC string (`disc.toc_string`, "first last lead-out offset1 … offsetN") as `ScanResult.cd_toc`. `MusicBrainzClient.lookup_disc_id(disc_id, toc=None)` keeps today's exact lookup; on a miss (404 or no releases) with a TOC it calls the fuzzy endpoint `/discid/-?toc=<plus-joined>&cdstubs=no`. One fitting release is a normal hit (payload `toc_match: "fuzzy"`); several make the top one a hit carrying `toc_candidates` (up to 5). The identify route holds an ambiguous fuzzy hit as an identity suggestion whatever the music auto-apply switch says. The dispatcher's attempt log notes a fuzzy match.

**Tech Stack:** python-discid 1.4 (ripper), httpx + respx tests (backend), pydantic (arm_common), docs.

**Context:** owner decision 2026-10-16 (CD list item 2). Branch `feat/cd-toc-lookup` from `feat/identification-review-flow` (PR #371).

## Global Constraints

- `ScanResult.cd_toc: str | None = None` (space-separated TOC exactly as libdiscid's `toc_string`; None when unavailable). Regenerate the OpenAPI snapshot and `api.gen.ts`.
- Ripper: `cd_toc = getattr(disc, "toc_string", None)` inside the existing `discid.read` block; any failure leaves it None and never fails the scan.
- MusicBrainz fuzzy request: `GET {base}/discid/-` with params `toc=<the TOC with spaces replaced by "+">`, `cdstubs=no`, `inc=artists+recordings+release-groups`, `fmt=json`. Build the URL so the `+` separators reach MusicBrainz as `+` (httpx encodes `+` in params as `%2B`, which MusicBrainz decodes back to `+`; verify in a respx test by asserting the decoded query value contains `+` separators). Uses the same rate limiter and User-Agent.
- Fuzzy response: `releases` list (no `id` of a disc). Zero releases → `LookupError("musicbrainz toc not found")`. Medium choice for a fuzzy hit: the first medium whose `track-count` (or `len(tracks)`) equals the TOC's track count (`last - first + 1`), else the first medium; `disc` = that medium's position. One release → `MetadataResult` like today with `payload["toc_match"] = "fuzzy"`. Several → the first release as the result with `payload["toc_match"] = "fuzzy"` and `payload["toc_candidates"] = [{"id","title","date","artist"} …]` for the first 5 releases.
- No TOC, or exact hit: behaviour identical to today (existing tests unchanged).
- Adapter `MusicBrainzSource.lookup_disc_id(cfg, disc_id, toc=None)`; dispatcher `_identify_cd` passes `scan.cd_toc`; the attempt for that source records `detail="matched by track layout"` on a fuzzy hit.
- Identify route: a hit whose `provider == "musicbrainz"` and whose payload has `len(toc_candidates) > 1` is held exactly like an auto-apply-off hit (`suggest_identity`, `awaiting_review`, no countdown), regardless of `music_auto_apply`. A single fuzzy hit follows the normal auto-apply rule.
- Docs: `docs/user/Configuring-ARM.md` Step 3 sentence becomes `Audio CDs are looked up on MusicBrainz by their track layout; when that exact disc isn't listed, ARM matches the track lengths instead and asks you to confirm when several releases fit.`; the lifecycle doc's CD row in "How identify decides" names the fuzzy TOC fallback.
- Tests zero-infra (fake discid module, respx, fake dispatcher). Commits carry no attribution trailers.

## Review Focus

1. A disc whose exact ID is listed never makes the fuzzy call (Task 2).
2. The fuzzy request carries `cdstubs=no` and `+`-separated TOC, through the rate limiter (Task 2).
3. Several fitting releases never auto-apply, even with music auto-apply on (Task 3).
4. A missing `toc_string` (older libdiscid) leaves `cd_toc` None and the scan still succeeds (Task 1).
5. The chosen medium for a two-disc set fuzzy hit is the one with the matching track count, so `{disc}` is right (Task 2).

---

### Task 1: Ripper sends the TOC

**Files:** `packages/arm_common/arm_common/schemas/ripper.py`, `services/ripper/arm_ripper/scan/musicbrainz_disc.py`; tests in `services/ripper/tests/` (find the scan_cd test), `packages/arm_common/tests` if a schema test exists; regen snapshot + `api.gen.ts`.

- [ ] Tests first (fake `discid` module in `sys.modules` with a disc exposing `id`, `tracks`, `toc_string`; one without `toc_string`). Implement. `uv run pytest services/ripper packages/arm_common -q`; ruff/ruff-format/mypy; regen. Commit `feat(ripper): send the CD's table of contents with the scan`.

### Task 2: MusicBrainz fuzzy TOC lookup

**Files:** `services/backend/arm_backend/metadata/musicbrainz.py`, `metadata/sources.py`, `metadata/dispatcher.py`; tests `services/backend/tests/test_metadata_clients*.py` (find the MusicBrainz client tests), `test_dispatcher.py`, `test_metadata_sources*.py`.

- [ ] Tests first per Global Constraints (exact hit unchanged and no fuzzy call; 404 + TOC → one release hit with `toc_match`; several → candidates capped at 5; no TOC → LookupError as today; fuzzy zero → LookupError; medium choice; query encoding; dispatcher passes `cd_toc` and records the detail). Implement. Backend suite; lint. Commit `feat(metadata): look a CD up by its track layout when its disc ID isn't listed`.

### Task 3: Hold ambiguous fuzzy hits; docs

**Files:** `services/backend/arm_backend/routers/ripper.py`, tests `test_ripper_router.py`; `docs/user/Configuring-ARM.md`, `docs/developers/architecture/02-job-lifecycle.md`.

- [ ] Tests first: several candidates with music auto-apply on → `awaiting_review`, `identity_suggestion` set, no countdown; one fuzzy hit with auto-apply on → applied. Implement; docs edits. Backend suite; lint. Commit `feat(identify): confirm a CD matched by track layout when several releases fit`.
