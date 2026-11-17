"""Application Preparation Graph (AGENT_DESIGN §10.2–10.3) with an interrupt() approval gate."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import select

from app import agents
from app.core.db import user_session
from app.core.errors import NotFound
from app.graphs.runtime import WorkflowContext, add_nodes, resume_graph, run_graph
from app.models import AgentRun, Application, CandidateProfileFact, Job, Resume, ResumeVersion
from app.services import applications as svc
from app.services import approvals as approvals_svc
from app.services import users as users_svc
from app.services.common import get_owned
from app.tasks.runner import TaskContext, handler, set_run_status


class State(TypedDict, total=False):
    application_id: str
    resume_version_id: str | None
    questions: list[str] | None
    approval_id: str | None
    result: dict[str, Any]


async def select_resume(state: State, ctx: WorkflowContext) -> dict:
    async with user_session(ctx.user_id) as s:
        app = await get_owned(s, Application, state["application_id"], ctx.user_id)
        if state.get("resume_version_id"):
            version = await get_owned(s, ResumeVersion, state["resume_version_id"], ctx.user_id)
        else:
            job = await s.get(Job, app.job_id)
            resume = await s.get(Resume, job.best_resume_id) if job.best_resume_id else (await s.execute(
                select(Resume).where(Resume.user_id == ctx.user_id, Resume.is_default))).scalars().first()
            if resume is None or resume.current_version_id is None:
                raise NotFound("Upload a resume before preparing an application.")
            version = await s.get(ResumeVersion, resume.current_version_id)
        app.resume_id, app.resume_version_id = version.resume_id, version.id
        await svc.set_status(s, app, "resume_selected", system=True)
        return {"resume_version_id": str(version.id), "_detail": {"resume_version": version.version_number}}


async def draft_answers(state: State, ctx: WorkflowContext) -> dict:
    async with user_session(ctx.user_id) as s:
        app = await get_owned(s, Application, state["application_id"], ctx.user_id)
        job = await s.get(Job, app.job_id)
        profile = await users_svc.get_profile(s, ctx.user_id)
        facts = (await s.execute(select(CandidateProfileFact).where(CandidateProfileFact.user_id == ctx.user_id,
                                                                    CandidateProfileFact.status == "confirmed"))).scalars().all()
        prof = {k: getattr(profile, k) for k in users_svc.PROFILE_FIELDS if k not in ("phone", "work_authorization")}
        prof["phone"] = profile.phone  # only used if a question asks for it
        summary = "\n".join(filter(None, [job.title, *(job.responsibilities or [])[:5]]))
    fact_texts = {f"fact:{f.id}": str(f.data.get("name") or f.data.get("title") or f.data.get("text") or "") for f in facts}
    answers, meta = await agents.draft_answers(state.get("questions") or svc.DEFAULT_QUESTIONS, profile=prof, facts=fact_texts,
                                               job_summary=summary, user_id=ctx.user_id, run_id=ctx.run_id)
    async with user_session(ctx.user_id) as s:
        app = await get_owned(s, Application, state["application_id"], ctx.user_id)
        app.answers = [a.model_dump() for a in answers.answers]
        await svc.set_status(s, app, "draft_prepared", system=True)
    return {"_detail": {"answers": len(answers.answers), "needs_input": sum(a.needs_user_input for a in answers.answers),
                        "model_id": meta.model_id}}


async def approval_gate(state: State, ctx: WorkflowContext) -> dict:
    async with user_session(ctx.user_id) as s:
        app = await get_owned(s, Application, state["application_id"], ctx.user_id)
        version = await s.get(ResumeVersion, app.resume_version_id)
        job = await s.get(Job, app.job_id)
        preview = {"job": {"id": str(job.id), "title": job.title}, "application_url": app.application_url,
                   "resume_version": {"id": str(version.id), "version_number": version.version_number,
                                      "filename": version.original_filename},
                   "answers": app.answers, "submission_method": "manual", "manual_steps": svc.manual_steps(app, version)}
        app.preview = preview
        # LangGraph re-runs this node from the top on resume, so reuse this run's approval instead of creating another.
        from app.models import Approval

        approval = (await s.execute(select(Approval).where(
            Approval.agent_run_id == ctx.run_id, Approval.reference_id == app.id,
            Approval.status.in_(("pending", "approved", "executed"))).order_by(Approval.created_at.desc()))).scalars().first()
        if approval is None:
            approval = await approvals_svc.create_pending(s, ctx.user_id, "submit_application", "application", app.id,
                                                          svc.submission_payload(app), preview, agent_run_id=ctx.run_id)
            await svc.set_status(s, app, "awaiting_approval", system=True)
        approval_id = str(approval.id)
    decision = interrupt({"approval_id": approval_id, "action_type": "submit_application"})
    return {"approval_id": decision.get("approval_id", approval_id)}


async def execute(state: State, ctx: WorkflowContext) -> dict:
    async with user_session(ctx.user_id) as s:
        app = await get_owned(s, Application, state["application_id"], ctx.user_id)
        result = await svc.execute_submission(s, ctx.user_id, app, uuid.UUID(state["approval_id"]))
    return {"result": result, "_detail": {"submission_method": result["submission_method"]}}


def build() -> StateGraph:
    g = StateGraph(State, context_schema=WorkflowContext)
    add_nodes(g, [("select_resume", select_resume), ("draft_answers", draft_answers)])
    add_nodes(g, [("approval_gate", approval_gate), ("execute", execute)], retry=False)
    g.add_edge(START, "select_resume")
    g.add_edge("select_resume", "draft_answers")
    g.add_edge("draft_answers", "approval_gate")
    g.add_edge("approval_gate", "execute")
    g.add_edge("execute", END)
    return g


@handler("prepare_application")
async def handle(ctx: TaskContext) -> dict:
    out = await run_graph(build(), dict(ctx.payload), WorkflowContext(ctx.user_id, ctx.agent_run_id, ctx))
    if out.get("__interrupt__"):
        return {"_status": "awaiting_approval", "application_id": ctx.payload["application_id"]}
    return {"application_id": ctx.payload["application_id"], **(out.get("result") or {})}


async def approve(user_id: uuid.UUID, application_id: uuid.UUID, approval_id: uuid.UUID, given_hash: str) -> dict[str, Any]:
    """Record the decision, then resume the paused graph (or execute directly if no checkpoint survived)."""
    async with user_session(user_id) as s:
        app = await get_owned(s, Application, application_id, user_id)
        approval = await approvals_svc.decide(s, user_id, approval_id, given_hash)
        if approval.reference_id != app.id:
            raise NotFound()
        if approval.status == "executed":
            return {"status": app.status, "submission_method": app.submission_method,
                    "manual_steps": (app.preview or {}).get("manual_steps", [])}
        run_id = approval.agent_run_id
    result = None
    if run_id:
        task_ctx = TaskContext(None, run_id, user_id, {})
        await set_run_status(run_id, "running")
        out = await resume_graph(build(), WorkflowContext(user_id, run_id, task_ctx), {"approval_id": str(approval_id)})
        if out is not None:
            result = out.get("result")
    if result is None:
        async with user_session(user_id) as s:
            app = await get_owned(s, Application, application_id, user_id)
            result = await svc.execute_submission(s, user_id, app, approval_id)
    if run_id:
        await set_run_status(run_id, "completed", output={"application_id": str(application_id), **result})
    return result


__all__ = ["AgentRun", "approve", "build", "handle"]
