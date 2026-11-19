"""The ripper's event message builders."""

import pytest

from arm_common import DiscType
from arm_ripper.rip_events import disc_type_label, rip_started_message


@pytest.mark.parametrize(
    ("disc_type", "label"),
    [
        (DiscType.CD, "CD"),
        (DiscType.BLURAY, "Blu-ray"),
        (DiscType.DVD, "DVD"),
        (DiscType.DATA, "data disc"),
        (DiscType.UNKNOWN, "unknown disc"),
    ],
)
def test_disc_type_label_is_human(disc_type: DiscType, label: str) -> None:
    assert disc_type_label(disc_type) == label


def test_rip_started_message_names_disc_tracks_preset_and_tool() -> None:
    assert (
        rip_started_message("CD", 19, "rpr_builtin_music_standard", "abcde")
        == "rip started: CD, 19 tracks, preset rpr_builtin_music_standard (abcde)"
    )


def test_rip_started_message_singular_track() -> None:
    assert rip_started_message("data disc", 1, "p", "dd") == "rip started: data disc, 1 track, preset p (dd)"
