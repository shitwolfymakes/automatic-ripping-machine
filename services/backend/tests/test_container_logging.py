from arm_backend.container_logging import log_config


def test_log_config_rotates_json_file() -> None:
    assert log_config() == {"type": "json-file", "config": {"max-size": "10m", "max-file": "3"}}


def test_log_config_is_a_fresh_dict_per_call() -> None:
    first = log_config()
    first["config"]["max-size"] = "1g"
    assert log_config()["config"]["max-size"] == "10m"
