"""Disc title text as classified tokens.

A disc names itself in several places (the studio's BDMT name, an ISO file name, the volume label), each with
its own noise: format branding (`3D Blu-ray™`), edition words, season / disc markers, a release year. Nothing is
deleted blindly. Each token lands in one class and the class decides how it is used:

* content and numbers are required evidence: a candidate that lacks one pays for it;
* format noise and edition words are optional evidence: they count when the candidate has them and cost
  nothing when it does not. At the tail of the title (or in brackets) they also leave the query text;
* markers (`S1D2`, `DISC 1 OF 4`, `P2`, `SEASON 3`) are removed and kept as season / disc numbers;
* a parenthesised year is removed and kept as a year; a bare year in the plausible range stays in the title as an
  optional token and is also a weak year candidate; any other number (`2049`) is a title number.

Pure; no I/O.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

STOPWORDS = frozenset({"the", "a", "an", "and", "of"})

_ROMAN_NUMERALS = {
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "x": "10",
}

# `blu-ray` is folded to one token before splitting, so `blu` and `ray` are not noise words on their own.
FORMAT_NOISE = frozenset(
    {
        "3d",
        "2d",
        "bluray",
        "tm",
        "bd",
        "bd25",
        "bd50",
        "uhd",
        "4k",
        "hdr",
        "dvd",
        "dvd5",
        "dvd9",
        "ntsc",
        "pal",
        "secam",
        "16x9",
        "4x3",
        "ws",
        "widescreen",
        "fs",
        "fullscreen",
    }
)
_SKU_RE = re.compile(r"sku\d*")
EDITION_WORDS = frozenset(
    {
        "extended",
        "directors",
        "director",
        "cut",
        "theatrical",
        "unrated",
        "uncut",
        "special",
        "edition",
        "collectors",
        "remastered",
        "anniversary",
        "ultimate",
        "imax",
        "final",
        "limited",
    }
)

# UDF / ISO 9660 volume ids top out at 32 characters; a label this long was probably cut.
TRUNCATED_LABEL_LENGTH = 31
TRUNCATION_PREFIX_MIN = 4

_MIN_BARE_YEAR = 1900
_MAX_NUMBER_DIGITS = 4
_COUNT_MAX = 999
_WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

_WORD_RE = re.compile(r"[^\W_]+")
_BRACKET_RE = re.compile(r"[\[(]([^\[\]()]*)[\])]")
_SEPARATOR_RE = re.compile(r":|\s[-–—]|[-–—]\s")
_BLURAY_RE = re.compile(r"blu[\s._-]*ray", re.IGNORECASE)
_BLURAY_TM_RE = re.compile(r"\b(bluray)(tm)\b", re.IGNORECASE)
_SUPERSCRIPT_RE = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉]")
_APOSTROPHES = str.maketrans("", "", "'’ʼ`")

# Trailing markers. Each needs a token before it (a marker never empties the title).
_COMBINED_RE = re.compile(r" s(\d+) ?(?:d|disc) ?(\d+)$")
_DISC_WORD_RE = re.compile(r" disc (" + "|".join(_WORD_NUMBERS) + r")$")
_DISC_RE = re.compile(r" (p|d|disc) ?(\d+)(?: of (\d+))?$")
_SEASON_KEYWORD_RE = re.compile(r" season ?(\d+)$")
_SEASON_RE = re.compile(r" s(\d+)$")


class TokenKind(StrEnum):
    CONTENT = "content"
    NUMBER = "number"
    YEAR = "year"
    NOISE = "noise"
    EDITION = "edition"


_OPTIONAL_KINDS = frozenset({TokenKind.NOISE, TokenKind.EDITION})


@dataclass(frozen=True)
class Token:
    surface: str
    norm: str
    kind: TokenKind
    # A title separator (`: ` or ` - `) sits between this token and the one before it.
    sep_before: bool = False

    @property
    def is_stopword(self) -> bool:
        return self.norm in STOPWORDS


@dataclass(frozen=True)
class TitleYear:
    year: int
    # Written bare in the text (a release year or part of the title) rather than as `(YYYY)`.
    bare: bool
    # The last token of the title as queried.
    trailing: bool


@dataclass(frozen=True)
class Markers:
    season: int | None = None
    disc: int | None = None
    disc_total: int | None = None
    part_only: bool = False


@dataclass(frozen=True)
class ParsedTitle:
    text: str
    # What a query carries: the title minus tail noise, brackets, markers and parenthesised years.
    tokens: tuple[Token, ...]
    # Normalised tokens a candidate must have, and those that count only when it has them.
    required: tuple[str, ...]
    optional: tuple[str, ...]
    years: tuple[TitleYear, ...]
    season: int | None
    disc: int | None
    disc_total: int | None
    part_only: bool
    # An edition word was stripped from the title.
    edition: bool
    truncated: bool

    @property
    def core(self) -> str:
        return " ".join(t.surface for t in self.tokens)

    @property
    def content(self) -> tuple[str, ...]:
        """The query's tokens with stopwords out: the key queries are deduplicated on."""
        return tuple(t.norm for t in self.tokens if not t.is_stopword)

    @property
    def numbers(self) -> tuple[str, ...]:
        return tuple(t for t in self.required if t.isdigit())


def _fold(text: str) -> str:
    """NFKC (full width to half width, `³` to `3`), `™` and `&` spelled out, `blu-ray` as one word, no apostrophes."""
    text = text.replace("™", " tm ")
    text = _SUPERSCRIPT_RE.sub(lambda m: " " + unicodedata.normalize("NFKC", m.group()) + " ", text)
    text = unicodedata.normalize("NFKC", text).replace("&", " and ")
    text = _BLURAY_RE.sub("bluray", text)
    text = _BLURAY_TM_RE.sub(r"\1 \2", text)
    return text.translate(_APOSTROPHES)


def _classify(norm: str, now_year: int) -> TokenKind:
    if norm.isascii() and norm.isdigit():
        is_year = len(norm) == _MAX_NUMBER_DIGITS and _MIN_BARE_YEAR <= int(norm) <= now_year + 1
        return TokenKind.YEAR if is_year else TokenKind.NUMBER
    if norm in FORMAT_NOISE or _SKU_RE.fullmatch(norm):
        return TokenKind.NOISE
    if norm in EDITION_WORDS:
        return TokenKind.EDITION
    return TokenKind.CONTENT


def _tokenize(text: str, now_year: int) -> list[Token]:
    tokens: list[Token] = []
    previous_end = 0
    for match in _WORD_RE.finditer(text):
        surface = match.group()
        norm = surface.casefold()
        norm = _ROMAN_NUMERALS.get(norm, norm)
        gap = text[previous_end : match.start()]
        sep = bool(tokens) and bool(_SEPARATOR_RE.search(gap.replace("_", " ")))
        tokens.append(Token(surface, norm, _classify(norm, now_year), sep))
        previous_end = match.end()
    return tokens


def _is_year_text(inner: str, now_year: int) -> int | None:
    stripped = inner.strip()
    if len(stripped) == _MAX_NUMBER_DIGITS and stripped.isascii() and stripped.isdigit():
        year = int(stripped)
        return year if _MIN_BARE_YEAR <= year <= now_year + 1 else None
    return None


@dataclass
class _Brackets:
    years: list[int]
    noise: list[Token]


def _extract_brackets(text: str, now_year: int) -> tuple[str, _Brackets]:
    """Remove `(YYYY)` and bracketed noise or edition words; other brackets become a separator."""
    found = _Brackets([], [])

    def replace(match: re.Match[str]) -> str:
        inner = match.group(1)
        year = _is_year_text(inner, now_year)
        if year is not None:
            found.years.append(year)
            return " "
        inner_tokens = _tokenize(inner, now_year)
        if inner_tokens and all(t.kind in _OPTIONAL_KINDS for t in inner_tokens):
            found.noise.extend(inner_tokens)
            return " "
        return f" - {inner} "

    return _BRACKET_RE.sub(replace, text), found


def _bounded(text: str) -> int | None:
    try:
        value = int(text)
    except ValueError:
        return None
    return value if 0 <= value <= _COUNT_MAX else None


def _tail_marker(tokens: list[Token], markers: Markers) -> tuple[list[Token], Markers] | None:
    """Strip one trailing marker, or None when the tail has none."""
    joined = " ".join(t.norm for t in tokens)
    for build in (_combined, _disc_word, _disc, _season_keyword, _season):
        found = build(joined)
        if found is not None:
            matched, update = found
            cut = matched.strip().count(" ") + 1
            return tokens[:-cut], _merged(markers, update)
    return None


def _combined(joined: str) -> tuple[str, Markers] | None:
    m = _COMBINED_RE.search(joined)
    return (m.group(), Markers(season=_bounded(m.group(1)), disc=_bounded(m.group(2)))) if m else None


def _disc_word(joined: str) -> tuple[str, Markers] | None:
    m = _DISC_WORD_RE.search(joined)
    return (m.group(), Markers(disc=_WORD_NUMBERS[m.group(1)])) if m else None


def _disc(joined: str) -> tuple[str, Markers] | None:
    m = _DISC_RE.search(joined)
    if not m:
        return None
    disc = _bounded(m.group(2))
    total = _bounded(m.group(3)) if m.group(3) else None
    if total is not None and disc is not None and total < disc:
        total = None
    return m.group(), Markers(disc=disc, disc_total=total, part_only=m.group(1) == "p")


def _season_keyword(joined: str) -> tuple[str, Markers] | None:
    m = _SEASON_KEYWORD_RE.search(joined)
    return (m.group(), Markers(season=_bounded(m.group(1)))) if m else None


def _season(joined: str) -> tuple[str, Markers] | None:
    m = _SEASON_RE.search(joined)
    return (m.group(), Markers(season=_bounded(m.group(1)))) if m else None


def _merged(old: Markers, new: Markers) -> Markers:
    """A marker found nearer the title does not overwrite one already found nearer the tail."""
    season = old.season if old.season is not None else new.season
    disc = old.disc if old.disc is not None else new.disc
    total = old.disc_total if old.disc_total is not None else new.disc_total
    part_only = (old.part_only or new.part_only) and season is None
    return Markers(season, disc, total, part_only)


def _is_title_word(token: Token) -> bool:
    return token.kind in (TokenKind.CONTENT, TokenKind.NUMBER, TokenKind.YEAR) and not token.is_stopword


def _strip_tail_noise(tokens: list[Token]) -> tuple[list[Token], list[Token]]:
    """Split off a trailing run of noise / edition tokens, unless nothing would be left of the title."""
    end = len(tokens)
    while end > 0 and tokens[end - 1].kind in _OPTIONAL_KINDS:
        end -= 1
    head, run = tokens[:end], tokens[end:]
    if run and any(_is_title_word(t) for t in head):
        return head, run
    return tokens, []


def _strip_tail(tokens: list[Token]) -> tuple[list[Token], list[Token], Markers]:
    """Alternately strip trailing noise and trailing markers until neither applies."""
    markers = Markers()
    stripped: list[Token] = []
    while True:
        tokens, run = _strip_tail_noise(tokens)
        stripped = run + stripped
        found = _tail_marker(tokens, markers)
        if not run and found is None:
            return tokens, stripped, markers
        if found is not None:
            tokens, markers = found


def _required_tokens(tokens: list[Token]) -> list[Token]:
    """The title words a candidate must carry. A title is never empty: a lone bare year, then lone noise or
    edition words (`Special`), then lone stopwords stand in when nothing else is left."""
    tiers = (
        [t for t in tokens if t.kind in (TokenKind.CONTENT, TokenKind.NUMBER) and not t.is_stopword],
        [t for t in tokens if t.kind is TokenKind.YEAR],
        [t for t in tokens if t.kind in _OPTIONAL_KINDS],
        list(tokens),
    )
    return next((tier for tier in tiers if tier), [])


def _unique(norms: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(norms))


def _title_years(tokens: list[Token], required: list[Token], paren: list[int]) -> tuple[TitleYear, ...]:
    years = [TitleYear(y, bare=False, trailing=False) for y in paren]
    required_ids = {id(t) for t in required}
    for index, token in enumerate(tokens):
        if token.kind is TokenKind.YEAR and id(token) not in required_ids:
            years.append(TitleYear(int(token.norm), bare=True, trailing=index == len(tokens) - 1))
    return tuple(years)


def parse_title(text: str, *, now_year: int, truncated: bool = False) -> ParsedTitle:
    """Classify the tokens of one disc title text. `now_year` fixes the plausible range of a bare year.
    `truncated`: the text is a volume label that hit the 32-character limit."""
    folded, brackets = _extract_brackets(_fold(text), now_year)
    tokens, stripped, markers = _strip_tail(_tokenize(folded, now_year))
    stripped = brackets.noise + stripped
    required = _required_tokens(tokens)
    required_ids = {id(t) for t in required}
    optional = [
        t for t in tokens if id(t) not in required_ids and not t.is_stopword and t.kind is not TokenKind.CONTENT
    ]
    return ParsedTitle(
        text=text,
        tokens=tuple(tokens),
        required=_unique(t.norm for t in required),
        optional=_unique(t.norm for t in [*optional, *stripped]),
        years=_title_years(tokens, required, brackets.years),
        season=markers.season,
        disc=markers.disc,
        disc_total=markers.disc_total,
        part_only=markers.part_only,
        edition=any(t.kind is TokenKind.EDITION for t in stripped),
        truncated=truncated,
    )


def candidate_tokens(title: str) -> frozenset[str]:
    """A candidate title as a set of normalised words, stopwords out (the same folding as a disc title)."""
    tokens = _tokenize(_fold(title), now_year=0)
    return frozenset(t.norm for t in tokens if not t.is_stopword)
