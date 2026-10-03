"""Path-template token expansion + save-time validation.

Templates reference `{token}` (required) or `{token?}` (optional: dropped, with
a wrapping ()/[] pair and one leading space, when its value is empty).

The token whitelist per `MediaType` mirrors arch §02 (`docs/developers/architecture/02-job-lifecycle.md`).
Save-time validation expands the template against a synthetic context that
populates every legal token; an empty expansion or an unknown token both
raise `TemplateValidationError`.
"""

import re

from arm_common.enums import MediaType

_TOKEN_RE = re.compile(r"\{(\w+)(\?)?\}")
# An optional token, optionally wrapped by one ()/[] pair that contains only it,
# optionally preceded by one space. Groups 1-3 hold the name for each shape.
_OPTIONAL_RE = re.compile(r" ?(?:\(\{(\w+)\?\}\)|\[\{(\w+)\?\}\]|\{(\w+)\?\})")


class TemplateValidationError(ValueError):
    pass


# Per-media-type allowed tokens (arch §02 token table).
_ALLOWED_TOKENS_BY_MEDIA: dict[MediaType, set[str]] = {
    MediaType.MOVIE: {"title", "year", "track", "duration_human", "transcode_slug", "ext"},
    MediaType.TV: {
        "show",
        "year",
        "season",
        "disc",
        "track",
        "episode",
        "episode_title",
        "duration_human",
        "transcode_slug",
        "ext",
    },
    MediaType.MUSIC: {"artist", "album", "disc", "track", "track_title", "transcode_slug", "ext"},
    MediaType.DATA: {"title"},
    MediaType.ISO: {"title", "year", "ext"},
}

# Synthetic stand-ins used at save-time validation. Every legal token gets a
# non-empty value so the validator can spot empty expansions and missing tokens.
_SYNTHETIC_CONTEXTS: dict[MediaType, dict[str, str]] = {
    MediaType.MOVIE: {
        "title": "Iron Man",
        "year": "2008",
        "track": "01",
        "duration_human": "02h05m",
        "transcode_slug": "plex-1080p-h265",
        "ext": "mkv",
    },
    MediaType.TV: {
        "show": "Battlestar Galactica",
        "year": "2004",
        "season": "01",
        "disc": "01",
        "track": "01",
        "episode": "01",
        "episode_title": "Pilot",
        "duration_human": "00h45m",
        "transcode_slug": "plex-1080p-h265",
        "ext": "mkv",
    },
    MediaType.MUSIC: {
        "artist": "Pink Floyd",
        "album": "The Dark Side of the Moon",
        "disc": "01",
        "track": "01",
        "track_title": "Speak to Me",
        "transcode_slug": "flac",
        "ext": "flac",
    },
    MediaType.DATA: {"title": "Data Disc"},
    MediaType.ISO: {"title": "Iron Man", "year": "2008", "ext": "iso"},
}


def synthetic_context(media_type: MediaType) -> dict[str, str]:
    """Return a copy of the synthetic stand-in values for a media type.

    Public accessor over the save-time-validation context. Callers (e.g. the
    naming-preview router) may merge real values on top; returning a copy keeps
    the module-level table immutable.
    """
    return dict(_SYNTHETIC_CONTEXTS[media_type])


class _StrictDict(dict[str, str]):
    """`format_map` helper that raises `TemplateValidationError` on unknown tokens."""

    def __missing__(self, key: str) -> str:
        raise TemplateValidationError(f"unknown token: {{{key}}}")


def expand_template(template: str, ctx: dict[str, str]) -> str:
    """Expand `{token}` / `{token?}` references against `ctx`. Unknown tokens raise.

    An optional token whose value is empty is removed together with a ()/[]
    pair wrapping only it and one preceding space; segments are then trimmed of
    edge whitespace and empty ones (with leading/trailing `/`) collapse. That
    collapse only happens when an optional token was dropped; otherwise the
    output is left byte-identical. A result that is empty after that raises.
    """
    dropped = False

    def _optional(m: re.Match[str]) -> str:
        nonlocal dropped
        name = m.group(1) or m.group(2) or m.group(3)
        if name in ctx and not ctx[name]:
            dropped = True
            return ""
        # Present (or unknown, so format_map raises "unknown token"): strip the "?".
        return m.group(0).replace("?}", "}")

    try:
        out = _OPTIONAL_RE.sub(_optional, template).format_map(_StrictDict(ctx))
    except TemplateValidationError:
        raise
    except (IndexError, ValueError) as exc:
        raise TemplateValidationError(f"malformed template: {exc}") from exc
    if dropped:
        out = "/".join(seg for seg in (s.strip() for s in out.split("/")) if seg)
        if not out:
            raise TemplateValidationError("output path is empty once optional tokens with no value are dropped")
    return out


def referenced_tokens(template: str) -> set[str]:
    return {m.group(1) for m in _TOKEN_RE.finditer(template)}


def optional_tokens(template: str) -> set[str]:
    return {m.group(1) for m in _TOKEN_RE.finditer(template) if m.group(2)}


def required_tokens(template: str) -> set[str]:
    """Tokens used at least once without `?` (a token used both ways stays required)."""
    return {m.group(1) for m in _TOKEN_RE.finditer(template) if not m.group(2)}


# Tokens that always have a value when allowed, so `?` on them is meaningless.
NEVER_OPTIONAL = frozenset({"ext", "transcode_slug"})


def expand_without_optional(template: str, media_type: MediaType) -> str | None:
    """Synthetic expansion with every optional token empty; None if the template has none."""
    opt = optional_tokens(template)
    if not opt:
        return None
    ctx = synthetic_context(media_type)
    for tok in opt:
        ctx[tok] = ""
    return expand_template(template, ctx)


def validate_template(template: str, media_type: MediaType, has_transcode_preset: bool) -> str:
    """Reject templates with disallowed/empty tokens. Returns the synthetic expansion as a preview hint."""
    tokens = referenced_tokens(template)
    allowed = _ALLOWED_TOKENS_BY_MEDIA[media_type]

    illegal = tokens - allowed
    if illegal:
        raise TemplateValidationError(f"tokens not allowed for media_type={media_type.value}: {sorted(illegal)}")

    never = optional_tokens(template) & NEVER_OPTIONAL
    if never:
        tok = min(never)
        raise TemplateValidationError(f"{{{tok}?}} can't be optional: {{{tok}}} always has a value when it is allowed")

    if "transcode_slug" in tokens and not has_transcode_preset:
        raise TemplateValidationError("{transcode_slug} requires a transcode preset; this session has none")
    if "ext" in tokens and not has_transcode_preset and media_type != MediaType.ISO:
        raise TemplateValidationError("{ext} requires a transcode preset (or media_type=iso, which is fixed)")

    # Synthetic ctx is fully populated, so this only fails for a literally empty
    # template (also caught by the schema's min_length).
    expansion = expand_template(template, _SYNTHETIC_CONTEXTS[media_type])
    # Raises if nothing is left once every optional token is empty.
    expand_without_optional(template, media_type)
    return expansion


def validate_template_or_http(template: str, media_type: MediaType, has_transcode_preset: bool) -> str:
    """Validate a template; raise FastAPI HTTPException(422) on failure.

    Shared by the sessions-preview and naming routers so the validate->422
    behaviour lives in exactly one place. Returns the synthetic expansion.
    """
    from fastapi import HTTPException, status

    try:
        return validate_template(template, media_type, has_transcode_preset)
    except TemplateValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


# Human-readable description per token, surfaced by GET /api/naming/variables.
_TOKEN_DESCRIPTIONS: dict[str, str] = {
    "title": "Movie/feature title",
    "show": "TV show name",
    "year": "Release year. Write {year?} to drop it, with its brackets, when the year is unknown",
    "season": "Season number, zero-padded",
    "episode": "Episode number, zero-padded (01, or 01-E02 for a two-episode title)",
    "episode_title": "Episode title",
    "disc": "Disc number within the set",
    "track": "Track number, zero-padded",
    "track_title": "Per-track title (music)",
    "artist": "Album artist (music)",
    "album": "Album name (music)",
    "duration_human": "Human-readable runtime, e.g. 02h05m",
    "transcode_slug": "Slug of the applied transcode preset",
    "ext": "Output file extension",
}


def tokens_for_media(media_type: MediaType) -> list[dict[str, str]]:
    """Return the allowed tokens for a media type with descriptions, sorted."""
    return [
        {"token": tok, "description": _TOKEN_DESCRIPTIONS.get(tok, "")}
        for tok in sorted(_ALLOWED_TOKENS_BY_MEDIA[media_type])
    ]
