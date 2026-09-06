"""Script discovery and header metadata for bash hooks.

A hook script may declare itself in its first 60 lines:

    # arm-hook: <one-line description>
    # arm-input: KEY label="..." [required] [secret] [default="..."] [values=a,b,c]

Lines that do not match are ignored, so a plain v2 BASH_SCRIPT works with no
inputs. Keys must match ``INPUT_KEY_RE`` and must not use the reserved
``ARM_`` prefix; a later line for the same key replaces the earlier one.
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


def validate_script_name(name: str) -> str:
    if not name or name in {".", ".."}:
        raise ValueError("script name is required")
    if any(ch in name for ch in ("/", "\\", "\x00")):
        raise ValueError("script must be a file name inside the scripts directory, not a path")
    return name


def resolve_script(root: str, name: str) -> Path:
    return Path(root) / validate_script_name(name)


def _parse_input(key: str, attrs: str) -> tuple[ScriptInput, bool] | None:
    """Parse a single arm-input line, returning (ScriptInput, has_explicit_label) or None if invalid."""
    if not INPUT_KEY_RE.match(key) or key.startswith("ARM_"):
        return None
    try:
        tokens = shlex.split(attrs)
    except ValueError:
        return None
    label = key
    default = ""
    values: list[str] | None = None
    flags: set[str] = set()
    has_explicit_label = False
    for tok in tokens:
        if tok in _FLAGS:
            flags.add(tok)
            continue
        name, sep, value = tok.partition("=")
        if not sep:
            continue
        if name == "label":
            label = value or key
            has_explicit_label = True
        elif name == "default":
            default = value
        elif name == "values":
            values = [v.strip() for v in value.split(",") if v.strip()] or None
    return (
        ScriptInput(
            key=key, label=label, required="required" in flags, secret="secret" in flags, default=default, values=values
        ),
        has_explicit_label,
    )


def parse_header(text: str) -> tuple[str, list[ScriptInput]]:
    description = ""
    inputs: dict[str, ScriptInput] = {}
    for line in text.splitlines()[:HEADER_LINES]:
        # Strip leading non-ASCII for binary-safe parsing
        line_cleaned = line.lstrip("�")
        m = _HOOK_RE.match(line_cleaned)
        if m:
            description = m.group(1)
            continue
        m = _INPUT_RE.match(line_cleaned)
        if m:
            result = _parse_input(m.group(1), m.group(2))
            if result is not None:
                parsed, has_explicit_label = result
                # Re-declaring a key keeps its first position; the later attributes win.
                if parsed.key in inputs:
                    # Merge: use explicit label from this line if present, OR the boolean flags, keep first default/values
                    existing = inputs[parsed.key]
                    inputs[parsed.key] = ScriptInput(
                        key=parsed.key,
                        label=parsed.label if has_explicit_label else existing.label,
                        required=parsed.required or existing.required,
                        secret=parsed.secret or existing.secret,
                        default=existing.default if existing.default else parsed.default,
                        values=existing.values if existing.values is not None else parsed.values,
                    )
                else:
                    inputs[parsed.key] = parsed
    return description, list(inputs.values())


def _read_head(path: Path) -> str:
    with path.open("rb") as fh:
        return fh.read(PREVIEW_BYTES).decode("utf-8", "replace")


def read_script_info(root: str, name: str) -> BashScriptInfo:
    path = resolve_script(root, name)
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
        description, _ = parse_header(_read_head(p))
        out.append(BashScriptSummary(name=p.name, executable=os.access(p, os.X_OK), description=description))
    return out
