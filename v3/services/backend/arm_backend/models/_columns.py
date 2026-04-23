from enum import Enum as _PyEnum
from typing import Any

from sqlalchemy import Column, DateTime, String, func


def enum_column(
    _enum_cls: type[_PyEnum],
    _name: str,
    *,
    nullable: bool = False,
    server_default: str | None = None,
    index: bool = False,
) -> Column[Any]:
    """String-backed enum column.

    Status/mode columns are stored as VARCHAR; the StrEnum class in
    arm_common.enums is the source of truth and validation happens at write
    time through the SQLModel/Pydantic layer. The enum class and name args are
    retained for call-site legibility and to keep the signature stable if we
    ever swap the storage strategy.
    """
    kwargs: dict[str, Any] = {"nullable": nullable, "index": index}
    if server_default is not None:
        kwargs["server_default"] = server_default
    return Column(String, **kwargs)


def created_at_column() -> Column[Any]:
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now())


def updated_at_column() -> Column[Any]:
    return Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
