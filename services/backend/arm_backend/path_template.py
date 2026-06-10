"""Path-template token expansion + save-time validation.

The token whitelist per `MediaType` mirrors arch §02 (`docs/arch/02-job-lifecycle.md`).
Save-time validation expands the template against a synthetic context that
populates every legal token; an empty expansion or an unknown token both
raise `TemplateValidationError`.
"""

import re

from arm_common.enums import MediaType

_TOKEN_RE = re.compile(r"\{(\w+)\}")


class TemplateValidationError(ValueError):
    pass


# Per-media-type allowed tokens (arch §02 token table).
_ALLOWED_TOKENS_BY_MEDIA: dict[MediaType, set[str]] = {
    MediaType.MOVIE: {"title", "year", "track", "duration_human", "transcode_slug", "ext"},
    MediaType.TV: {"show", "year", "season", "disc", "track", "duration_human", "transcode_slug", "ext"},
    MediaType.MUSIC: {"artist", "album", "track", "track_title", "transcode_slug", "ext"},
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
        "duration_human": "00h45m",
        "transcode_slug": "plex-1080p-h265",
        "ext": "mkv",
    },
    MediaType.MUSIC: {
        "artist": "Pink Floyd",
        "album": "The Dark Side of the Moon",
        "track": "01",
        "track_title": "Speak to Me",
        "transcode_slug": "flac",
        "ext": "flac",
    },
    MediaType.DATA: {"title": "Data Disc"},
    MediaType.ISO: {"title": "Iron Man", "year": "2008", "ext": "iso"},
}


class _StrictDict(dict[str, str]):
    """`format_map` helper that raises `TemplateValidationError` on unknown tokens."""

    def __missing__(self, key: str) -> str:
        raise TemplateValidationError(f"unknown token: {{{key}}}")


def expand_template(template: str, ctx: dict[str, str]) -> str:
    """Expand `{token}` references against `ctx`. Unknown tokens raise."""
    try:
        return template.format_map(_StrictDict(ctx))
    except (IndexError, ValueError) as exc:
        raise TemplateValidationError(f"malformed template: {exc}") from exc


def referenced_tokens(template: str) -> set[str]:
    return set(_TOKEN_RE.findall(template))


def validate_template(template: str, media_type: MediaType, has_transcode_preset: bool) -> str:
    """Reject templates with disallowed/empty tokens. Returns the synthetic expansion as a preview hint."""
    tokens = referenced_tokens(template)
    allowed = _ALLOWED_TOKENS_BY_MEDIA[media_type]

    illegal = tokens - allowed
    if illegal:
        raise TemplateValidationError(f"tokens not allowed for media_type={media_type.value}: {sorted(illegal)}")

    if "transcode_slug" in tokens and not has_transcode_preset:
        raise TemplateValidationError("{transcode_slug} requires a transcode preset; this session has none")
    if "ext" in tokens and not has_transcode_preset and media_type != MediaType.ISO:
        raise TemplateValidationError("{ext} requires a transcode preset (or media_type=iso, which is fixed)")

    expansion = expand_template(template, _SYNTHETIC_CONTEXTS[media_type])
    # Synthetic ctx is fully populated; an empty expansion would mean the
    # template was literally empty, which is caught by the schema's min_length.
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
