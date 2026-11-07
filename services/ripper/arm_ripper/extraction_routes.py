"""Which ISO images MakeMKV reads from an extracted disc folder instead of the image itself.

`iso_extract` adds a route once it has unpacked an image and drops them all when the pipeline ends;
`source.makemkv_source_url` reads them.
"""

from __future__ import annotations

from pathlib import Path

# Image path -> the extracted disc folder MakeMKV should read instead.
_extracted: dict[str, Path] = {}


def extracted_dir(image_path: str) -> Path | None:
    """The extracted disc folder MakeMKV reads in place of this image; None when it was not extracted."""
    return _extracted.get(image_path)


def route(image_path: str, folder: Path) -> None:
    """Have MakeMKV read `image_path` from the extracted `folder` from now on."""
    _extracted[image_path] = folder


def drop_all() -> list[Path]:
    """Forget every route and return the folders they pointed at."""
    folders = list(_extracted.values())
    _extracted.clear()
    return folders
