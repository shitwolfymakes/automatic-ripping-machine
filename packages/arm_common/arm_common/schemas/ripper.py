from typing import Any

from pydantic import BaseModel, Field

from arm_common.enums import DiscType, DriveMediaStatus, KeydbState, MakemkvKeyState, MakemkvSdfState, TrackStatus
from arm_common.schemas.system import HostResourcesSnapshot


class MakemkvKeyStatusReport(BaseModel):
    """Body of POST /api/ripper/makemkv-key-status — the ripper's disc-free
    `makemkvcon` probe outcome. Global (not per-drive); the backend writes it
    to the Config singleton. `detail` is a human-readable reason string."""

    state: MakemkvKeyState
    detail: str | None = None


class KeydbStatusReport(BaseModel):
    """Body of POST /api/ripper/keydb-status — the ripper's community-keydb
    fetch outcome. Global (not per-drive); the backend writes it to the Config
    singleton. `vuk_count` / `age_days` are present on ok / fresh_kept.
    Both fields are None on all other states."""

    state: KeydbState
    vuk_count: int | None = None
    age_days: int | None = None


class SdfStatusReport(BaseModel):
    """Body of POST /api/ripper/sdf-status — the ripper's MakeMKV SDF fetch
    outcome. Global (not per-drive); the backend writes it to the Config
    singleton. `age_days` is present on fresh_kept; None on all other states."""

    state: MakemkvSdfState
    age_days: int | None = None


class RegisterRequest(BaseModel):
    hostname: str
    device_path: str
    ripper_version: str
    hw_caps: dict[str, Any] = Field(default_factory=dict)
    # Hardware serial (udev ID_SERIAL_SHORT), when the drive exposes one.
    # Lets the backend detect a physical drive swap behind an unchanged
    # hostname/srN slot instead of silently rebinding it.
    serial: str | None = None


class RipperHeartbeatRequest(BaseModel):
    """POST /api/ripper/heartbeat body. Each ripper sends one of these
    every HEARTBEAT_INTERVAL_SECONDS so the backend can refuse manual-
    trigger requests against drives whose tray is open / empty without
    waiting for a doomed identify.

    Named distinctly from the transcoder HeartbeatRequest because the
    two services post completely different payloads to different paths.
    """

    drive_id: str
    media_status: DriveMediaStatus
    # The ripper's own HOSTNAME env — keys the backend `host` manifest UPSERT.
    hostname: str
    # Optional live host telemetry (CPU/mem/disk). None when a probe failed;
    # liveness still updates. Backend stores the latest per hostname in-memory.
    resources: HostResourcesSnapshot | None = None


class ScanTitle(BaseModel):
    index: int
    duration_seconds: int
    chapter_count: int | None = None
    size_bytes: int | None = None
    source_file: str | None = None


class DiscFingerprintInput(BaseModel):
    """One (algo, value) pair on a scanned disc.

    Canonical algo names: `crc64` (pydvdid DVD), `aacs` (Blu-ray AACS
    Disc ID), `musicbrainz` (CD disc id), `matrix256` (ARM-native).
    Free-form to permit new algos without a schema bump.
    """

    algo: str
    value: str


class ScanResult(BaseModel):
    disc_type: DiscType
    volume_label: str | None = None
    titles: list[ScanTitle] = Field(default_factory=list)
    musicbrainz_disc_id: str | None = None
    # All disc fingerprints the scan was able to compute. Drives 1337server
    # lookup (crc64), and reverse "have we seen this disc before?" lookup
    # in future flows. Empty when nothing fingerprintable.
    fingerprints: list[DiscFingerprintInput] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class IdentifyRequest(BaseModel):
    drive_id: str
    scan_result: ScanResult
    # Set by the ripper when it's running a manual-trigger flow; backend
    # stamps it into job.metadata_json so `maybe_auto_apply_session` can
    # prefer it over the drive's persistent default_session_id.
    pending_session_id: str | None = None


class TrackUpdateRequest(BaseModel):
    """PATCH /api/ripper/tracks/{track_id} body.

    Only fields that are non-None are written. Backend validates the
    state-machine transition implied by `status`.
    """

    status: TrackStatus
    output_path: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    duration_seconds: int | None = None
    last_error: str | None = None


class JobCompleteRequest(BaseModel):
    """POST /api/ripper/jobs/{job_id}/rip-complete body.

    Empty for now; backend computes the final job status from the track
    outcomes. Reserved for future flags (e.g. user-initiated abort).
    """


class RipperConfigView(BaseModel):
    """Subset of `Config` the ripper reads to gate its automatic behaviour.

    Polled on disc-insert before the pipeline kicks off; small enough to
    keep cheap. Does not include any UI-only fields.
    """

    auto_rip_on_insert: bool
    # Operator's MakeMKV key, when configured in the UI. The ripper writes it
    # into ~/.MakeMKV/settings.conf before each rip (overriding the legacy
    # MAKEMKV_KEY env var). `None` => fall back to that env var, then the
    # monthly forum beta-key scrape. Defaulted so older backends omitting it
    # still validate.
    makemkv_key: str | None = None
    # Operator toggle for the community-keydb (FindVUK) auto-fetch. Defaulted
    # True so older backends omitting it still validate and keep the feature on.
    community_keydb_enabled: bool = True
    makemkv_sdf_enabled: bool = True
    # Timed review gate: global pause suppresses the auto-start at countdown
    # expiry; manual_wait_seconds is the countdown duration. The ripper re-reads
    # these while parked so a mid-wait pause/duration change is honoured.
    # Defaulted so older backends omitting them still validate (no hold, 60s).
    ripping_paused: bool = False
    manual_wait_seconds: int = 60
