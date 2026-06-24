# Unidentified rip dead-ends at "Apply session": `token {year} resolved empty`

## Summary

A job that **rips successfully but is never identified** (its `title` is the raw
MakeMKV disc label and `year` is empty) cannot be transcoded. Applying any
session whose output-path template references `{year}` fails with:

```
track index=0: token {year} resolved empty against the job's metadata
```

The MKVs sit in `/raw` with no way to reach `completed/` through the UI, and the
error message points at a template token rather than the actual fix (identify
the disc first).

## Environment

- ARM v3 (FastAPI backend + SvelteKit ui-neu), deployed build.
- Disc ripped fine: 2 valid Matroska files in `/raw/<job>/`
  (`B1_t00.mkv`, `B3_t01.mkv`), both tracks `done`, job status `ripped`.
- Job metadata: `title = HIDDEN_AGENDA_AND_LIFEPOD` (raw disc label),
  `year = NULL`. The disc was never matched against TMDB/OMDb.

## Steps to reproduce

1. Rip a disc that auto-identification can't match (or skip identification), so
   the job lands in `ripped` with the raw disc label as `title` and no `year`.
2. Open the job and choose **Apply session** → "Movie → Archive H.265 (GPU
   preferred)" (or any built-in movie session — their templates are
   `{title} ({year})/...`).
3. Apply fails with `422` and the message
   `track index=0: token {year} resolved empty against the job's metadata`.

## Root cause

`compute_outputs()` in `services/backend/arm_backend/transcode_apply.py`
validates every template token against the per-track context and raises
`TemplateValidationError` on the first empty one:

```python
# transcode_apply.py
eff_year = track.year if track.year is not None else job.year      # ~L81
ctx["year"] = str(eff_year) if eff_year is not None else ""         # ~L91
...
for token in referenced_tokens(template):                          # ~L138
    if not ctx.get(token):
        raise TemplateValidationError(
            f"track index={track.index}: token {{{token}}} resolved empty "
            f"against the job's metadata"                           # ~L141
        )
```

The built-in movie sessions (`seeders.py`) all use
`{title} ({year})/{title} ({year}) - Track {track} ...`, so an empty `year`
always trips this. There is **no earlier guard** that checks whether the job is
identified — the only gate is this token check at apply time, and its message
describes the symptom (empty token) rather than the cause (job not identified).

## Why this is a problem

- A perfectly good rip becomes a dead-end in the UI: the only built-in movie
  sessions reference `{year}`, so an unidentified disc can't be transcoded
  without either editing metadata by hand or hitting the raw error repeatedly.
- The error is presented at the wrong layer. The user did nothing wrong with the
  *session*; the *job* lacks metadata. Nothing routes them to "Search / identify
  the disc first."
- Multi-title discs make it worse (see below) — even a correct single-movie
  match doesn't describe this disc.

## Aggravating detail: multi-title disc

This particular disc is effectively a **double feature** — label
`HIDDEN_AGENDA_AND_LIFEPOD`, two unrelated tracks (≈88 min + ≈101 min). A single
`{title} ({year})` match can't name both. Identification + naming for
many-titles-one-disc is a related gap worth considering alongside this.

## Suggested resolutions (pick/compose)

1. **Pre-apply identification guard + actionable message.** Before validating the
   template, detect that the job is unidentified (e.g. `year`/`tmdb` empty and
   `title` still the raw disc label) and return a clear error like
   *"This disc isn't identified yet — Search and apply a match before
   transcoding,"* with a link/affordance to the identify flow. Keeps the strict
   behavior but tells the user what to do.

2. **Make `{year}` optional in path expansion.** When `year` is unknown, render a
   year-less path (drop the ` ()` cleanly, e.g. `HIDDEN_AGENDA_AND_LIFEPOD/...`)
   instead of failing, so an unidentified disc can still land in `completed/`.
   Could be template-level (mark tokens optional) or a global "empty parenthetical
   collapses" rule.

3. **Surface the 422 helpfully in ui-neu.** Today the Apply dialog shows the raw
   backend message. At minimum, map `token {year} resolved empty` to a friendly
   "identify the disc first" hint in the dialog.

(1) + (3) is the smallest correct fix; (2) is the better experience for genuinely
un-identifiable discs.

## Acceptance

- Applying a movie session to an unidentified `ripped` job either (a) succeeds
  with a sensible year-less path, or (b) fails with a message that names the real
  cause and points to identification — not a raw template-token error.
