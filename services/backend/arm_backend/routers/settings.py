"""Settings page metadata + read-only infra values. The settings UI fetches
the schema (how to render) here and the values from /api/config; infra values
(read-only, non-secret env settings) come from /api/settings/infra (Task 4)."""

from collections import OrderedDict

from fastapi import APIRouter, Depends

from arm_backend.auth import require_jwt
from arm_common import User
from arm_common.config_metadata import CONFIG_FIELD_META, ConfigFieldMeta
from arm_common.schemas import SettingsGroup, SettingsSchemaResponse

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Group display order for the settings page.
_GROUP_ORDER = ["Metadata", "Ripping", "Transcoding", "Notifications", "System"]


@router.get("/schema", response_model=SettingsSchemaResponse)
async def settings_schema(_: User = Depends(require_jwt)) -> SettingsSchemaResponse:
    grouped: OrderedDict[str, list[ConfigFieldMeta]] = OrderedDict((g, []) for g in _GROUP_ORDER)
    for meta in CONFIG_FIELD_META:
        grouped.setdefault(meta.group, []).append(meta)
    groups = [SettingsGroup(name=name, fields=fields) for name, fields in grouped.items() if fields]
    return SettingsSchemaResponse(groups=groups)
