"""API request/response models (docs/API_SPEC.md). The generated OpenAPI is the contract the frontend consumes."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from datetime import date as Date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models import enums as E


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------------------------------------ common
class Subject(Out):
    type: str
    id: uuid.UUID


class Accepted(Out):
    workflow_id: uuid.UUID
    status: str
    status_url: str
    subject: Subject | None = None


class Deduplicated(Out):
    job_id: uuid.UUID
    deduplicated: bool = True


class Page[T](Out):
    items: list[T]
    next_cursor: str | None = None


class OkOut(Out):
    ok: bool = True


# ------------------------------------------------------------------------------------------------ auth / me
class DevLoginIn(In):
    email: str = Field(min_length=3, max_length=200)


class TokenOut(Out):
    access_token: str
    token_type: str = "bearer"


class MeOut(Out):
    id: uuid.UUID
    email: str
    timezone: str
    auth_mode: str
    llm: dict[str, Any]
    embeddings: dict[str, Any]
    integrations: dict[str, Any]
    profile_complete: bool


# ------------------------------------------------------------------------------------------------ profile
class SalaryPreference(BaseModel):
    minimum: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default="INR", max_length=3)
    period: Literal["annual", "monthly", "hourly"] = "annual"


class ProfileFields(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    preferred_email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    current_location: str | None = Field(default=None, max_length=120)
    preferred_locations: list[str] | None = None
    preferred_work_modes: list[Literal["remote", "hybrid", "onsite"]] | None = None
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)
    total_experience_months: int | None = Field(default=None, ge=0, le=600)
    preferred_roles: list[str] | None = None
    preferred_industries: list[str] | None = None
    portfolio_url: str | None = Field(default=None, max_length=300)
    github_url: str | None = Field(default=None, max_length=300)
    linkedin_url: str | None = Field(default=None, max_length=300)
    salary_preference: SalaryPreference | None = None
    employment_type_preferences: list[Literal["full_time", "part_time", "contract", "internship", "temporary"]] | None = None
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    work_authorization: str | None = Field(default=None, max_length=300)


class ProfileUpdate(ProfileFields, In):
    pass


class ProfileOut(ProfileFields, Out):
    id: uuid.UUID
    field_sources: dict[str, str] = {}
    updated_at: datetime


class FactCreate(In):
    fact_type: Literal["education", "project", "experience", "certification", "achievement", "skill"]
    data: dict[str, Any]


class FactUpdate(In):
    data: dict[str, Any] | None = None
    status: Literal["confirmed", "suggested", "rejected"] | None = None


class FactOut(Out):
    id: uuid.UUID
    fact_type: str
    data: dict[str, Any]
    source: str
    status: str
    source_resume_version_id: uuid.UUID | None
    confirmed_at: datetime | None
    created_at: datetime


class SearchConfigIn(In):
    name: str = Field(default="Default", max_length=80)
    role_filters: list[str] = []
    experience_bands: list[dict[str, Any]] = []
    locations: list[str] = []
    work_modes: list[str] = []
    skills: list[str] = []
    salary_minimum: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    is_active: bool = True


class SearchConfigPatch(In):
    name: str | None = None
    role_filters: list[str] | None = None
    experience_bands: list[dict[str, Any]] | None = None
    locations: list[str] | None = None
    work_modes: list[str] | None = None
    skills: list[str] | None = None
    salary_minimum: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    is_active: bool | None = None


class SearchConfigOut(Out):
    id: uuid.UUID
    name: str
    role_filters: list[str]
    experience_bands: list[dict[str, Any]]
    locations: list[str]
    work_modes: list[str]
    skills: list[str]
    salary_minimum: float | None
    salary_currency: str | None
    salary_period: str | None
    is_active: bool


class SettingsIn(In):
    timezone: str | None = Field(default=None, max_length=60)
    scheduler_local_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    auto_generate_outreach: bool | None = None
    notifications: dict[str, Any] | None = None


class SettingsOut(Out):
    timezone: str
    scheduler_local_time: str
    auto_generate_outreach: bool
    notifications: dict[str, Any]
    llm: dict[str, Any]
    embeddings: dict[str, Any]
    search_provider: str
    scheduler: dict[str, Any]


# ------------------------------------------------------------------------------------------------ jobs
class ManualFields(In):
    company: str | None = Field(default=None, max_length=200)
    job_title: str = Field(max_length=200)
    location: str | None = Field(default=None, max_length=200)
    work_mode: str | None = None
    employment_type: str | None = None
    experience: str | None = Field(default=None, max_length=120)
    salary: str | None = Field(default=None, max_length=120)
    application_url: str | None = Field(default=None, max_length=1000)
    requirements: list[str] | str | None = None
    nice_to_have: list[str] | str | None = None
    responsibilities: list[str] | str | None = None
    description: str | None = Field(default=None, max_length=30000)


class AnalyzeTextIn(In):
    input_type: Literal["text", "manual"] = "text"
    text: str | None = Field(default=None, max_length=60000)
    source_url: str | None = Field(default=None, max_length=2000)
    company_hint: str | None = Field(default=None, max_length=200)
    manual_fields: ManualFields | None = None


class AnalyzeUrlIn(In):
    url: HttpUrl


class CompanyOut(Out):
    id: uuid.UUID
    name: str
    domain: str | None = None


class ExperienceOut(Out):
    min_years: float | None
    max_years: float | None
    explicit: bool
    evidence: str | None = None


class SalaryOut(Out):
    minimum: float | None = None
    maximum: float | None = None
    currency: str | None = None
    period: str | None = None
    source_type: str
    is_base: bool | None = None
    source_url: str | None = None


class ResumeRef(Out):
    id: uuid.UUID
    label: str


class JobListItem(Out):
    id: uuid.UUID
    title: str | None
    company: CompanyOut | None
    locations: list[dict[str, Any]]
    work_mode: str
    employment_type: str
    seniority: str
    experience: ExperienceOut
    salary: SalaryOut
    job_score: float | None
    priority: str | None
    match_score: float | None
    best_resume: ResumeRef | None
    posted_at: datetime | None
    created_at: datetime
    sources: list[str]
    status: str
    saved: bool
    has_application: bool
    input_type: str


class JobSkillOut(Out):
    name: str
    category: str
    importance: str
    evidence_text: str | None
    evidence_verified: bool
    confidence: float | None
    skill_id: uuid.UUID | None


class JobEvidenceOut(Out):
    field: str
    value: Any
    evidence_text: str | None
    explicit: bool
    verified: bool
    confidence: float | None


class SourceRecordOut(Out):
    source_name: str
    source_url: str | None
    collected_at: datetime
    dedup_signal: str


class MatchSummary(Out):
    resume_id: uuid.UUID
    label: str
    score: float
    rank: int


class RunRef(Out):
    workflow_id: uuid.UUID
    workflow_name: str
    status: str


class JobDetail(JobListItem):
    department: str | None
    description_text: str
    responsibilities: list[str]
    technical_requirements: list[str]
    soft_skills: list[str]
    education: list[str]
    business_domain: str | None
    application_deadline: date | None
    application_url: str | None
    source_url: str | None
    posted_by: dict[str, Any] | None
    hiring_expectations: str | None
    missing_information: list[str]
    skills: list[JobSkillOut]
    evidence: list[JobEvidenceOut]
    source_records: list[SourceRecordOut]
    job_score_breakdown: dict[str, Any] | None
    match_summary: list[MatchSummary]
    latest_run: RunRef | None
    analysis_method: str | None
    model_id: str | None


class JobPatch(In):
    saved: bool | None = None
    archived: bool | None = None
    application_url: str | None = Field(default=None, max_length=1000)


class ComponentOut(Out):
    score: float | None
    weight: float
    explanation: str
    evidence_refs: list[str] = []
    detail: dict[str, Any] = {}


class MatchItem(Out):
    rank: int
    resume: dict[str, Any]
    score: float
    components: dict[str, ComponentOut]
    mandatory_coverage: float | None
    preferred_coverage: float | None
    skill_breakdown: list[dict[str, Any]]
    missing_skills: list[dict[str, Any]]
    weakly_highlighted_skills: list[str]
    relevant_projects: list[dict[str, Any]]
    relevant_experience: list[dict[str, Any]]
    suggestions: dict[str, Any] | None
    explanation: str | None
    limitations: list[Any]
    is_best: bool


class MatchesOut(Out):
    job_id: uuid.UUID
    scoring_config_version: str
    best_resume_id: uuid.UUID | None
    items: list[MatchItem]
    evidence: dict[str, str] = {}
    disclaimer: str = "Match scores rank your resumes for this job. They are not a probability of being shortlisted."


# ------------------------------------------------------------------------------------------------ resumes
class ResumeVersionOut(Out):
    id: uuid.UUID
    version_number: int
    parent_version_id: uuid.UUID | None
    approval_status: str
    original_filename: str
    mime_type: str
    page_count: int | None
    change_summary: str | None
    job_id: uuid.UUID | None
    parse_method: str | None
    parse_warnings: list[Any]
    created_at: datetime


class ResumeOut(Out):
    id: uuid.UUID
    label: str
    label_suggested: str | None
    category: str | None
    is_default: bool
    status: str
    current_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ResumeDetail(ResumeOut):
    current_version: ResumeVersionOut | None
    parsed_data: dict[str, Any] | None
    versions: list[ResumeVersionOut]
    latest_run: RunRef | None


class ResumePatch(In):
    label: str | None = Field(default=None, max_length=80)
    category: str | None = Field(default=None, max_length=80)
    is_default: bool | None = None


class VersionChange(In):
    section: str = Field(default="experience", max_length=40)
    before: str = Field(min_length=1, max_length=1200)
    after: str = Field(min_length=1, max_length=1200)
    evidence_refs: list[str] = []


class TailoredVersionIn(In):
    job_id: uuid.UUID | None = None
    base_version_id: uuid.UUID | None = None
    changes: list[VersionChange] = Field(default_factory=list, max_length=30)
    skill_order: list[str] | None = Field(default=None, max_length=80)
    change_summary: str | None = Field(default=None, max_length=500)


class TailoredVersionOut(Out):
    version: ResumeVersionOut
    approval: ApprovalOut


class ActivationOut(Out):
    status: str
    current_version_id: uuid.UUID


class DownloadOut(Out):
    url: str | None
    filename: str


# ------------------------------------------------------------------------------------------------ runs
class AgentRunOut(Out):
    id: uuid.UUID
    workflow_name: str
    status: str
    current_node: str | None
    progress: list[dict[str, Any]]
    subject: Subject | None
    output: dict[str, Any] | None
    error: dict[str, Any] | None
    approval: dict[str, Any] | None = None
    children: list[RunRef] = []
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


# ------------------------------------------------------------------------------------------------ people
class PersonIn(In):
    name: str = Field(min_length=2, max_length=120)
    linkedin_url: str | None = Field(default=None, max_length=300)
    designation: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    job_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class PersonPatch(In):
    contact_status: Literal["new", "contacted", "responded", "do_not_contact"] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    designation: str | None = Field(default=None, max_length=200)


class EvidenceItemOut(Out):
    id: uuid.UUID
    source_type: str
    source_url: str
    source_title: str | None
    snippet: str
    retrieved_at: datetime


class PersonOut(Out):
    id: uuid.UUID
    name: str
    designation: str | None
    department: str | None
    company: CompanyOut | None = None
    linkedin_url: str | None
    public_email: str | None
    association_status: str
    contact_status: str
    added_by: str
    notes: str | None
    first_discovered_at: datetime
    last_verified_at: datetime | None


class JobPersonOut(Out):
    rank: int
    person_id: uuid.UUID
    name: str
    designation: str | None
    department: str | None
    role_category: str
    linkedin_url: str | None
    public_email: str | None
    association_status: str
    relevance_score: float
    components: dict[str, Any]
    relevance_reason: str
    confidence: float | None
    evidence: list[EvidenceItemOut]
    contact_status: str
    outreach_count: int


class JobPeopleOut(Out):
    job_id: uuid.UUID
    company: CompanyOut | None
    verified_count: int
    unavailable_count: int
    target: int = 15
    coverage_note: str | None
    items: list[JobPersonOut]
    latest_run: RunRef | None


# ------------------------------------------------------------------------------------------------ outreach / approvals
MessageType = Literal[E.MESSAGE_TYPES]  # type: ignore[valid-type]


class OutreachGenerateIn(In):
    job_id: uuid.UUID
    person_ids: list[uuid.UUID] | None = None
    message_types: list[Literal["linkedin_connection", "linkedin_follow_up", "referral_request", "hiring_manager_message",
                                "recruiter_email", "recruiter_follow_up", "thank_you"]] = ["linkedin_connection", "recruiter_email"]
    resume_id: uuid.UUID | None = None


class OutreachDraftIn(In):
    job_id: uuid.UUID | None = None
    person_id: uuid.UUID | None = None
    message_type: Literal["linkedin_connection", "linkedin_follow_up", "referral_request", "hiring_manager_message",
                          "recruiter_email", "recruiter_follow_up", "thank_you"]
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1, max_length=4000)


class OutreachPatch(In):
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=4000)
    discard: bool | None = None


class OutreachOut(Out):
    id: uuid.UUID
    job_id: uuid.UUID | None
    person_id: uuid.UUID | None
    message_type: str
    channel: str
    recipient_name: str | None
    recipient_email: str | None
    subject: str | None
    body: str
    recommended_resume_id: uuid.UUID | None
    personalization_evidence: list[Any]
    claim_check: dict[str, Any]
    requires_review: bool
    status: str
    gmail_draft_id: str | None
    sent_at: datetime | None
    model_id: str | None
    prompt_version: str | None
    created_at: datetime
    updated_at: datetime


class ApprovalOut(Out):
    approval_id: uuid.UUID
    action_type: str
    status: str
    expires_at: datetime
    payload_hash: str
    payload_preview: dict[str, Any]
    reference_type: str
    reference_id: uuid.UUID


class ApproveIn(In):
    approval_id: uuid.UUID
    payload_hash: str
    confirm: Literal[True]


# ------------------------------------------------------------------------------------------------ applications
class PrepareIn(In):
    job_id: uuid.UUID
    resume_version_id: uuid.UUID | None = None
    questions: list[str] | None = None


class ApplicationPatch(In):
    status: Literal[E.APPLICATION_STATUSES] | None = None  # type: ignore[valid-type]
    notes: str | None = Field(default=None, max_length=5000)
    follow_up_date: date | None = None


class ConfirmSubmissionIn(In):
    evidence_type: Literal["external_receipt", "user_attestation"]
    detail: str = Field(min_length=3, max_length=2000)


class ApplicationOut(Out):
    id: uuid.UUID
    job_id: uuid.UUID
    job_title: str | None = None
    company_name: str | None = None
    resume_id: uuid.UUID | None
    resume_version_id: uuid.UUID | None
    application_url: str | None
    status: str
    submission_method: str | None
    submitted_at: datetime | None
    confirmation_evidence: dict[str, Any] | None
    answers: list[Any]
    preview: dict[str, Any] | None
    follow_up_date: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------------------------------------ sources / scheduler
class SourceIn(In):
    source_type: Literal["greenhouse", "lever", "ashby", "rss", "career_page"]
    identifier: str = Field(min_length=1, max_length=500)
    name: str | None = Field(default=None, max_length=120)
    company_name: str | None = Field(default=None, max_length=200)
    enabled: bool = True
    config: dict[str, Any] = {}
    terms_note: str | None = Field(default=None, max_length=500)


class SourcePatch(In):
    enabled: bool | None = None
    name: str | None = None
    config: dict[str, Any] | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=120)
    terms_note: str | None = None


class SourceOut(Out):
    id: uuid.UUID
    source_type: str
    name: str
    identifier: str
    enabled: bool
    config: dict[str, Any]
    rate_limit_per_minute: int
    last_crawled_at: datetime | None
    last_status: str | None
    last_error: str | None
    consecutive_failures: int
    terms_reviewed_at: datetime | None
    terms_note: str | None


class DiscoverIn(In):
    source_ids: list[uuid.UUID] | None = None


class SchedulerRunIn(In):
    date: Date | None = None


class NotificationOut(Out):
    id: uuid.UUID
    type: str
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime


class AccountDeleteIn(In):
    confirm: Literal["DELETE"]


TailoredVersionOut.model_rebuild()
