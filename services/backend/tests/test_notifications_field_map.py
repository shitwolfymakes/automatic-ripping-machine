from arm_backend.notifications import field_map as fm


def _patch_catalog(monkeypatch) -> None:
    fake = {
        "featured": [],
        "services": [
            {
                "id": "discord",
                "name": "Discord",
                "docs_url": "",
                "url_scheme": "discord",
                "required_fields": [
                    {"key": "webhook_id", "label": "Webhook ID", "type": "string", "private": True, "required": True},
                    {"key": "webhook_token", "label": "Token", "type": "string", "private": True, "required": True},
                ],
                "advanced_fields": [
                    {"key": "format", "label": "Format", "type": "choice", "private": False, "required": False},
                ],
            }
        ],
    }
    monkeypatch.setattr(fm, "build_catalog", lambda: fake)


def test_field_is_private(monkeypatch) -> None:
    _patch_catalog(monkeypatch)
    assert fm.apprise_field_is_private("discord", "webhook_id") is True
    assert fm.apprise_field_is_private("discord", "format") is False
    assert fm.apprise_field_is_private("discord", "nope") is None
    assert fm.apprise_field_is_private("unknown", "x") is None


def test_compose_url_from_fields(monkeypatch) -> None:
    _patch_catalog(monkeypatch)
    url = fm.compose_url_from_fields("discord", {"webhook_id": "1", "webhook_token": "2", "format": "markdown"})
    assert url == "discord://1/2?format=markdown"
    assert fm.compose_url_from_fields(None, {}) is None
    assert fm.compose_url_from_fields("unknown", {"a": "b"}) is None


def test_mask_config_masks_private_apprise_fields(monkeypatch) -> None:
    _patch_catalog(monkeypatch)
    cfg = {
        "type": "apprise",
        "url": "discord://1/2",
        "service_id": "discord",
        "fields": {"webhook_id": "1", "webhook_token": "2", "format": "markdown"},
    }
    masked = fm.mask_config(cfg)
    assert masked["fields"]["webhook_id"] == fm._HIDDEN_LITERAL
    assert masked["fields"]["webhook_token"] == fm._HIDDEN_LITERAL
    assert masked["fields"]["format"] == "markdown"
    assert masked["url"] == "discord://****"  # url redacted on read
    # original not mutated
    assert cfg["fields"]["webhook_id"] == "1"


def test_mask_config_url_only_redacts(monkeypatch) -> None:
    """Migration-imported channels store credentials ONLY in url — masking
    must not be a no-op for them."""
    _patch_catalog(monkeypatch)
    cfg = {"type": "apprise", "url": "discord://raw"}
    assert fm.mask_config(cfg)["url"] == "discord://****"
    assert cfg["url"] == "discord://raw"  # original not mutated
    assert fm.mask_config({}) == {}
    assert fm.mask_config({"type": "inapp"}) == {"type": "inapp"}


def test_merge_patch_keeps_hidden_secret(monkeypatch) -> None:
    _patch_catalog(monkeypatch)
    existing = {
        "type": "apprise",
        "service_id": "discord",
        "url": "discord://1/2",
        "fields": {"webhook_id": "1", "webhook_token": "2"},
    }
    incoming = {
        "type": "apprise",
        "service_id": "discord",
        "fields": {"webhook_id": fm._HIDDEN_LITERAL, "webhook_token": "NEW"},
    }
    merged = fm.merge_patch_config(existing, incoming)
    assert merged["fields"]["webhook_id"] == "1"  # kept
    assert merged["fields"]["webhook_token"] == "NEW"  # overwritten
    assert merged["url"] == "discord://1/NEW"  # recomposed


def test_merge_patch_incoming_none(monkeypatch) -> None:
    _patch_catalog(monkeypatch)
    existing = {"type": "apprise", "url": "x"}
    assert fm.merge_patch_config(existing, None) == existing


def test_merge_patch_non_apprise_returns_incoming(monkeypatch) -> None:
    _patch_catalog(monkeypatch)
    existing = {"type": "apprise", "url": "x"}
    incoming = {"type": "apprise", "url": "y"}  # no fields -> just returned as-is
    assert fm.merge_patch_config(existing, incoming) == incoming


def test_merge_patch_incoming_missing_service_id_falls_back(monkeypatch) -> None:
    _patch_catalog(monkeypatch)
    existing = {
        "type": "apprise",
        "service_id": "discord",
        "url": "discord://1/2",
        "fields": {"webhook_id": "1", "webhook_token": "2"},
    }
    # incoming omits service_id entirely
    incoming = {"type": "apprise", "fields": {"webhook_token": "NEW"}}
    merged = fm.merge_patch_config(existing, incoming)
    assert merged["service_id"] == "discord"  # fell back to existing
    assert merged["fields"]["webhook_id"] == "1"  # untouched stored field kept
    assert merged["fields"]["webhook_token"] == "NEW"
    assert merged["url"] == "discord://1/NEW"  # recomposed via fallback service_id


def test_merge_patch_unknown_service_keeps_url(monkeypatch) -> None:
    _patch_catalog(monkeypatch)
    # service_id present on both but not in the catalog -> compose returns None
    existing = {"type": "apprise", "service_id": "ghost", "url": "ghost://old", "fields": {"a": "1"}}
    incoming = {"type": "apprise", "service_id": "ghost", "url": "ghost://old", "fields": {"a": "2"}}
    merged = fm.merge_patch_config(existing, incoming)
    assert merged["fields"]["a"] == "2"  # field still merged
    assert merged["url"] == "ghost://old"  # url unchanged (compose returned None)


def test_compose_orders_required_segments_by_catalog_not_dict_order(monkeypatch) -> None:
    """The catalog's token order is webhook_id/webhook_token; a token-first
    payload must not compose discord://token/id."""
    _patch_catalog(monkeypatch)
    url = fm.compose_url_from_fields("discord", {"webhook_token": "TOK", "webhook_id": "ID"})
    assert url is not None
    assert url.startswith("discord://ID/TOK")


def test_merge_patch_config_keeps_stored_url_when_uncomposable(monkeypatch) -> None:
    """Raw-URL channels (migration-imported, no service_id) must keep their
    stored url through a fields-bearing merge instead of dropping it."""
    _patch_catalog(monkeypatch)
    existing = {"type": "apprise", "url": "json://host/x"}
    incoming = {"type": "apprise", "fields": {"whatever": "v"}}
    merged = fm.merge_patch_config(existing, incoming)
    assert merged.get("url") == "json://host/x"


def test_mask_config_redacts_composed_url(monkeypatch) -> None:
    """config['url'] embeds the same credentials the fields masking hides —
    it must not round-trip in cleartext."""
    _patch_catalog(monkeypatch)
    with_fields = fm.mask_config(
        {
            "type": "apprise",
            "service_id": "discord",
            "url": "discord://ID/SECRET",
            "fields": {"webhook_id": "ID", "webhook_token": "SECRET"},
        }
    )
    assert "SECRET" not in str(with_fields.get("url"))
