from pydantic import BaseModel


class FileRoot(BaseModel):
    key: str
    label: str
    path: str
    writable: bool


class FileEntry(BaseModel):
    name: str
    type: str  # "file" | "directory"
    size: int | None = None
    modified: str | None = None  # ISO-8601
    extension: str | None = None
    category: str = "other"  # video|audio|image|subtitle|archive|document|other
    permissions: str | None = None  # octal e.g. "644"


class DirectoryListing(BaseModel):
    root: str
    subpath: str
    parent_subpath: str | None = None
    readonly: bool
    entries: list[FileEntry]
    # True when the root's own base directory does not exist on disk (a
    # configured-but-unmounted root, e.g. ISO ingress with no bind mount). The
    # listing is empty and the UI shows "not mounted" rather than an error.
    unavailable: bool = False


class FilePathResponse(BaseModel):
    root: str
    subpath: str


class FixPermsResponse(BaseModel):
    fixed: int


class MkdirRequest(BaseModel):
    root: str
    subpath: str
    name: str


class RenameRequest(BaseModel):
    root: str
    subpath: str
    new_name: str


class MoveRequest(BaseModel):
    root: str
    subpath: str
    dest_root: str
    dest_subpath: str


class FilePathRequest(BaseModel):
    root: str
    subpath: str
