"""One weighted identify: evidence -> queries -> retrieve -> score -> decide, with the second-kind pass (spec 3, 5)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from arm_common import Config
from arm_common.enums import MediaType
from arm_common.schemas import IdentifyMatch

from arm_backend.metadata.base import MetadataResult
from arm_backend.metadata.match.decide import (
    DEFAULT_THRESHOLDS,
    Decision,
    Thresholds,
    Verdict,
    decide,
    text_disagrees,
)
from arm_backend.metadata.match.evidence import DiscEvidence
from arm_backend.metadata.match.explain import build_match
from arm_backend.metadata.match.queries import Query, build_queries
from arm_backend.metadata.match.retrieve import Budget, Retrieved, Retriever, ids_of, other_kind, plan_kinds, runtime_of
from arm_backend.metadata.match.score import Candidate, ScoredCandidate, rank_candidates, score_candidate
from arm_backend.metadata.sources import Kind


@dataclass(frozen=True)
class Weighted:
    """The outcome: the winner's own provider record on accept, else None; and why."""

    result: MetadataResult | None
    match: IdentifyMatch


def _judge(
    ev: DiscEvidence, pool: Sequence[Retrieved], thresholds: Thresholds
) -> tuple[Verdict, list[ScoredCandidate]]:
    ranked = rank_candidates(ev, [r.candidate for r in pool])
    return decide(ranked, thresholds), ranked


def _count(verdict: Verdict) -> int:
    return len(verdict.shortlist) if verdict.decision is Decision.SHORTLIST else 0


async def identify_weighted(
    retriever: Retriever, cfg: Config, ev: DiscEvidence, *, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> Weighted:
    """Search every enabled provider with the disc's few queries, score every candidate against the disc and decide.

    A pass that does not accept searches the other kind once, with the first-variant queries only."""
    queries = build_queries(ev)
    budget = Budget()
    asked: list[tuple[Query, list[Kind]]] = [(q, []) for q in queries]
    pool: list[Retrieved] = []
    if queries:
        kinds = plan_kinds(ev.p_tv)
        pool = await retriever.search(cfg, ev, queries, kinds, budget)
        for _, seen in asked:
            seen.extend(kinds)
    verdict, ranked = _judge(ev, pool, thresholds)
    second = other_kind(plan_kinds(ev.p_tv)) if queries else None
    if verdict.decision is not Decision.ACCEPT and second is not None:
        first = [q for q in queries if q.variant == "v1"]
        pool = [*pool, *await retriever.search(cfg, ev, first, (second,), budget)]
        for q, seen in asked:
            if q in first:
                seen.append(second)
        verdict, ranked = _judge(ev, pool, thresholds)
    match = build_match(
        decision=verdict.decision,
        ev=ev,
        queries=asked,
        budget=budget,
        ranked=ranked,
        shortlist=_count(verdict),
        runner_up=verdict.runner_up_score,
        thresholds=thresholds,
    )
    if verdict.decision is not Decision.ACCEPT or verdict.winner is None:
        return Weighted(None, match)
    winner = next(r for r in pool if r.candidate is verdict.winner.candidate)
    return Weighted(winner.result, match)


def exact_candidate(result: MetadataResult) -> Candidate | None:
    """An exact hit as a candidate, from the data already in it; None for anything that is not a movie or show."""
    if result.kind not in ("movie", "tv"):
        return None
    source = result.provider or ""
    payload = result.payload or {}
    original = payload.get("original_title") or payload.get("original_name")
    return Candidate(
        title=result.title,
        kind=MediaType(result.kind),
        year=result.year,
        original_title=original if isinstance(original, str) and original != result.title else None,
        runtime_minutes=runtime_of(source, result.kind, payload),
        providers=(source,) if source else (),
        provider_rank=0,
        ids=ids_of(source, payload),
    )


def explain_exact(
    ev: DiscEvidence, result: MetadataResult, how: str, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> IdentifyMatch | None:
    """The text score of an exact hit (TheDiscDB, fingerprint). It is never re-ranked: the hit applies either way,
    and a very low score only sets `text_disagrees` for the card to say so (D68)."""
    candidate = exact_candidate(result)
    if candidate is None:
        return None
    no_queries: list[tuple[Query, list[Kind]]] = []
    scored = score_candidate(ev, candidate)
    return build_match(
        decision=None,
        ev=ev,
        queries=no_queries,
        budget=Budget(),
        ranked=[scored],
        shortlist=0,
        runner_up=None,
        thresholds=thresholds,
        exact=how,
        text_disagrees=text_disagrees(scored, thresholds),
    )
