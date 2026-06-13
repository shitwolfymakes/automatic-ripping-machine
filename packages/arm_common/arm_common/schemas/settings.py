from pydantic import BaseModel

from arm_common.config_metadata import ConfigFieldMeta


class SettingsGroup(BaseModel):
    """A named section of the settings page (e.g. Metadata, Ripping, System)."""

    name: str
    fields: list[ConfigFieldMeta]


class SettingsSchemaResponse(BaseModel):
    """Render metadata for the settings page — grouped field classification.
    Static (derived from CONFIG_FIELD_META); values come from /api/config and
    /api/settings/infra."""

    groups: list[SettingsGroup]
