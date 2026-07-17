"""Shared human-readable detail strings for the makemkv key-validity state.
Read by the test-key endpoint and the system preflight check — keep it in one
place so both surfaces describe a given MakemkvKeyState identically."""

_MAKEMKV_STATE_DETAIL: dict[str, str] = {
    "valid": "MakeMKV key is valid",
    "unregistered_or_expired": "no valid MakeMKV key in effect (evaluation expired)",
    "binary_expired": "MakeMKV binary is expired — rebuild the ripper image (no key fixes this)",
    "format_invalid": "configured key is not a valid MakeMKV serial",
    "probe_failed": "could not validate — the ripper's makemkvcon probe failed",
}


def makemkv_state_detail(state: str | None) -> str | None:
    """Human-readable detail for a stored makemkv_key_state value (None → None)."""
    if state is None:
        return None
    return _MAKEMKV_STATE_DETAIL.get(state, state)
