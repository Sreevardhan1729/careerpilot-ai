"""ORM models. Importing this package registers every table on Base.metadata."""

from app.models.base import Base
from app.models.identity import CandidateProfile, CandidateProfileFact, Company, SearchConfig, Skill, User
from app.models.jobs import Job, JobEvidence, JobSkill, JobSourceRecord, ResumeMatch
from app.models.ops import (
    AgentRun,
    AuditEvent,
    CrawlRun,
    CrawlSource,
    DeletedUser,
    IdempotencyKey,
    LLMCall,
    Notification,
    OAuthConnection,
    OAuthState,
    ScheduledTask,
)
from app.models.people import (
    Application,
    ApplicationEvent,
    Approval,
    JobPerson,
    Outreach,
    Person,
    PersonEvidence,
)
from app.models.resumes import Resume, ResumeChunk, ResumeVersion

__all__ = [
    "AgentRun", "Application", "ApplicationEvent", "Approval", "AuditEvent", "Base", "CandidateProfile",
    "CandidateProfileFact", "Company", "CrawlRun", "CrawlSource", "DeletedUser", "IdempotencyKey", "Job", "JobEvidence",
    "JobPerson", "JobSkill", "JobSourceRecord", "LLMCall", "Notification", "OAuthConnection", "OAuthState",
    "Outreach", "Person", "PersonEvidence", "Resume", "ResumeChunk", "ResumeMatch", "ResumeVersion",
    "ScheduledTask", "SearchConfig", "Skill", "User",
]

# Tables without user_id (no owner policy): shared reference data and system-only tables.
SHARED_TABLES = ("companies", "skills")
SYSTEM_TABLES = ("scheduled_tasks", "oauth_states", "deleted_users")
