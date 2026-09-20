"""Direct seeders coverage: guest account seed (fixed, disabled) + admin role.

See also `test_seeders_full.py` (admin idempotency + first-boot banner,
config signing-key back-fill, `_insert_missing` idempotency) and
`test_seed_inapp_channel.py` (in-app notification channel seed).
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.seeders import (  # noqa: E402
    GUEST_USERNAME,
    _seed_admin_user,
    _seed_guest_user,
)
from arm_common import User  # noqa: E402
from arm_common.models.user import ADMIN_ROLE, GUEST_ROLE  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


async def test_seed_guest_creates_disabled_guest() -> None:
    db = FakeSession()
    await _seed_guest_user(db)

    created = [u for u in db.added if isinstance(u, User)]
    assert len(created) == 1
    guest = created[0]
    assert guest.username == GUEST_USERNAME
    assert guest.role == GUEST_ROLE
    assert guest.disabled is True
    assert guest.password_must_change is False


async def test_seed_guest_idempotent() -> None:
    db = FakeSession()
    await _seed_guest_user(db)
    assert len([u for u in db.added if isinstance(u, User)]) == 1

    # Second run: guest already present → early return, no second insert.
    await _seed_guest_user(db)
    assert len([u for u in db.added if isinstance(u, User)]) == 1


async def test_seed_admin_sets_admin_role() -> None:
    db = FakeSession()
    await _seed_admin_user(db)

    created = [u for u in db.added if isinstance(u, User)]
    assert len(created) == 1
    assert created[0].role == ADMIN_ROLE
