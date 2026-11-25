"""The music tag choices a session can switch on."""

from arm_common import MediaType, Session
from arm_common.enums import MusicTagField
from arm_common.music_tags import COVER, MUSIC_TAG_CHOICES
from arm_common.schemas import MusicTags


def test_choices_are_the_music_tags_fields_then_the_cover() -> None:
    # Every tag the transcoder can write is a choice, once; the cover comes last.
    assert set(MUSIC_TAG_CHOICES[:-1]) == set(MusicTags.model_fields)
    assert len(MUSIC_TAG_CHOICES) == len(set(MUSIC_TAG_CHOICES))
    assert MUSIC_TAG_CHOICES[-1] == COVER == "cover"


def test_choices_follow_the_enum() -> None:
    assert MUSIC_TAG_CHOICES == tuple(choice.value for choice in MusicTagField)


def test_a_session_writes_every_tag_by_default() -> None:
    def make() -> Session:
        return Session(name="Music", media_type=MediaType.MUSIC, rip_preset_id="rpr", output_path_template="{album}")

    first, second = make(), make()
    assert first.music_tag_fields == list(MUSIC_TAG_CHOICES)
    assert first.music_tag_fields is not second.music_tag_fields  # no shared mutable default
