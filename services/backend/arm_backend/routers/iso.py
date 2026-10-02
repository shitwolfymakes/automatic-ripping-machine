"""`/api/iso`: browse the ISO library and create/cancel "Rip from ISO" jobs
(spec 2026-09-30-iso-source-rip, sections 5-6). The lifecycle plumbing
(create, cancel, the watchdog) lives in `iso_rips`; this router is thin."""

from __future__ import annotations

import asyncio

import logging
from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend import file_browser
from arm_backend.auth import require_jwt, require_writer
from arm_backend.db import get_session
from arm_backend.iso_library import library_configured, library_host_path
from arm_backend.iso_rips import IsoRipError, cancel_iso_rip, create_iso_rip
from arm_backend.ripper_manager import RipperManager
from arm_backend.ws import WSHub
from arm_common import Drive, DriveKind, DriveLifecycle, User
from arm_common.schemas import IsoLibraryEntry, IsoLibraryListing, IsoRipCreated, IsoRipRequest

logger = logging.getLogger("arm_backend.routers.iso")

router = APIRouter(prefix="/api/iso", tags=["iso"])

# `file_browser.PathError.code` -> HTTP status for the library listing.
# Anything else (there is nothing else `list_dir` raises) is a 400.
_LIST_STATUS = {"not_found": status.HTTP_404_NOT_FOUND}


def _get_hub(request: Request) -> WSHub:
    hub: WSHub = request.app.state.ws_hub
    return hub


def _manager(request: Request) -> RipperManager:
    manager: RipperManager | None = getattr(request.app.state, "ripper_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ripper manager unavailable: docker socket not available",
        )
    return manager


@router.get("/library", response_model=IsoLibraryListing)
async def library(
    subpath: str = "",
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> IsoLibraryListing:
    if not library_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="the ISO library is not configured")
    try:
        # Off the event loop: the library usually sits on a network share, and a
        # single stat there has been seen to take seconds (or, under load, minutes).
        listing = await asyncio.to_thread(file_browser.list_dir, "ISO", subpath)
    except file_browser.PathError as exc:
        raise HTTPException(
            status_code=_LIST_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST), detail=exc.code
        ) from exc

    live = list(
        (
            await db.execute(
                select(Drive).where(
                    col(Drive.kind) == DriveKind.VIRTUAL, col(Drive.lifecycle) == DriveLifecycle.ENROLLED
                )
            )
        )
        .scalars()
        .all()
    )
    ripping_paths = {d.source_path for d in live if d.source_path}

    entries: list[IsoLibraryEntry] = []
    for fe in listing.entries:
        kind: Literal["folder", "iso"]
        if fe.type == "directory":
            kind = "folder"
        elif fe.name.endswith(".iso"):
            kind = "iso"
        else:
            continue
        rel = str(PurePosixPath(listing.subpath) / fe.name) if listing.subpath else fe.name
        entries.append(
            IsoLibraryEntry(
                name=fe.name,
                kind=kind,
                size_bytes=fe.size,
                modified_at=datetime.fromisoformat(fe.modified) if fe.modified else None,
                ripping=kind == "iso" and rel in ripping_paths,
            )
        )

    return IsoLibraryListing(
        host_path=library_host_path(),
        subpath=listing.subpath,
        parent_subpath=listing.parent_subpath,
        entries=entries,
    )


@router.post("/rips", response_model=IsoRipCreated, status_code=status.HTTP_201_CREATED)
async def create_rip(
    req: IsoRipRequest,
    request: Request,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> IsoRipCreated:
    manager = _manager(request)
    hub = _get_hub(request)
    try:
        drive = await create_iso_rip(db, manager, hub, req.path, req.session_id)
    except IsoRipError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return IsoRipCreated(drive_id=drive.id)


@router.delete("/rips/{drive_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_rip(
    drive_id: str,
    request: Request,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> Response:
    manager = _manager(request)
    hub = _get_hub(request)
    try:
        await cancel_iso_rip(db, manager, hub, drive_id)
    except IsoRipError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
