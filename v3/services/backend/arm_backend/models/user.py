from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String
from sqlmodel import Field, SQLModel

from arm_backend.models._columns import created_at_column, updated_at_column
from arm_common import new_id


def _user_id() -> str:
    return new_id("usr")


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_user_id, primary_key=True)
    username: str = Field(sa_column=Column(String, unique=True, nullable=False, index=True))
    password_hash: str = Field(sa_column=Column(String, nullable=False))
    password_must_change: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="true"))
    last_login_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
