"""Application tracking, status transitions, approval-gated submission (spec §4.7)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Duplicate, InvalidStateTransition
from app.models import Application, ApplicationEvent, Job, ResumeVersion
from app.services import approvals as approvals_svc
from app.services.common import audit, get_owned

PRE_SUBMIT = ("discovered", "analyzed", "interested", "resume_selected", "draft_prepared", "awaiting_approval", "ready_to_submit")
TRANSITIONS: dict[str, set[str]] = {
    "discovered": {"analyzed", "interested", "withdrawn"},
    "analyzed": {"interested", "withdrawn"},
    "interested": {"resume_selected", "draft_prepared", "withdrawn"},
    "resume_selected": {"draft_prepared", "interested", "withdrawn"},
    "draft_prepared": {"awaiting_approval", "resume_selected", "withdrawn"},
    "awaiting_approval": {"ready_to_submit", "draft_prepared", "withdrawn"},
    "ready_to_submit": {"draft_prepared", "withdrawn"},
    "applied": {"recruiter_contacted", "interview_scheduled", "rejected", "offer_received", "withdrawn"},
    "recruiter_contacted": {"interview_scheduled", "rejected", "offer_received", "withdrawn"},
    "interview_scheduled": {"rejected", "offer_received", "withdrawn", "recruiter_contacted"},
    "rejected": set(),
    "offer_received": {"withdrawn"},
    "withdrawn": {"interested"},
}
DEFAULT_QUESTIONS = [
    "Full name", "Email address", "Phone number", "Current location", "LinkedIn profile", "GitHub profile",
    "Years of experience", "Notice period", "Expected salary", "Why do you want to join us?",
    "Are you authorised to work in this country?", "I certify that the information provided is true",
]


async def event(s: AsyncSession, app: Application, event_type: str, from_status: str | None, to_status: str | None, **meta: Any) -> None:
    s.add(ApplicationEvent(user_id=app.user_id, application_id=app.id, event_type=event_type, from_status=from_status,
                           to_status=to_status, metadata_=meta))


async def set_status(s: AsyncSession, app: Application, new: str, *, system: bool = False) -> None:
    if new == app.status:
        return
    if new == "applied" and not system:
        raise InvalidStateTransition("Use 'confirm submission' with evidence to mark an application as applied.")
    if not system and new not in TRANSITIONS.get(app.status, set()):
        raise InvalidStateTransition(f"Cannot move from {app.status} to {new}.")
    old = app.status
    app.status = new
    await event(s, app, "status_changed", old, new)


async def get_or_create(s: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> Application:
    job = await get_owned(s, Job, job_id, user_id)
    app = (await s.execute(select(Application).where(Application.user_id == user_id, Application.job_id == job_id))).scalar_one_or_none()
    if app is None:
        app = Application(user_id=user_id, job_id=job_id, company_id=job.company_id, application_url=job.application_url,
                          status="interested")
        s.add(app)
        await s.flush()
        await event(s, app, "status_changed", None, "interested")
    elif app.status not in PRE_SUBMIT and app.status != "withdrawn":
        raise Duplicate("You already have an application for this job.", details={"application_id": str(app.id)})
    return app


def submission_payload(app: Application) -> dict[str, Any]:
    return {"application_id": str(app.id), "resume_version_id": str(app.resume_version_id) if app.resume_version_id else None,
            "answers": app.answers, "application_url": app.application_url}


def manual_steps(app: Application, version: ResumeVersion | None) -> list[str]:
    steps = [f"Open the application page: {app.application_url}" if app.application_url else "Open the company's application page"]
    if version:
        steps.append(f"Upload resume version {version.version_number} ({version.original_filename})")
    steps.append("Fill in the drafted answers; complete every item marked 'needs your input' yourself")
    steps.append("Review and accept any declarations yourself — they are never auto-accepted")
    steps.append("Submit, then record the confirmation (email or screenshot detail) here")
    return steps


async def execute_submission(s: AsyncSession, user_id: uuid.UUID, app: Application, approval_id: uuid.UUID) -> dict[str, Any]:
    """Consume the approval (hash recomputed from current state) and complete via the supported mechanism.

    No platform integration is supported in this build, so the result is always the manual-completion checklist.
    """
    approval = await approvals_svc.consume(s, user_id, approval_id, submission_payload(app))
    version = await s.get(ResumeVersion, app.resume_version_id) if app.resume_version_id else None
    steps = manual_steps(app, version)
    app.submission_method = "manual"
    app.preview = {**(app.preview or {}), "manual_steps": steps}
    await set_status(s, app, "ready_to_submit", system=True)
    await approvals_svc.record_result(s, approval, True, {"submission_method": "manual", "manual_steps": steps})
    await audit(s, user_id, "application.approved", "application", app.id)
    return {"status": app.status, "submission_method": "manual", "manual_steps": steps}


async def confirm_submission(s: AsyncSession, user_id: uuid.UUID, app: Application, evidence_type: str, detail: str) -> Application:
    if app.status not in ("interested", "resume_selected", "draft_prepared", "ready_to_submit"):
        raise InvalidStateTransition(f"Cannot record a submission from status {app.status}.")
    app.confirmation_evidence = {"type": evidence_type, "detail": detail, "captured_at": datetime.now(tz=UTC).isoformat()}
    app.submitted_at = datetime.now(tz=UTC)
    app.submission_method = app.submission_method or "manual"
    await set_status(s, app, "applied", system=True)
    await event(s, app, "submitted", None, "applied", evidence_type=evidence_type)
    await audit(s, user_id, "application.submitted", "application", app.id, evidence_type=evidence_type)
    return app
