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


class JobStatus(StrEnum):
    CREATED = "created"
    AWAITING_USER_ID = "awaiting_user_id"
    IDENTIFIED = "identified"
    RIPPING = "ripping"
    RIPPED = "ripped"
    RIPPED_PARTIAL = "ripped_partial"
    ABANDONED = "abandoned"
    FAILED = "failed"


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
