"""Which of a music track's tags, and whether its cover, the transcoder writes into the encoded file.

The choice belongs to the music session the track is transcoded with.
"""

from collections.abc import Collection

from arm_common import Session
from arm_common.music_tags import MUSIC_TAG_CHOICES
from arm_common.schemas import MusicTags


def music_tag_fields_setting(sess: Session) -> tuple[str, ...]:
    """The session's switched-on choices in `MUSIC_TAG_CHOICES` order; every choice for a row with no value."""
    value = getattr(sess, "music_tag_fields", None)
    if value is None:
        return MUSIC_TAG_CHOICES
    return tuple(choice for choice in MUSIC_TAG_CHOICES if choice in value)


def enabled_music_tags(tags: MusicTags, enabled: Collection[str]) -> MusicTags:
    """`tags` with every field not in `enabled` cleared, so the transcoder leaves it out of the file."""
    return tags.model_copy(update={name: None for name in MusicTags.model_fields if name not in enabled})


def session_music_tags(tags: MusicTags | None, sess: Session) -> MusicTags | None:
    """A track's tags as its session has them switched on; None for a track with no tags
    (anything but an audio CD track)."""
    if tags is None:
        return None
    return enabled_music_tags(tags, music_tag_fields_setting(sess))
