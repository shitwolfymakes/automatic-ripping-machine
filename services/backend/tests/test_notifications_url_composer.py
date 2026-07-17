from arm_backend.notifications.url_composer import compose_apprise_url


def test_compose_required_only() -> None:
    url = compose_apprise_url(service_id="discord", required={"webhook_id": "1", "webhook_token": "2"}, advanced={})
    assert url == "discord://1/2"


def test_compose_url_encodes_segments() -> None:
    url = compose_apprise_url(service_id="x", required={"a": "a/b c"}, advanced={})
    assert url == "x://a%2Fb%20c"


def test_compose_advanced_as_query() -> None:
    url = compose_apprise_url(service_id="x", required={"a": "1"}, advanced={"format": "markdown"})
    assert url == "x://1?format=markdown"


def test_compose_drops_blank_advanced() -> None:
    url = compose_apprise_url(service_id="x", required={"a": "1"}, advanced={"thread": "", "tz": None})
    assert url == "x://1"


def test_compose_bool_yes_no() -> None:
    url = compose_apprise_url(service_id="x", required={"a": "1"}, advanced={"image": True, "footer": False})
    assert url == "x://1?image=yes&footer=no"


def test_compose_skips_blank_required_segment() -> None:
    url = compose_apprise_url(service_id="x", required={"a": "1", "b": ""}, advanced={})
    assert url == "x://1"
