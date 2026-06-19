"""theme_service — built-in load, user merge/override, validate, save, delete, path-guard."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend import theme_service  # noqa: E402


@pytest.fixture
def user_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(theme_service.settings, "ARM_THEMES_PATH", str(tmp_path))
    return tmp_path


def test_builtins_present_and_parse():
    themes = theme_service.get_all_themes()
    by_id = {t["id"]: t for t in themes}
    assert len(themes) >= 30
    assert by_id["blockbuster"]["builtin"] is True
    assert "tokens" in by_id["blockbuster"]
    assert all("css" not in t for t in themes)


def test_get_theme_returns_full_with_css(user_dir):
    full = theme_service.get_theme("lcars")
    assert full is not None
    assert full["builtin"] is True
    assert "css" in full


def test_get_unknown_returns_none(user_dir):
    assert theme_service.get_theme("does-not-exist") is None


def test_save_user_theme_writes_json_and_css(user_dir):
    data = {"id": "mine", "label": "Mine", "tokens": {"--color-primary": "rgb(1,2,3)"}}
    saved = theme_service.save_user_theme(data, css="[data-scheme=mine]{}")
    assert saved["builtin"] is False
    assert (user_dir / "mine.json").is_file()
    assert (user_dir / "mine.css").read_text() == "[data-scheme=mine]{}"
    assert any(t["id"] == "mine" and t["builtin"] is False for t in theme_service.get_all_themes())


def test_save_without_css_removes_sidecar(user_dir):
    (user_dir / "mine.css").write_text("stale")
    theme_service.save_user_theme({"id": "mine", "label": "Mine", "tokens": {}}, css="")
    assert not (user_dir / "mine.css").exists()


def test_save_rejects_missing_required_fields(user_dir):
    with pytest.raises(ValueError):
        theme_service.save_user_theme({"id": "x"}, css="")


def test_save_rejects_unsafe_id(user_dir):
    with pytest.raises(ValueError):
        theme_service.save_user_theme({"id": "../evil", "label": "x", "tokens": {}}, css="")


def test_user_overrides_builtin_by_id(user_dir):
    theme_service.save_user_theme({"id": "blockbuster", "label": "Mine BB", "tokens": {"--x": "y"}}, css="")
    full = theme_service.get_theme("blockbuster")
    assert full["label"] == "Mine BB"
    assert full["builtin"] is False


def test_delete_user_theme(user_dir):
    theme_service.save_user_theme({"id": "mine", "label": "Mine", "tokens": {}}, css="x")
    assert theme_service.delete_user_theme("mine") is True
    assert not (user_dir / "mine.json").exists()
    assert not (user_dir / "mine.css").exists()


def test_delete_builtin_refused(user_dir):
    assert theme_service.delete_user_theme("blockbuster") is False


def test_delete_absent_returns_false(user_dir):
    assert theme_service.delete_user_theme("nope") is False


def test_delete_rejects_unsafe_id(user_dir):
    with pytest.raises(ValueError):
        theme_service.delete_user_theme("../../etc/passwd")


def test_load_skips_corrupt_json(user_dir):
    # a corrupt user theme file is silently skipped (not raised), leaving the list intact
    (user_dir / "broken.json").write_text("{not json")
    ids = {t["id"] for t in theme_service.get_all_themes()}
    assert "broken" not in ids
    assert "blockbuster" in ids  # built-ins still load


def test_save_whitespace_only_css_removes_sidecar(user_dir):
    (user_dir / "mine.css").write_text("stale")
    saved = theme_service.save_user_theme({"id": "mine", "label": "Mine", "tokens": {}}, css="   ")
    assert not (user_dir / "mine.css").exists()
    assert saved["css"] == ""


def test_save_does_not_mutate_caller_dict(user_dir):
    original = {"id": "mine", "label": "Mine", "tokens": {}}
    theme_service.save_user_theme(original, css="x")
    # caller's dict is untouched — no version/swatch/builtin/css injected
    assert original == {"id": "mine", "label": "Mine", "tokens": {}}


def test_get_user_theme_includes_css(user_dir):
    theme_service.save_user_theme({"id": "mine", "label": "Mine", "tokens": {}}, css="[data-scheme=mine]{}")
    full = theme_service.get_theme("mine")
    assert full["css"] == "[data-scheme=mine]{}"
    assert full["builtin"] is False
