from arm_backend.url_masking import strip_userinfo


def test_strip_userinfo_passes_non_urls_through():
    assert strip_userinfo("/var/run/docker.sock") == "/var/run/docker.sock"
    assert strip_userinfo("http://host:80/x") == "http://host:80/x"


def test_strip_userinfo_username_only_and_ipv6():
    assert strip_userinfo("ssh://bob@nas") == "ssh://***@nas"
    assert strip_userinfo("ssh://u:p@[::1]:22") == "ssh://***@[::1]:22"


def test_strip_userinfo_malformed_fails_closed():
    assert strip_userinfo("http://bob:pw@[bad") == "***"
