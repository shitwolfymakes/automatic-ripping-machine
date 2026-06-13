from arm_common.secrets import HIDDEN_SECRET


def test_hidden_secret_literal():
    assert HIDDEN_SECRET == "<hidden>"


def test_field_map_uses_shared_constant():
    # The notifications masking literal must come from the one shared source,
    # so config + notifications can never drift.
    from arm_backend.notifications import field_map

    assert field_map._HIDDEN_LITERAL is HIDDEN_SECRET
