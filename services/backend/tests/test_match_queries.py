from datetime import UTC, datetime

import pytest

from arm_backend.metadata.match.evidence import build_evidence
from arm_backend.metadata.match.queries import MAX_QUERIES, Query, build_queries

NOW = datetime(2026, 11, 27, tzinfo=UTC)


def _queries(*, bd_title: str | None = None, iso_name: str | None = None, label: str | None = None) -> list[Query]:
    ev = build_evidence(
        bd_title=bd_title,
        iso_name=iso_name,
        label=label,
        titles=[],
        structured=False,
        set_number=None,
        num_sets=None,
        now=NOW,
    )
    return build_queries(ev)


def _texts(queries: list[Query]) -> list[str]:
    return [q.text for q in queries]


def test_blade_runner_2049_3d_is_one_query() -> None:
    queries = _queries(bd_title="Blade Runner 2049 - 3D Blu-ray™", iso_name="Blade_Runner_2049_(2017)_[3D].iso")
    assert queries == [Query("Blade Runner 2049", "bd_title", "v1")]


def test_wonder_woman_1984_adds_the_year_less_variant() -> None:
    queries = _queries(bd_title="Wonder Woman 1984", label="WONDER_WOMAN_1984")
    assert queries == [Query("Wonder Woman 1984", "bd_title", "v1"), Query("Wonder Woman", "bd_title", "v2")]


def test_a_lone_year_title_is_searched_alone_once() -> None:
    assert _queries(label="1917") == [Query("1917", "label", "v1")]


def test_a_title_with_a_separator_adds_its_head() -> None:
    queries = _queries(bd_title="Star Wars: The Empire Strikes Back")
    assert queries == [
        Query("Star Wars The Empire Strikes Back", "bd_title", "v1"),
        Query("Star Wars", "bd_title", "v3"),
    ]


def test_a_head_with_one_content_token_is_not_a_query() -> None:
    assert _texts(_queries(bd_title="Alien: Resurrection")) == ["Alien Resurrection"]
    assert _texts(_queries(bd_title="The Hobbit: An Unexpected Journey")) == ["The Hobbit An Unexpected Journey"]


def test_year_variant_needs_a_content_token_left() -> None:
    assert _texts(_queries(label="HEAT_1995")) == ["HEAT 1995", "HEAT"]
    assert _texts(_queries(label="1984")) == ["1984"]


def test_sources_with_the_same_content_tokens_are_one_query() -> None:
    queries = _queries(bd_title="Indiana Jones and the Last Crusade", label="INDIANA_JONES_LAST_CRUSADE")
    assert queries == [Query("Indiana Jones and the Last Crusade", "bd_title", "v1")]


def test_roman_numerals_dedupe_with_digits() -> None:
    assert _texts(_queries(bd_title="Rocky II", label="ROCKY_2")) == ["Rocky II"]


def test_distinct_sources_each_contribute_in_source_order() -> None:
    queries = _queries(bd_title="The Matrix", iso_name="Matrix Reloaded (2003)", label="MATRIX_REVOLUTIONS")
    assert [(q.source, q.text) for q in queries] == [
        ("bd_title", "The Matrix"),
        ("iso_name", "Matrix Reloaded"),
        ("label", "MATRIX REVOLUTIONS"),
    ]


def test_hard_cap() -> None:
    queries = _queries(
        bd_title="Alpha Beta 1999",
        iso_name="Gamma Delta: Epsilon Zeta 2001",
        label="ETA_THETA_2003",
    )
    assert len(queries) == MAX_QUERIES
    assert [q.source for q in queries] == ["bd_title", "bd_title", "iso_name", "iso_name"]


def test_markers_noise_and_empty_sources_make_no_query() -> None:
    assert _queries() == []
    assert _queries(label="___") == []
    assert _texts(_queries(label="KOLCHAK_THE_NIGHT_STALKER_DISC_1")) == ["KOLCHAK THE NIGHT STALKER"]


def test_no_query_is_a_trimmed_chain_of_another() -> None:
    """Only the three fixed variants exist: v2 differs from v1 by one trailing year, v3 cuts at a separator."""
    queries = _queries(bd_title="Star Wars: Episode V - The Empire Strikes Back 1980")
    assert [q.variant for q in queries] == ["v1", "v2", "v3"]
    v1, v2, v3 = (q.text.split() for q in queries)
    assert v2 == v1[:-1]
    assert v1[: len(v3)] == v3
    assert len(v1) - len(v3) > 1


@pytest.mark.parametrize(
    "label",
    ["BLADE_RUNNER_2049", "ALIEN_3", "THE_MATRIX_NTSC", "APOLLO_13_UHD", "FEATURE_16x9_SKU12"],
)
def test_queries_never_end_in_format_noise_or_markers(label: str) -> None:
    for query in _queries(label=label):
        assert query.text.split()[-1].lower() not in {"ntsc", "uhd", "16x9", "sku12"}
