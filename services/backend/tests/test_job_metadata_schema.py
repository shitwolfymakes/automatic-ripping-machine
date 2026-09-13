"""JobMetadata typed core (step 2 §3.4): flag helpers + round-trip safety."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_common.schemas import JobMetadata, flag_is_set, with_flags  # noqa: E402


def test_with_flags_sets_section_and_removes_legacy_key() -> None:
    md = {"unidentified": True, "k": "v"}
    out = with_flags(md, unidentified=True, dispatch_timeout=True)
    assert out["flags"] == {"unidentified": True, "dispatch_timeout": True}
    assert "unidentified" not in out
    assert out["k"] == "v"
    assert md == {"unidentified": True, "k": "v"}  # input untouched


def test_flag_is_set_prefers_section_over_legacy() -> None:
    assert flag_is_set({"flags": {"unidentified": True}}, "unidentified") is True
    assert flag_is_set({"flags": {"unidentified": False}, "unidentified": True}, "unidentified") is False
    assert flag_is_set({"unidentified": True}, "unidentified") is True  # pre-0031 rows
    assert flag_is_set(None, "unidentified") is False


def test_job_metadata_round_trips_unknown_keys() -> None:
    """extra="allow" everywhere: pre-0031 rows and the transitional
    pending_session_id mirror must survive validate → dump unchanged."""
    raw = {
        "scan_result": None,
        "pending_session_id": "ses_x",
        "some_legacy_key": {"nested": 1},
        "flags": {"unidentified": True, "future_flag": True},
    }
    parsed = JobMetadata.model_validate(raw)
    assert parsed.flags.unidentified is True
    dumped = parsed.model_dump(mode="json")
    assert dumped["pending_session_id"] == "ses_x"
    assert dumped["some_legacy_key"] == {"nested": 1}
    assert dumped["flags"]["future_flag"] is True


def _load_reshape():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0031_job_metadata_sections.py"
    spec = importlib.util.spec_from_file_location("mig_0031", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._reshape


def test_migration_0031_reshape_lifts_legacy_rows() -> None:
    reshape = _load_reshape()
    md = {
        "scan_result": {"disc_type": "dvd"},
        "pending_session_id": "ses_x",
        "imdb_id": "tt123",
        "artist": "The Beatles",
        "album": "Abbey Road",
        "tracks": [{"title": "Come Together"}],
        "unidentified": True,
        "poster_path": "/a.jpg",
        "Title": "Stale OMDb Key",
    }
    out = reshape(md)
    assert out is not None
    assert out["scan_result"] == {"disc_type": "dvd"}
    assert out["pending_session_id"] == "ses_x"
    assert out["identity"] == {"provider": "legacy", "external_ids": {"imdb": "tt123"}}
    assert out["music"]["artist"] == "The Beatles"
    assert out["music"]["tracks"][0]["title"] == "Come Together"
    assert out["flags"] == {"unidentified": True}
    assert out["provider_raw"]["legacy"] == {"poster_path": "/a.jpg", "Title": "Stale OMDb Key"}
    for stray in ("imdb_id", "artist", "album", "tracks", "unidentified", "poster_path", "Title"):
        assert stray not in out


def test_migration_0031_reshape_is_idempotent() -> None:
    reshape = _load_reshape()
    clean = {
        "scan_result": {"disc_type": "dvd"},
        "identity": {"provider": "tmdb", "external_ids": {"tmdb": "1726"}},
        "flags": {"unidentified": False},
        "provider_raw": {"tmdb": {"id": 1726}},
    }
    assert reshape(clean) is None
