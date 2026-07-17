import logging

from fastapi import APIRouter, Depends, HTTPException, status

from arm_backend import file_browser as fb
from arm_backend.auth import require_jwt
from arm_common import User
from arm_common.schemas import (
    DirectoryListing,
    FilePathRequest,
    FilePathResponse,
    FileRoot,
    FixPermsResponse,
    MkdirRequest,
    MoveRequest,
    RenameRequest,
)

logger = logging.getLogger("arm_backend.routers.files")

router = APIRouter(prefix="/api/files", tags=["files"])

# code -> HTTP status for PathError.code; default 400.
_STATUS = {
    "read_only_root": status.HTTP_403_FORBIDDEN,
    "dest_not_writable": status.HTTP_403_FORBIDDEN,
    "not_found": status.HTTP_404_NOT_FOUND,
    "already_exists": status.HTTP_409_CONFLICT,
}


def _http(e: fb.PathError) -> HTTPException:
    return HTTPException(status_code=_STATUS.get(e.code, status.HTTP_400_BAD_REQUEST), detail=e.code)


@router.get("/roots", response_model=list[FileRoot])
async def roots(_: User = Depends(require_jwt)) -> list[FileRoot]:
    return fb.list_roots()


def _os_error(e: OSError) -> HTTPException:
    """Log the real error server-side and return a generic 500."""
    logger.exception("Unexpected filesystem error: %s", e)
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="filesystem_error")


@router.get("/list", response_model=DirectoryListing)
async def list_directory(root: str, subpath: str = "", _: User = Depends(require_jwt)) -> DirectoryListing:
    try:
        return fb.list_dir(root, subpath)
    except fb.PathError as e:
        raise _http(e) from e
    except OSError as e:
        raise _os_error(e) from e


@router.post("/mkdir", response_model=FilePathResponse)
async def mkdir(req: MkdirRequest, _: User = Depends(require_jwt)) -> FilePathResponse:
    try:
        root, subpath = fb.make_dir(req.root, req.subpath, req.name)
    except fb.PathError as e:
        raise _http(e) from e
    except OSError as e:
        raise _os_error(e) from e
    return FilePathResponse(root=root, subpath=subpath)


@router.post("/rename", response_model=FilePathResponse)
async def rename(req: RenameRequest, _: User = Depends(require_jwt)) -> FilePathResponse:
    try:
        root, subpath = fb.rename(req.root, req.subpath, req.new_name)
    except fb.PathError as e:
        raise _http(e) from e
    except OSError as e:
        raise _os_error(e) from e
    return FilePathResponse(root=root, subpath=subpath)


@router.post("/move", response_model=FilePathResponse)
async def move(req: MoveRequest, _: User = Depends(require_jwt)) -> FilePathResponse:
    try:
        root, subpath = fb.move(req.root, req.subpath, req.dest_root, req.dest_subpath)
    except fb.PathError as e:
        raise _http(e) from e
    except OSError as e:
        raise _os_error(e) from e
    return FilePathResponse(root=root, subpath=subpath)


@router.post("/fix-permissions", response_model=FixPermsResponse)
async def fix_permissions(req: FilePathRequest, _: User = Depends(require_jwt)) -> FixPermsResponse:
    try:
        return FixPermsResponse(fixed=fb.fix_permissions(req.root, req.subpath))
    except fb.PathError as e:
        raise _http(e) from e
    except OSError as e:
        raise _os_error(e) from e


@router.delete("", response_model=dict[str, bool])
async def delete(root: str, subpath: str, _: User = Depends(require_jwt)) -> dict[str, bool]:
    try:
        fb.delete(root, subpath)
    except fb.PathError as e:
        raise _http(e) from e
    except OSError as e:
        raise _os_error(e) from e
    return {"deleted": True}
