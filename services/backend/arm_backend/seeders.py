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

from arm_common.models import (
    Config,
    RipPreset,
    Session,
    SessionRoute,
    TranscodePreset,
    User,
)
from arm_common.models.user import ADMIN_ROLE, GUEST_ROLE
from arm_common import (
    ContainerFormat,
    DiscType,
    HwPreference,
    IdentificationMode,
    MediaType,
    NotificationChannel,
    OutputMode,
    RetentionPolicy,
    TrackSelection,
    TranscodeTool,
    VideoCodec,
)

logger = logging.getLogger("arm_backend.seeders")

FIRST_BOOT_LOG = Path("/logs/first-boot.log")


# --- Admin user ---------------------------------------------------------------

ADMIN_USERNAME = "admin"
ADMIN_DEFAULT_PASSWORD = "admin"
GUEST_USERNAME = "guest"


async def _seed_admin_user(session: AsyncSession) -> None:
    existing = (await session.execute(select(User).where(col(User.username) == ADMIN_USERNAME))).scalar_one_or_none()
    if existing is not None:
        return

    hasher = PasswordHasher()
    user = User(
        username=ADMIN_USERNAME,
        password_hash=hasher.hash(ADMIN_DEFAULT_PASSWORD),
        password_must_change=True,
        role=ADMIN_ROLE,
    )
    session.add(user)
    await session.flush()

    banner = (
        f"\n{'=' * 72}\n"
        f" ARM v3 first-boot: default admin credentials\n"
        f" username: {ADMIN_USERNAME}\n"
        f" password: {ADMIN_DEFAULT_PASSWORD}\n"
        f" You MUST change this on first login: the rest of the API is\n"
        f" 403'd until you do.\n"
        f"{'=' * 72}\n"
    )
    logger.warning(banner)
    try:
        FIRST_BOOT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with FIRST_BOOT_LOG.open("a", encoding="utf-8") as f:
            f.write(banner)
    except OSError as exc:
        logger.warning("could not write %s: %s", FIRST_BOOT_LOG, exc)


async def _seed_guest_user(session: AsyncSession) -> None:
    existing = (await session.execute(select(User).where(col(User.username) == GUEST_USERNAME))).scalar_one_or_none()
    if existing is not None:
        return
    hasher = PasswordHasher()
    session.add(
        User(
            username=GUEST_USERNAME,
            # Unusable until an admin sets a real one via /api/users/{id}/password.
            password_hash=hasher.hash(secrets.token_urlsafe(32)),
            password_must_change=False,
            role=GUEST_ROLE,
            disabled=True,
        )
    )
    await session.flush()


# --- Config singleton ---------------------------------------------------------

CONFIG_SINGLETON_ID = 1


async def _seed_config_singleton(session: AsyncSession) -> None:
    existing = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if existing is None:
        session.add(
            Config(
                id=CONFIG_SINGLETON_ID,
                auto_transcode_on_idle=False,
                auto_rip_on_insert=True,
                block_on_miss=True,
                default_retention_policy=RetentionPolicy.KEEP_FOREVER,
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

    # One-shot backfill for the env->DB move of the dispatcher parallelism
    # cap: NULL means this install has never seen the column, so seed it from
    # the legacy MAX_PARALLEL_TRANSCODES env value (default 1). After this,
    # the column is authoritative and Settings edits stick.
    if existing.max_parallel_transcodes is None:
        from arm_backend.config import settings  # noqa: PLC0415 — avoid import cycle at module load

        existing.max_parallel_transcodes = settings.MAX_PARALLEL_TRANSCODES
        session.add(existing)
        await session.flush()


# --- In-app notification channel ----------------------------------------------


async def _seed_inapp_channel(session: AsyncSession) -> None:
    # Local imports to avoid the seeders ↔ notification_dispatcher cycle
    # (notification_dispatcher imports CONFIG_SINGLETON_ID from seeders at
    # module level; a top-level import here would be circular).
    from arm_backend.notification_dispatcher import DEFAULT_INBOX_EVENT_TYPES  # noqa: PLC0415
    from arm_backend.notifications.inbox_listener import INBOX_CHANNEL_ID  # noqa: PLC0415

    existing = (
        await session.execute(select(NotificationChannel).where(col(NotificationChannel.id) == INBOX_CHANNEL_ID))
    ).scalar_one_or_none()
    if existing is not None:
        return
    session.add(
        NotificationChannel(
            id=INBOX_CHANNEL_ID,
            type="inapp",
            name="In-app notifications",
            enabled=True,
            config={"type": "inapp"},
            subscribed_events=sorted(DEFAULT_INBOX_EVENT_TYPES),
            templates={},
        )
    )
    await session.flush()


# --- Built-in rip presets -----------------------------------------------------

RIP_PRESETS: list[dict[str, Any]] = [
    {
        "id": "rpr_builtin_movie_main_feature",
        "name": "Movie: Main Feature",
        "media_type": MediaType.MOVIE,
        "track_selection": TrackSelection.MAIN_FEATURE,
        "identification_mode": IdentificationMode.REQUIRED,
        "output_mode": OutputMode.TRACKS,
    },
    {
        "id": "rpr_builtin_movie_all_tracks",
        "name": "Movie: All Tracks",
        "media_type": MediaType.MOVIE,
        "track_selection": TrackSelection.ALL_TRACKS,
        "identification_mode": IdentificationMode.REQUIRED,
        "output_mode": OutputMode.TRACKS,
    },
    {
        "id": "rpr_builtin_movie_archive",
        "name": "Movie: Archive (all tracks + extras)",
        "media_type": MediaType.MOVIE,
        "track_selection": TrackSelection.ARCHIVE,
        "identification_mode": IdentificationMode.REQUIRED,
        "output_mode": OutputMode.TRACKS,
    },
    {
        "id": "rpr_builtin_tv_all_tracks",
        "name": "TV: All Tracks",
        "media_type": MediaType.TV,
        "track_selection": TrackSelection.ALL_TRACKS,
        "identification_mode": IdentificationMode.REQUIRED,
        "output_mode": OutputMode.TRACKS,
    },
    {
        "id": "rpr_builtin_music_standard",
        "name": "Music: Standard CD",
        "media_type": MediaType.MUSIC,
        "track_selection": TrackSelection.ALL_TRACKS,
        "identification_mode": IdentificationMode.REQUIRED,
        "output_mode": OutputMode.TRACKS,
    },
    {
        "id": "rpr_builtin_data_copy",
        "name": "Data: Copy",
        "media_type": MediaType.DATA,
        "track_selection": TrackSelection.ALL_TRACKS,
        "identification_mode": IdentificationMode.SKIP,
        "output_mode": OutputMode.DATA_COPY,
    },
    {
        "id": "rpr_builtin_iso_dump",
        "name": "ISO: Full-disc dump",
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
        "codec": VideoCodec.H265,
        "hw_preference": None,
    },
    {
        # GPU-preferred sibling: same HandBrake preset, but `hw_preference=ANY`
        # so the dispatcher will hand it the first available NVENC/VAAPI/QSV
        # GPU advertising H.265 and fall back to CPU if none is free.
        "id": "tpr_builtin_plex_1080p_h265_gpu",
        "name": "Plex 1080p H.265 (GPU preferred)",
        "media_type": MediaType.MOVIE,
        "tool": TranscodeTool.HANDBRAKE,
        "preset_ref": "H.265 MKV 1080p30",
        "container": ContainerFormat.MKV,
        "codec": VideoCodec.H265,
        "hw_preference": HwPreference.ANY,
    },
    {
        "id": "tpr_builtin_plex_2160p_hevc",
        "name": "Plex 2160p HEVC",
        "media_type": MediaType.MOVIE,
        "tool": TranscodeTool.HANDBRAKE,
        "preset_ref": "H.265 MKV 2160p60 4K",
        "container": ContainerFormat.MKV,
        "codec": VideoCodec.H265,
        "hw_preference": None,
    },
    {
        # Pure copy of the MakeMKV-produced .mkv onto /media — `tool=none`
        # routes through `transcode_none` which renames the file. HandBrake
        # has no real "Matroska Passthrough" preset (it's a transcoder, not
        # a remuxer); using TranscodeTool.NONE is the correct expression.
        "id": "tpr_builtin_passthrough_mkv",
        "name": "MKV Passthrough",
        "media_type": MediaType.MOVIE,
        "tool": TranscodeTool.NONE,
        "preset_ref": None,
        "container": ContainerFormat.MKV,
        "codec": None,
        "hw_preference": None,
    },
    {
        "id": "tpr_builtin_tv_plex_1080p_h265",
        "name": "Plex TV 1080p H.265",
        "media_type": MediaType.TV,
        "tool": TranscodeTool.HANDBRAKE,
        "preset_ref": "H.265 MKV 1080p30",
        "container": ContainerFormat.MKV,
        "codec": VideoCodec.H265,
        "hw_preference": None,
    },
    {
        "id": "tpr_builtin_music_flac",
        "name": "FLAC",
        "media_type": MediaType.MUSIC,
        "tool": TranscodeTool.ABCDE,
        "preset_ref": "flac",
        "container": ContainerFormat.FLAC,
        "codec": None,
        "hw_preference": None,
    },
    {
        "id": "tpr_builtin_music_mp3_v0",
        "name": "MP3 V0",
        "media_type": MediaType.MUSIC,
        "tool": TranscodeTool.ABCDE,
        "preset_ref": "mp3",
        "container": ContainerFormat.MP3,
        "codec": None,
        "hw_preference": None,
    },
    {
        "id": "tpr_builtin_data_passthrough",
        "name": "Data Passthrough",
        "media_type": MediaType.DATA,
        "tool": TranscodeTool.NONE,
        "preset_ref": None,
        "container": ContainerFormat.NONE,
        "codec": None,
        "hw_preference": None,
    },
    {
        "id": "tpr_builtin_iso_passthrough",
        "name": "ISO Passthrough",
        "media_type": MediaType.ISO,
        "tool": TranscodeTool.NONE,
        "preset_ref": None,
        "container": ContainerFormat.ISO,
        "codec": None,
        "hw_preference": None,
    },
]


# --- Built-in sessions --------------------------------------------------------

SESSIONS: list[dict[str, Any]] = [
    {
        "id": "ses_builtin_movie_plex_1080p",
        "name": "Movie to Plex 1080p H.265",
        "media_type": MediaType.MOVIE,
        "rip_preset_id": "rpr_builtin_movie_main_feature",
        "transcode_preset_id": "tpr_builtin_plex_1080p_h265",
        "output_path_template": "{title} ({year})/{title} ({year}) - Track {track} - {transcode_slug}.{ext}",
    },
    {
        "id": "ses_builtin_movie_plex_1080p_gpu",
        "name": "Movie to Plex 1080p H.265 (GPU preferred)",
        "media_type": MediaType.MOVIE,
        "rip_preset_id": "rpr_builtin_movie_main_feature",
        "transcode_preset_id": "tpr_builtin_plex_1080p_h265_gpu",
        "output_path_template": "{title} ({year})/{title} ({year}) - Track {track} - {transcode_slug}.{ext}",
    },
    {
        "id": "ses_builtin_movie_plex_2160p",
        "name": "Movie to Plex 2160p HEVC",
        "media_type": MediaType.MOVIE,
        "rip_preset_id": "rpr_builtin_movie_main_feature",
        "transcode_preset_id": "tpr_builtin_plex_2160p_hevc",
        "output_path_template": "{title} ({year})/{title} ({year}) - Track {track} - {transcode_slug}.{ext}",
    },
    {
        "id": "ses_builtin_movie_archive",
        "name": "Movie to Archive MKV",
        "media_type": MediaType.MOVIE,
        "rip_preset_id": "rpr_builtin_movie_archive",
        "transcode_preset_id": "tpr_builtin_passthrough_mkv",
        "output_path_template": "{title} ({year})/{title} ({year}) - Track {track} ({duration_human}) - {transcode_slug}.{ext}",
    },
    {
        # Same `rpr_builtin_movie_archive` (every title), but each track is
        # transcoded H.265 with `hw_preference=ANY` instead of remuxed —
        # disc-equivalent contents in a smaller form, GPU-accelerated when
        # the host has matching silicon and CPU otherwise.
        "id": "ses_builtin_movie_archive_gpu",
        "name": "Movie to Archive H.265 (GPU preferred)",
        "media_type": MediaType.MOVIE,
        "rip_preset_id": "rpr_builtin_movie_archive",
        "transcode_preset_id": "tpr_builtin_plex_1080p_h265_gpu",
        "output_path_template": "{title} ({year})/{title} ({year}) - Track {track} ({duration_human}) - {transcode_slug}.{ext}",
    },
    {
        "id": "ses_builtin_tv_plex_1080p",
        "name": "TV to Plex 1080p H.265",
        "media_type": MediaType.TV,
        "rip_preset_id": "rpr_builtin_tv_all_tracks",
        "transcode_preset_id": "tpr_builtin_tv_plex_1080p_h265",
        "output_path_template": "{show} ({year})/Season {season}/{show} - S{season}D{disc}T{track} ({duration_human}) - {transcode_slug}.{ext}",
    },
    {
        "id": "ses_builtin_music_flac",
        "name": "Music to FLAC",
        "media_type": MediaType.MUSIC,
        "rip_preset_id": "rpr_builtin_music_standard",
        "transcode_preset_id": "tpr_builtin_music_flac",
        "output_path_template": "{artist}/{album}/{track} - {track_title} - {transcode_slug}.{ext}",
    },
    {
        "id": "ses_builtin_music_mp3",
        "name": "Music to MP3 V0",
        "media_type": MediaType.MUSIC,
        "rip_preset_id": "rpr_builtin_music_standard",
        "transcode_preset_id": "tpr_builtin_music_mp3_v0",
        "output_path_template": "{artist}/{album}/{track} - {track_title} - {transcode_slug}.{ext}",
    },
    {
        "id": "ses_builtin_data_copy",
        "name": "Data: Copy",
        "media_type": MediaType.DATA,
        "rip_preset_id": "rpr_builtin_data_copy",
        "transcode_preset_id": "tpr_builtin_data_passthrough",
        "output_path_template": "{title}/",
    },
    {
        "id": "ses_builtin_iso_dump",
        "name": "ISO: Full-disc dump",
        "media_type": MediaType.ISO,
        "rip_preset_id": "rpr_builtin_iso_dump",
        "transcode_preset_id": "tpr_builtin_iso_passthrough",
        "output_path_template": "{title} ({year})/{title} ({year}).iso",
    },
]


# --- Built-in session routes (G-17) --------------------------------------------

# A music disc routes to a music session out of the box; video stays on the
# drive default to preserve existing behavior (no video routes seeded).
SESSION_ROUTES: list[dict[str, Any]] = [
    {"media_type": MediaType.MUSIC, "disc_type": DiscType.CD, "session_id": "ses_builtin_music_flac"},
    {"media_type": MediaType.MUSIC, "disc_type": None, "session_id": "ses_builtin_music_flac"},
]


async def _seed_session_routes(session: AsyncSession) -> None:
    """Seed the built-in session routes exactly once (I1).

    Unlike the id-keyed builtins above, `SessionRoute` rows have no
    deterministic id to key an idempotent per-row insert on (their natural
    key is `(media_type, disc_type)`), so a plain empty-table gate isn't
    enough: a user who deliberately clears every route would get them
    silently reseeded on the very next boot, since "empty" can't distinguish
    "never seeded" from "seeded then deleted".

    `config.session_routes_seeded` closes that gap: seed only when the table
    is empty AND the flag is false, then set the flag true — whether this
    call actually inserted fresh rows or found the table already populated
    (converges old/pre-migration states where rows exist but the flag
    hadn't been set yet).
    """
    config_row = (
        await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))
    ).scalar_one_or_none()
    if config_row is not None and config_row.session_routes_seeded:
        return
    existing = (await session.execute(select(SessionRoute))).scalars().first()
    if existing is None:
        for row in SESSION_ROUTES:
            session.add(SessionRoute(**row))
    if config_row is not None:
        config_row.session_routes_seeded = True
        session.add(config_row)
    await session.flush()


class _BuiltinRow(Protocol):
    """Seedable model: has a string id and name and accepts row dicts plus is_builtin in its ctor."""

    id: str
    name: str

    def __init__(self, **kwargs: Any) -> None: ...


async def _insert_missing(
    session: AsyncSession,
    model: type[_BuiltinRow],
    rows: Iterable[dict[str, Any]],
) -> None:
    """Insert built-in rows that are absent. An existing row is left alone
    except for its name: built-ins are clone-to-edit, so the seeder owns the
    name and corrects it when the shipped text changes (e.g. the 2026-09
    special-character cleanup), without a migration."""
    for row in rows:
        existing = (await session.execute(select(model).where(col(model.id) == row["id"]))).scalar_one_or_none()
        if existing is not None:
            if getattr(existing, "name", None) != row["name"]:
                existing.name = row["name"]
                session.add(existing)
            continue
        session.add(model(**row, is_builtin=True))
    await session.flush()


async def run_seeders(session: AsyncSession) -> None:
    await _seed_admin_user(session)
    await _seed_guest_user(session)
    await _seed_config_singleton(session)
    await _seed_inapp_channel(session)
    await _insert_missing(session, RipPreset, RIP_PRESETS)
    await _insert_missing(session, TranscodePreset, TRANSCODE_PRESETS)
    await _insert_missing(session, Session, SESSIONS)
    await _seed_session_routes(session)
    await session.commit()
