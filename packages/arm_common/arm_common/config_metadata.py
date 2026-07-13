from pydantic import BaseModel


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
    type: str  # "string" | "bool" | "int" | "enum" | "string[]"
    editable: bool
    enum_values: list[str] | None = None


CONFIG_FIELD_META: list[ConfigFieldMeta] = [
    # --- Metadata ---
    ConfigFieldMeta(
        key="metadata_provider",
        group="Metadata",
        tier="operator",
        label="Default metadata provider",
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
    # NOTE: musicbrainz_user_agent is intentionally NOT registered — the column
    # + ConfigView/ConfigUpdateRequest wire fields persist (dropping them would be
    # an OpenAPI change), but the value is no longer read: the backend hardcodes
    # MUSICBRAINZ_USER_AGENT next to its use (arm_backend.metadata.dispatcher).
    # See tests/test_config_metadata.py::_DORMANT_EDITABLE_FIELDS.
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
        key="community_keydb_enabled",
        group="Ripping",
        tier="operator",
        label="Community keydb (FindVUK)",
        help="Auto-download community AACS VUK keys so MakeMKV can decrypt "
        "Blu-rays its own key server no longer covers.",
        type="bool",
        editable=True,
    ),
    ConfigFieldMeta(
        key="makemkv_sdf_enabled",
        group="Ripping",
        tier="operator",
        label="MakeMKV SDF refresh",
        help="Auto-download MakeMKV's SDF decryption data file so protected "
        "discs scan instead of timing out. A baseline SDF ships in the image; "
        "this keeps it current.",
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
        key="hold_for_review",
        group="Ripping",
        tier="operator",
        label="Hold discs for review",
        help="Hold each inserted disc in a timed review state after scan + "
        "identify, so you can correct it before the rip starts. The rip "
        "auto-starts when the countdown ends (unless rips are paused).",
        type="bool",
        editable=True,
    ),
    ConfigFieldMeta(
        key="manual_wait_seconds",
        group="Ripping",
        tier="operator",
        label="Review countdown (seconds)",
        help="How long a held disc waits for review before the rip auto-starts.",
        type="int",
        editable=True,
    ),
    # NOTE: default_retention_policy is intentionally NOT registered — the column
    # + RetentionPolicy enum persist, but no consumer prunes raw rips yet, so the
    # knob is hidden rather than shown-but-inert. Re-add when retention lands.
    # See docs/superpowers/specs/2026-06-18-settings-audit-design.md §1.1.
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
    # NOTE: notification_apprise_urls (legacy flat list) is hidden — dispatch is
    # driven by NotificationChannel rows (/api/notifications), not this field. It
    # still round-trips in ConfigView for back-compat. §1.2.
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
