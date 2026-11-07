from pathlib import Path

from arm_common import DiscType
from arm_common.schemas import ScanTitle
from arm_ripper.scan.makemkv import (
    _TINFO_FIELDS,
    _InfoParser,
    _split_robot_line,
    _scan_title,
    _to_int,
    parse_makemkvcon_info,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_dvd_with_two_titles():
    lines = (FIXTURES / "makemkvcon_dvd_short.txt").read_text().splitlines()
    volume_label, titles, disc_type = parse_makemkvcon_info(lines)

    assert volume_label == "THE_MATRIX_1999"  # CINFO:2 wins (first match)
    assert disc_type == DiscType.DVD  # CINFO:1,"DVD"
    assert len(titles) == 2

    feature = titles[0]
    assert feature.index == 0
    assert feature.duration_seconds == 2 * 3600 + 16 * 60 + 17
    assert feature.chapter_count == 32
    assert feature.size_bytes == 7340032000
    assert feature.source_file == "title00.mkv"

    extra = titles[1]
    assert extra.index == 1
    assert extra.duration_seconds == 113


def test_handles_disc_with_no_titles():
    lines = (FIXTURES / "makemkvcon_no_titles.txt").read_text().splitlines()
    volume_label, titles, disc_type = parse_makemkvcon_info(lines)

    assert volume_label is None
    assert titles == []
    assert disc_type is None


def test_skips_titles_without_duration():
    lines = ['TINFO:5,8,0,"4"', 'TINFO:5,27,0,"title05.mkv"']
    _, titles, _ = parse_makemkvcon_info(lines)
    assert titles == []


def test_ignores_unknown_message_types():
    lines = ['MSG:1005,0,1,"hello"', "DRV:0,2,...", "BOGUS:nope"]
    volume_label, titles, disc_type = parse_makemkvcon_info(lines)
    assert volume_label is None
    assert titles == []
    assert disc_type is None


def test_classifies_blu_ray_from_cinfo():
    # CINFO:1,N,"Blu-ray disc" is the upstream value for BD-Video discs.
    lines = ['CINFO:1,6210,"Blu-ray disc"', 'CINFO:2,0,"GUARDIANS_OF_THE_GALAXY"']
    volume_label, _, disc_type = parse_makemkvcon_info(lines)
    assert volume_label == "GUARDIANS_OF_THE_GALAXY"
    assert disc_type == DiscType.BLURAY


def test_classifies_audio_cd_from_cinfo():
    lines = ['CINFO:1,6201,"Audio CD"']
    _, _, disc_type = parse_makemkvcon_info(lines)
    assert disc_type == DiscType.CD


def test_classifies_unknown_cinfo_string_as_none():
    lines = ['CINFO:1,9999,"Mystery format"']
    _, _, disc_type = parse_makemkvcon_info(lines)
    assert disc_type is None


def test_classifies_dvd_disc_suffix_from_cinfo():
    # MakeMKV v1.18 emits "DVD disc" rather than the "DVD" string v1.17 emitted.
    # Real example from a region-locked Blood Diamond DVD-9 we saw in prod.
    lines = ['CINFO:1,6206,"DVD disc"', 'CINFO:2,0,"BLOOD DIAMOND"']
    volume_label, _, disc_type = parse_makemkvcon_info(lines)
    assert volume_label == "BLOOD DIAMOND"
    assert disc_type == DiscType.DVD


def test_hd_dvd_does_not_match_dvd_branch():
    # "HD-DVD" contains "dvd" — the HD-DVD branch must be checked first
    # so we don't silently treat HD-DVD as a regular DVD.
    lines = ['CINFO:1,6207,"HD-DVD"']
    _, _, disc_type = parse_makemkvcon_info(lines)
    assert disc_type is None  # no enum yet — caller falls back to probe/heuristic


def test_ignores_blank_lines_and_lines_without_colon():
    lines = ["", "   ", "no colon here", 'CINFO:1,0,"DVD"', "TINFO 0 9 0 0:00:05"]
    assert parse_makemkvcon_info(lines) == (None, [], DiscType.DVD)


def test_ignores_cinfo_with_non_int_code():
    assert parse_makemkvcon_info(['CINFO:x,0,"DVD"', 'CINFO:2,0,"LABEL"']) == ("LABEL", [], None)


def test_ignores_cinfo_with_fewer_than_three_fields():
    assert parse_makemkvcon_info(["CINFO:2,0", "CINFO:1", 'CINFO:1,0,"DVD"']) == (None, [], DiscType.DVD)


def test_ignores_tinfo_with_non_int_title_index():
    lines = ['TINFO:x,9,0,"0:00:05"', 'TINFO:1,9,0,"0:00:07"']
    assert parse_makemkvcon_info(lines) == (None, [ScanTitle(index=1, duration_seconds=7)], None)


def test_ignores_tinfo_with_non_int_code():
    lines = ['TINFO:0,x,0,"0:00:05"', 'TINFO:1,9,0,"0:00:07"']
    assert parse_makemkvcon_info(lines) == (None, [ScanTitle(index=1, duration_seconds=7)], None)


def test_ignores_tinfo_with_fewer_than_four_fields():
    lines = ["TINFO:0,9,0", "TINFO:0,9", 'TINFO:1,9,0,"0:00:07"']
    assert parse_makemkvcon_info(lines) == (None, [ScanTitle(index=1, duration_seconds=7)], None)


def test_non_int_chapter_count_stays_none_but_title_is_kept():
    lines = ['TINFO:0,9,0,"0:01:00"', 'TINFO:0,8,0,"many"']
    assert parse_makemkvcon_info(lines) == (None, [ScanTitle(index=0, duration_seconds=60)], None)


def test_non_int_size_stays_none_but_title_is_kept():
    lines = ['TINFO:0,9,0,"0:01:00"', 'TINFO:0,11,0,"big"']
    assert parse_makemkvcon_info(lines) == (None, [ScanTitle(index=0, duration_seconds=60)], None)


def test_unparseable_duration_drops_the_title():
    lines = ['TINFO:0,9,0,"soon"', 'TINFO:0,8,0,"4"', 'TINFO:0,27,0,"title00.mkv"']
    assert parse_makemkvcon_info(lines) == (None, [], None)


def test_unknown_tinfo_code_changes_nothing():
    lines = ['TINFO:0,9,0,"0:00:09"', 'TINFO:0,2,0,"Some name"']
    assert parse_makemkvcon_info(lines) == (None, [ScanTitle(index=0, duration_seconds=9)], None)


def test_all_tinfo_fields_populate_the_title():
    lines = ['TINFO:3,9,0,"1:02:03"', 'TINFO:3,8,0,"12"', 'TINFO:3,11,0,"2048"', 'TINFO:3,27,0,"title03.mkv"']
    expected = ScanTitle(index=3, duration_seconds=3723, chapter_count=12, size_bytes=2048, source_file="title03.mkv")
    assert parse_makemkvcon_info(lines) == (None, [expected], None)


def test_first_cinfo_1_wins_once_classified():
    lines = ['CINFO:1,0,"DVD"', 'CINFO:1,0,"Blu-ray disc"']
    assert parse_makemkvcon_info(lines) == (None, [], DiscType.DVD)


def test_later_cinfo_1_wins_while_disc_type_is_still_unclassified():
    # The guard is `mkv_disc_type is None`, so an unrecognised first value does not lock it.
    lines = ['CINFO:1,0,"Mystery format"', 'CINFO:1,0,"Blu-ray disc"']
    assert parse_makemkvcon_info(lines) == (None, [], DiscType.BLURAY)


def test_first_label_wins_across_cinfo_2_and_30():
    lines = ['CINFO:30,0,"FROM_30"', 'CINFO:2,0,"FROM_2"', 'CINFO:30,0,"LATER_30"']
    assert parse_makemkvcon_info(lines) == ("FROM_30", [], None)


def test_empty_first_label_lets_a_later_one_win():
    lines = ['CINFO:2,0,""', 'CINFO:30,0,"FROM_30"']
    assert parse_makemkvcon_info(lines) == ("FROM_30", [], None)


def test_commas_inside_quotes_are_rejoined():
    lines = ['CINFO:2,0,"Hello, World"', 'TINFO:0,9,0,"0:00:05"', 'TINFO:0,27,0,"a,b.mkv"']
    expected = ScanTitle(index=0, duration_seconds=5, source_file="a,b.mkv")
    assert parse_makemkvcon_info(lines) == ("Hello,World", [expected], None)


def test_titles_are_sorted_by_index_even_when_lines_arrive_out_of_order():
    lines = ['TINFO:2,9,0,"0:00:30"', 'TINFO:0,9,0,"0:00:10"', 'TINFO:1,9,0,"0:00:20"', 'TINFO:0,8,0,"3"']
    _, titles, _ = parse_makemkvcon_info(lines)
    assert titles == [
        ScanTitle(index=0, duration_seconds=10, chapter_count=3),
        ScanTitle(index=1, duration_seconds=20),
        ScanTitle(index=2, duration_seconds=30),
    ]


def test_split_robot_line_skips_blank_whitespace_and_colonless_lines():
    assert _split_robot_line("") is None
    assert _split_robot_line("   \t") is None
    assert _split_robot_line("no colon here") is None


def test_split_robot_line_splits_only_on_the_first_colon():
    assert _split_robot_line('TINFO:0,9,0,"1:02:03"') == ("TINFO", ["0", "9", "0", '"1:02:03"'])


def test_split_robot_line_strips_the_line_and_each_field():
    assert _split_robot_line("  CINFO: 1 ,  2 , x  \n") == ("CINFO", ["1", "2", "x"])


def test_split_robot_line_with_nothing_after_the_colon_gives_one_empty_field():
    assert _split_robot_line("MSG:") == ("MSG", [""])


def test_to_int_parses_ints_and_returns_none_otherwise():
    assert _to_int("12") == 12
    assert _to_int(" 7 ") == 7
    assert _to_int("x") is None
    assert _to_int("") is None


def test_tinfo_fields_covers_exactly_the_known_codes():
    assert set(_TINFO_FIELDS) == {8, 9, 11, 27}


def test_later_unparseable_chapter_count_keeps_the_earlier_valid_one():
    lines = ['TINFO:0,9,0,"0:01:00"', 'TINFO:0,8,0,"4"', 'TINFO:0,8,0,"many"']
    _, titles, _ = parse_makemkvcon_info(lines)
    assert titles[0].chapter_count == 4


def test_scan_title_without_a_duration_is_none():
    assert _scan_title(0, {"chapter_count": 4}) is None


def test_scan_title_with_a_non_int_duration_is_none():
    assert _scan_title(0, {"duration_seconds": "60"}) is None


def test_scan_title_builds_the_exact_scan_title_from_a_full_entry():
    entry: dict[str, object] = {
        "duration_seconds": 60,
        "chapter_count": 4,
        "size_bytes": 2048,
        "source_file": "title02.mkv",
    }
    assert _scan_title(2, entry) == ScanTitle(
        index=2, duration_seconds=60, chapter_count=4, size_bytes=2048, source_file="title02.mkv"
    )


def test_scan_title_maps_wrongly_typed_optional_values_to_none():
    entry: dict[str, object] = {"duration_seconds": 60, "chapter_count": "4", "size_bytes": "2048", "source_file": 7}
    assert _scan_title(1, entry) == ScanTitle(index=1, duration_seconds=60)


def test_on_cinfo_code_1_sets_disc_type_only_while_unset():
    parser = _InfoParser()
    parser.on_cinfo(["1", "0", '"Blu-ray disc"'])
    parser.on_cinfo(["1", "0", '"DVD"'])
    assert parser.mkv_disc_type == DiscType.BLURAY


def test_on_cinfo_code_1_with_unclassified_value_leaves_type_unset_for_a_later_one():
    parser = _InfoParser()
    parser.on_cinfo(["1", "0", '"???"'])
    assert parser.mkv_disc_type is None
    parser.on_cinfo(["1", "0", '"DVD"'])
    assert parser.mkv_disc_type == DiscType.DVD


def test_on_cinfo_codes_2_and_30_set_the_label_only_while_empty():
    parser = _InfoParser()
    parser.on_cinfo(["2", "0", '""'])
    assert parser.volume_label == ""
    parser.on_cinfo(["30", "0", '"FIRST"'])
    parser.on_cinfo(["2", "0", '"SECOND"'])
    assert parser.volume_label == "FIRST"


def test_on_cinfo_with_non_int_code_changes_nothing():
    parser = _InfoParser()
    parser.on_cinfo(["x", "0", '"DVD"'])
    assert (parser.volume_label, parser.mkv_disc_type) == (None, None)


def test_on_tinfo_fills_the_entry_via_the_table():
    parser = _InfoParser()
    parser.on_tinfo(["3", "27", "0", '"title03.mkv"'])
    parser.on_tinfo(["3", "8", "0", '"12"'])
    assert parser.titles == {3: {"source_file": "title03.mkv", "chapter_count": 12}}


def test_on_tinfo_with_non_int_index_or_code_changes_nothing():
    parser = _InfoParser()
    parser.on_tinfo(["x", "8", "0", '"1"'])
    parser.on_tinfo(["0", "y", "0", '"1"'])
    assert parser.titles == {}


def test_on_tinfo_with_unknown_code_creates_the_empty_entry():
    parser = _InfoParser()
    parser.on_tinfo(["4", "99", "0", '"v"'])
    assert parser.titles == {4: {}}


def test_feed_routes_cinfo_and_tinfo_and_ignores_everything_else():
    parser = _InfoParser()
    parser.feed('CINFO:2,0,"LABEL"')
    parser.feed('TINFO:0,8,0,"5"')
    parser.feed("CINFO:2,0")
    parser.feed("TINFO:0,8,0")
    parser.feed('MSG:1005,0,1,"x"')
    parser.feed("")
    parser.feed("no colon")
    assert parser.volume_label == "LABEL"
    assert parser.titles == {0: {"chapter_count": 5}}


def test_scan_titles_sorts_by_index_and_drops_titles_without_duration():
    parser = _InfoParser()
    parser.titles = {2: {"duration_seconds": 30}, 1: {"chapter_count": 3}, 0: {"duration_seconds": 10}}
    assert parser.scan_titles() == [
        ScanTitle(index=0, duration_seconds=10),
        ScanTitle(index=2, duration_seconds=30),
    ]
