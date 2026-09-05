from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String
from sqlmodel import Field, SQLModel

from arm_common.enums import UserRole
from arm_common.models._columns import created_at_column, enum_column, updated_at_column
from arm_common.ulid import new_id

# Convenience aliases for the two members. `UserRole` is the source of truth;
# these keep the many `role=ADMIN_ROLE` / `role != ADMIN_ROLE` call sites
# reading naturally, and compare equal to the wire strings because
# `UserRole` is a StrEnum.
ADMIN_ROLE = UserRole.ADMIN
GUEST_ROLE = UserRole.GUEST


def _user_id() -> str:
    return new_id("usr")


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_user_id, primary_key=True)
    username: str = Field(sa_column=Column(String, unique=True, nullable=False, index=True))
    password_hash: str = Field(sa_column=Column(String, nullable=False))
    password_must_change: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="true"))
    role: UserRole = Field(
        default=UserRole.ADMIN,
        sa_column=enum_column(UserRole, "user_role", server_default=UserRole.ADMIN.value),
    )
    disabled: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default="false"))
    last_login_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
