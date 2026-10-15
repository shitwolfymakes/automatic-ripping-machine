"""Tier-1 settings audit: default_retention_policy + notification_apprise_urls
are hidden from the editable surface (registry + ConfigUpdateRequest) but stay
readable in ConfigView for back-compat."""

from arm_common.config_metadata import CONFIG_FIELD_META
from arm_common.schemas import ConfigUpdateRequest, ConfigView

_HIDDEN = {"default_retention_policy", "notification_apprise_urls"}


def test_hidden_fields_absent_from_registry():
    keys = {m.key for m in CONFIG_FIELD_META}
    assert _HIDDEN.isdisjoint(keys), f"still in registry: {_HIDDEN & keys}"


def test_hidden_fields_not_editable():
    assert _HIDDEN.isdisjoint(set(ConfigUpdateRequest.model_fields)), "still editable"


def test_hidden_fields_still_readable_in_view():
    view_fields = set(ConfigView.model_fields)
    assert _HIDDEN <= view_fields, f"lost from ConfigView: {_HIDDEN - view_fields}"
