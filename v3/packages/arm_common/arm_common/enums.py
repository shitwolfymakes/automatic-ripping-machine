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
