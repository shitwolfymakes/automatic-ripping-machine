from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String
from sqlmodel import Field, SQLModel

from arm_common.models._columns import created_at_column, updated_at_column
from arm_common.ulid import new_id

# App-validated role set — stored as VARCHAR, never a Postgres enum.
ADMIN_ROLE = "admin"
GUEST_ROLE = "guest"
USER_ROLES = frozenset({ADMIN_ROLE, GUEST_ROLE})


def _user_id() -> str:
    return new_id("usr")


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_user_id, primary_key=True)
    username: str = Field(sa_column=Column(String, unique=True, nullable=False, index=True))
    password_hash: str = Field(sa_column=Column(String, nullable=False))
    password_must_change: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="true"))
    role: str = Field(default=ADMIN_ROLE, sa_column=Column(String, nullable=False, server_default="admin"))
    disabled: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default="false"))
    last_login_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
