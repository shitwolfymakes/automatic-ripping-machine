from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

import arm_ripper.extraction_routes as extraction_routes


@pytest.fixture(autouse=True)
def _empty_registry() -> Iterator[None]:
    extraction_routes.drop_all()
    yield
    extraction_routes.drop_all()


def test_unknown_image_has_no_extracted_dir():
    assert extraction_routes.extracted_dir("/media/a.iso") is None


def test_routed_image_returns_its_folder():
    extraction_routes.route("/media/a.iso", Path("/raw/a"))

    assert extraction_routes.extracted_dir("/media/a.iso") == Path("/raw/a")


def test_routing_an_image_again_replaces_the_folder():
    extraction_routes.route("/media/a.iso", Path("/raw/a"))
    extraction_routes.route("/media/a.iso", Path("/raw/b"))

    assert extraction_routes.extracted_dir("/media/a.iso") == Path("/raw/b")


def test_drop_all_returns_every_folder_and_empties_the_registry():
    extraction_routes.route("/media/a.iso", Path("/raw/a"))
    extraction_routes.route("/media/b.iso", Path("/raw/b"))

    assert sorted(extraction_routes.drop_all()) == [Path("/raw/a"), Path("/raw/b")]
    assert extraction_routes.extracted_dir("/media/a.iso") is None
    assert extraction_routes.extracted_dir("/media/b.iso") is None


def test_drop_all_on_an_empty_registry_returns_nothing():
    assert extraction_routes.drop_all() == []
