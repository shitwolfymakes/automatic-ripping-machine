"""The docs link registry for configuration fields, and the field ids each source declares.

``field_docs.json`` maps a namespaced field id to the page that documents it, or to a
reason the field has none. Python and the UI read the same file. The checks here are
offline: they parse the registry, vet its external URLs, and compare its ids with the
ids the settings registry, the HandBrake overlay and the featured notification
services declare. ``form.*`` ids belong to hand-written UI forms and are checked by
the UI's own tests.
"""

import json
from importlib import resources
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, StringConstraints

from arm_common.config_metadata import CONFIG_FIELD_META
from arm_common.handbrake_schema.overlay import KEY_OVERLAY

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

# The HandBrake encoder card families: hardware families by encoder id prefix, and
# "default" for every software encoder.
ENCODER_FAMILIES = ("nvenc", "qsv", "vcn", "default")

# Each featured notification service's form fields, as the backend's Apprise catalog
# builds them (required tokens, then advanced args). Declared here so these checks
# never import Apprise; a backend test holds this list to the live catalog.
FEATURED_NOTIFY_FIELDS: dict[str, tuple[str, ...]] = {
    "discord": (
        "webhook_id",
        "webhook_token",
        "format",
        "tts",
        "avatar",
        "avatar_url",
        "href",
        "thread",
        "footer",
        "footer_logo",
        "fields",
        "flags",
        "image",
        "ping",
    ),
    "slack": (
        "access_token",
        "token_a",
        "token_b",
        "token_c",
        "format",
        "image",
        "footer",
        "blocks",
        "timestamp",
        "mode",
    ),
    "tgram": ("bot_token", "format", "image", "detect", "silent", "preview", "topic", "mdv", "content"),
    "pbul": ("accesstoken", "format"),
    "pover": ("user_key", "token", "format", "priority", "sound", "url", "url_title", "retry", "expire"),
    "ntfys": (
        "format",
        "attach",
        "image",
        "avatar_url",
        "filename",
        "click",
        "delay",
        "email",
        "priority",
        "xtags",
        "actions",
        "mode",
        "auth",
    ),
    "mailtos": ("host", "format", "from", "name", "smtp", "mode", "reply", "pgp", "pgpkey", "to", "cc", "bcc"),
    "ifttt": ("webhook_id", "events", "format"),
    "gotifys": ("token", "host", "format", "priority"),
    "matrixs": ("host", "token", "format", "image", "discovery", "hsreq", "mode", "path", "version", "msgtype", "e2ee"),
}

# Namespaces whose ids these checks hold to a declared field.
_CHECKED_NAMESPACES = ("config", "handbrake", "notify")
# Namespaces whose ids are checked elsewhere (the UI's hand-written forms).
_UI_NAMESPACES = ("form",)


class _Entry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExternalLink(_Entry):
    """A third-party tool's own docs page."""

    type: Literal["external"]
    url: NonEmpty


class InternalLink(_Entry):
    """A page of ARM's in-app help, and optionally a heading on it."""

    type: Literal["internal"]
    page: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+/[a-z0-9_-]+$")]
    section: NonEmpty | None = None


class NoLink(_Entry):
    """An explicit opt-out: the field has no docs link, for the stated reason."""

    none: NonEmpty


FieldDocsEntry = ExternalLink | InternalLink | NoLink


class FieldDocs(_Entry):
    """The whole registry: allowed external hosts and one entry per field id."""

    version: Literal[1]
    hosts: list[NonEmpty]
    fields: dict[str, FieldDocsEntry]


def parse_field_docs(text: str) -> FieldDocs:
    """Parse registry JSON; raises ``pydantic.ValidationError`` on a malformed entry."""
    return FieldDocs.model_validate(json.loads(text))


def load_field_docs() -> FieldDocs:
    """The registry shipped with this package."""
    return parse_field_docs(resources.files("arm_common").joinpath("field_docs.json").read_text(encoding="utf-8"))


def config_ids() -> frozenset[str]:
    """One ``config.<key>`` per settings registry field."""
    return frozenset(f"config.{meta.key}" for meta in CONFIG_FIELD_META)


def handbrake_ids() -> frozenset[str]:
    """Every HandBrake id that needs an entry: each overlay tab group and each encoder family."""
    groups = {f"handbrake.group.{row.tab}.{row.group}" for row in KEY_OVERLAY.values()}
    families = {f"handbrake.family.{family}" for family in ENCODER_FAMILIES}
    return frozenset(groups | families)


def handbrake_key_ids() -> frozenset[str]:
    """The optional per-key HandBrake ids: one ``handbrake.key.<Key>`` per overlay key."""
    return frozenset(f"handbrake.key.{key}" for key in KEY_OVERLAY)


def notify_ids() -> frozenset[str]:
    """One ``notify.<service>.<field>`` per featured notification service field."""
    return frozenset(
        f"notify.{service}.{field}" for service, fields in FEATURED_NOTIFY_FIELDS.items() for field in fields
    )


def required_ids() -> frozenset[str]:
    """Every id that must have an entry (a link or an opt-out)."""
    return config_ids() | handbrake_ids() | notify_ids()


def external_url_problem(url: str, hosts: list[str]) -> str | None:
    """Why an external URL is not acceptable, or None when it is."""
    parts = urlsplit(url)
    if parts.scheme != "https":
        return "is not https"
    if parts.username is not None or parts.password is not None:
        return "carries credentials"
    if parts.netloc != parts.hostname:
        return "names a port or a non-lowercase host"
    if parts.hostname not in hosts:
        return f"host {parts.hostname} is not in hosts"
    return None


def url_problems(docs: FieldDocs) -> list[str]:
    """One message per external entry whose URL is not acceptable."""
    problems = []
    for field_id, entry in sorted(docs.fields.items()):
        if not isinstance(entry, ExternalLink):
            continue
        problem = external_url_problem(entry.url, docs.hosts)
        if problem:
            problems.append(f"{field_id}: {entry.url} {problem}")
    return problems


def missing_ids(docs: FieldDocs, required: frozenset[str]) -> list[str]:
    """Required ids with no entry."""
    return sorted(required - docs.fields.keys())


def _namespace(field_id: str) -> str:
    return field_id.split(".", 1)[0]


def orphan_ids(docs: FieldDocs, declared: frozenset[str]) -> list[str]:
    """Entries that belong to no declared field: a checked-namespace id not in ``declared``,
    or an id in a namespace no source declares."""
    return sorted(
        field_id
        for field_id in docs.fields
        if _namespace(field_id) not in _UI_NAMESPACES
        and (_namespace(field_id) not in _CHECKED_NAMESPACES or field_id not in declared)
    )
