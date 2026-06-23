"""Theme loading and management.

Built-in themes ship read-only in the image (arm_backend/themes/builtin/).
User themes live under settings.ARM_THEMES_PATH (the /data/themes mount).
The merged view has user themes override built-ins of the same id.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from arm_backend.config import settings

log = logging.getLogger(__name__)

# Built-in themes ship with the package (baked read-only into the image).
_BUILTIN_DIR = Path(__file__).parent / "themes" / "builtin"

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _safe_theme_id(theme_id: str) -> str:
    """Validate a theme id is safe for use as a filename. Raises ValueError if not."""
    if not _SAFE_ID.match(theme_id) or ".." in theme_id:
        raise ValueError(f"Invalid theme id: {theme_id!r}")
    return theme_id


def _safe_path(base: Path, filename: str) -> Path:
    """Build a path inside *base* and verify it resolves within it (traversal guard)."""
    target = (base / filename).resolve()
    if not target.is_relative_to(base.resolve()):
        raise ValueError(f"Path traversal blocked: {target}")
    return target


def _validate_theme(data: Any) -> bool:
    """Check required fields are present."""
    if not isinstance(data, dict):
        return False
    required = {"id", "label", "tokens"}
    return required.issubset(data.keys()) and isinstance(data["tokens"], dict)


def _load_theme_file(path: Path) -> dict[str, Any] | None:
    """Load a theme JSON file and its optional sidecar CSS. None on parse/validate failure."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Skipping unreadable theme file %s: %s", path.name, exc)
        return None
    if not _validate_theme(data):
        return None
    theme: dict[str, Any] = data
    css_path = path.with_suffix(".css")
    if css_path.is_file():
        theme["css"] = css_path.read_text(encoding="utf-8")
    else:
        theme.setdefault("css", "")
    return theme


def _user_dir() -> Path:
    """Return the user themes directory, creating it if needed."""
    p = Path(settings.ARM_THEMES_PATH)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_all() -> dict[str, dict[str, Any]]:
    """Load all themes; user themes override built-ins with the same id."""
    themes: dict[str, dict[str, Any]] = {}
    if _BUILTIN_DIR.is_dir():
        for f in sorted(_BUILTIN_DIR.glob("*.json")):
            t = _load_theme_file(f)
            if t:
                t["builtin"] = True
                themes[t["id"]] = t
    user_dir = Path(settings.ARM_THEMES_PATH)
    if user_dir.is_dir():
        for f in sorted(user_dir.glob("*.json")):
            t = _load_theme_file(f)
            if t:
                t["builtin"] = False
                themes[t["id"]] = t
    return themes


def get_all_themes() -> list[dict[str, Any]]:
    """Return metadata for all themes (no css)."""
    return [{k: v for k, v in t.items() if k != "css"} for t in _load_all().values()]


def get_theme(theme_id: str) -> dict[str, Any] | None:
    """Return full theme data including css, or None if unknown."""
    return _load_all().get(theme_id)


def save_user_theme(data: dict[str, Any], css: str = "") -> dict[str, Any]:
    """Save a user theme (json + optional css sidecar). Raises ValueError on bad input."""
    if not _validate_theme(data):
        raise ValueError("Invalid theme: missing required fields (id, label, tokens)")
    theme_id = _safe_theme_id(data["id"])
    result = dict(data)
    result.setdefault("version", 1)
    result.setdefault("swatch", "#888888")

    user_dir = _user_dir()
    json_path = _safe_path(user_dir, f"{theme_id}.json")
    css_path = _safe_path(user_dir, f"{theme_id}.css")

    save_data = {k: v for k, v in result.items() if k not in ("builtin", "css")}
    json_path.write_text(json.dumps(save_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if css.strip():
        css_path.write_text(css, encoding="utf-8")
        result["css"] = css
    else:
        css_path.unlink(missing_ok=True)
        result["css"] = ""
    result["builtin"] = False
    return result


def delete_user_theme(theme_id: str) -> bool:
    """Delete a user theme. False if it's a built-in or doesn't exist."""
    theme_id = _safe_theme_id(theme_id)
    if _safe_path(_BUILTIN_DIR, f"{theme_id}.json").exists():
        return False
    user_dir = _user_dir()
    json_path = _safe_path(user_dir, f"{theme_id}.json")
    if not json_path.exists():
        return False
    json_path.unlink()
    _safe_path(user_dir, f"{theme_id}.css").unlink(missing_ok=True)
    return True
