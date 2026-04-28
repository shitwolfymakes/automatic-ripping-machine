from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, Dialect, String, func
from sqlalchemy.types import TypeDecorator


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
        if value is None:
            return None
        return self._enum_cls(value)


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
