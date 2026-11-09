"""Turn a bash channel config + event into a concrete run.

Everything that decides WHAT a script receives lives here, so the dispatcher
listener, the test endpoints, and the UI preview cannot drift: resolve the
title/body templates, resolve inputs (script default < channel value <
per-event override for non-secret keys), render input templates, build the
env, and expose a masked view for the API.
"""

from __future__ import annotations

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


def clean_inputs(raw: Any) -> dict[str, str]:
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


def _resolve_one_input(
    spec: ScriptInput,
    channel_inputs: dict[str, str],
    event_inputs: dict[str, str],
    secret_keys: frozenset[str],
) -> str:
    """The value one declared input takes before rendering: the script
    default, then a non-empty channel value, then a non-empty per-event value
    unless the key is secret.
    """
    key = spec.key
    value = spec.default
    if key in channel_inputs and channel_inputs[key] != "":
        value = channel_inputs[key]
    if key not in secret_keys and key in event_inputs and event_inputs[key] != "":
        value = event_inputs[key]
    return value


def _check_input(spec: ScriptInput, value: str) -> None:
    """Raise HookError when a rendered input breaks its header's rules:
    required, or one of a fixed set.
    """
    if spec.required and value == "":
        raise HookError(f"input {spec.key} is required")
    if spec.values and value != "" and value not in spec.values:
        raise HookError(f"input {spec.key} must be one of {', '.join(spec.values)}")


def _resolve_inputs(
    declared: list[ScriptInput],
    channel_inputs: dict[str, str],
    event_inputs: dict[str, str],
    secret_keys: frozenset[str],
    context: dict[str, str],
) -> dict[str, str]:
    """Resolve, render and check every input the script header declares."""
    # Only keys the script header declares reach the child: an undeclared stored
    # or per-event key is ignored, so a script with no header gets no inputs.
    resolved: dict[str, str] = {}
    for spec in declared:
        value = _render_input(spec.key, _resolve_one_input(spec, channel_inputs, event_inputs, secret_keys), context)
        _check_input(spec, value)
        resolved[spec.key] = value
    return resolved


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
    channel_inputs = clean_inputs(config.get("inputs"))
    event_inputs = clean_inputs((template or {}).get("inputs"))

    resolved = _resolve_inputs(declared, channel_inputs, event_inputs, secret_keys, context)

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
