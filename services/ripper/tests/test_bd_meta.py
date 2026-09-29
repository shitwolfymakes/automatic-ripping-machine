"""BDMT (Blu-ray disc title) parsing and the soft-failing probe."""

from unittest import mock

from arm_common.schemas import BdDiscMeta

from arm_ripper.scan.bd_meta import parse_bdmt, pick_bdmt_file, probe_bd_meta

_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<disclib xmlns="urn:BDA:bdmv;disclib" xmlns:di="urn:BDA:bdmv;discinfo">
  <di:discinfo><di:title>
    <di:name>The West Wing: The Complete Third Season</di:name>
    <di:numSets>6</di:numSets><di:setNumber>2</di:setNumber>
  </di:title></di:discinfo>
</disclib>"""


def test_parse_bdmt_full() -> None:
    assert parse_bdmt(_XML, "eng") == BdDiscMeta(
        name="The West Wing: The Complete Third Season", set_number=2, num_sets=6, language="eng"
    )


def test_parse_bdmt_name_only() -> None:
    xml = _XML.replace(b"<di:numSets>6</di:numSets><di:setNumber>2</di:setNumber>", b"")
    assert parse_bdmt(xml, None) == BdDiscMeta(name="The West Wing: The Complete Third Season")


def test_parse_bdmt_drops_bad_numbers() -> None:
    xml = _XML.replace(b"<di:setNumber>2</di:setNumber>", b"<di:setNumber>two</di:setNumber>")
    meta = parse_bdmt(xml, "eng")
    assert meta is not None and meta.set_number is None and meta.num_sets == 6


def test_parse_bdmt_drops_set_number_above_total() -> None:
    xml = _XML.replace(b"<di:setNumber>2</di:setNumber>", b"<di:setNumber>9</di:setNumber>")
    meta = parse_bdmt(xml, "eng")
    assert meta is not None and (meta.set_number, meta.num_sets) == (None, None)


def test_parse_bdmt_drops_out_of_range_set_number() -> None:
    """A setNumber outside 1-999 must be dropped, not overflow Postgres's
    int4 disc_number column."""
    xml = _XML.replace(b"<di:setNumber>2</di:setNumber>", b"<di:setNumber>100000</di:setNumber>")
    meta = parse_bdmt(xml, "eng")
    assert meta is not None and meta.set_number is None


def test_parse_bdmt_invalid_or_nameless() -> None:
    assert parse_bdmt(b"<not xml", "eng") is None
    assert parse_bdmt(_XML.replace(b"The West Wing: The Complete Third Season", b"   "), "eng") is None


def test_pick_bdmt_file_prefers_english() -> None:
    assert pick_bdmt_file(["bdmt_jpn.xml", "bdmt_eng.xml", "bdmt_fra.xml"]) == ("bdmt_eng.xml", "eng")
    assert pick_bdmt_file(["BDMT_JPN.XML", "bdmt_fra.xml"]) == ("bdmt_fra.xml", "fra")
    assert pick_bdmt_file(["index.bdmv", "bdmt_jpn.xml;1"]) == ("bdmt_jpn.xml;1", "jpn")
    assert pick_bdmt_file(["index.bdmv"]) is None


def test_probe_bd_meta_soft_fails() -> None:
    with mock.patch("arm_ripper.scan.bd_meta._read_bdmt", side_effect=OSError("boom")):
        assert probe_bd_meta("/dev/sr0") is None
