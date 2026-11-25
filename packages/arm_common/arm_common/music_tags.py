"""What a music track's encoded file may carry: one choice per `MusicTags` field, then the cover.

A music session's `music_tag_fields` lists the choices it has switched on.
The values are `MusicTagField`'s, in its order; a test pins the tag choices
to the `MusicTags` fields.
"""

from arm_common.enums import MusicTagField

COVER = MusicTagField.COVER.value

MUSIC_TAG_CHOICES: tuple[str, ...] = tuple(choice.value for choice in MusicTagField)
