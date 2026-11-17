from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, MetaData, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.enums import check_in

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}
    # Fetch server-generated values (updated_at, defaults) via RETURNING so async code never lazy-loads them.
    __mapper_args__ = {"eager_defaults": True}


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def user_fk(nullable: bool = False) -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=nullable, index=True
    )


def fk(target: str, ondelete: str = "CASCADE", nullable: bool = True, index: bool = True, **kw: Any) -> Mapped[Any]:
    return mapped_column(UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete, **kw), nullable=nullable, index=index)


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


def tstz(nullable: bool = True) -> Mapped[datetime | None]:
    return mapped_column(DateTime(timezone=True), nullable=nullable)


def jsonb(default: str = "'{}'::jsonb") -> Mapped[Any]:
    return mapped_column(JSONB, nullable=False, server_default=text(default))


def enum_check(column: str, values: tuple[str, ...], name: str | None = None) -> CheckConstraint:
    return CheckConstraint(check_in(column, values), name=name or column)
