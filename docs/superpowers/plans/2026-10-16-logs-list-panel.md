# Logs List Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the Logs page's job list (`/logs`, not the log viewer `/logs/[job_id]`) as the dashboard's All Jobs panel, with more job metadata and each log's last-modified time.

**Architecture:** A small backend endpoint `GET /api/logs` lists the per-job log files (`/logs/jobs/<job_id>.log`) with size and modified time. The page loads the jobs (one page of up to 200, newest first, with the `X-Total-Count` total) and the log index together, joins them by job id, and renders one panel: a header (title, count, status filter, search) over a table. Styling follows the All Jobs panel in `routes/+page.svelte` (`.dashboard-jobs*`); shared pieces (status filter, status badge, poster, type helpers) are reused, not copied.

**Tech Stack:** FastAPI + pydantic (arm_common schema), SvelteKit/Svelte 5, vitest, pytest.

**Context:** owner request 2026-10-16 with a mockup (the All Jobs panel look). Branch `feat/logs-list-panel` from `feat/jobs-panel-2b` (PR #365, which introduced the panel).

## Global Constraints

- **Endpoint:** `GET /api/logs` (JWT, same auth as the other log routes) returns `list[JobLogFileView]`, `JobLogFileView = {job_id: str, size_bytes: int, modified_at: datetime}` (UTC, timezone-aware) in `arm_common` schemas. It scans `LOG_DIR / "jobs"` for `*.log` whose stem passes `is_valid_id("job", stem)`; anything else is skipped; a missing directory returns `[]`. Ordered by `modified_at` descending. Declared so it does not collide with the existing `/{job_id}.zip` and `/{job_id}` routes (the bare `/api/logs` path is distinct). Regenerate the OpenAPI snapshot and `api.gen.ts`; add `fetchJobLogIndex()` to `lib/api/logs.ts`.
- **Panel header:** title `Job logs`, the count `<N> jobs` (`1 job`), the existing status filter (`JobFilterBar`) and a search input with placeholder `Search title or id` and `aria-label="Search jobs by title or id"`. Header, border, radius, shadow, spacing and the uppercase table-header row match `.dashboard-jobs` / `.dashboard-jobs-header` / the dashboard's table head. The old page title/hint paragraph is replaced by this panel (keep `<svelte:head>` title `ARM - Logs`).
- **Columns, in order:** `Title` (poster thumbnail via the existing `PosterImage` with its fallback; the title as a link to `/logs/<id>`, falling back to the job id; under it the job id in mono, shortened like `job_9a41` style the app already uses if a helper exists, else the full id), `Status` (`StatusBadge` with `effectiveJobStatus`), `Type` (two chips: `Series` for media_type tv / `Movie` for movie / `Music` for CDs, using the existing type helper's label and colour; and the disc kind via `discTypeLabel`, or `ISO`/`Folder` for ISO/folder sources the way `IsoSourceChip`/the job page decide it), `Disc` (`S<season> · Disc <n>/<total>` with parts omitted when unknown: `Disc 2/4`, `S1`, `S1 · Disc 2`; `-` when nothing), `Drive` (`driveLabel(job.drive_id, $dashboard.drive_names)`, truncated with an ellipsis and a `title` tooltip), `Year` (`-` when unknown), `Last modified` (relative on the first line using the app's existing relative-time helper if there is one, e.g. `42 min ago`, `Yesterday`, `2 days ago`; the absolute date and time on the second line, muted, e.g. `Oct 16, 8:18 AM`; `No log yet` muted when the job has no log file).
- **Order and filtering:** rows sorted by last modified, newest first; jobs without a log file after those with one, by job order. Status filter and search filter client-side over the loaded page (search matches title and id, case-insensitive). The count shows the number of rows after filtering when a filter or search is active (`<shown> of <total> jobs`), else the total.
- **States:** loading, error and empty keep the existing `LoadState` wrapper; `No jobs match.` when filters exclude everything.
- **Phone width:** the table uses the app's `responsive-table` pattern with `data-label`s so rows stack on narrow screens; no horizontal page scroll.
- Copy follows the docs' voice. Tests zero-infra. Commits carry no attribution trailers. Nothing under `.superpowers/` or `.svelte-kit/` committed.

## Review Focus

1. A log file whose name isn't a valid job id (e.g. `../x.log`, `notes.log`) is never listed (Task 1).
2. A job with no log file shows `No log yet` and sorts after jobs with logs (Task 2).
3. The `Disc` column renders each partial combination correctly (Task 2).
4. Rows link to `/logs/<id>`, keyboard reachable (Task 2).
5. The log index request failing still renders the jobs (last modified falls back to `No log yet`, no page error) (Task 2).

---

### Task 1: Log index endpoint

**Files:** `packages/arm_common/arm_common/schemas/` (add `JobLogFileView` next to related log/job schemas and export it), `services/backend/arm_backend/routers/logs.py`, tests in `services/backend/tests/test_logs_router.py` (or the existing logs router test file); `services/ui-neu/frontend/src/lib/api/logs.ts` (`fetchJobLogIndex`), its test; regen snapshot + `api.gen.ts`.

- [ ] Tests first: lists valid files with size and mtime, newest first; skips invalid names and non-`.log` files; missing directory → `[]`; requires auth; does not shadow `/{job_id}` and `/{job_id}.zip`. Implement. `uv run pytest services/backend packages/arm_common -q`; ruff/ruff-format/mypy; regen; UI `npm run check`. Commit `feat(logs): list each job log's size and last-modified time`.

### Task 2: The panel

**Files:** `services/ui-neu/frontend/src/routes/logs/+page.svelte`, `routes/logs/__tests__/logs-page.test.ts`; a small pure helper for the Disc column and last-modified formatting if none exists (e.g. in `lib/utils/format.ts` or a new `lib/utils/log-list.ts`) with its test.

- [ ] Tests first for every column, the ordering, the count text, filtering, the no-log fallback, and the index-failure fallback. Implement per Global Constraints, reusing the dashboard panel's look. `npm run check && npx vitest run && npm run lint`. Commit `style(ui): Logs page job list as a panel with metadata and last modified`.
