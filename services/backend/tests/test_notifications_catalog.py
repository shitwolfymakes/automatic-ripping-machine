from arm_backend.notifications import catalog as cat


class _FakePlugin:
    def __init__(self, *, scheme, name, tokens=None, args=None, url="https://docs"):
        self.secure_protocol = scheme
        self.protocol = None
        self.service_name = name
        self.service_url = url
        self.template_tokens = tokens or {}
        self.template_args = args or {}


class _FakeManager:
    def __init__(self, plugins):
        self._plugins = plugins

    def load_modules(self):
        return None

    def plugins(self):
        return self._plugins


def _patch(monkeypatch, plugins):
    cat.build_catalog.cache_clear()
    monkeypatch.setattr(cat, "_get_manager", lambda: _FakeManager(plugins))


def test_catalog_builds_required_and_advanced(monkeypatch) -> None:
    p = _FakePlugin(
        scheme="discord",
        name="Discord",
        tokens={"webhook_id": {"name": "Webhook ID", "type": "string", "required": True, "private": True}},
        args={"format": {"name": "Format", "type": "choice:string", "values": ["text", "markdown"], "default": "text"}},
    )
    _patch(monkeypatch, [p])
    c = cat.build_catalog()
    svc = c["services"][0]
    assert svc["id"] == "discord"
    assert svc["name"] == "Discord"
    assert svc["required_fields"][0] == {
        "key": "webhook_id", "label": "Webhook ID", "type": "string", "private": True, "required": True,
    }
    adv = svc["advanced_fields"][0]
    assert adv["type"] == "choice"
    assert adv["values"] == ["markdown", "text"]
    assert adv["default"] == "text"


def test_catalog_blocklist_and_alias_skipped(monkeypatch) -> None:
    p = _FakePlugin(
        scheme="x", name="X",
        args={"verify": {"name": "v", "type": "bool"}, "real": {"name": "r", "type": "string"}, "alias": {"alias_of": "real"}},
    )
    _patch(monkeypatch, [p])
    c = cat.build_catalog()
    keys = [f["key"] for f in c["services"][0]["advanced_fields"]]
    assert keys == ["real"]


def test_catalog_dedup_and_featured(monkeypatch) -> None:
    p1 = _FakePlugin(scheme="discord", name="Discord")
    p2 = _FakePlugin(scheme="discord", name="Discord dup")
    p3 = _FakePlugin(scheme="zzz", name="Zzz")
    _patch(monkeypatch, [p1, p2, p3])
    c = cat.build_catalog()
    ids = [s["id"] for s in c["services"]]
    assert ids.count("discord") == 1
    assert c["featured"] == ["discord"]  # only featured ids that exist
    # services sorted by name (lowercased): "Discord" before "Zzz"
    assert ids == ["discord", "zzz"]


def test_catalog_skips_plugin_with_no_scheme(monkeypatch) -> None:
    p = _FakePlugin(scheme=None, name="NoScheme")
    p.protocol = None
    _patch(monkeypatch, [p])
    c = cat.build_catalog()
    assert c["services"] == []


def test_catalog_unwraps_enum_default_value(monkeypatch) -> None:
    # a default carrying a ``.value`` (apprise enum-ish) is unwrapped -> line 53
    class _Enumish:
        value = "html"

    p = _FakePlugin(
        scheme="x", name="X",
        args={"format": {"name": "Format", "type": "string", "default": _Enumish()}},
    )
    _patch(monkeypatch, [p])
    c = cat.build_catalog()
    assert c["services"][0]["advanced_fields"][0]["default"] == "html"


def test_catalog_normalizes_plain_type_and_list_scheme(monkeypatch) -> None:
    # scheme as a list -> _service_id takes [0]; plain "string" advanced type -> passthrough
    p = _FakePlugin(
        scheme=["multi", "multis"],
        name="Multi",
        args={"token": {"name": "Token", "type": "string"}},
    )
    _patch(monkeypatch, [p])
    c = cat.build_catalog()
    svc = c["services"][0]
    assert svc["id"] == "multi"  # list scheme -> first element
    assert svc["advanced_fields"][0]["type"] == "string"  # plain type passthrough


def test_catalog_skips_plugin_that_raises(monkeypatch) -> None:
    bad = _FakePlugin(scheme="bad", name="Bad")
    # template_tokens that raises on .items()
    class _Boom:
        def items(self):
            raise RuntimeError("boom")
    bad.template_tokens = _Boom()
    good = _FakePlugin(scheme="good", name="Good")
    _patch(monkeypatch, [bad, good])
    c = cat.build_catalog()
    assert [s["id"] for s in c["services"]] == ["good"]
