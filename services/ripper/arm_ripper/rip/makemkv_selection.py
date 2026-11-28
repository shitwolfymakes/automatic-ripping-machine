"""MakeMKV's track selection for a rip that keeps a 3D title's MVC dependent view.

makemkvcon decides which streams of a title it saves from `app_DefaultSelectionString`, a setting read from
`$HOME/.MakeMKV/settings.conf`. The built-in default is
`-sel:all,+sel:(favlang|nolang),-sel:mvcvideo,=100:all,-10:favlang` (read from the makemkvcon binary the ripper image
ships), and its `-sel:mvcvideo` drops the dependent view of a 3D Blu-ray: the output holds only the base view. A rip
that keeps 3D swaps that clause for `+sel:mvcvideo`, in a throwaway HOME so the shared settings are never touched and
every other rip keeps MakeMKV's default.
"""

import contextlib
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

SETTINGS_DIR = ".MakeMKV"
SETTINGS_FILE = "settings.conf"
SELECTION_KEY = "app_DefaultSelectionString"
KEEP_MVC_SELECTION = "-sel:all,+sel:(favlang|nolang),+sel:mvcvideo,=100:all,-10:favlang"


def _settings_with_selection(text: str) -> str:
    """`settings.conf` text with its selection string (if any) replaced by the one that keeps MVC video."""
    kept = [line for line in text.splitlines() if line.partition("=")[0].strip() != SELECTION_KEY]
    kept.append(f'{SELECTION_KEY} = "{KEEP_MVC_SELECTION}"')
    return "\n".join(kept) + "\n"


def write_keep_mvc_home(home: Path, shared_home: Path) -> None:
    """Build `home/.MakeMKV`: the shared settings dir's files linked in (key database, SDF, caches), and a
    `settings.conf` copy that keeps MVC video."""
    shared = shared_home / SETTINGS_DIR
    target = home / SETTINGS_DIR
    target.mkdir(parents=True)
    if shared.is_dir():
        for entry in shared.iterdir():
            if entry.name != SETTINGS_FILE:
                (target / entry.name).symlink_to(entry)
    source = shared / SETTINGS_FILE
    text = source.read_text() if source.is_file() else ""
    (target / SETTINGS_FILE).write_text(_settings_with_selection(text))


@contextlib.contextmanager
def keep_mvc_environment() -> Iterator[dict[str, str]]:
    """The environment of a makemkvcon run that keeps MVC video: this process's, with HOME at a throwaway dir."""
    with tempfile.TemporaryDirectory(prefix="arm-makemkv-3d-") as scratch:
        write_keep_mvc_home(Path(scratch), Path(os.environ.get("HOME", "~")).expanduser())
        yield {**os.environ, "HOME": scratch}
