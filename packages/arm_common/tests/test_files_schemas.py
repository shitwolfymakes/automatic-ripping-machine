from arm_common.schemas import (
    DirectoryListing,
    FileEntry,
    FilePathResponse,
    FileRoot,
    FixPermsResponse,
    MkdirRequest,
    MoveRequest,
    RenameRequest,
)


def test_file_path_request():
    from arm_common.schemas import FilePathRequest

    assert FilePathRequest(root="MEDIA", subpath="a").subpath == "a"


def test_file_entry_defaults():
    e = FileEntry(name="x.mkv", type="file")
    assert e.size is None and e.extension is None and e.category == "other"
    assert e.permissions is None


def test_directory_listing_shape():
    dl = DirectoryListing(
        root="MEDIA",
        subpath="movies",
        parent_subpath="",
        readonly=False,
        entries=[FileEntry(name="a", type="directory")],
    )
    assert dl.entries[0].type == "directory"
    assert dl.parent_subpath == ""


def test_root_and_request_models():
    assert FileRoot(key="MEDIA", label="Media", path="/media", writable=True).writable
    assert MkdirRequest(root="MEDIA", subpath="movies", name="new").name == "new"
    assert RenameRequest(root="MEDIA", subpath="movies/old", new_name="new").new_name == "new"
    mv = MoveRequest(root="RAW", subpath="a", dest_root="MEDIA", dest_subpath="b")
    assert mv.dest_root == "MEDIA"
    assert FilePathResponse(root="MEDIA", subpath="movies/new").subpath == "movies/new"
    assert FixPermsResponse(fixed=3).fixed == 3
