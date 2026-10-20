import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from arm_common import models  # noqa: F401  # register tables on SQLModel.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_url() -> str:
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql+psycopg://" + url[len("postgresql+asyncpg://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


target_metadata = SQLModel.metadata


class _NoRows(list[tuple[object, ...]]):
    """Empty result for a statement executed on the offline mock connection."""

    def scalar(self) -> None:
        return None

    def first(self) -> None:
        return None


def _offline_safe_bind() -> None:
    """Make ``op.get_bind().execute()`` return an empty result offline.

    Offline, the bind is a mock connection that renders each statement and
    returns ``None``. Data-lift revisions (0032, 0033) iterate a SELECT's rows,
    so ``--sql`` crashed there. Returning no rows renders the SELECT and skips
    the row-by-row rewrite, which has no SQL form anyway.
    """
    conn = context.get_context().connection
    # `_execute_impl` is private to sqlalchemy.engine.mock.MockConnection
    # (2.0.x). If an upgrade renames it, test_every_revision_after_0011_renders_offline
    # fails first; update the name here.
    render = conn._execute_impl  # type: ignore[union-attr]

    def execute(obj: object, parameters: object = None) -> _NoRows:
        render(obj, parameters)
        return _NoRows()

    conn._execute_impl = execute  # type: ignore[union-attr]


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    _offline_safe_bind()
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _sync_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
