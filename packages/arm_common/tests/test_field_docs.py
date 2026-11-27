import json

import pytest
from pydantic import ValidationError

from arm_common.config_metadata import CONFIG_FIELD_META
from arm_common.field_docs import (
    ENCODER_FAMILIES,
    FEATURED_NOTIFY_FIELDS,
    ExternalLink,
    InternalLink,
    NoLink,
    config_ids,
    external_url_problem,
    handbrake_ids,
    handbrake_key_ids,
    load_field_docs,
    missing_ids,
    notify_ids,
    orphan_ids,
    parse_field_docs,
    required_ids,
    url_problems,
)
from arm_common.handbrake_schema.overlay import KEY_OVERLAY

_HOSTS = ["handbrake.fr"]


def _docs(fields: dict, hosts: list[str] | None = None):
    return parse_field_docs(json.dumps({"version": 1, "hosts": hosts or _HOSTS, "fields": fields}))


# --- the shipped registry: checks 1-4 ---


def test_registry_parses_into_the_three_entry_shapes():
    docs = load_field_docs()
    assert docs.fields
    assert all(isinstance(e, (ExternalLink, InternalLink, NoLink)) for e in docs.fields.values())


def test_registry_external_urls_are_https_on_allowed_hosts():
    assert url_problems(load_field_docs()) == []


def test_registry_covers_every_declared_field():
    assert missing_ids(load_field_docs(), required_ids()) == []


def test_registry_has_no_orphan_entries():
    assert orphan_ids(load_field_docs(), required_ids() | handbrake_key_ids()) == []


def test_registry_carries_the_official_presets_link():
    entry = load_field_docs().fields["form.transcode_preset.preset_ref"]
    assert entry == ExternalLink(
        type="external", url="https://handbrake.fr/docs/en/latest/technical/official-presets.html"
    )


# --- declared ids ---


def test_config_ids_name_every_settings_field():
    assert config_ids() == {f"config.{m.key}" for m in CONFIG_FIELD_META}
    assert len(config_ids()) == 41


def test_handbrake_ids_are_the_overlay_groups_and_the_encoder_families():
    ids = handbrake_ids()
    groups = {i for i in ids if i.startswith("handbrake.group.")}
    assert len(groups) == 27
    assert "handbrake.group.audio.Track settings" in groups
    assert {i for i in ids if i.startswith("handbrake.family.")} == {f"handbrake.family.{f}" for f in ENCODER_FAMILIES}
    assert ids == groups | {f"handbrake.family.{f}" for f in ENCODER_FAMILIES}


def test_handbrake_key_ids_name_every_overlay_key():
    assert handbrake_key_ids() == {f"handbrake.key.{k}" for k in KEY_OVERLAY}


def test_notify_ids_name_every_featured_service_field():
    ids = notify_ids()
    assert len(FEATURED_NOTIFY_FIELDS) == 10
    assert len(ids) == sum(len(f) for f in FEATURED_NOTIFY_FIELDS.values())
    assert "notify.discord.webhook_id" in ids
    assert "notify.matrixs.e2ee" in ids


def test_required_ids_join_config_handbrake_and_notify():
    assert required_ids() == config_ids() | handbrake_ids() | notify_ids()


# --- check 1: entry shape ---


@pytest.mark.parametrize(
    "entry",
    [
        {"type": "external", "url": "https://handbrake.fr/x"},
        {"type": "internal", "page": "guide/configuring-arm"},
        {"type": "internal", "page": "guide/configuring-arm", "section": "Keys"},
        {"none": "Generated at install."},
    ],
)
def test_each_entry_shape_parses(entry):
    assert _docs({"config.x": entry}).fields["config.x"]


@pytest.mark.parametrize(
    "entry",
    [
        {},
        {"type": "external"},
        {"type": "external", "url": ""},
        {"type": "internal"},
        {"type": "internal", "page": "Configuring-ARM"},
        {"type": "internal", "page": "guide/configuring-arm", "section": " "},
        {"none": ""},
        {"none": "   "},
        {"type": "external", "url": "https://handbrake.fr/x", "none": "both"},
        {"type": "internal", "page": "guide/a", "url": "https://handbrake.fr/x"},
        {"type": "other", "url": "https://handbrake.fr/x"},
    ],
)
def test_malformed_entries_are_rejected(entry):
    with pytest.raises(ValidationError):
        _docs({"config.x": entry})


def test_wrong_version_is_rejected():
    with pytest.raises(ValidationError):
        parse_field_docs(json.dumps({"version": 2, "hosts": [], "fields": {}}))


# --- check 2: external URLs ---


@pytest.mark.parametrize(
    ("url", "problem"),
    [
        ("https://handbrake.fr/docs/", None),
        ("https://handbrake.fr/docs/page.html#anchor", None),
        ("http://handbrake.fr/docs/", "is not https"),
        ("#anchor", "is not https"),
        ("https://user:pw@handbrake.fr/", "carries credentials"),
        ("https://user@handbrake.fr/", "carries credentials"),
        ("https://handbrake.fr:8443/", "names a port or a non-lowercase host"),
        ("https://HandBrake.fr/", "names a port or a non-lowercase host"),
        ("https://evil.example/", "host evil.example is not in hosts"),
    ],
)
def test_external_url_problem(url, problem):
    assert external_url_problem(url, _HOSTS) == problem


def test_url_problems_report_only_bad_external_entries():
    docs = _docs(
        {
            "config.b": {"type": "external", "url": "http://handbrake.fr/"},
            "config.a": {"type": "external", "url": "https://handbrake.fr/"},
            "config.c": {"type": "internal", "page": "guide/x"},
            "config.d": {"none": "Secret."},
        }
    )
    assert url_problems(docs) == ["config.b: http://handbrake.fr/ is not https"]


# --- checks 3 and 4: coverage and orphans ---


def test_missing_ids_lists_required_ids_without_entries():
    docs = _docs({"config.a": {"none": "Secret."}})
    assert missing_ids(docs, frozenset({"config.a", "config.c", "config.b"})) == ["config.b", "config.c"]


def test_orphan_ids_flags_undeclared_and_unknown_namespace_entries():
    docs = _docs(
        {
            "config.kept": {"none": "Secret."},
            "config.gone": {"none": "Secret."},
            "handbrake.key.Gone": {"none": "Secret."},
            "notify.gone.field": {"none": "Secret."},
            "mystery.field": {"none": "Secret."},
            "form.session.name": {"none": "Checked by the UI."},
        }
    )
    assert orphan_ids(docs, frozenset({"config.kept"})) == [
        "config.gone",
        "handbrake.key.Gone",
        "mystery.field",
        "notify.gone.field",
    ]
