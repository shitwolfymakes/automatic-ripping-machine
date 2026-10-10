"""JobMetadata typed core (step 2 §3.4): flag helpers + round-trip safety."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_common.enums import DiscType, JobStatus  # noqa: E402
from arm_common.models.job import Job  # noqa: E402
from arm_common.schemas import JobMetadata, JobView, flag_is_set, with_flags  # noqa: E402


def make_job(**overrides: object) -> Job:
    defaults: dict[str, object] = {
        "id": "job_01JZXR7K3M5Q8N4VWA00000099",
        "drive_id": "drv_x",
        "disc_type": DiscType.DVD,
        "status": JobStatus.RIPPED,
        "title": "X",
        "year": 2000,
        "metadata_json": {},
        "resumed_from_crash": False,
    }
    defaults.update(overrides)
    return Job(**defaults)


def test_jobview_types_metadata_and_keeps_unknown_keys() -> None:
    job = make_job(
        metadata_json={
            "identity": {"provider": "tmdb"},
            "someday_key": {"kept": True},  # extra="allow" grace must survive the wire
        }
    )
    view = JobView.model_validate(job)
    assert view.metadata_json.identity.provider == "tmdb"
    dumped = view.model_dump(mode="json")["metadata_json"]
    assert dumped["someday_key"] == {"kept": True}


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
    assert flag_is_set({"unidentified": True}, "unidentified") is True  # pre-0032 rows (no flags section yet)
    assert flag_is_set(None, "unidentified") is False


def test_job_metadata_round_trips_unknown_keys() -> None:
    """extra="allow" everywhere: pre-0032 rows (no typed sections yet) and
    pre-0033 rows that still carry the (now-retired) pending_session_id
    mirror must survive a validate -> dump round-trip unchanged."""
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

    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0032_job_metadata_sections.py"
    spec = importlib.util.spec_from_file_location("mig_0032", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._reshape


def test_migration_0032_reshape_lifts_legacy_rows() -> None:
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


def test_migration_0032_reshape_is_idempotent() -> None:
    reshape = _load_reshape()
    clean = {
        "scan_result": {"disc_type": "dvd"},
        "identity": {"provider": "tmdb", "external_ids": {"tmdb": "1726"}},
        "flags": {"unidentified": False},
        "provider_raw": {"tmdb": {"id": 1726}},
    }
    assert reshape(clean) is None


def _load_strip_mirror_keys():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0033_drop_metadata_mirrors.py"
    spec = importlib.util.spec_from_file_location("mig_0033", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.strip_mirror_keys


def test_migration_0033_strip_mirror_keys_removes_lifted_columns() -> None:
    strip_mirror_keys = _load_strip_mirror_keys()
    md = {
        "scan_result": {"disc_type": "dvd"},
        "pending_session_id": "ses_x",
        "season": 3,
        "disc": 2,
        "identity": {"provider": "tmdb", "external_ids": {"tmdb": "1726"}},
    }
    out, changed = strip_mirror_keys(md)
    assert changed is True
    assert "pending_session_id" not in out
    assert "season" not in out
    assert "disc" not in out
    # other keys untouched
    assert out["scan_result"] == {"disc_type": "dvd"}
    assert out["identity"] == {"provider": "tmdb", "external_ids": {"tmdb": "1726"}}
    # input untouched (pure function)
    assert md["pending_session_id"] == "ses_x"


def test_migration_0033_strip_mirror_keys_is_idempotent() -> None:
    strip_mirror_keys = _load_strip_mirror_keys()
    clean = {
        "scan_result": {"disc_type": "dvd"},
        "identity": {"provider": "tmdb", "external_ids": {"tmdb": "1726"}},
        "flags": {"unidentified": False},
    }
    out, changed = strip_mirror_keys(clean)
    assert changed is False
    assert out == clean

    # second pass on the already-stripped output is a no-op too
    md = {"scan_result": {}, "pending_session_id": "ses_x", "season": 1, "disc": 1}
    first_out, first_changed = strip_mirror_keys(md)
    assert first_changed is True
    second_out, second_changed = strip_mirror_keys(first_out)
    assert second_changed is False
    assert second_out == first_out
