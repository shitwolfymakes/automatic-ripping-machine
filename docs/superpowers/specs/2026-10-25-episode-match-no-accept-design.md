# Episode match without an accept step

Date: 2026-10-25. Builds on the TV season selection design
(`2026-10-23-tv-season-selection-design.md`, wolfy PR #402) and the tester
walk of 2026-10-25. Owner decision: "once a value is set it applies, so no
accept process is required other than Start rip."

## 1. Intent

The operator answers one question at the review gate: are these the right
episodes? Today the UI asks them to manage the matcher's bookkeeping
instead: a held result is drawn in the rows but not written to the tracks,
and the operator has to Accept, Pin, Unpin or Re-run to move between states
that look the same on screen. Pin means nothing to an operator.

After this change every match is written to the tracks. How sure ARM is
becomes a colour and a reason line, not a gate. Start rip rips with whatever
is on the tracks, as it always has. There is no accept verb anywhere.

## 2. Goals

- A held result is applied like a confident one, marked as a guess.
- One control to change a match (Fix match), one to remove it (Clear
  episodes), per-track edits as they are.
- The card and the panel say "a guess" in amber with the strongest reason,
  the other reasons behind an (i).
- A guessed placement never auto-starts: the review countdown holds while
  the job's episodes are a guess. Start rip by hand always works.
- Pin disappears from the UI and from the operator's vocabulary. It stays
  in the claims as the internal record of a source the operator chose in
  Fix match.

## 3. Non-goals

- No change to the alignment model, the season scan, the hold reasons or
  the sibling logic. They feed the colour instead of the gate.
- No change to how files are named or filed. A guessed episode number is an
  episode number.
- The Settings switch `episode_auto_apply` keeps its key and storage.
- The design canvas is updated separately.

## 4. Behaviour

### 4.1 Resolver and claims

A held episode source (its stored `suggestion` is true) is usable. Within the
episode tier the order is: pinned source first, then clean results before
held ones, then the operator's Settings order. One episode source still wins
outright. The resolver reports which episode source won and whether its
result was held: `Resolution.episode_source`, `Resolution.episode_unsure`.

`IdentityClaims` gains `unsure: bool` (default false). `resolve_job` writes
it from the resolution every time it runs, so it is authoritative: true only
while the winning episode source's result is held. Clearing the match,
re-running with a clean result, or a hand edit that changes the winner all
re-resolve and refresh it.

`JobView` gains a computed field `episodes_unsure: bool`, read from
`metadata_json.identity_claims.unsure`. It travels to the UI and to the
ripper without a migration.

The stored `suggestion` flag and `extra.hold_reasons` on a source are
unchanged; the UI reads the reasons from the winning source as today.

`episode_auto_apply` off means every TV match is held, so every TV match is
a guess: applied, amber, countdown held. Its Settings label says so.

### 4.2 Clearing a match

`DELETE /api/jobs/{job_id}/identity/match` forgets the episode match on a
job: every `episodes_*` source is removed from the claims, the episode pin
is cleared, `unsure` is false, the job re-resolves, and
`job.identity_updated` plus one `track.updated` per changed track are
emitted. Manual track claims are untouched, so a track the operator placed
by hand keeps its placement and its Revert. Show ids are kept: the next
Fix match needs them. Returns the `IdentityView`. Writer role required.

`DELETE /identity/pin` stays for API compatibility; nothing in the UI calls
it.

### 4.3 Ripper

`_review_countdown_expired` returns false while `view.episodes_unsure` is
true, the same way it does for `manual_pause`. The ripper logs once per job
when the hold first applies. Start rip by hand is unaffected. When the hold
lifts, the countdown resumes from its original start; a disc the operator
has just fixed may auto-start promptly, which is what pressing Fix match on
a review card means.

### 4.4 Match Episodes panel

Views: `noseries`, `matching`, `unavailable`, `nomatch`, `unsure`,
`applied`. `suggestion` and `pinned` are gone.

Header: source chip; an amber "Guess" chip when `unsure`; "N of M tracks
placed". Actions, right-aligned: **Fix match** (whenever the operator may
act), **Clear episodes** (when any track is placed), **Fill the rest** (as
today, after a hand pick), **View sources** (as today).

Below the header, when `unsure`: one amber line, "Season 3 is a guess:
another season fits about as well.", with the (i) that opens the remaining
reasons, and the fit facts "Season 3, 4 of 4 titles. Also fits Season 2 (4
of 4 titles)". No button in that block.

Fix match opens the existing re-run form (season, disc, source, tolerance).
Its buttons read **Preview** and **Apply**. Apply still records the chosen
source in the claims; nothing on screen calls that a pin.

Rows: a placement from a held source shows the chip "Guess, TMDb" (warning
tone) instead of "Auto, TMDb". Everything else as today.

Removed: Accept, Re-run..., the pinned banner, Unpin, "Pinned by you",
"Suggestion, not applied", "Applied automatically" (the rows' origin chips
already say it).

### 4.5 Home card and job page

The Episodes row gains a `guess` state: amber "Episodes placed, a guess" with
a Review link, and the Episodes button stays visible. `matched` is reserved
for a confident, complete placement.

While `episodes_unsure` is true on a review-gate card, the countdown shows
as held with the note "Held: episodes are a guess" and the pause toggle is
hidden; the ripper is doing the holding, the card only says so. Start rip is
unchanged.

The Season row and the Info form are unchanged.

### 4.6 Copy

ASCII only. New strings: "Guess", "Guess, {source}", "Fix match", "Clear
episodes", "Clear episodes?" is not asked (it is reversible with Fix match),
"Episodes placed, a guess", "Held: episodes are a guess", "Apply".
Settings label for `episode_auto_apply`: "Trust confident TV matches", help:
"Off: every TV match is shown as a guess and holds the review countdown."

## 5. Definition of done

1. A held result appears on the tracks with the Guess chip; the card says
   "Episodes placed, a guess"; the countdown reads held; Start rip rips with
   those numbers.
2. Fix match on that job with the right season applies a confident result;
   the amber goes away; the countdown resumes.
3. Clear episodes empties the placements, keeps a hand-set track, and the
   card goes to "needs attention".
4. No Accept, Pin or Unpin anywhere in the UI; the pin endpoint still
   answers.
5. Suites: backend, ripper and UI green; OpenAPI snapshot and generated
   types regenerated; ASCII copy guard green.
