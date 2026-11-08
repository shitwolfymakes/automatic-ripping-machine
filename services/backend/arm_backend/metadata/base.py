"""Result and error types every metadata provider client shares."""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class MetadataResult:
    title: str
    year: int | None
    kind: Literal["movie", "tv", "music"]
    payload: dict[str, Any] = field(default_factory=dict)
    # Stamped by the dispatcher's _call wrapper (the one place that knows
    # which client produced the hit); None for results built outside it.
    provider: str | None = None


class LookupError(Exception):
    """Provider returned no usable result, or auth/transport failed."""


class LookupTimeout(LookupError):
    """Provider exceeded its per-call timeout budget."""
