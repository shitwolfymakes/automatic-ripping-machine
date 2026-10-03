"""First-run setup walkthrough state (setup spec 2026-10-01 §6.1).

The walkthrough writes every setting through the router that owns it; this
router only records which steps are done, skipped or need attention, whether
the walkthrough is complete, and whether the dashboard checklist was dismissed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_writer
from arm_backend.auto_session import route_session_id_for
from arm_backend.db import get_session
from arm_backend.routers.system import _app_version, collect_diagnostics
from arm_backend.seeders import ADMIN_USERNAME, CONFIG_SINGLETON_ID
from arm_common import Config, MediaType, RipPreset, Session, TranscodePreset, User
from arm_common.enums import SETUP_STEP_ORDER, SetupStep, SetupStepState
from arm_common.schemas import (
    DiscRouteSummary,
    SetupStatusPublic,
    SetupStepProgress,
    SetupStepUpdate,
    SetupView,
    SystemDiagnosticsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/setup", tags=["setup"])

# The diagnostics checks the "System check" step is about. Drives, the MakeMKV
# key and decryption data are later steps' concern, so their warnings never
# hold the system step in "attention". The UI's SystemStep uses the same set.
_SYSTEM_STEP_CHECKS = frozenset({"config", "MEDIA_ROOT", "RAW_ROOT", "LOG_DIR", "ripper_manager", "transcoder"})


def system_checks_ok(resp: SystemDiagnosticsResponse) -> bool:
    return all(ch.status == "ok" for ch in resp.checks if ch.name in _SYSTEM_STEP_CHECKS)


async def _diagnostics_ok(request: Request, db: AsyncSession) -> bool:
    return system_checks_ok(await collect_diagnostics(request, db))


async def _config(db: AsyncSession) -> Config:
    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="config singleton missing")
    return cfg


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _entry(state: SetupStepState) -> dict[str, Any]:
    return {"state": state.value, "at": _now().isoformat()}


def _progress(cfg: Config) -> dict[str, Any]:
    # Always a fresh dict: SQLAlchemy only notices a JSON change on reassignment.
    return dict(cfg.setup_progress or {})


def _current_step(progress: dict[str, Any]) -> SetupStep:
    for step in SETUP_STEP_ORDER:
        if step.value not in progress:
            return step
    return SetupStep.FINISH


async def _view(db: AsyncSession, cfg: Config) -> SetupView:
    admin = (await db.execute(select(User).where(col(User.username) == ADMIN_USERNAME))).scalar_one_or_none()
    # password_must_change stays true until /api/auth/password succeeds, and that
    # route rejects new == current, so it also means "still the seeded password".
    must_change = bool(admin is not None and admin.password_must_change)
    progress = _progress(cfg)
    if not must_change and SetupStep.ACCOUNT.value not in progress:
        progress[SetupStep.ACCOUNT.value] = {"state": SetupStepState.DONE.value, "at": None}
    return SetupView(
        completed_at=cfg.setup_completed_at,
        progress={k: SetupStepProgress.model_validate(v) for k, v in progress.items()},
        current_step=_current_step(progress),
        admin_default_password=must_change,
        checklist_dismissed=cfg.setup_checklist_dismissed_at is not None,
        deferred=cfg.setup_deferred_at is not None,
    )


async def _save(db: AsyncSession, cfg: Config) -> SetupView:
    db.add(cfg)
    await db.commit()
    return await _view(db, cfg)


@router.get("/status", response_model=SetupStatusPublic)
async def setup_status(db: AsyncSession = Depends(get_session)) -> SetupStatusPublic:
    """Public: the login page and the first-run guard read it before anyone
    signs in. `first_run` is false once setup is completed or deferred ("Finish
    later" holds for every browser, not just the one that clicked it). Fails
    closed to first_run=false, so a backend or DB hiccup never traps the UI in
    /setup."""
    try:
        cfg = await _config(db)
        first_run = cfg.setup_completed_at is None and cfg.setup_deferred_at is None
    except Exception:  # noqa: BLE001 - any failure means "don't redirect"
        logger.warning("setup status unavailable; reporting first_run=false", exc_info=True)
        first_run = False
    return SetupStatusPublic(first_run=first_run, arm_version=_app_version())


@router.get("", response_model=SetupView)
async def get_setup(
    request: Request,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> SetupView:
    cfg = await _config(db)
    progress = _progress(cfg)
    system = progress.get(SetupStep.SYSTEM.value)
    if system and system.get("state") == SetupStepState.ATTENTION.value and await _diagnostics_ok(request, db):
        # The operator fixed the server since; stop flagging the step.
        progress[SetupStep.SYSTEM.value] = _entry(SetupStepState.DONE)
        cfg.setup_progress = progress
        return await _save(db, cfg)
    return await _view(db, cfg)


@router.put("/steps/{step}", response_model=SetupView)
async def put_step(
    step: str,
    req: SetupStepUpdate,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> SetupView:
    try:
        target = SetupStep(step)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown setup step: {step}") from exc
    if target is SetupStep.ACCOUNT and req.state is not SetupStepState.DONE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="the account step can only be done")
    cfg = await _config(db)
    progress = _progress(cfg)
    progress[target.value] = _entry(req.state)
    cfg.setup_progress = progress
    return await _save(db, cfg)


@router.post("/complete", response_model=SetupView)
async def complete_setup(_: User = Depends(require_writer), db: AsyncSession = Depends(get_session)) -> SetupView:
    cfg = await _config(db)
    progress = _progress(cfg)
    # The account step is "done" the moment the seeded password is gone, even
    # when the walkthrough never visited it (an admin who changed the password
    # elsewhere resumes at step 2). Persist it as done, not skipped, so the
    # dashboard checklist agrees with the Finish summary.
    admin = (await db.execute(select(User).where(col(User.username) == ADMIN_USERNAME))).scalar_one_or_none()
    password_changed = admin is not None and not admin.password_must_change
    for step in SETUP_STEP_ORDER:
        if step is SetupStep.FINISH:
            progress[step.value] = _entry(SetupStepState.DONE)
        elif step.value not in progress:
            done = step is SetupStep.ACCOUNT and password_changed
            progress[step.value] = _entry(SetupStepState.DONE if done else SetupStepState.SKIPPED)
    cfg.setup_progress = progress
    cfg.setup_completed_at = _now()
    cfg.setup_deferred_at = None
    return await _save(db, cfg)


@router.post("/restart", response_model=SetupView)
async def restart_setup(_: User = Depends(require_writer), db: AsyncSession = Depends(get_session)) -> SetupView:
    """Settings > System "Run setup again": keep what was recorded, reopen the walkthrough."""
    cfg = await _config(db)
    progress = _progress(cfg)
    progress.pop(SetupStep.FINISH.value, None)
    cfg.setup_progress = progress
    cfg.setup_completed_at = None
    cfg.setup_checklist_dismissed_at = None
    cfg.setup_deferred_at = None
    return await _save(db, cfg)


@router.post("/defer", response_model=SetupView)
async def defer_setup(_: User = Depends(require_writer), db: AsyncSession = Depends(get_session)) -> SetupView:
    """The walkthrough's Finish later: stop the first-run redirect for every browser and sign-in
    (the dashboard checklist still lists what is left). Settings > "Run setup
    again" (`/restart`) picks it back up."""
    cfg = await _config(db)
    cfg.setup_deferred_at = _now()
    return await _save(db, cfg)


@router.post("/checklist/dismiss", response_model=SetupView)
async def dismiss_checklist(_: User = Depends(require_writer), db: AsyncSession = Depends(get_session)) -> SetupView:
    cfg = await _config(db)
    cfg.setup_checklist_dismissed_at = _now()
    return await _save(db, cfg)


# Kinds shown in setup step 6's "What happens to each kind of disc" table.
_DISC_KINDS = (MediaType.MOVIE, MediaType.TV, MediaType.MUSIC, MediaType.DATA, MediaType.ISO)


@router.get("/disc-routes", response_model=list[DiscRouteSummary])
async def disc_routes(
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> list[DiscRouteSummary]:
    """What each kind of disc gets with no drive default and no per-rip choice:
    the session route for that media type, else the first built-in session of
    that type by name (what an operator picking by type would get). Read-only."""
    sessions = list((await db.execute(select(Session))).scalars().all())
    by_id = {s.id: s for s in sessions}
    rip = {p.id: p for p in (await db.execute(select(RipPreset))).scalars().all()}
    tc = {p.id: p for p in (await db.execute(select(TranscodePreset))).scalars().all()}
    out: list[DiscRouteSummary] = []
    for kind in _DISC_KINDS:
        sid = await route_session_id_for(db, kind, None)
        if sid is None:
            builtin = sorted((s for s in sessions if s.is_builtin and s.media_type == kind), key=lambda s: s.name)
            sid = builtin[0].id if builtin else None
        sess = by_id.get(sid) if sid else None
        if sess is None:
            out.append(DiscRouteSummary(kind=kind))
            continue
        rp = rip.get(sess.rip_preset_id)
        tp = tc.get(sess.transcode_preset_id) if sess.transcode_preset_id else None
        out.append(
            DiscRouteSummary(
                kind=kind,
                session_id=sess.id,
                session_name=sess.name,
                rip_summary=rp.name if rp else None,
                transcode_summary=tp.name if tp else None,
                output_template=sess.output_path_template,
            )
        )
    return out
