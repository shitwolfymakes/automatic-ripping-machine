from typing import Any

from pydantic import BaseModel, Field

from arm_common.enums import DiscType, DriveMediaStatus, MakemkvKeyState, TrackStatus


class MakemkvKeyStatusReport(BaseModel):
    """Body of POST /api/ripper/makemkv-key-status — the ripper's disc-free
    `makemkvcon` probe outcome. Global (not per-drive); the backend writes it
    to the Config singleton. `detail` is a human-readable reason string."""

    state: MakemkvKeyState
    detail: str | None = None


class RegisterRequest(BaseModel):
    hostname: str
    device_path: str
    ripper_version: str
    hw_caps: dict[str, Any] = Field(default_factory=dict)


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
