"""Result and error types every metadata provider client shares."""

from dataclasses import dataclass, field
from typing import Any, Literal

import httpx


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


def json_object(r: httpx.Response, provider: str) -> dict[str, Any]:
    """The body of a 200 as a JSON object.

    A proxy error page or captive portal answers 200 with HTML, and a broken
    mirror can answer with a bare list. Either raises `LookupError` (one
    provider's miss, which the dispatcher records and moves past) instead of a
    ValueError or AttributeError that would escape it and fail identify.
    """
    try:
        body = r.json()
    except ValueError as e:
        raise LookupError(f"{provider} returned a non-JSON response") from e
    if not isinstance(body, dict):
        raise LookupError(f"{provider} returned a non-object JSON response")
    return body
