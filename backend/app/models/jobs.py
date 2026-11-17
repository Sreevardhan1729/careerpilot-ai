from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, Index, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    company_id: Mapped[uuid.UUID | None] = fk("companies.id", ondelete="RESTRICT")
    input_type: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    application_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    normalized_title: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    seniority: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unknown'"))
    experience_min_years: Mapped[float | None] = mapped_column(Numeric(4, 1))
    experience_max_years: Mapped[float | None] = mapped_column(Numeric(4, 1))
    experience_explicit: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    experience_evidence: Mapped[str | None] = mapped_column(Text)
    locations: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    work_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unknown'"))
    employment_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unknown'"))
    salary_min: Mapped[float | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[float | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str | None] = mapped_column(Text)
    salary_period: Mapped[str | None] = mapped_column(Text)
    salary_source_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'not_disclosed'"))
    salary_is_base: Mapped[bool | None] = mapped_column(Boolean)
    salary_source_url: Mapped[str | None] = mapped_column(Text)
    salary_retrieved_at: Mapped[datetime | None] = tstz()
    salary_confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    education: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    responsibilities: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    technical_requirements: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    soft_skills: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    business_domain: Mapped[str | None] = mapped_column(Text)
    application_deadline: Mapped[date | None] = mapped_column(Date)
    posted_at: Mapped[datetime | None] = tstz()
    posted_at_source: Mapped[str | None] = mapped_column(Text)
    hiring_expectations: Mapped[str | None] = mapped_column(Text)
    posted_by: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    description_text: Mapped[str] = mapped_column(Text, nullable=False)
    description_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    missing_information: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    field_confidence: Mapped[dict[str, Any]] = jsonb()
    status: Mapped[str] = mapped_column(Text, nullable=False)
    saved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    best_resume_id: Mapped[uuid.UUID | None] = fk("resumes.id", ondelete="SET NULL")
    match_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    job_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    job_score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    priority: Mapped[str | None] = mapped_column(Text)
    scoring_config_version: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    model_id: Mapped[str | None] = mapped_column(Text)
    analyzed_at: Mapped[datetime | None] = tstz()
    last_seen_at: Mapped[datetime | None] = tstz()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    __table_args__ = (
        enum_check("input_type", E.JOB_INPUT_TYPES),
        enum_check("seniority", E.SENIORITY),
        enum_check("work_mode", E.WORK_MODES),
        enum_check("employment_type", E.EMPLOYMENT_TYPES),
        enum_check("salary_source_type", E.SALARY_SOURCE_TYPES),
        enum_check("status", E.JOB_STATUSES),
        Index("uq_jobs_user_canonical_url", "user_id", "canonical_url", unique=True,
              postgresql_where=text("canonical_url IS NOT NULL")),
        Index("ix_jobs_user_desc_hash", "user_id", "description_sha256"),
        Index("ix_jobs_user_created", "user_id", text("created_at DESC")),
        Index("ix_jobs_user_posted", "user_id", text("posted_at DESC")),
        Index("ix_jobs_user_status", "user_id", "status"),
        Index("ix_jobs_user_priority_score", "user_id", "priority", text("job_score DESC")),
    )


class JobSourceRecord(Base):
    __tablename__ = "job_source_records"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    job_id: Mapped[uuid.UUID] = fk("jobs.id", nullable=False)
    crawl_source_id: Mapped[uuid.UUID | None] = fk("crawl_sources.id", ondelete="SET NULL")
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_listing_id: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    application_url: Mapped[str | None] = mapped_column(Text)
    raw_title: Mapped[str | None] = mapped_column(Text)
    raw_company: Mapped[str | None] = mapped_column(Text)
    raw_location: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = tstz()
    collected_at: Mapped[datetime] = tstz(nullable=False)  # type: ignore[assignment]
    raw_description: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str | None] = mapped_column(Text)
    dedup_signal: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = created_at_col()
    __table_args__ = (
        enum_check("dedup_signal", E.DEDUP_SIGNALS),
        Index("uq_jsr_user_source_listing", "user_id", "source_name", "source_listing_id", unique=True,
              postgresql_where=text("source_listing_id IS NOT NULL")),
        Index("ix_jsr_user_canonical", "user_id", "canonical_url"),
        Index("ix_jsr_user_application", "user_id", "application_url"),
    )


class JobEvidence(Base):
    __tablename__ = "job_evidence"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    job_id: Mapped[uuid.UUID] = fk("jobs.id", nullable=False)
    field: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Any] = mapped_column(JSONB)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    explicit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    source_record_id: Mapped[uuid.UUID | None] = fk("job_source_records.id", ondelete="SET NULL")
    created_at: Mapped[datetime] = created_at_col()
    __table_args__ = (Index("ix_job_evidence_job_field", "job_id", "field"),)


class JobSkill(Base):
    __tablename__ = "job_skills"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    job_id: Mapped[uuid.UUID] = fk("jobs.id", nullable=False)
    skill_id: Mapped[uuid.UUID | None] = fk("skills.id", ondelete="RESTRICT")
    raw_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    evidence_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    created_at: Mapped[datetime] = created_at_col()
    __table_args__ = (
        UniqueConstraint("job_id", "normalized_name"),
        enum_check("importance", E.SKILL_IMPORTANCE),
        enum_check("category", E.SKILL_CATEGORIES),
    )


class ResumeMatch(Base):
    __tablename__ = "resume_matches"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    job_id: Mapped[uuid.UUID] = fk("jobs.id", nullable=False)
    resume_id: Mapped[uuid.UUID] = fk("resumes.id", nullable=False)
    resume_version_id: Mapped[uuid.UUID] = fk("resume_versions.id", nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    components: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    mandatory_coverage: Mapped[float | None] = mapped_column(Numeric(5, 4))
    preferred_coverage: Mapped[float | None] = mapped_column(Numeric(5, 4))
    skill_breakdown: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    relevant_projects: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    relevant_experience: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    suggestions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    explanation: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    is_best: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scoring_config_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    __table_args__ = (
        UniqueConstraint("job_id", "resume_version_id", "scoring_config_version"),
        Index("ix_resume_matches_job_rank", "job_id", "rank"),
    )
