"""Outputs of match explanation, people classification, outreach, improvement, answers, digest prompts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.llm.common import LLMModel

RoleCategory = Literal[
    "job_poster", "technical_recruiter", "talent_acquisition", "hr_recruiter", "hiring_manager", "engineering_manager",
    "team_lead", "department_head", "senior_engineer", "team_member", "talent_partner", "hr_business_partner",
    "alumni", "technical_leader", "other_employee",
]
MessageType = Literal[
    "linkedin_connection", "linkedin_follow_up", "referral_request", "hiring_manager_message", "recruiter_email",
    "recruiter_follow_up", "thank_you",
]


class BulletRewrite(LLMModel):
    before: str = Field(max_length=600)
    after: str = Field(max_length=600)
    evidence_refs: list[str] = Field(default_factory=list, max_length=10)
    reason: str | None = Field(default=None, max_length=300)


class MatchExplanation(LLMModel):
    explanation: str = Field(max_length=2000)
    suggested_summary: str | None = Field(default=None, max_length=1200)
    bullet_rewrites: list[BulletRewrite] = Field(default_factory=list, max_length=10)
    keywords_to_highlight: list[str] = Field(default_factory=list, max_length=20)


class ClassifiedPerson(LLMModel):
    name: str = Field(max_length=120)
    designation: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    role_category: RoleCategory = "other_employee"
    linkedin_url: str | None = Field(default=None, max_length=300)
    public_email: str | None = Field(default=None, max_length=200)
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)
    current_company_verified: bool = False
    relevance_reason: str | None = Field(default=None, max_length=400)
    confidence: float = Field(default=0.5, ge=0, le=1)


class PeopleClassification(LLMModel):
    people: list[ClassifiedPerson] = Field(default_factory=list, max_length=40)


class DraftMessage(LLMModel):
    message_type: MessageType
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(max_length=4000)
    used_evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class OutreachDrafts(LLMModel):
    drafts: list[DraftMessage] = Field(default_factory=list, max_length=10)


class SuggestedChange(LLMModel):
    section: str = Field(max_length=60)
    before: str | None = Field(default=None, max_length=800)
    after: str = Field(max_length=800)
    evidence_refs: list[str] = Field(default_factory=list, max_length=10)
    reason: str | None = Field(default=None, max_length=300)


class ResumeImprovement(LLMModel):
    updated_summary: str | None = Field(default=None, max_length=1200)
    suggested_changes: list[SuggestedChange] = Field(default_factory=list, max_length=20)
    keywords_to_highlight: list[str] = Field(default_factory=list, max_length=30)
    missing_evidence: list[str] = Field(default_factory=list, max_length=30)
    skill_order: list[str] = Field(default_factory=list, max_length=40)
    section_order: list[str] = Field(default_factory=list, max_length=12)


class DraftAnswer(LLMModel):
    question: str = Field(max_length=500)
    answer: str | None = Field(default=None, max_length=2000)
    source_fact_ids: list[str] = Field(default_factory=list, max_length=10)
    needs_user_input: bool = False


class ApplicationAnswers(LLMModel):
    answers: list[DraftAnswer] = Field(default_factory=list, max_length=40)


class DailyDigest(LLMModel):
    summary: str = Field(max_length=2000)
