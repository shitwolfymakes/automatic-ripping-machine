from typing import Any

from pydantic import BaseModel, Field

from arm_common.enums import DiscType, DriveMediaStatus, KeydbState, MakemkvKeyState, MakemkvSdfState, TrackStatus


class MakemkvKeyStatusReport(BaseModel):
    """Body of POST /api/ripper/makemkv-key-status — the ripper's disc-free
    `makemkvcon` probe outcome. Global (not per-drive); the backend writes it
    to the Config singleton. `detail` is a human-readable reason string."""

    state: MakemkvKeyState
    detail: str | None = None
    # Reporting drive, for setup's "checked by". Optional so
    # rippers older than the backend still validate.
    drive_id: str | None = None


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
    """POST /api/ripper/register. Keyed on the Drive row the backend handed
    this container (ARM_DRIVE_ID); `by_id_name` is the udev link the ripper
    is bound to (None for a port-identity drive) and must match the row."""

    drive_id: str
    hostname: str
    device_path: str
    ripper_version: str
    hw_caps: dict[str, Any] = Field(default_factory=dict)
    by_id_name: str | None = None


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
    # MakeMKV's source for the title: a playlist (`00800.mpls`), a raw stream
    # (`00010.m2ts`) or, on a DVD, a title number. TheDiscDB's SourceFile.
    source_file: str | None = None
    # The clips the title plays, in play order, and how many there are.
    segment_count: int | None = None
    segment_map: list[int] | None = None
    # The disc's own name for the playlist, when it has one
    # (`FPL_MainFeature`). Decoy playlists usually have none.
    playlist_name: str | None = None
    # Which angle of a multi-angle playlist the title plays (1-based); None for a single-angle one.
    angle: int | None = None
    # A 3D title: its play items have MVC dependent-view clips (the base and dependent views are ripped together).
    stereo_3d: bool = False


class DiscFingerprintInput(BaseModel):
    """One (algo, value) pair on a scanned disc.

    Canonical algo names: `crc64` (pydvdid DVD), `aacs` (Blu-ray AACS
    Disc ID), `musicbrainz` (CD disc id), `matrix256` (matrix256v1
    structural hash), `thediscdb` (TheDiscDB content hash).
    Free-form to permit new algos without a schema bump.
    """

    algo: str
    value: str


class BdDiscMeta(BaseModel):
    """Blu-ray disc title from BDMV/META/DL/bdmt_<lang>.xml (studio-authored).
    Optional on the wire: older rippers never send it."""

    name: str
    set_number: int | None = None
    num_sets: int | None = None
    language: str | None = None


class BdPlaylist(BaseModel):
    """One Blu-ray playlist (`BDMV/PLAYLIST/<name>.mpls`) as the ripper read it off the disc."""

    name: str  # "00202.mpls"
    # Clip numbers in play order (ScanTitle.segment_map numbering) and the
    # seconds each plays; the two lists are parallel.
    clips: list[int]
    clip_seconds: list[float]
    duration_seconds: int
    chapter_count: int
    # One list per extra angle (angle 2, 3, ...), parallel to `clips`: the clip
    # each PlayItem plays in that angle. An item without angles repeats its own
    # clip. Empty for a single-angle playlist.
    angle_clips: list[list[int]] = Field(default_factory=list)
    # Dependent-view (3D) clips named by MVC SubPaths, in play order, every
    # angle included. Empty for 2D.
    mvc_clips: list[int] = Field(default_factory=list)


class BdClip(BaseModel):
    """One Blu-ray clip (`BDMV/CLIPINF/<number>.clpi` + `BDMV/STREAM/<number>.m2ts`)."""

    number: int
    seconds: float  # CLPI sequence info: the clip's whole presentation time
    size_bytes: int | None = None  # the .m2ts size from the STREAM listing; None when unlisted
    mvc: bool = False  # CLPI declares an MVC dependent-view video stream (a 3D dependent clip)


class ScanResult(BaseModel):
    disc_type: DiscType
    volume_label: str | None = None
    titles: list[ScanTitle] = Field(default_factory=list)
    musicbrainz_disc_id: str | None = None
    cd_toc: str | None = None
    # All disc fingerprints the scan was able to compute. Drives 1337server
    # lookup (crc64) and the reverse "have we seen this disc before?" lookup.
    # Empty when nothing fingerprintable.
    fingerprints: list[DiscFingerprintInput] = Field(default_factory=list)
    # Studio disc title + set position from the Blu-ray BDMT file, when present.
    bd_meta: BdDiscMeta | None = None
    # Blu-ray playlists read from BDMV/PLAYLIST before makemkvcon ran; empty
    # on other media or when the read failed.
    playlists: list[BdPlaylist] = Field(default_factory=list)
    # Per-clip length, size and 3D marker from BDMV/CLIPINF and BDMV/STREAM.
    clips: list[BdClip] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class IdentifyRequest(BaseModel):
    drive_id: str
    scan_result: ScanResult
    # Set by the ripper when it's running a manual-trigger flow; backend
    # stamps it into the job's `pending_session_id` column so
    # `maybe_auto_apply_session` can prefer it over the drive's persistent
    # default_session_id.
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
