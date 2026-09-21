from enum import StrEnum


class DiscType(StrEnum):
    DVD = "dvd"
    BLURAY = "bluray"
    CD = "cd"
    DATA = "data"
    UNKNOWN = "unknown"


class DriveStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    RIPPING = "ripping"
    ERROR = "error"


class DriveMediaStatus(StrEnum):
    """What the drive thinks is in its tray. Reported by each ripper
    on a heartbeat so the backend can fail manual-trigger requests
    fast when the user clicks Start without loading a disc."""

    LOADED = "loaded"  # CDS_DISC_OK
    NO_DISC = "no_disc"  # CDS_NO_DISC
    TRAY_OPEN = "tray_open"  # CDS_TRAY_OPEN
    NOT_READY = "not_ready"  # CDS_DRIVE_NOT_READY (medium spinning up)
    UNAVAILABLE = "unavailable"  # open() failed — kernel ENODEV / device file gone
    UNKNOWN = "unknown"  # CDS_NO_INFO, or ioctl unsupported on a probed device


class DriveMode(StrEnum):
    AUTO = "auto"  # ripper auto-rips on disc insert
    MANUAL = "manual"  # ripper waits for an explicit manual.trigger


class JobStatus(StrEnum):
    CREATED = "created"
    AWAITING_USER_ID = "awaiting_user_id"
    IDENTIFIED = "identified"
    RIPPING = "ripping"
    RIPPED = "ripped"
    RIPPED_PARTIAL = "ripped_partial"
    # A scanned + identified disc held for operator review (timed review gate).
    # The rip pipeline parks here, counting down `manual_wait_seconds`; on expiry
    # it auto-starts (unless globally paused), or the operator Starts/Cancels.
    # Distinct from AWAITING_USER_ID ("could not identify — needs operator ID").
    # Resolvable (PRESERVE) for identity edits; non-terminal; not an APPLY status.
    AWAITING_REVIEW = "awaiting_review"
    # Set by the (future) deferred-placeholder rip path when a disc rips
    # successfully but identification never landed. Resolvable via the
    # /resolve endpoint just like AWAITING_USER_ID. Inert today — no code
    # path sets this yet.
    RIPPED_AWAITING_IDENTIFY = "ripped_awaiting_identify"
    ABANDONED = "abandoned"
    FAILED = "failed"


# Canonical JobStatus groupings. Single source of truth — routers/services must
# import these rather than re-defining local copies.
TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.RIPPED,
        JobStatus.RIPPED_PARTIAL,
        JobStatus.RIPPED_AWAITING_IDENTIFY,
        JobStatus.ABANDONED,
        JobStatus.FAILED,
    }
)
# Pre-rip = disc present, not yet committed to a rip (reusable on re-identify).
PRE_RIP_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.CREATED,
        JobStatus.AWAITING_USER_ID,
        JobStatus.IDENTIFIED,
        JobStatus.AWAITING_REVIEW,
    }
)
NON_TERMINAL_JOB_STATUSES: frozenset[JobStatus] = PRE_RIP_JOB_STATUSES | frozenset({JobStatus.RIPPING})


class TrackStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class TrackKind(StrEnum):
    VIDEO_TITLE = "video_title"
    AUDIO_TRACK = "audio_track"
    DATA_DUMP = "data_dump"


class MediaType(StrEnum):
    MOVIE = "movie"
    TV = "tv"
    MUSIC = "music"
    DATA = "data"
    ISO = "iso"


class TrackSelection(StrEnum):
    MAIN_FEATURE = "main_feature"
    ALL_TRACKS = "all_tracks"
    ARCHIVE = "archive"
    CUSTOM = "custom"


class IdentificationMode(StrEnum):
    REQUIRED = "required"
    SKIP = "skip"
    DEFERRED_PLACEHOLDER = "deferred_placeholder"


class OutputMode(StrEnum):
    TRACKS = "tracks"
    ISO = "iso"
    DATA_COPY = "data_copy"


class TranscodeTool(StrEnum):
    HANDBRAKE = "handbrake"
    ABCDE = "abcde"
    NONE = "none"


class ContainerFormat(StrEnum):
    MKV = "mkv"
    MP4 = "mp4"
    WEBM = "webm"
    FLAC = "flac"
    MP3 = "mp3"
    OGG = "ogg"
    ISO = "iso"
    NONE = "none"


class HwPreference(StrEnum):
    CPU_ONLY = "cpu_only"
    ANY = "any"


class RetentionPolicy(StrEnum):
    KEEP_FOREVER = "keep_forever"
    PRUNE_AFTER_SESSION = "prune_after_session"
    CUSTOM = "custom"


class SessionApplicationStatus(StrEnum):
    WAITING_IDENTIFY = "waiting_identify"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    DONE_PARTIAL = "done_partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TranscodeTaskStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class GpuVendor(StrEnum):
    VAAPI = "vaapi"
    NVENC = "nvenc"
    QSV = "qsv"


class GpuStatus(StrEnum):
    AVAILABLE = "available"
    BUSY = "busy"


class VideoCodec(StrEnum):
    H264 = "h264"
    H265 = "h265"
    AV1 = "av1"


class MakemkvKeyState(StrEnum):
    """Outcome of the ripper's disc-free `makemkvcon info disc:9999` probe.
    Stored on the Config singleton and read by the key check, preflight and config view.

    VALID                   — clean probe, key accepted.
    UNREGISTERED_OR_EXPIRED — MSG:5052/5055 (evaluation expired / no valid key).
    BINARY_EXPIRED          — MSG:5021 (60-day kill-switch; no key overrides it).
    FORMAT_INVALID          — configured key fails the M-/T- serial regex (pre-probe).
    PROBE_FAILED            — binary missing / timeout / undeterminable (→ valid=null).
    """

    VALID = "valid"
    UNREGISTERED_OR_EXPIRED = "unregistered_or_expired"
    BINARY_EXPIRED = "binary_expired"
    FORMAT_INVALID = "format_invalid"
    PROBE_FAILED = "probe_failed"


class KeydbState(StrEnum):
    """Outcome of the ripper's community-keydb fetch (`update_keydb.sh`),
    stored on the Config singleton and surfaced by /api/system/preflight.

    OK              — downloaded, filtered, installed; vuk_count set.
    DISABLED        — community keydb gated off via config.
    FRESH_KEPT      — age-gated skip; existing keydb retained (age_days set).
    DOWNLOAD_FAILED — all download retries failed; existing keydb retained.
    EMPTY           — fetched file not a ZIP / no keydb.cfg / no VUK entries.
    PROBE_FAILED    — wrapper could not run or parse the script.
    """

    OK = "ok"
    DISABLED = "disabled"
    FRESH_KEPT = "fresh_kept"
    DOWNLOAD_FAILED = "download_failed"
    EMPTY = "empty"
    PROBE_FAILED = "probe_failed"


class MakemkvSdfState(StrEnum):
    """Outcome of the ripper's MakeMKV SDF fetch (`update_sdf.sh`), stored on
    the Config singleton and surfaced by /api/system/preflight.

    UPDATED         — downloaded (official or mirror) and installed.
    FRESH_KEPT      — age-gated skip; existing SDF retained (age_days set).
    DISABLED        — SDF refresh gated off via config.
    DOWNLOAD_FAILED — all sources failed; baked/existing SDF retained.
    PROBE_FAILED    — wrapper could not run or parse the script.
    """

    UPDATED = "updated"
    FRESH_KEPT = "fresh_kept"
    DISABLED = "disabled"
    DOWNLOAD_FAILED = "download_failed"
    PROBE_FAILED = "probe_failed"


class UserRole(StrEnum):
    """Fixed two-account model (spec 2026-07-12-basic-user-management-design).

    ADMIN — the single writer; the only account that can hold a session.
    GUEST — read-everything/write-nothing; acquired by having no token at all
            rather than by logging in, and gated by the `disabled` flag on its
            row.

    Stored as VARCHAR via `enum_column`, never a Postgres CREATE TYPE.
    """

    ADMIN = "admin"
    GUEST = "guest"
