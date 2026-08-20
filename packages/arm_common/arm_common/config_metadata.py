from pydantic import BaseModel

from arm_common.enums import RetentionPolicy


class ConfigFieldMeta(BaseModel):
    """Render + classification metadata for one configuration field. The single
    source of truth for the settings UI: tier (secret/operator/infra), grouping,
    help text, render-type, and editability. Lives in code (not a DB table — the
    field set is migration-gated; not a sidecar JSON — that drifts). The guard
    test (tests/test_config_metadata.py) keeps it in sync with the schemas."""

    key: str
    group: str
    tier: str  # "secret" | "operator" | "infra"
    label: str
    help: str
    type: str  # "string" | "bool" | "enum" | "string[]"
    editable: bool
    enum_values: list[str] | None = None


_RETENTION = [p.value for p in RetentionPolicy]

CONFIG_FIELD_META: list[ConfigFieldMeta] = [
    # --- Metadata ---
    ConfigFieldMeta(
        key="metadata_provider",
        group="Metadata",
        tier="operator",
        label="Metadata provider",
        help="Provider for title identify (search + detail).",
        type="enum",
        editable=True,
        enum_values=["tmdb", "omdb"],
    ),
    ConfigFieldMeta(
        key="tmdb_api_key",
        group="Metadata",
        tier="secret",
        label="TMDb API key",
        help="The Movie Database API key (free; recommended).",
        type="string",
        editable=True,
    ),
    ConfigFieldMeta(
        key="omdb_api_key",
        group="Metadata",
        tier="secret",
        label="OMDb API key",
        help="Open Movie Database API key (1000 req/day free tier).",
        type="string",
        editable=True,
    ),
    ConfigFieldMeta(
        key="tvdb_api_key",
        group="Metadata",
        tier="secret",
        label="TVDb API key",
        help="TheTVDB v4 API key (used for episode matching).",
        type="string",
        editable=True,
    ),
    ConfigFieldMeta(
        key="makemkv_key",
        group="Metadata",
        tier="secret",
        label="MakeMKV key",
        help="MakeMKV registration key (purchased perma-key or beta key).",
        type="string",
        editable=True,
    ),
    ConfigFieldMeta(
        key="musicbrainz_user_agent",
        group="Metadata",
        tier="operator",
        label="MusicBrainz User-Agent",
        help="Identifies ARM to MusicBrainz (app/version + contact).",
        type="string",
        editable=True,
    ),
    # --- Ripping ---
    ConfigFieldMeta(
        key="auto_rip_on_insert",
        group="Ripping",
        tier="operator",
        label="Auto-rip on insert",
        help="Start ripping automatically when a disc is detected.",
        type="bool",
        editable=True,
    ),
    ConfigFieldMeta(
        key="block_on_miss",
        group="Ripping",
        tier="operator",
        label="Block on metadata miss",
        help="Hold a job for manual ID when no metadata match is found.",
        type="bool",
        editable=True,
    ),
    ConfigFieldMeta(
        key="ripping_paused",
        group="Ripping",
        tier="operator",
        label="Pause new rips",
        help="Reject new rip jobs (in-flight rips continue).",
        type="bool",
        editable=True,
    ),
    ConfigFieldMeta(
        key="default_retention_policy",
        group="Ripping",
        tier="operator",
        label="Default retention policy",
        help="What to do with raw rips after a session completes.",
        type="enum",
        editable=True,
        enum_values=_RETENTION,
    ),
    # --- Transcoding ---
    ConfigFieldMeta(
        key="auto_transcode_on_idle",
        group="Transcoding",
        tier="operator",
        label="Auto-transcode when idle",
        help="Queue transcodes automatically when the system is idle.",
        type="bool",
        editable=True,
    ),
    # --- Notifications ---
    ConfigFieldMeta(
        key="notifications_enabled",
        group="Notifications",
        tier="operator",
        label="Enable notifications",
        help="Master toggle for outbound notification dispatch.",
        type="bool",
        editable=True,
    ),
    ConfigFieldMeta(
        key="notification_apprise_urls",
        group="Notifications",
        tier="operator",
        label="Apprise URLs (legacy)",
        help="Deprecated flat URL list; prefer notification channels.",
        type="string[]",
        editable=True,
    ),
    # --- System (read-only infra, values from env Settings) ---
    ConfigFieldMeta(
        key="MEDIA_ROOT",
        group="System",
        tier="infra",
        label="Media root",
        help="Container path where finished media is written.",
        type="string",
        editable=False,
    ),
    ConfigFieldMeta(
        key="RAW_ROOT",
        group="System",
        tier="infra",
        label="Raw root",
        help="Container path for per-job raw rips.",
        type="string",
        editable=False,
    ),
    ConfigFieldMeta(
        key="ISO_INGRESS_ROOT",
        group="System",
        tier="infra",
        label="ISO ingress root",
        help="Sandbox path for ISO-import scanning.",
        type="string",
        editable=False,
    ),
    ConfigFieldMeta(
        key="BIND_PORT",
        group="System",
        tier="infra",
        label="Bind port",
        help="Backend HTTPS listen port.",
        type="string",
        editable=False,
    ),
    ConfigFieldMeta(
        key="MAX_PARALLEL_TRANSCODES",
        group="System",
        tier="infra",
        label="Max parallel transcodes",
        help="Concurrent transcode containers (deploy-time; UI-editable later).",
        type="string",
        editable=False,
    ),
    ConfigFieldMeta(
        key="ARM_DOCKER_NETWORK",
        group="System",
        tier="infra",
        label="Docker network",
        help="Network the spawned transcoders join.",
        type="string",
        editable=False,
    ),
    ConfigFieldMeta(
        key="ARM_GPUS",
        group="System",
        tier="infra",
        label="GPU inventory",
        help="GPUs detected host-side at install (empty = CPU-only).",
        type="string",
        editable=False,
    ),
]
