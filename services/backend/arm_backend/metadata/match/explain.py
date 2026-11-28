"""The weighted search's breakdown as the job's `identify_match` section, and its log line (spec 6). Pure."""

from __future__ import annotations

from collections.abc import Sequence

from arm_common.schemas import (
    IdentifyMatch,
    MatchCalls,
    MatchCandidate,
    MatchEvidence,
    MatchParts,
    MatchQuery,
    MatchThresholds,
    MatchTitle,
    MatchYear,
)

from arm_backend.metadata.match.decide import Decision, Thresholds
from arm_backend.metadata.match.evidence import DiscEvidence
from arm_backend.metadata.match.queries import Query
from arm_backend.metadata.match.retrieve import Budget
from arm_backend.metadata.match.score import ScoredCandidate
from arm_backend.metadata.sources import Kind

# At most this many candidates are stored (the shortlist is at most as long).
MAX_STORED_CANDIDATES = 5
_DECIMALS = 1


def _round(value: float) -> float:
    return round(value, _DECIMALS)


def evidence_record(ev: DiscEvidence) -> MatchEvidence:
    runtime = ev.runtime
    minutes: list[float] = []
    if runtime is not None:
        minutes = list(runtime.feature_minutes) or ([runtime.episode_minutes] if runtime.episode_minutes else [])
    numbers = sorted({n for t in ev.titles for n in t.parsed.numbers})
    return MatchEvidence(
        titles=[
            MatchTitle(source=t.source, text=t.text, core=t.parsed.core, optional=list(t.parsed.optional))
            for t in ev.titles
        ],
        years=[MatchYear(year=y.year, sources=list(y.sources), reliability=_round(y.reliability)) for y in ev.years],
        numbers=numbers,
        runtime_min=minutes,
        runtime_source=runtime.source if runtime is not None else None,
        p_tv=ev.p_tv,
        kind_reasons=list(ev.kind_reasons),
    )


def candidate_record(scored: ScoredCandidate, extra_flags: Sequence[str] = ()) -> MatchCandidate:
    c = scored.candidate
    p = scored.parts
    return MatchCandidate(
        title=c.title,
        year=c.year,
        kind="tv" if c.kind.value == "tv" else "movie",
        runtime=c.runtime_minutes,
        providers=list(c.providers),
        provider=c.providers[0] if c.providers else None,
        ids=dict(c.ids),
        score=_round(scored.score),
        parts=MatchParts(
            title=_round(p.title),
            year=_round(p.year),
            runtime=_round(p.runtime),
            kind=_round(p.kind),
            agreement=_round(p.agreement),
        ),
        flags=[*scored.flags, *extra_flags],
    )


def build_match(
    *,
    decision: Decision | None,
    ev: DiscEvidence,
    queries: Sequence[tuple[Query, Sequence[Kind]]],
    budget: Budget,
    ranked: Sequence[ScoredCandidate],
    shortlist: int,
    runner_up: float | None,
    thresholds: Thresholds,
    exact: str | None = None,
    text_disagrees: bool = False,
) -> IdentifyMatch:
    """`decision` None records an exact hit (`exact` names how it was found)."""
    flags = ("text_disagrees",) if text_disagrees else ()
    return IdentifyMatch(
        decision=decision.value if decision is not None else "exact",
        exact=exact,  # type: ignore[arg-type]
        text_disagrees=text_disagrees,
        evidence=evidence_record(ev),
        queries=[MatchQuery(text=q.text, kinds=list(kinds)) for q, kinds in queries],
        calls=MatchCalls(list=budget.list_calls, detail=budget.detail_calls, cached=budget.cached),
        candidates=[candidate_record(s, flags if decision is None else ()) for s in ranked[:MAX_STORED_CANDIDATES]],
        shortlist=shortlist,
        runner_up=_round(runner_up) if runner_up is not None else None,
        thresholds=MatchThresholds(
            accept=thresholds.accept, margin=thresholds.margin, floor=thresholds.floor, title_min=thresholds.title_min
        ),
    )


def log_line(job_id: str, match: IdentifyMatch) -> str:
    """`identify match job_id=... decision=accept winner="Blade Runner 2049 (2017)" score=91.5 ...`"""
    top = match.candidates[0] if match.candidates else None
    shown = match.decision in ("accept", "exact")
    winner = f'"{top.title} ({top.year})"' if top is not None and shown else "-"
    parts = ""
    if top is not None:
        p = top.parts
        parts = f" parts=t{p.title:.1f} y{p.year:.1f} r{p.runtime:.1f} k{p.kind:.1f} a{p.agreement:.1f}"
    score = f" score={top.score:.1f}" if top is not None else ""
    runner = f" runner_up={match.runner_up:.1f}" if match.runner_up is not None else ""
    exact = f" exact={match.exact}" if match.exact else ""
    note = " text_disagrees=yes" if match.text_disagrees else ""
    calls = match.calls
    return (
        f"identify match job_id={job_id} decision={match.decision} winner={winner}{score}{runner}{parts}"
        f" calls={calls.list}+{calls.detail}{exact}{note}"
    )
