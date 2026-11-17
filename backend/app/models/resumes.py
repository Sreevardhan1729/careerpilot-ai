from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.models import enums as E
from app.models.base import Base, created_at_col, enum_check, fk, jsonb, updated_at_col, user_fk, uuid_pk

EMBEDDING_DIM = get_settings().embedding_dimensions


class Resume(Base):
    __tablename__ = "resumes"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    label: Mapped[str] = mapped_column(Text, nullable=False)
    label_suggested: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_versions.id", ondelete="SET NULL", use_alter=True, name="fk_resumes_current_version"),
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    __table_args__ = (
        enum_check("status", E.RESUME_STATUSES),
        Index("uq_resumes_one_default", "user_id", unique=True, postgresql_where=text("is_default")),
    )


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    resume_id: Mapped[uuid.UUID] = fk("resumes.id", nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[uuid.UUID | None] = fk("resume_versions.id", ondelete="SET NULL")
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    parsed_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    parsed_data_origin: Mapped[str | None] = mapped_column(Text)
    parse_method: Mapped[str | None] = mapped_column(Text)
    parse_warnings: Mapped[list[Any]] = jsonb("'[]'::jsonb")
    change_summary: Mapped[str | None] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(Text, nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL", use_alter=True, name="fk_resume_versions_job")
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approvals.id", ondelete="SET NULL", use_alter=True, name="fk_resume_versions_approval"),
    )
    created_at: Mapped[datetime] = created_at_col()
    __table_args__ = (
        UniqueConstraint("resume_id", "version_number"),
        enum_check("approval_status", E.RESUME_VERSION_APPROVAL),
        Index("ix_resume_versions_user_sha", "user_id", "file_sha256"),
    )


class ResumeChunk(Base):
    __tablename__ = "resume_chunks"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    resume_version_id: Mapped[uuid.UUID] = fk("resume_versions.id", nullable=False)
    section: Mapped[str] = mapped_column(Text, nullable=False)
    section_index: Mapped[int] = mapped_column(Integer, nullable=False)
    item_ref: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    __table_args__ = (
        enum_check("section", E.RESUME_SECTIONS),
        Index(
            "ix_resume_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
