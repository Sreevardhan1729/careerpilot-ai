from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, Index, Integer, Numeric, Text, UniqueConstraint, text
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


class Person(Base):
    __tablename__ = "people"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    company_id: Mapped[uuid.UUID | None] = fk("companies.id", ondelete="RESTRICT")
    name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    designation: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    public_email: Mapped[str | None] = mapped_column(Text)
    public_email_evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    association_status: Mapped[str] = mapped_column(Text, nullable=False)
    contact_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'new'"))
    added_by: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    first_discovered_at: Mapped[datetime] = tstz(nullable=False)  # type: ignore[assignment]
    last_verified_at: Mapped[datetime | None] = tstz()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    __table_args__ = (
        enum_check("association_status", E.ASSOCIATION_STATUSES),
        enum_check("contact_status", E.CONTACT_STATUSES),
        Index("uq_people_user_linkedin", "user_id", "linkedin_url", unique=True,
              postgresql_where=text("linkedin_url IS NOT NULL")),
        Index("ix_people_user_company_name", "user_id", "company_id", "normalized_name"),
    )


class PersonEvidence(Base):
    __tablename__ = "people_evidence"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    person_id: Mapped[uuid.UUID | None] = fk("people.id")
    job_id: Mapped[uuid.UUID | None] = fk("jobs.id", ondelete="SET NULL")
    company_id: Mapped[uuid.UUID | None] = fk("companies.id", ondelete="RESTRICT")
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = tstz(nullable=False)  # type: ignore[assignment]
    created_at: Mapped[datetime] = created_at_col()
    __table_args__ = (
        enum_check("source_type", E.PEOPLE_SOURCE_TYPES),
        UniqueConstraint("user_id", "content_sha256"),
    )


class JobPerson(Base):
    __tablename__ = "job_people"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    job_id: Mapped[uuid.UUID] = fk("jobs.id", nullable=False)
    person_id: Mapped[uuid.UUID] = fk("people.id", nullable=False)
    role_category: Mapped[str] = mapped_column(Text, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    components: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    relevance_reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    __table_args__ = (
        UniqueConstraint("job_id", "person_id"),
        enum_check("role_category", E.ROLE_CATEGORIES),
        CheckConstraint("cardinality(evidence_ids) > 0", name="has_evidence"),
        Index("ix_job_people_job_rank", "job_id", "rank"),
    )


class Outreach(Base):
    __tablename__ = "outreach"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    job_id: Mapped[uuid.UUID | None] = fk("jobs.id")
    person_id: Mapped[uuid.UUID | None] = fk("people.id", ondelete="SET NULL")
    application_id: Mapped[uuid.UUID | None] = fk("applications.id", ondelete="SET NULL", use_alter=True)
    message_type: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_name: Mapped[str | None] = mapped_column(Text)
    recipient_email: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_resume_id: Mapped[uuid.UUID | None] = fk("resumes.id", ondelete="SET NULL")
    personalization_evidence: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    claim_check: Mapped[dict[str, Any]] = jsonb()
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    gmail_draft_id: Mapped[str | None] = mapped_column(Text)
    gmail_message_id: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = tstz()
    prompt_version: Mapped[str | None] = mapped_column(Text)
    model_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    __table_args__ = (
        enum_check("message_type", E.MESSAGE_TYPES),
        enum_check("channel", E.CHANNELS),
        enum_check("status", E.OUTREACH_STATUSES),
        Index("ix_outreach_user_status", "user_id", "status"),
    )


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    job_id: Mapped[uuid.UUID] = fk("jobs.id", nullable=False)
    company_id: Mapped[uuid.UUID | None] = fk("companies.id", ondelete="RESTRICT")
    resume_id: Mapped[uuid.UUID | None] = fk("resumes.id", ondelete="SET NULL")
    resume_version_id: Mapped[uuid.UUID | None] = fk("resume_versions.id", ondelete="SET NULL")
    application_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    submission_method: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = tstz()
    confirmation_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    answers: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    follow_up_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    __table_args__ = (
        UniqueConstraint("user_id", "job_id"),
        enum_check("status", E.APPLICATION_STATUSES),
        CheckConstraint("status <> 'applied' OR confirmation_evidence IS NOT NULL", name="applied_needs_evidence"),
        Index("ix_applications_user_status", "user_id", "status"),
        Index("ix_applications_user_follow_up", "user_id", "follow_up_date"),
    )


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    application_id: Mapped[uuid.UUID] = fk("applications.id", nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = created_at_col()


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    reference_type: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    payload_preview: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    agent_run_id: Mapped[uuid.UUID | None] = fk("agent_runs.id", ondelete="SET NULL")
    requested_at: Mapped[datetime] = created_at_col()
    decided_at: Mapped[datetime | None] = tstz()
    expires_at: Mapped[datetime] = tstz(nullable=False)  # type: ignore[assignment]
    executed_at: Mapped[datetime | None] = tstz()
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    external_confirmation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    __table_args__ = (
        enum_check("action_type", E.APPROVAL_ACTIONS),
        enum_check("status", E.APPROVAL_STATUSES),
        Index("ix_approvals_reference", "reference_type", "reference_id"),
    )
