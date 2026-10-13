"""Turn a bash channel config + event into a concrete run.

Everything that decides WHAT a script receives lives here, so the dispatcher
listener, the test endpoints, and the UI preview cannot drift: resolve the
title/body templates, resolve inputs (script default < channel value <
per-event override for non-secret keys), render input templates, build the
env, and expose a masked view for the API.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from arm_backend.notification_format import TemplateRenderError, resolve_title_body
from arm_backend.notifications.bash_runner import build_env
from arm_backend.notifications.script_meta import (
    INPUT_KEY_RE,
    RESERVED_INPUT_KEYS,
    ScriptUnreadableError,
    read_script_info,
    resolve_script,
)
from arm_common.schemas import ScriptInput
from arm_common.secrets import HIDDEN_SECRET

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 600


class HookError(Exception):
    """Configuration or rendering problem; ``str(exc)`` is user-facing."""


@dataclass(frozen=True)
class PreparedRun:
    path: Path
    argv: list[str]
    title: str
    body: str
    env: dict[str, str]
    inputs: dict[str, str]
    secret_keys: frozenset[str]
    timeout_seconds: int


def _declared(scripts_root: str, script: str) -> list[ScriptInput]:
    try:
        return read_script_info(scripts_root, script).inputs
    except FileNotFoundError, ScriptUnreadableError:
        return []


def _clean_inputs(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {
        str(k): str(v)
        for k, v in raw.items()
        if INPUT_KEY_RE.match(str(k)) and not str(k).startswith("ARM_") and str(k) not in RESERVED_INPUT_KEYS
    }


# Same bound as a rendered body: a width spec ({job_title:>300000}) must not
# grow an env var past the kernel's per-string exec limit (128 KiB).
INPUT_RENDER_CAP = 16000


def _render_input(key: str, value: str, context: dict[str, str]) -> str:
    try:
        rendered = value.format_map(context)
    except (KeyError, IndexError, ValueError) as exc:
        raise HookError(f"input {key} references an unknown variable: {exc}") from exc
    if len(rendered) > INPUT_RENDER_CAP:
        raise HookError(f"input {key} renders to {len(rendered)} characters (limit {INPUT_RENDER_CAP})")
    return rendered


def prepare_run(
    *,
    config: dict[str, Any],
    template: dict[str, Any] | None,
    event_type: str,
    default_title: str,
    default_body: str,
    context: dict[str, str],
    scripts_root: str,
    media_root: str,
    raw_root: str,
) -> PreparedRun:
    script = str(config.get("script") or "")
    try:
        path = resolve_script(scripts_root, script)
    except ValueError as exc:
        raise HookError(str(exc)) from exc
    try:
        title, body = resolve_title_body(
            event_type=event_type,
            default_title=default_title,
            default_body=default_body,
            template=template,
            context=context,
        )
    except TemplateRenderError as exc:
        raise HookError(str(exc)) from exc

    declared = _declared(scripts_root, script)
    secret_keys = frozenset(secret_set(config) | {i.key for i in declared if i.secret})
    channel_inputs = _clean_inputs(config.get("inputs"))
    event_inputs = _clean_inputs((template or {}).get("inputs"))

    # Only keys the script header declares reach the child: an undeclared stored
    # or per-event key is ignored, so a script with no header gets no inputs.
    resolved: dict[str, str] = {}
    for spec in declared:
        key = spec.key
        value = spec.default
        if key in channel_inputs and channel_inputs[key] != "":
            value = channel_inputs[key]
        if key not in secret_keys and key in event_inputs and event_inputs[key] != "":
            value = event_inputs[key]
        value = _render_input(key, value, context)
        if spec.required and value == "":
            raise HookError(f"input {key} is required")
        if spec.values and value != "" and value not in spec.values:
            raise HookError(f"input {key} must be one of {', '.join(spec.values)}")
        resolved[key] = value

    env = build_env(context, title=title, body=body, inputs=resolved, media_root=media_root, raw_root=raw_root)
    timeout = int(config.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
    return PreparedRun(
        path=path,
        argv=["/usr/bin/env", "bash", str(path), title, body],
        title=title,
        body=body,
        env=env,
        inputs=resolved,
        secret_keys=secret_keys,
        timeout_seconds=timeout,
    )


def redact_secrets(text: str, run: PreparedRun) -> str:
    """Replace every non-empty secret input value in *text* with ``<hidden>``.

    Script output can echo a secret (a curl error quoting the URL, ``set -x``
    tracing); anything persisted as an error goes through here first.
    """
    for key in run.secret_keys:
        value = run.inputs.get(key, "")
        if value:
            text = text.replace(value, HIDDEN_SECRET)
    return text


def masked(run: PreparedRun) -> tuple[dict[str, str], dict[str, str]]:
    inputs = {k: (HIDDEN_SECRET if k in run.secret_keys else v) for k, v in run.inputs.items()}
    env = {k: (HIDDEN_SECRET if k in run.secret_keys else v) for k, v in run.env.items()}
    return inputs, env


def secret_set(config: dict[str, Any]) -> set[str]:
    """The input keys a stored bash config holds as secret."""
    return {str(k) for k in (config.get("secret_keys") or [])}


def mask_bash_config(config: dict[str, Any]) -> dict[str, Any]:
    out = dict(config)
    secret = secret_set(config)
    out["inputs"] = {k: (HIDDEN_SECRET if k in secret else v) for k, v in (config.get("inputs") or {}).items()}
    return out


def merge_bash_config(existing: dict[str, Any], incoming: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """Resolve ``<hidden>`` inputs against the stored config; return the merged config and the carried keys.

    ``<hidden>`` on an input the stored config holds as secret keeps the stored
    value (a carried key); every other key is taken from incoming. A non-secret
    stored value is never masked on read, so ``<hidden>`` for it is a literal
    the client typed and stays one. This neither validates the config nor
    re-stamps ``secret_keys``: ``storage_config`` is the only gate that writes
    ``secret_keys``, and it keeps every carried key secret.
    """
    stored = existing.get("inputs") or {}
    secret = secret_set(existing)
    carried = {k for k, v in (incoming.get("inputs") or {}).items() if v == HIDDEN_SECRET and k in secret}
    merged = dict(incoming)
    merged["inputs"] = {
        k: (stored.get(k, "") if k in carried else v) for k, v in (incoming.get("inputs") or {}).items()
    }
    return merged, carried


def patch_bash_config(existing: dict[str, Any], incoming: dict[str, Any], scripts_root: str) -> dict[str, Any]:
    """Apply a PATCH to a stored bash config without ever unmasking a stored secret.

    An unreadable script keeps the stored ``secret_keys`` (never the request's),
    and a value carried over from a stored secret stays secret until the client
    replaces it, whatever the new script header says.
    """
    merged, carried = merge_bash_config(existing, incoming)
    return storage_config(
        merged,
        scripts_root,
        fallback_secret_keys=existing.get("secret_keys") or [],
        carried_secret_keys=carried,
    )


def storage_config(
    incoming: dict[str, Any],
    scripts_root: str,
    *,
    fallback_secret_keys: Sequence[str] = (),
    carried_secret_keys: Collection[str] = (),
) -> dict[str, Any]:
    """Validate a bash config for persistence and stamp ``secret_keys`` from the script header.

    ``secret_keys`` is server-owned: the incoming value is ignored. A script
    whose header cannot be read gets ``fallback_secret_keys`` (the stored set on
    a PATCH, the request's own on a create) so masking survives a removed
    script, and ``carried_secret_keys`` are added either way so a stored secret
    is never unmasked by a header that no longer declares it.
    """
    script = str(incoming.get("script") or "")
    try:
        resolve_script(scripts_root, script)
    except ValueError as exc:
        raise HookError(str(exc)) from exc
    raw_timeout = incoming.get("timeout_seconds")
    # ``is None`` and not ``or``: an explicit 0 must fail the range check below
    # rather than silently becoming the default.
    timeout = DEFAULT_TIMEOUT_SECONDS if raw_timeout is None else int(raw_timeout)
    if not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        raise HookError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")
    try:
        secret_keys = [i.key for i in read_script_info(scripts_root, script).inputs if i.secret]
    except FileNotFoundError, ScriptUnreadableError:
        secret_keys = [str(k) for k in fallback_secret_keys]
    secret_keys += sorted(set(carried_secret_keys) - set(secret_keys))
    return {
        "type": "bash",
        "script": script,
        "timeout_seconds": timeout,
        "inputs": _clean_inputs(incoming.get("inputs")),
        "secret_keys": secret_keys,
    }
