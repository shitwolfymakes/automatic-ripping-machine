"""Score a provider's candidate against the disc's evidence.

    S = 45*T + 15*Y + 20*R + 10*K + 10*A

T title overlap in [0, 1], Y year in [-1, 1], R runtime in [-1, 1], K movie-vs-TV in [-1, 1], A agreement between
providers in [0, 1]. One pure function per component; no I/O, no clock, no randomness.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from arm_common.enums import MediaType

from arm_backend.metadata.match.evidence import DiscEvidence, YearEvidence
from arm_backend.metadata.match.tokens import TRUNCATION_PREFIX_MIN, ParsedTitle, candidate_tokens

WEIGHT_TITLE = 45.0
WEIGHT_YEAR = 15.0
WEIGHT_RUNTIME = 20.0
WEIGHT_KIND = 10.0
WEIGHT_AGREEMENT = 10.0

# Number rule factors (spec 4.1).
NUMBERS_DIFFER = 0.3
NUMBERS_PARTIAL = 0.6
DISC_NUMBER_MISSING = 0.6
CANDIDATE_SEQUEL_NUMBER = 0.7

# Year distance factors (spec 4.2): festival vs release year is one apart.
YEAR_ONE_APART = 0.5
YEAR_FAR_DISTANCE = 3

# Runtime tolerances (spec 4.3, D65): full inside max(3 min, 3 %), zero at 10 %, -0.5 at 25 %, -1 beyond.
RUNTIME_FLAT_MINUTES = 3.0
RUNTIME_FLAT_SHARE = 0.03
RUNTIME_ZERO_SHARE = 0.10
RUNTIME_EDITION_SHARE = 0.25
RUNTIME_EDITION_FLOOR = -0.5
# A broadcast slot is longer than the episode it holds.
TV_SLOT_MIN_SHARE = 0.65
TV_SLOT_MAX_SHARE = 1.05
TV_SLOT_FACTOR = 0.5

AGREEMENT_TWO = 0.6
AGREEMENT_TWO_PROVIDERS = 2
AGREEMENT_FULL_PROVIDERS = 3

FLAG_YEAR_MISMATCH = "year_mismatch"
FLAG_RUNTIME_FAR = "runtime_far"
FLAG_EDITION_TOLERANCE = "edition_tolerance"


@dataclass(frozen=True)
class Candidate:
    """One merged provider result."""

    title: str
    kind: MediaType
    year: int | None = None
    original_title: str | None = None
    runtime_minutes: float | None = None
    # Every provider that returned it, and the best (lowest) operator rank among them.
    providers: tuple[str, ...] = ()
    provider_rank: int = 0
    ids: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreParts:
    """The weighted parts of a score."""

    title: float
    year: float
    runtime: float
    kind: float
    agreement: float


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    score: float
    parts: ScoreParts
    # T in [0, 1], before weighting: the accept rule's title floor reads it.
    title_fit: float
    flags: tuple[str, ...]


# --- title --------------------------------------------------------------------------------------------------------


def number_factor(parsed: ParsedTitle, candidate: frozenset[str]) -> tuple[float, str | None]:
    """How far the numbers of the disc and the candidate agree: `Blade Runner 2049` is not `... 2099`."""
    disc = {t for t in parsed.required if t.isdigit()}
    cand = {t for t in candidate if t.isdigit()}
    if disc and cand:
        if not disc & cand:
            return NUMBERS_DIFFER, "numbers_differ"
        return (1.0, None) if disc == cand else (NUMBERS_PARTIAL, "numbers_partial")
    if disc:
        return DISC_NUMBER_MISSING, "disc_number_missing"
    if cand - {t for t in parsed.optional if t.isdigit()}:
        return CANDIDATE_SEQUEL_NUMBER, "candidate_sequel_number"
    return 1.0, None


def _matched_required(parsed: ParsedTitle, candidate: frozenset[str]) -> int:
    matched = sum(1 for t in parsed.required if t in candidate)
    last = parsed.required[-1] if parsed.required else ""
    if parsed.truncated and last not in candidate and len(last) >= TRUNCATION_PREFIX_MIN:
        matched += any(c.startswith(last) for c in candidate)
    return matched


def title_score(parsed: ParsedTitle, candidate: frozenset[str]) -> tuple[float, str | None]:
    """T for one disc title against one candidate title: the disc's words are required (squared), the
    candidate's extra words cost less."""
    if not candidate or not parsed.required:
        return 0.0, None
    matched = _matched_required(parsed, candidate)
    if matched == 0:
        return 0.0, None
    optional = sum(1 for t in parsed.optional if t in candidate)
    cov_disc = matched / len(parsed.required)
    cov_cand = min(1.0, (matched + optional) / len(candidate))
    factor, flag = number_factor(parsed, candidate)
    return cov_disc**2 * (1 + cov_cand) / 2 * factor, flag


def _best_title(ev: DiscEvidence, candidate_titles: Iterable[frozenset[str]]) -> tuple[float, str | None]:
    best: tuple[float, str | None] = (0.0, None)
    for title in ev.titles:
        for tokens in candidate_titles:
            fit = title_score(title.parsed, tokens)
            if fit[0] > best[0]:
                best = fit
    return best


# --- year ---------------------------------------------------------------------------------------------------------


def year_factor(distance: int, *, tv: bool) -> float:
    """1 for the same year, 0.5 one apart, 0 two apart, -1 further; never negative for a TV candidate."""
    if distance == 0:
        factor = 1.0
    elif distance == 1:
        factor = YEAR_ONE_APART
    elif distance < YEAR_FAR_DISTANCE:
        factor = 0.0
    else:
        factor = -1.0
    return max(factor, 0.0) if tv else factor


def year_score(
    years: Sequence[YearEvidence], candidate_year: int | None, candidate: frozenset[str], *, tv: bool
) -> float:
    """Y from the strongest year the candidate's own title does not already explain."""
    if candidate_year is None:
        return 0.0
    live = [y for y in years if not (y.bare and str(y.year) in candidate)]
    if not live:
        return 0.0
    strongest = max(live, key=lambda y: y.reliability)
    return strongest.reliability * year_factor(abs(candidate_year - strongest.year), tv=tv)


# --- runtime ------------------------------------------------------------------------------------------------------


def runtime_factor(disc_minutes: Sequence[float], candidate_minutes: float, *, capped: bool) -> tuple[float, bool]:
    """f in [-1, 1] for a movie. `capped`: the disc may be an edition, so no worse than -0.5; the second value
    says the cap was what set the result."""
    if candidate_minutes <= 0 or not disc_minutes:
        return 0.0, False
    error = min(abs(d - candidate_minutes) for d in disc_minutes)
    flat = max(RUNTIME_FLAT_MINUTES, RUNTIME_FLAT_SHARE * candidate_minutes)
    if error <= flat:
        return 1.0, False
    share = error / candidate_minutes
    flat_share = flat / candidate_minutes
    if share <= RUNTIME_ZERO_SHARE:
        return 1 - (share - flat_share) / (RUNTIME_ZERO_SHARE - flat_share), False
    if share <= RUNTIME_EDITION_SHARE:
        return RUNTIME_EDITION_FLOOR * (share - RUNTIME_ZERO_SHARE) / (
            RUNTIME_EDITION_SHARE - RUNTIME_ZERO_SHARE
        ), False
    return (RUNTIME_EDITION_FLOOR, True) if capped else (-1.0, False)


def _tv_slot_factor(episode_minutes: float, candidate_minutes: float) -> float:
    inside = TV_SLOT_MIN_SHARE * candidate_minutes <= episode_minutes <= TV_SLOT_MAX_SHARE * candidate_minutes
    return TV_SLOT_FACTOR if inside else 0.0


def runtime_score(ev: DiscEvidence, candidate: Candidate) -> tuple[float, tuple[str, ...]]:
    """R in [-1, 1]. Only like compares with like: a movie against a feature, a TV show against an episode."""
    runtime = ev.runtime
    minutes = candidate.runtime_minutes
    if runtime is None or minutes is None or minutes <= 0:
        return 0.0, ()
    if candidate.kind is MediaType.TV:
        if runtime.episode_minutes is None:
            return 0.0, ()
        return _tv_slot_factor(runtime.episode_minutes, minutes), ()
    if not runtime.feature_minutes:
        return 0.0, ()
    capped = ev.edition_hint or len(runtime.feature_minutes) >= 2
    factor, cap_used = runtime_factor(runtime.feature_minutes, minutes, capped=capped)
    flags = ((FLAG_RUNTIME_FAR,) if factor < 0 else ()) + ((FLAG_EDITION_TOLERANCE,) if cap_used else ())
    return runtime.reliability * factor, flags


# --- kind and agreement -------------------------------------------------------------------------------------------


def kind_score(p_tv: float, kind: MediaType) -> float:
    """K in [-1, 1]: a TV candidate gains from a TV-looking disc, a movie from a movie-looking one."""
    return 2 * p_tv - 1 if kind is MediaType.TV else 1 - 2 * p_tv


def agreement_score(provider_count: int) -> float:
    """A: 0 for one provider, 0.6 for two, 1 for three or more."""
    if provider_count >= AGREEMENT_FULL_PROVIDERS:
        return 1.0
    return AGREEMENT_TWO if provider_count == AGREEMENT_TWO_PROVIDERS else 0.0


# --- total --------------------------------------------------------------------------------------------------------


def score_candidate(ev: DiscEvidence, candidate: Candidate) -> ScoredCandidate:
    titles = [candidate.title, *([candidate.original_title] if candidate.original_title else [])]
    token_sets = [candidate_tokens(t) for t in titles]
    tv = candidate.kind is MediaType.TV
    t, title_flag = _best_title(ev, token_sets)
    y = year_score(ev.years, candidate.year, frozenset().union(*token_sets), tv=tv)
    r, runtime_flags = runtime_score(ev, candidate)
    k = kind_score(ev.p_tv, candidate.kind)
    a = agreement_score(len(set(candidate.providers)))
    parts = ScoreParts(WEIGHT_TITLE * t, WEIGHT_YEAR * y, WEIGHT_RUNTIME * r, WEIGHT_KIND * k, WEIGHT_AGREEMENT * a)
    flags = (*((title_flag,) if title_flag else ()), *((FLAG_YEAR_MISMATCH,) if y < 0 else ()), *runtime_flags)
    total = parts.title + parts.year + parts.runtime + parts.kind + parts.agreement
    return ScoredCandidate(candidate, total, parts, t, flags)


def ranking_key(scored: ScoredCandidate) -> tuple[float, float, int, str, int]:
    """Best first; ties break on title fit, provider rank, title, then year, so the order never depends on input."""
    c = scored.candidate
    return (-round(scored.score, 9), -round(scored.title_fit, 9), c.provider_rank, c.title.casefold(), c.year or 0)


def rank_candidates(ev: DiscEvidence, candidates: Iterable[Candidate]) -> list[ScoredCandidate]:
    return sorted((score_candidate(ev, c) for c in candidates), key=ranking_key)
