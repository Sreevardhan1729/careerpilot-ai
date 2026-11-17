"""Allowed values for text+CHECK enum columns (docs/DATABASE_SCHEMA.md §1). Single source for DB and schemas."""

from __future__ import annotations

FACT_TYPES = ("education", "project", "experience", "certification", "achievement", "skill")
FACT_SOURCES = ("user_entered", "resume_derived", "inferred")
FACT_STATUSES = ("confirmed", "suggested", "rejected")

SKILL_CATEGORIES = (
    "programming_languages",
    "frameworks_libraries",
    "ai_ml",
    "llm_engineering",
    "retrieval_vector_db",
    "databases",
    "cloud",
    "devops_infra",
    "data_engineering",
    "system_design",
    "domain_knowledge",
    "soft_skills",
)

RESUME_STATUSES = ("uploaded", "parsing", "parsed", "needs_review", "failed")
RESUME_VERSION_APPROVAL = ("original", "draft", "pending_approval", "approved", "rejected")
RESUME_SECTIONS = ("summary", "skills", "experience", "project", "education", "certification", "achievement", "other")

JOB_INPUT_TYPES = ("text", "url", "pdf", "docx", "manual", "discovery")
SENIORITY = ("intern", "graduate", "junior", "mid", "senior", "lead", "principal", "unknown")
WORK_MODES = ("remote", "hybrid", "onsite", "unknown")
EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "internship", "temporary", "unknown")
SALARY_PERIODS = ("annual", "monthly", "hourly", "unknown")
SALARY_SOURCE_TYPES = ("jd", "source_website", "third_party_estimate", "not_disclosed")
JOB_STATUSES = ("queued", "analyzing", "analyzed", "failed", "archived")
PRIORITIES = ("excellent", "strong", "moderate", "low")
SKILL_IMPORTANCE = ("mandatory", "preferred", "mentioned")
DEDUP_SIGNALS = ("new", "canonical_url", "source_listing_id", "application_url", "content_hash", "company_title_location", "near_duplicate")

ASSOCIATION_STATUSES = ("verified_current", "likely_current", "unverified")
CONTACT_STATUSES = ("new", "contacted", "responded", "do_not_contact")
PEOPLE_SOURCE_TYPES = ("company_page", "job_post", "user_provided", "search_result", "conference", "blog", "directory")
# Spec §4.3 priority order — index+1 is the rank used by People Score T.
ROLE_CATEGORIES = (
    "job_poster",
    "technical_recruiter",
    "talent_acquisition",
    "hr_recruiter",
    "hiring_manager",
    "engineering_manager",
    "team_lead",
    "department_head",
    "senior_engineer",
    "team_member",
    "talent_partner",
    "hr_business_partner",
    "alumni",
    "technical_leader",
    "other_employee",
)

MESSAGE_TYPES = (
    "linkedin_connection",
    "linkedin_follow_up",
    "referral_request",
    "hiring_manager_message",
    "recruiter_email",
    "recruiter_follow_up",
    "thank_you",
)
EMAIL_MESSAGE_TYPES = ("recruiter_email", "recruiter_follow_up", "thank_you")
CHANNELS = ("linkedin", "email")
OUTREACH_STATUSES = ("draft", "edited", "approved", "gmail_draft_created", "sent", "manually_sent", "discarded")

APPLICATION_STATUSES = (
    "discovered",
    "analyzed",
    "interested",
    "resume_selected",
    "draft_prepared",
    "awaiting_approval",
    "ready_to_submit",
    "applied",
    "recruiter_contacted",
    "interview_scheduled",
    "rejected",
    "offer_received",
    "withdrawn",
)
SUBMISSION_METHODS = ("supported_integration", "manual")

APPROVAL_ACTIONS = ("send_email", "submit_application", "activate_resume_version", "share_personal_info", "external_action")
APPROVAL_STATUSES = ("pending", "approved", "rejected", "expired", "executed", "failed")

SOURCE_TYPES = ("greenhouse", "lever", "ashby", "rss", "career_page", "manual")
RUN_STATUSES = ("queued", "running", "partially_completed", "completed", "failed", "cancelled")
TASK_STATUSES = ("queued", "running", "partially_completed", "completed", "failed", "cancelled", "dead")
AGENT_RUN_STATUSES = ("queued", "running", "awaiting_approval", "partially_completed", "completed", "failed", "cancelled")
TERMINAL_RUN_STATUSES = ("partially_completed", "completed", "failed", "cancelled")
TASK_TYPES = (
    "parse_resume",
    "analyze_job",
    "match_resumes",
    "discover_jobs",
    "discover_people",
    "generate_outreach",
    "optimize_resume",
    "prepare_application",
    "daily_pipeline",
    "export_account",
)
LLM_CALL_STATUSES = ("ok", "repaired", "invalid_output", "error", "cache_hit")
NOTIFICATION_TYPES = ("daily_summary", "run_failed", "approval_needed", "source_disabled", "reconnect_google", "quota_exhausted")
OAUTH_STATUSES = ("active", "expired", "revoked", "error")


def check_in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"
