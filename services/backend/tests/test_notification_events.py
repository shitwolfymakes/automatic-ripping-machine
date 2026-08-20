from arm_backend.notification_events import EVENT_VOCAB, EventSpec, event_keys

_EXPECTED = {
    "rip.completed",
    "rip.failed",
    "rip.partial",
    "rip.needs_user_input",
    "session.completed",
    "session.failed",
    "session.partial",
}


def test_vocab_covers_exactly_the_real_keys():
    assert set(EVENT_VOCAB) == _EXPECTED
    assert event_keys() == sorted(_EXPECTED)


def test_each_spec_is_well_formed():
    for key, spec in EVENT_VOCAB.items():
        assert isinstance(spec, EventSpec)
        assert spec.label and spec.default_title and spec.default_body
        # every {var} used in the default templates must be declared in variables
        import string

        used = set()
        for tmpl in (spec.default_title, spec.default_body):
            used |= {f[1] for f in string.Formatter().parse(tmpl) if f[1]}
        assert used <= set(spec.variables), f"{key}: {used - set(spec.variables)} not declared"


def test_common_variables_present_on_every_event():
    for spec in EVENT_VOCAB.values():
        for v in ("job_title", "job_id", "drive_id", "event_type", "occurred_at"):
            assert v in spec.variables


def test_vocab_keys_match_notable_event_types():
    from arm_backend.notification_dispatcher import NOTABLE_EVENT_TYPES

    assert set(EVENT_VOCAB) == set(NOTABLE_EVENT_TYPES)
