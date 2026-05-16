"""_build_engine SSL-mode + URL-rewrite branch coverage.

create_async_engine makes no connection at construction, so we just need
each sslmode branch to run. The ssl.SSLContext is captured by patching
ssl.create_default_context so we can assert the per-mode mutations.
"""

from __future__ import annotations

import os
import ssl

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend import db as db_mod  # noqa: E402
from arm_backend.db import _build_engine  # noqa: E402


@pytest.fixture
def captured_ctx(monkeypatch: pytest.MonkeyPatch) -> list[ssl.SSLContext]:
    made: list[ssl.SSLContext] = []
    real = ssl.create_default_context

    def _capture(*args: object, **kwargs: object) -> ssl.SSLContext:
        ctx = real()  # ignore cafile so a bogus path doesn't raise
        made.append(ctx)
        return ctx

    monkeypatch.setattr(db_mod.ssl, "create_default_context", _capture)
    return made


def test_sslmode_require(captured_ctx: list[ssl.SSLContext]) -> None:
    eng = _build_engine("postgresql://u:p@h:5432/db?sslmode=require")
    assert eng.url.drivername == "postgresql+asyncpg"  # rewrite happened
    assert len(captured_ctx) == 1
    assert captured_ctx[0].check_hostname is False
    assert captured_ctx[0].verify_mode == ssl.CERT_NONE


def test_sslmode_verify_full(captured_ctx: list[ssl.SSLContext]) -> None:
    _build_engine("postgresql://u:p@h/db?sslmode=verify-full")
    assert captured_ctx[0].check_hostname is True


def test_sslmode_verify_ca(captured_ctx: list[ssl.SSLContext]) -> None:
    _build_engine("postgresql://u:p@h/db?sslmode=verify-ca&sslrootcert=/etc/ca.pem")
    assert captured_ctx[0].check_hostname is False


def test_no_sslmode_no_context(captured_ctx: list[ssl.SSLContext]) -> None:
    eng = _build_engine("postgresql://u:p@h/db")
    assert captured_ctx == []
    assert eng.url.drivername == "postgresql+asyncpg"


def test_already_qualified_url_not_rewritten(captured_ctx: list[ssl.SSLContext]) -> None:
    """A `postgresql+asyncpg://` URL doesn't start with `postgresql://`,
    so the rewrite branch is skipped (30->33)."""
    eng = _build_engine("postgresql+asyncpg://u:p@h/db")
    assert eng.url.drivername == "postgresql+asyncpg"
    assert captured_ctx == []
