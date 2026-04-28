from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class MetadataResult:
    title: str
    year: int | None
    kind: Literal["movie", "tv", "music"]
    payload: dict[str, Any] = field(default_factory=dict)


class LookupError(Exception):
    """Provider returned no usable result, or auth/transport failed."""


class LookupTimeout(LookupError):
    """Provider exceeded its per-call timeout budget."""
