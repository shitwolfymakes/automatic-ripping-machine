"""Alembic revision-chain integrity.

Migrations authored on stacked branches can reference a parent revision that
exists on a sibling line but not here (a dangling ``down_revision``). Alembic
only detects that at runtime — the backend's startup ``alembic upgrade head``
crash-loops — so assert the chain is intact statically. No DB required.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_BACKEND_DIR = Path(__file__).parent.parent


def _script_directory() -> ScriptDirectory:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))
    return ScriptDirectory.from_config(cfg)


def test_every_down_revision_resolves() -> None:
    """Walking base→heads forces the full revision map; a dangling
    down_revision (or duplicate id) raises here instead of at backend boot."""
    script = _script_directory()
    revisions = list(script.walk_revisions("base", "heads"))
    assert revisions, "no migrations found"


def test_single_linear_head() -> None:
    """Two heads mean two migrations claim the same parent — ``alembic
    upgrade head`` refuses to run until a merge revision reconciles them."""
    script = _script_directory()
    heads = script.get_heads()
    assert len(heads) == 1, f"expected one migration head, found {heads}"
