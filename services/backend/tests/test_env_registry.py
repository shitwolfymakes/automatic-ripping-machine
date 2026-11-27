from arm_backend.config import Settings
from arm_backend.env_registry import CONTAINER_PUBLIC_ENV, ENV_GROUP_ORDER, ENV_REGISTRY


def test_every_settings_field_is_classified():
    assert set(Settings.model_fields) - set(ENV_REGISTRY) == set()


def test_registry_names_only_real_fields():
    assert set(ENV_REGISTRY) - set(Settings.model_fields) == set()


def test_groups_are_known():
    assert {m.group for m in ENV_REGISTRY.values()} <= set(ENV_GROUP_ORDER)


def test_pinned_secrets():
    for key in ("DATABASE_URL", "ARM_SERVICE_TOKEN", "TLS_CERT_PATH", "TLS_KEY_PATH"):
        assert ENV_REGISTRY[key].secret


def test_seed_only_vars():
    assert ENV_REGISTRY["MAX_PARALLEL_TRANSCODES"].seed_of == "max_parallel_transcodes"
    assert ENV_REGISTRY["ARM_RIPPER_MIN_LENGTH_SECONDS"].seed_of is None
    assert ENV_REGISTRY["ARM_GPUS"].seed_of == "gpus"


def test_service_token_never_public_in_containers():
    assert "ARM_SERVICE_TOKEN" not in CONTAINER_PUBLIC_ENV
