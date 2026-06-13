"""Compose an apprise URL from catalog form values.

The UI posts ``{required: {...}, advanced: {...}}``; this assembles the
``scheme://<required-joined>?<advanced-as-query>`` shape apprise expects.
Services with unusual separators (e.g. Pushover's ``@``) use the raw-URL
escape hatch in the UI instead.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode


def _stringify(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def compose_apprise_url(*, service_id: str, required: dict[str, object], advanced: dict[str, object]) -> str:
    """Assemble an apprise URL from required + advanced field values.

    Required values become URL-encoded path segments in dict-iteration
    order (blank/None segments dropped). Advanced values become query
    parameters; blank/None advanced values are omitted (apprise rejects
    bare ``?key=`` on some plugins).
    """
    path = "/".join(quote(_stringify(v), safe="") for v in required.values() if v not in (None, ""))
    base = f"{service_id}://{path}"
    pairs = [(k, _stringify(v)) for k, v in advanced.items() if v not in (None, "")]
    if pairs:
        return f"{base}?{urlencode(pairs)}"
    return base
