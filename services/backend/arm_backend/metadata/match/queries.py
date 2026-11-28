"""The few provider queries a disc's title evidence is worth.

Per title source (BDMT name, ISO name, volume label, in that order) at most three variants:

* v1: the core title (tail noise, brackets, markers and parenthesised years removed);
* v2: v1 without a trailing bare year (`WONDER WOMAN 1984` -> `WONDER WOMAN`);
* v3: v1 cut at its last ` - ` or `: ` (`Star Wars: The Empire Strikes Back` -> `Star Wars`).

Queries are deduplicated on their content tokens and capped at `MAX_QUERIES`. There is no word-by-word
trimming, no single word cut out of a longer title and no query made only of noise, markers or a year: the
provider's own fuzzy search covers small differences, and the scorer chooses among the results. Pure; no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from arm_backend.metadata.match.evidence import DiscEvidence
from arm_backend.metadata.match.tokens import ParsedTitle, Token, TokenKind

MAX_QUERIES = 4
# A head cut off at a separator must keep this many content tokens to be a query.
HEAD_MIN_CONTENT = 2

Variant = Literal["v1", "v2", "v3"]


@dataclass(frozen=True)
class Query:
    text: str
    source: str
    variant: Variant


def _content_count(tokens: Sequence[Token]) -> int:
    return sum(1 for t in tokens if not t.is_stopword)


def _without_trailing_year(tokens: Sequence[Token]) -> Sequence[Token] | None:
    if tokens and tokens[-1].kind is TokenKind.YEAR and _content_count(tokens[:-1]) >= 1:
        return tokens[:-1]
    return None


def _head(tokens: Sequence[Token]) -> Sequence[Token] | None:
    cuts = [i for i, t in enumerate(tokens) if t.sep_before]
    if cuts and _content_count(tokens[: cuts[-1]]) >= HEAD_MIN_CONTENT:
        return tokens[: cuts[-1]]
    return None


def _variants(parsed: ParsedTitle) -> list[tuple[Variant, Sequence[Token]]]:
    tokens = parsed.tokens
    candidates: list[tuple[Variant, Sequence[Token] | None]] = [
        ("v1", tokens),
        ("v2", _without_trailing_year(tokens)),
        ("v3", _head(tokens)),
    ]
    return [(variant, found) for variant, found in candidates if found]


def build_queries(ev: DiscEvidence) -> list[Query]:
    """At most `MAX_QUERIES` queries, in source order and v1, v2, v3 order, one per distinct content tuple."""
    seen: set[tuple[str, ...]] = set()
    queries: list[Query] = []
    for title in ev.titles:
        for variant, tokens in _variants(title.parsed):
            key = tuple(t.norm for t in tokens if not t.is_stopword)
            if not key or key in seen:
                continue
            seen.add(key)
            queries.append(Query(" ".join(t.surface for t in tokens), title.source, variant))
            if len(queries) == MAX_QUERIES:
                return queries
    return queries
