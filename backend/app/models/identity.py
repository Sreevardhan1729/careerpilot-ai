from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import enums as E
from app.models.base import (
    Base,
    created_at_col,
    enum_check,
    fk,
    jsonb,
    tstz,
    updated_at_col,
    user_fk,
    uuid_pk,
)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'Asia/Kolkata'"))
    settings: Mapped[dict[str, Any]] = jsonb()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


def _text_array() -> Mapped[list[str]]:
    return mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    full_name: Mapped[str | None] = mapped_column(Text)
    preferred_email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    current_location: Mapped[str | None] = mapped_column(Text)
    preferred_locations: Mapped[list[str]] = _text_array()
    preferred_work_modes: Mapped[list[str]] = _text_array()
    graduation_year: Mapped[int | None] = mapped_column(Integer)
    total_experience_months: Mapped[int | None] = mapped_column(Integer)
    preferred_roles: Mapped[list[str]] = _text_array()
    preferred_industries: Mapped[list[str]] = _text_array()
    portfolio_url: Mapped[str | None] = mapped_column(Text)
    github_url: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    salary_preference: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    employment_type_preferences: Mapped[list[str]] = _text_array()
    notice_period_days: Mapped[int | None] = mapped_column(Integer)
    work_authorization: Mapped[str | None] = mapped_column(Text)
    field_sources: Mapped[dict[str, Any]] = jsonb()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    __table_args__ = (UniqueConstraint("user_id"), {"comment": "Candidate profile scalar fields (spec §3.1)"})


class CandidateProfileFact(Base):
    __tablename__ = "candidate_profile_facts"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    fact_type: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_resume_version_id: Mapped[uuid.UUID | None] = fk("resume_versions.id", ondelete="SET NULL")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_at: Mapped[datetime | None] = tstz()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    __table_args__ = (
        enum_check("fact_type", E.FACT_TYPES),
        enum_check("source", E.FACT_SOURCES),
        enum_check("status", E.FACT_STATUSES),
    )


class SearchConfig(Base):
    __tablename__ = "search_configs"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role_filters: Mapped[list[str]] = _text_array()
    experience_bands: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    locations: Mapped[list[str]] = _text_array()
    work_modes: Mapped[list[str]] = _text_array()
    skills: Mapped[list[str]] = _text_array()
    salary_minimum: Mapped[float | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str | None] = mapped_column(Text)
    salary_period: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Company(Base):
    """Shared reference table (no user_id)."""

    __tablename__ = "companies"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    domain: Mapped[str | None] = mapped_column(Text, unique=True)
    website: Mapped[str | None] = mapped_column(Text)
    careers_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Skill(Base):
    """Shared skill taxonomy, seeded from app/data/skills_taxonomy.yaml."""

    __tablename__ = "skills"
    id: Mapped[uuid.UUID] = uuid_pk()
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[list[str]] = _text_array()
    parent_id: Mapped[uuid.UUID | None] = fk("skills.id", ondelete="SET NULL")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    __table_args__ = (enum_check("category", E.SKILL_CATEGORIES),)
