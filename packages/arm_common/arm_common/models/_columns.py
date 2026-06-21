import logging
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, Dialect, String, func
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger("arm_common.models")


class _StrEnumString(TypeDecorator[StrEnum]):
    """SQLAlchemy column that stores a StrEnum as VARCHAR and reconstructs
    the enum instance on load.

    Without this, rows fetched from Postgres assign a plain `str` to a field
    typed as a StrEnum, and Pydantic emits a serialization warning every time
    the row is serialized to JSON. With this, the column round-trips
    StrEnum ↔ str at the SQL boundary and the field always carries the typed
    enum.
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_cls: type[StrEnum]) -> None:
        self._enum_cls = enum_cls
        super().__init__()

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if isinstance(value, self._enum_cls):
            return value.value
        return str(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> StrEnum | None:
        # The declared return type matches TypeDecorator's supertype (StrEnum | None)
        # so the override type-checks. At runtime the except branch may return a raw
        # str for a forward-incompatible value (see below); callers must treat the
        # loaded value as possibly-str and render it via `enum_value_str`, not `.value`.
        if value is None:
            return None
        try:
            return self._enum_cls(value)
        except ValueError:
            # Tolerant coercion: a value written by a NEWER build (an enum member
            # this build doesn't know) must not raise on load — a single such row
            # would 500 every bulk query (job list / detail). Return the raw
            # string so the row still loads; the unknown status simply won't match
            # any known-value branch. This keeps a status enum addition
            # rollback-safe (old build reading a new row degrades, not crashes).
            logger.warning(
                "unknown %s value %r loaded from DB; returning raw string (forward-compat)",
                self._enum_cls.__name__,
                value,
            )
            return str(value)  # type: ignore[return-value]  # intentional runtime-only widening


def enum_value_str(value: Any) -> str:
    """Render an enum-backed column value as its string form, tolerating the
    forward-compat raw-string case.

    `_StrEnumString.process_result_value` returns a plain `str` (not the enum)
    for a value written by a newer build (see its docstring). Code that builds
    an error message off such a value must not assume `.value` exists — a `str`
    has none, so `f"...{status.value}"` would raise AttributeError and turn an
    intended 4xx into a 500. Use this instead: it returns `.value` for a known
    enum member and the value unchanged for a raw string.
    """
    return value.value if isinstance(value, StrEnum) else str(value)


def enum_column(
    enum_cls: type[StrEnum],
    _name: str,
    *,
    nullable: bool = False,
    server_default: str | None = None,
    index: bool = False,
) -> Column[Any]:
    """String-backed enum column.

    Stored as VARCHAR; converts str ↔ enum at the SQLAlchemy boundary via
    `_StrEnumString` so loaded rows present the typed enum to Pydantic. The
    StrEnum class in arm_common.enums remains the source of truth.
    """
    kwargs: dict[str, Any] = {"nullable": nullable, "index": index}
    if server_default is not None:
        kwargs["server_default"] = server_default
    return Column(_StrEnumString(enum_cls), **kwargs)


def created_at_column() -> Column[Any]:
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now())


def updated_at_column() -> Column[Any]:
    return Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
