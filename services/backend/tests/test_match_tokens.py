import pytest

from arm_backend.metadata.match.tokens import ParsedTitle, candidate_tokens, parse_title

NOW_YEAR = 2026


def parse(text: str, *, truncated: bool = False) -> ParsedTitle:
    return parse_title(text, now_year=NOW_YEAR, truncated=truncated)


@pytest.mark.parametrize(
    ("text", "core", "required", "optional"),
    [
        ("Blade Runner 2049 - 3D Blu-ray™", "Blade Runner 2049", ("blade", "runner", "2049"), ("3d", "bluray", "tm")),
        ("Blade Runner 2049 - 3D Blu-rayTM", "Blade Runner 2049", ("blade", "runner", "2049"), ("3d", "bluray", "tm")),
        ("THE_MATRIX_NTSC", "THE MATRIX", ("matrix",), ("ntsc",)),
        ("Uncut Gems", "Uncut Gems", ("gems",), ("uncut",)),
        ("3 Days to Kill", "3 Days to Kill", ("3", "days", "to", "kill"), ()),
        ("ROCKY_II", "ROCKY II", ("rocky", "2"), ()),
        ("ALIEN³", "ALIEN 3", ("alien", "3"), ()),
        ("Ocean's Eleven", "Oceans Eleven", ("oceans", "eleven"), ()),
        ("Fast & Furious", "Fast and Furious", ("fast", "furious"), ()),
        ("FEATURE_16x9_SKU1234", "FEATURE", ("feature",), ("16x9", "sku1234")),
        ("Special", "Special", ("special",), ()),
        ("The Final Cut", "The Final Cut", ("final", "cut"), ()),
        ("Amélie", "Amélie", ("amélie",), ()),
        ("君の名は", "君の名は", ("君の名は",), ()),
        ("Movie (Extended Cut) [4K UHD]", "Movie", ("movie",), ("extended", "cut", "4k", "uhd")),
        ("Blade Runner 2049 3D Blu ray", "Blade Runner 2049", ("blade", "runner", "2049"), ("3d", "bluray")),
    ],
)
def test_title_classes(text: str, core: str, required: tuple[str, ...], optional: tuple[str, ...]) -> None:
    parsed = parse(text)
    assert parsed.core == core
    assert parsed.required == required
    assert set(optional) <= set(parsed.optional)
    assert not set(parsed.optional) & set(parsed.required)


def test_tail_noise_is_not_in_the_core_but_leading_noise_is() -> None:
    assert parse("3D Movies Rock").core == "3D Movies Rock"
    assert parse("Movies Rock 3D").core == "Movies Rock"


def test_edition_words_set_the_flag_only_when_stripped() -> None:
    assert parse("ALIEN_1979_DIRECTORS_CUT").edition
    assert parse("Movie (Theatrical)").edition
    assert not parse("Uncut Gems").edition
    assert not parse("The Final Cut").edition


@pytest.mark.parametrize(
    ("text", "expected_years"),
    [
        ("Blade_Runner_2049_(2017)_[3D]", [(2017, False, False)]),
        ("WONDER_WOMAN_1984", [(1984, True, True)]),
        ("ALIEN_1979_DIRECTORS_CUT", [(1979, True, True)]),
        ("Movie 1999 Remastered Edition", [(1999, True, True)]),
        ("Movie 1999 Part Two Of It", [(1999, True, False)]),
        ("Movie 2027", [(2027, True, True)]),
        ("Movie 2028", []),
        ("BLADE_RUNNER_2049", []),
        ("1917", []),
        ("Movie [1999]", [(1999, False, False)]),
    ],
)
def test_years(text: str, expected_years: list[tuple[int, bool, bool]]) -> None:
    assert [(y.year, y.bare, y.trailing) for y in parse(text).years] == expected_years


def test_a_bare_year_is_optional_unless_it_is_the_only_content() -> None:
    assert parse("WONDER_WOMAN_1984").optional == ("1984",)
    assert parse("WONDER_WOMAN_1984").required == ("wonder", "woman")
    assert parse("1917").required == ("1917",)
    assert parse("1917").optional == ()


def test_numbers_above_next_year_are_title_numbers() -> None:
    parsed = parse("BLADE_RUNNER_2049")
    assert parsed.required == ("blade", "runner", "2049")
    assert parsed.numbers == ("2049",)


@pytest.mark.parametrize(
    ("text", "season", "disc", "total", "part_only", "core"),
    [
        ("SHOW_S1D2", 1, 2, None, False, "SHOW"),
        ("SHOW_S01_D02", 1, 2, None, False, "SHOW"),
        ("SHOW_SEASON_3", 3, None, None, False, "SHOW"),
        ("SHOW_S3", 3, None, None, False, "SHOW"),
        ("Kolchak The Night Stalker - Disc 1 of 4", None, 1, 4, False, "Kolchak The Night Stalker"),
        ("KOLCHAK_THE_NIGHT_STALKER_DISC_1", None, 1, None, False, "KOLCHAK THE NIGHT STALKER"),
        ("SHOW_DISC_TWO", None, 2, None, False, "SHOW"),
        ("HARRY_POTTER_DEATHLY_HALLOWS_P2", None, 2, None, True, "HARRY POTTER DEATHLY HALLOWS"),
        ("Show Season 2 Disc 1", 2, 1, None, False, "Show"),
        ("Show Disc 1 3D", None, 1, None, False, "Show"),
        ("APOLLO_13", None, None, None, False, "APOLLO 13"),
    ],
)
def test_markers(
    text: str, season: int | None, disc: int | None, total: int | None, part_only: bool, core: str
) -> None:
    parsed = parse(text)
    assert (parsed.season, parsed.disc, parsed.disc_total, parsed.part_only) == (season, disc, total, part_only)
    assert parsed.core == core


def test_a_marker_never_leaves_the_title_empty() -> None:
    assert parse("DISC_1").core == "DISC 1"


def test_separators_are_recorded_before_the_token_they_precede() -> None:
    parsed = parse("Star Wars: The Empire Strikes Back")
    assert [t.sep_before for t in parsed.tokens] == [False, False, True, False, False, False]
    spider = parse("Spider-Man - Homecoming")
    assert [t.sep_before for t in spider.tokens] == [False, False, True]


def test_truncated_flag_is_carried() -> None:
    assert parse("INDIANA_JONES_LAST_CRUSAD", truncated=True).truncated
    assert not parse("INDIANA_JONES_LAST_CRUSAD").truncated


def test_content_tuple_drops_stopwords_and_folds_roman_numerals() -> None:
    assert parse("Indiana Jones and the Last Crusade").content == ("indiana", "jones", "last", "crusade")
    assert parse("Rocky II").content == parse("ROCKY_2").content


def test_the_single_letter_i_stays_a_word() -> None:
    assert parse("I Am Legend").required == ("i", "am", "legend")


def test_candidate_tokens() -> None:
    assert candidate_tokens("Blade Runner 2049") == frozenset({"blade", "runner", "2049"})
    assert candidate_tokens("Indiana Jones and the Temple of Doom") == frozenset({"indiana", "jones", "temple", "doom"})
    assert candidate_tokens("Rocky IV") == frozenset({"rocky", "4"})
    assert candidate_tokens("") == frozenset()
