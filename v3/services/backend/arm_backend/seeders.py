"""First-boot seeding of the admin user, config singleton, and built-in presets/sessions.

Idempotent — safe to run on every Backend startup. Rows are keyed on deterministic
IDs (for built-ins) or a known sentinel (config.id=1, username="admin") so re-runs
do not duplicate.
"""

import logging
import secrets
from pathlib import Path
from typing import Any, Iterable, Protocol

from argon2 import PasswordHasher
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.models import (
    Config,
    RipPreset,
    Session,
    TranscodePreset,
    User,
)
from arm_common import (
    ContainerFormat,
    IdentificationMode,
    MediaType,
    OutputMode,
    RetentionPolicy,
    TrackSelection,
    TranscodeTool,
)

logger = logging.getLogger("arm_backend.seeders")

FIRST_BOOT_LOG = Path("/logs/first-boot.log")


# --- Admin user ---------------------------------------------------------------

ADMIN_USERNAME = "admin"


async def _seed_admin_user(session: AsyncSession) -> None:
    existing = (await session.execute(select(User).where(col(User.username) == ADMIN_USERNAME))).scalar_one_or_none()
    if existing is not None:
        return

    password = secrets.token_urlsafe(18)
    hasher = PasswordHasher()
    user = User(
        username=ADMIN_USERNAME,
        password_hash=hasher.hash(password),
        password_must_change=True,
    )
    session.add(user)
    await session.flush()

    banner = (
        f"\n{'=' * 72}\n"
        f" ARM v3 first-boot: default admin credentials\n"
        f" username: {ADMIN_USERNAME}\n"
        f" password: {password}\n"
        f" You will be forced to change this on first login.\n"
        f"{'=' * 72}\n"
    )
    # stdout via logger at WARNING so it survives default log levels.
    logger.warning(banner)
    try:
        FIRST_BOOT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with FIRST_BOOT_LOG.open("a", encoding="utf-8") as f:
            f.write(banner)
    except OSError as exc:
        logger.warning("could not write %s: %s", FIRST_BOOT_LOG, exc)


# --- Config singleton ---------------------------------------------------------

CONFIG_SINGLETON_ID = 1


async def _seed_config_singleton(session: AsyncSession) -> None:
    existing = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if existing is None:
        session.add(
            Config(
                id=CONFIG_SINGLETON_ID,
                auto_transcode_on_idle=False,
                block_on_miss=True,
                default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
                notification_apprise_urls=[],
                session_signing_key=secrets.token_bytes(32),
            )
        )
        await session.flush()
        return

    # Back-fill session_signing_key if it was never generated.
    if existing.session_signing_key is None:
        existing.session_signing_key = secrets.token_bytes(32)
        session.add(existing)
        await session.flush()


# --- Built-in rip presets -----------------------------------------------------

RIP_PRESETS: list[dict[str, Any]] = [
    {
        "id": "rpr_builtin_movie_main_feature",
        "name": "Movie — Main Feature",
        "media_type": MediaType.MOVIE,
        "track_selection": TrackSelection.MAIN_FEATURE,
        "identification_mode": IdentificationMode.REQUIRED,
        "output_mode": OutputMode.TRACKS,
    },
    {
        "id": "rpr_builtin_movie_all_tracks",
        "name": "Movie — All Tracks",
        "media_type": MediaType.MOVIE,
        "track_selection": TrackSelection.ALL_TRACKS,
        "identification_mode": IdentificationMode.REQUIRED,
        "output_mode": OutputMode.TRACKS,
    },
    {
        "id": "rpr_builtin_movie_archive",
        "name": "Movie — Archive (all tracks + extras)",
        "media_type": MediaType.MOVIE,
        "track_selection": TrackSelection.ARCHIVE,
        "identification_mode": IdentificationMode.REQUIRED,
        "output_mode": OutputMode.TRACKS,
    },
    {
        "id": "rpr_builtin_tv_all_tracks",
        "name": "TV — All Tracks",
        "media_type": MediaType.TV,
        "track_selection": TrackSelection.ALL_TRACKS,
        "identification_mode": IdentificationMode.REQUIRED,
        "output_mode": OutputMode.TRACKS,
    },
    {
        "id": "rpr_builtin_music_standard",
        "name": "Music — Standard CD",
        "media_type": MediaType.MUSIC,
        "track_selection": TrackSelection.ALL_TRACKS,
        "identification_mode": IdentificationMode.REQUIRED,
        "output_mode": OutputMode.TRACKS,
    },
    {
        "id": "rpr_builtin_data_copy",
        "name": "Data — Copy",
        "media_type": MediaType.DATA,
        "track_selection": TrackSelection.ALL_TRACKS,
        "identification_mode": IdentificationMode.SKIP,
        "output_mode": OutputMode.DATA_COPY,
    },
    {
        "id": "rpr_builtin_iso_dump",
        "name": "ISO — Full-disc dump",
        "media_type": MediaType.ISO,
        "track_selection": TrackSelection.ALL_TRACKS,
        "identification_mode": IdentificationMode.SKIP,
        "output_mode": OutputMode.ISO,
    },
]


# --- Built-in transcode presets -----------------------------------------------

TRANSCODE_PRESETS: list[dict[str, Any]] = [
    {
        "id": "tpr_builtin_plex_1080p_h265",
        "name": "Plex 1080p H.265",
        "media_type": MediaType.MOVIE,
        "tool": TranscodeTool.HANDBRAKE,
        "preset_ref": "H.265 MKV 1080p30",
        "container": ContainerFormat.MKV,
        "hw_preference": None,
    },
    {
        "id": "tpr_builtin_plex_2160p_hevc",
        "name": "Plex 2160p HEVC",
        "media_type": MediaType.MOVIE,
        "tool": TranscodeTool.HANDBRAKE,
        "preset_ref": "H.265 MKV 2160p60 4K",
        "container": ContainerFormat.MKV,
        "hw_preference": None,
    },
    {
        "id": "tpr_builtin_passthrough_mkv",
        "name": "MKV Passthrough",
        "media_type": MediaType.MOVIE,
        "tool": TranscodeTool.HANDBRAKE,
        "preset_ref": "Matroska Passthrough",
        "container": ContainerFormat.MKV,
        "hw_preference": None,
    },
    {
        "id": "tpr_builtin_tv_plex_1080p_h265",
        "name": "Plex TV 1080p H.265",
        "media_type": MediaType.TV,
        "tool": TranscodeTool.HANDBRAKE,
        "preset_ref": "H.265 MKV 1080p30",
        "container": ContainerFormat.MKV,
        "hw_preference": None,
    },
    {
        "id": "tpr_builtin_music_flac",
        "name": "FLAC",
        "media_type": MediaType.MUSIC,
        "tool": TranscodeTool.ABCDE,
        "preset_ref": "flac",
        "container": ContainerFormat.FLAC,
        "hw_preference": None,
    },
    {
        "id": "tpr_builtin_music_mp3_v0",
        "name": "MP3 V0",
        "media_type": MediaType.MUSIC,
        "tool": TranscodeTool.ABCDE,
        "preset_ref": "mp3",
        "container": ContainerFormat.MP3,
        "hw_preference": None,
    },
    {
        "id": "tpr_builtin_data_passthrough",
        "name": "Data Passthrough",
        "media_type": MediaType.DATA,
        "tool": TranscodeTool.NONE,
        "preset_ref": None,
        "container": ContainerFormat.NONE,
        "hw_preference": None,
    },
    {
        "id": "tpr_builtin_iso_passthrough",
        "name": "ISO Passthrough",
        "media_type": MediaType.ISO,
        "tool": TranscodeTool.NONE,
        "preset_ref": None,
        "container": ContainerFormat.ISO,
        "hw_preference": None,
    },
]


# --- Built-in sessions --------------------------------------------------------

SESSIONS: list[dict[str, Any]] = [
    {
        "id": "ses_builtin_movie_plex_1080p",
        "name": "Movie → Plex 1080p H.265",
        "media_type": MediaType.MOVIE,
        "rip_preset_id": "rpr_builtin_movie_main_feature",
        "transcode_preset_id": "tpr_builtin_plex_1080p_h265",
        "output_path_template": "{title} ({year})/{title} ({year}) - {transcode_slug}.{ext}",
    },
    {
        "id": "ses_builtin_movie_plex_2160p",
        "name": "Movie → Plex 2160p HEVC",
        "media_type": MediaType.MOVIE,
        "rip_preset_id": "rpr_builtin_movie_main_feature",
        "transcode_preset_id": "tpr_builtin_plex_2160p_hevc",
        "output_path_template": "{title} ({year})/{title} ({year}) - {transcode_slug}.{ext}",
    },
    {
        "id": "ses_builtin_movie_archive",
        "name": "Movie → Archive MKV",
        "media_type": MediaType.MOVIE,
        "rip_preset_id": "rpr_builtin_movie_archive",
        "transcode_preset_id": "tpr_builtin_passthrough_mkv",
        "output_path_template": "{title} ({year})/{title} ({year}) - Track {track} ({duration_human}) - {transcode_slug}.{ext}",
    },
    {
        "id": "ses_builtin_tv_plex_1080p",
        "name": "TV → Plex 1080p H.265",
        "media_type": MediaType.TV,
        "rip_preset_id": "rpr_builtin_tv_all_tracks",
        "transcode_preset_id": "tpr_builtin_tv_plex_1080p_h265",
        "output_path_template": "{show} ({year})/Season {season}/{show} - S{season}D{disc}T{track} ({duration_human}) - {transcode_slug}.{ext}",
    },
    {
        "id": "ses_builtin_music_flac",
        "name": "Music → FLAC",
        "media_type": MediaType.MUSIC,
        "rip_preset_id": "rpr_builtin_music_standard",
        "transcode_preset_id": "tpr_builtin_music_flac",
        "output_path_template": "{artist}/{album}/{track} - {track_title} - {transcode_slug}.{ext}",
    },
    {
        "id": "ses_builtin_music_mp3",
        "name": "Music → MP3 V0",
        "media_type": MediaType.MUSIC,
        "rip_preset_id": "rpr_builtin_music_standard",
        "transcode_preset_id": "tpr_builtin_music_mp3_v0",
        "output_path_template": "{artist}/{album}/{track} - {track_title} - {transcode_slug}.{ext}",
    },
    {
        "id": "ses_builtin_data_copy",
        "name": "Data — Copy",
        "media_type": MediaType.DATA,
        "rip_preset_id": "rpr_builtin_data_copy",
        "transcode_preset_id": "tpr_builtin_data_passthrough",
        "output_path_template": "{title}/",
    },
    {
        "id": "ses_builtin_iso_dump",
        "name": "ISO — Full-disc dump",
        "media_type": MediaType.ISO,
        "rip_preset_id": "rpr_builtin_iso_dump",
        "transcode_preset_id": "tpr_builtin_iso_passthrough",
        "output_path_template": "{title} ({year})/{title} ({year}).iso",
    },
]


class _BuiltinRow(Protocol):
    """Seedable model: has a string id and accepts row dicts plus is_builtin in its ctor."""

    id: str

    def __init__(self, **kwargs: Any) -> None: ...


async def _insert_missing(
    session: AsyncSession,
    model: type[_BuiltinRow],
    rows: Iterable[dict[str, Any]],
) -> None:
    for row in rows:
        existing = (await session.execute(select(model).where(col(model.id) == row["id"]))).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(model(**row, is_builtin=True))
    await session.flush()


async def run_seeders(session: AsyncSession) -> None:
    await _seed_admin_user(session)
    await _seed_config_singleton(session)
    await _insert_missing(session, RipPreset, RIP_PRESETS)
    await _insert_missing(session, TranscodePreset, TRANSCODE_PRESETS)
    await _insert_missing(session, Session, SESSIONS)
    await session.commit()
