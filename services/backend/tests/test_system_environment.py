import pytest
from arm_backend.config import Settings
from arm_backend.env_registry import ENV_GROUP_ORDER
from arm_backend.system_environment import build_env_groups, strip_userinfo
from arm_common import Config
from arm_common.schemas.system import EnvEffectiveView, EnvGroupView, EnvVarView


@pytest.fixture
def make_settings(monkeypatch: pytest.MonkeyPatch):
    def _make(**env: str) -> Settings:
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/arm")
        monkeypatch.setenv("ARM_SERVICE_TOKEN", "tok")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        return Settings()

    return _make


def _var(groups: list[EnvGroupView], key: str) -> EnvVarView:
    return next(v for g in groups for v in g.vars if v.key == key)


def test_groups_follow_order_and_cover_every_field(make_settings):
    groups = build_env_groups(make_settings(), Config(id=1), 0)
    assert [g.name for g in groups] == [n for n in ENV_GROUP_ORDER if any(g.name == n for g in groups)]
    assert {v.key for g in groups for v in g.vars} == set(Settings.model_fields)


def test_secret_masked_but_reported_set(make_settings):
    v = _var(build_env_groups(make_settings(), Config(id=1), 0), "ARM_SERVICE_TOKEN")
    assert v.value is None and v.secret and v.is_set and v.source == "env"


def test_source_default_vs_env(make_settings):
    groups = build_env_groups(make_settings(BIND_PORT="9443"), Config(id=1), 0)
    assert _var(groups, "BIND_PORT").source == "env" and _var(groups, "BIND_PORT").value == "9443"
    assert _var(groups, "RAW_ROOT").source == "default" and _var(groups, "RAW_ROOT").value == "/raw"


def test_explicit_empty_string_is_env_source(make_settings):
    v = _var(
        build_env_groups(make_settings(ARM_RIPPER_MIN_LENGTH_SECONDS=""), Config(id=1), 0),
        "ARM_RIPPER_MIN_LENGTH_SECONDS",
    )
    assert v.source == "env" and v.value == "" and v.is_set is False


def test_url_userinfo_stripped(make_settings):
    groups = build_env_groups(make_settings(ARM_TRANSCODE_DOCKER_HOST="ssh://bob:pw@nas:22"), Config(id=1), 0)
    assert _var(groups, "ARM_TRANSCODE_DOCKER_HOST").value == "ssh://***@nas:22"


def test_strip_userinfo_passes_non_urls_through():
    assert strip_userinfo("/var/run/docker.sock") == "/var/run/docker.sock"
    assert strip_userinfo("http://host:80/x") == "http://host:80/x"


def test_seed_only_shows_effective_db_value(make_settings):
    groups = build_env_groups(make_settings(MAX_PARALLEL_TRANSCODES="2"), Config(id=1, max_parallel_transcodes=4), 0)
    eff = _var(groups, "MAX_PARALLEL_TRANSCODES").effective
    assert eff == EnvEffectiveView(value="4", setting_key="max_parallel_transcodes", tab="Transcoding")


def test_seed_only_falls_back_without_config_row(make_settings):
    groups = build_env_groups(make_settings(MAX_PARALLEL_TRANSCODES="2"), None, 0)
    eff = _var(groups, "MAX_PARALLEL_TRANSCODES").effective
    assert eff is not None and eff.value == "2"


def test_gpus_effective_is_inventory_count(make_settings):
    eff = _var(build_env_groups(make_settings(), Config(id=1), 3), "ARM_GPUS").effective
    assert eff is not None and eff.value == "3 device(s) in inventory"
