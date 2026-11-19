"""Message builders for the events only the ripper can see."""

from arm_common import DiscType

_DISC_TYPE_LABELS: dict[DiscType, str] = {
    DiscType.CD: "CD",
    DiscType.BLURAY: "Blu-ray",
    DiscType.DVD: "DVD",
    DiscType.DATA: "data disc",
    DiscType.UNKNOWN: "unknown disc",
}


def disc_type_label(disc_type: DiscType) -> str:
    """The disc type as an operator reads it."""
    return _DISC_TYPE_LABELS[disc_type]


def rip_started_message(disc_type: str, track_count: int, preset: str, tool: str) -> str:
    """The `rip.started` line: what is being ripped, how many tracks, with which preset and tool."""
    noun = "track" if track_count == 1 else "tracks"
    return f"rip started: {disc_type}, {track_count} {noun}, preset {preset} ({tool})"
