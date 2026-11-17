from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
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


class CrawlSource(Base):
    __tablename__ = "crawl_sources"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    identifier: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[uuid.UUID | None] = fk("companies.id", ondelete="RESTRICT")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    config: Mapped[dict[str, Any]] = jsonb()
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("30"))
    last_crawled_at: Mapped[datetime | None] = tstz()
    last_status: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    terms_reviewed_at: Mapped[datetime | None] = tstz()
    terms_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "identifier"),
        enum_check("source_type", E.SOURCE_TYPES),
    )


class CrawlRun(Base):
    __tablename__ = "crawl_runs"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    crawl_source_id: Mapped[uuid.UUID] = fk("crawl_sources.id", nullable=False)
    task_id: Mapped[uuid.UUID | None] = fk("scheduled_tasks.id", ondelete="SET NULL")
    agent_run_id: Mapped[uuid.UUID | None] = fk("agent_runs.id", ondelete="SET NULL")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime | None] = tstz()
    completed_at: Mapped[datetime | None] = tstz()
    listings_found: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    listings_filtered_out: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    listings_new: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    listings_merged: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    http_requests: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    errors: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    created_at: Mapped[datetime] = created_at_col()
    __table_args__ = (
        enum_check("status", E.RUN_STATUSES),
        Index("ix_crawl_runs_source_created", "crawl_source_id", text("created_at DESC")),
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    workflow_name: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_version: Mapped[str] = mapped_column(Text, nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    parent_run_id: Mapped[uuid.UUID | None] = fk("agent_runs.id", ondelete="SET NULL")
    subject_type: Mapped[str | None] = mapped_column(Text)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    current_node: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = tstz()
    completed_at: Mapped[datetime | None] = tstz()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    __table_args__ = (
        enum_check("status", E.AGENT_RUN_STATUSES),
        Index("ix_agent_runs_user_created", "user_id", text("created_at DESC")),
        Index("ix_agent_runs_user_status", "user_id", "status"),
        Index("ix_agent_runs_subject", "subject_type", "subject_id"),
    )


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = user_fk(nullable=True)
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    payload: Mapped[dict[str, Any]] = jsonb()
    status: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("5"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    locked_by: Mapped[str | None] = mapped_column(Text)
    locked_until: Mapped[datetime | None] = tstz()
    last_error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    agent_run_id: Mapped[uuid.UUID | None] = fk("agent_runs.id", ondelete="SET NULL")
    completed_at: Mapped[datetime | None] = tstz()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    __table_args__ = (
        enum_check("task_type", E.TASK_TYPES),
        enum_check("status", E.TASK_STATUSES),
        Index("ix_tasks_claim", "status", "run_after", "priority", postgresql_where=text("status = 'queued'")),
        Index("ix_tasks_lease", "locked_until", postgresql_where=text("status = 'running'")),
    )


class LLMCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = user_fk(nullable=True)
    agent_run_id: Mapped[uuid.UUID | None] = fk("agent_runs.id", ondelete="SET NULL")
    node: Mapped[str | None] = mapped_column(Text)
    prompt_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()
    __table_args__ = (
        enum_check("status", E.LLM_CALL_STATUSES),
        Index("ix_llm_calls_cache", "input_hash", postgresql_where=text("status IN ('ok','repaired')")),
        Index("ix_llm_calls_user_created", "user_id", "created_at"),
    )


class OAuthConnection(Base):
    __tablename__ = "oauth_connections"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    account_email: Mapped[str | None] = mapped_column(Text)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    access_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    refresh_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_key_id: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = tstz()
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    __table_args__ = (UniqueConstraint("user_id", "provider"), enum_check("status", E.OAUTH_STATUSES))


class OAuthState(Base):
    """Single-use OAuth `state` + PKCE verifier (10 min TTL)."""

    __tablename__ = "oauth_states"
    state: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = user_fk()
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    code_verifier: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = tstz(nullable=False)  # type: ignore[assignment]
    created_at: Mapped[datetime] = created_at_col()


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = tstz()
    created_at: Mapped[datetime] = created_at_col()
    __table_args__ = (
        enum_check("type", E.NOTIFICATION_TYPES),
        Index("ix_notifications_inbox", "user_id", "read_at", text("created_at DESC")),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL")
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    request_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    user_id: Mapped[uuid.UUID] = user_fk()
    key: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[Any] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()
    expires_at: Mapped[datetime] = tstz(nullable=False)  # type: ignore[assignment]
    __table_args__ = (PrimaryKeyConstraint("user_id", "key"),)


class DeletedUser(Base):
    """Tombstone: a deleted account is never silently recreated by a still-valid token (system-only table)."""

    __tablename__ = "deleted_users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    deleted_at: Mapped[datetime] = created_at_col()
