"""Script discovery and header metadata for bash hooks.

A hook script may declare itself in its first 60 lines:

    # arm-hook: <one-line description>
    # arm-input: KEY label="..." [required] [secret] [default="..."] [values=a,b,c]

Lines that do not match are ignored, so a plain v2 BASH_SCRIPT works with no
inputs. Keys must match ``INPUT_KEY_RE``, must not use the reserved ``ARM_``
prefix, and must not be one of ``RESERVED_INPUT_KEYS`` (shell-sensitive names
such as ``PATH`` or ``BASH_ENV``); a later line for the same key keeps its
first position, but the later attributes replace the earlier ones.
"""

from __future__ import annotations

import os
import re
import shlex
from datetime import UTC, datetime
from pathlib import Path

from arm_common.schemas import BashScriptInfo, BashScriptSummary, ScriptInput

HEADER_LINES = 60
PREVIEW_BYTES = 8192
PREVIEW_LINES = 80
INPUT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_HOOK_RE = re.compile(r"^#\s*arm-hook:\s*(.*?)\s*$")
_INPUT_RE = re.compile(r"^#\s*arm-input:\s*(\S+)\s*(.*?)\s*$")
_FLAGS = {"required", "secret"}

# Names a declared input may never take: they either steer the shell/loader or
# are part of the fixed passthrough environment built by ``bash_runner``.
RESERVED_INPUT_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "BASH_ENV",
        "ENV",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "SHELLOPTS",
        "BASHOPTS",
        "IFS",
        "PS4",
        "CDPATH",
        "GLOBIGNORE",
    }
)


def validate_script_name(name: str) -> str:
    if not name or name in {".", ".."}:
        raise ValueError("script name is required")
    if any(ch in name for ch in ("/", "\\", "\x00")):
        raise ValueError("script must be a file name inside the scripts directory, not a path")
    return name


def resolve_script(root: str, name: str) -> Path:
    path = Path(root) / validate_script_name(name)
    # A symlink inside the mount may still point outside it; only entries that
    # really live in the scripts directory are addressable.
    if path.exists() and path.resolve().parent != Path(root).resolve():
        raise ValueError("script must be a regular file inside the scripts directory")
    return path


def _parse_input(key: str, attrs: str) -> ScriptInput | None:
    """Parse a single arm-input line, returning ScriptInput or None if invalid."""
    if not INPUT_KEY_RE.match(key) or key.startswith("ARM_") or key in RESERVED_INPUT_KEYS:
        return None
    try:
        tokens = shlex.split(attrs)
    except ValueError:
        return None
    label = key
    default = ""
    values: list[str] | None = None
    flags: set[str] = set()
    for tok in tokens:
        if tok in _FLAGS:
            flags.add(tok)
            continue
        name, sep, value = tok.partition("=")
        if not sep:
            continue
        if name == "label":
            label = value or key
        elif name == "default":
            default = value
        elif name == "values":
            values = [v.strip() for v in value.split(",") if v.strip()] or None
    return ScriptInput(
        key=key, label=label, required="required" in flags, secret="secret" in flags, default=default, values=values
    )


def parse_header(text: str) -> tuple[str, list[ScriptInput]]:
    description = ""
    inputs: dict[str, ScriptInput] = {}
    for line in text.splitlines()[:HEADER_LINES]:
        # Drop leading U+FFFD replacement chars so a binary preamble still parses
        line_cleaned = line.lstrip("�")
        m = _HOOK_RE.match(line_cleaned)
        if m:
            description = m.group(1)
            continue
        m = _INPUT_RE.match(line_cleaned)
        if m:
            parsed = _parse_input(m.group(1), m.group(2))
            if parsed is not None:
                # Re-declaring a key keeps its first position; the later attributes replace the earlier ones.
                inputs[parsed.key] = parsed
    return description, list(inputs.values())


def _read_head(path: Path) -> str:
    with path.open("rb") as fh:
        return fh.read(PREVIEW_BYTES).decode("utf-8", "replace")


def read_script_info(root: str, name: str) -> BashScriptInfo:
    try:
        path = resolve_script(root, name)
    except ValueError as exc:
        raise FileNotFoundError(name) from exc
    if not path.is_file():
        raise FileNotFoundError(name)
    st = path.stat()
    head = _read_head(path)
    description, inputs = parse_header(head)
    preview = "\n".join(head.splitlines()[:PREVIEW_LINES])
    return BashScriptInfo(
        name=path.name,
        executable=os.access(path, os.X_OK),
        description=description,
        size_bytes=st.st_size,
        modified_at=datetime.fromtimestamp(st.st_mtime, tz=UTC),
        inputs=inputs,
        preview=preview,
    )


def list_scripts(root: str) -> list[BashScriptSummary]:
    base = Path(root)
    if not base.is_dir():
        return []
    out: list[BashScriptSummary] = []
    for p in sorted(base.iterdir()):
        if p.name.startswith(".") or not p.is_file():
            continue
        if p.resolve().parent != base.resolve():
            continue
        description, _ = parse_header(_read_head(p))
        out.append(BashScriptSummary(name=p.name, executable=os.access(p, os.X_OK), description=description))
    return out
