"""Session-routing CRUD (gap analysis G-02/G-17).

A route maps `(media_type, disc_type)` -> a session; `disc_type=None` is the
wildcard for that media_type. `resolve_routed_session_id` in auto_session.py
consults these rows behind the pending choice and the per-drive default.

`PUT /api/session-routes` upserts by the `(media_type, disc_type)` key
(writer role): create when no row matches that key, otherwise update the
existing row's `session_id` in place so re-PUTting the same key never
duplicates a route.

The upsert's compatibility check reuses `_media_types_compatible` from
`auto_session.py` rather than requiring strict equality (Fix 76-2): a movie
route to an iso-dump session, or a movie/tv pairing, is exactly what the
apply path (`resolve_routed_session_id` / `apply_session_internal`) already
lets through, so the router must accept it too instead of 422ing something
that would work once routed. It's imported directly from `auto_session`
(no cycle: that module never imports this router) rather than relocated to
a neutral module, since it's a one-line pure function with a single other
call site and duplicating or extracting it for one extra import would be
more churn than the import itself.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt, require_writer
from arm_backend.auto_session import _media_types_compatible
from arm_backend.db import get_session
from arm_common import Session, SessionRoute, User
from arm_common.schemas import SessionRouteUpsert, SessionRouteView

router = APIRouter(prefix="/api/session-routes", tags=["session-routes"])


@router.get("", response_model=list[SessionRouteView])
async def list_session_routes(
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> list[SessionRoute]:
    result = await db.execute(select(SessionRoute))
    return list(result.scalars().all())


@router.put("", response_model=SessionRouteView)
async def upsert_session_route(
    req: SessionRouteUpsert,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> SessionRoute:
    session_row = (await db.execute(select(Session).where(col(Session.id) == req.session_id))).scalar_one_or_none()
    if session_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown session_id: {req.session_id}")
    # `req.media_type` plays the role of the disc/job's media type here (it's
    # what discs this route fires for), so it goes first — same argument
    # order the apply path uses (`_media_types_compatible(job_mt, sess_mt)`
    # in auto_session.py). This lets a movie route point at an iso-dump
    # session, or a movie/tv pairing, matching what apply already allows;
    # only genuinely incompatible pairs (e.g. movie -> music) are rejected.
    if not _media_types_compatible(req.media_type, session_row.media_type):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"session media_type ({session_row.media_type}) is not compatible with "
                f"route media_type ({req.media_type})"
            ),
        )

    existing_rows = (
        (await db.execute(select(SessionRoute).where(col(SessionRoute.media_type) == req.media_type))).scalars().all()
    )
    existing = next((r for r in existing_rows if r.disc_type == req.disc_type), None)

    if existing is not None:
        # Already attached to the session (loaded via `select` above); no
        # `db.add()` needed for an update, and re-adding an already-tracked
        # row would duplicate it in a naive in-memory session.
        existing.session_id = req.session_id
        await db.commit()
        await db.refresh(existing)
        return existing

    row = SessionRoute(media_type=req.media_type, disc_type=req.disc_type, session_id=req.session_id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session_route(
    route_id: str,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> None:
    row = (await db.execute(select(SessionRoute).where(col(SessionRoute.id) == route_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown route_id: {route_id}")
    await db.delete(row)
    await db.commit()
