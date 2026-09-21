from arm_common.config_metadata import ConfigFieldMeta
from arm_common.schemas import SettingsGroup, SettingsSchemaResponse


def test_settings_schema_response_shape():
    grp = SettingsGroup(
        name="Metadata",
        fields=[
            ConfigFieldMeta(key="x", group="Metadata", tier="operator", label="X", help="h", type="bool", editable=True)
        ],
    )
    resp = SettingsSchemaResponse(groups=[grp])
    assert resp.groups[0].name == "Metadata"
    assert resp.groups[0].fields[0].key == "x"
