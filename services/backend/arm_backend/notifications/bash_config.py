"""Persist a bash channel config: validate it, stamp its secret keys from the
script header, and mask or merge its stored secrets.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Any

from arm_backend.notifications.bash_hook import DEFAULT_TIMEOUT_SECONDS, HookError, clean_inputs, secret_set
from arm_backend.notifications.script_meta import ScriptUnreadableError, read_script_info, resolve_script
from arm_common.secrets import HIDDEN_SECRET

MAX_TIMEOUT_SECONDS = 600


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
        "inputs": clean_inputs(incoming.get("inputs")),
        "secret_keys": secret_keys,
    }
