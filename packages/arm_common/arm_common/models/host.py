from datetime import datetime

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, SQLModel


class Host(SQLModel, table=True):
    """A container that reports in (the backend or a ripper). Identity is
    durable; live resource telemetry (CPU/mem/disk) is NOT stored here — it
    lives in the backend's in-memory snapshot map. `role` is a VARCHAR enum
    validated in the app layer (v3 invariant: no Postgres CREATE TYPE).
    Rows are never auto-deleted; the read filter hides stale hosts from tabs.
    """

    __tablename__ = "hosts"

    hostname: str = Field(sa_column=Column(String, primary_key=True))
    role: str = Field(sa_column=Column(String, nullable=False))  # "backend" | "ripper"
    version: str = Field(sa_column=Column(String, nullable=False, server_default=""))
    first_seen: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    last_seen: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))
