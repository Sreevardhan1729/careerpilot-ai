from app.domain.claims import ClaimContext, check_claims
from app.heuristics.answers import draft_answers
from app.heuristics.improve import suggest_improvements
from app.heuristics.outreach import Fact, OutreachContext, write_drafts
from app.heuristics.people import EvidenceItem, classify_evidence
from app.heuristics.resume_parse import parse_resume
from app.models.enums import MESSAGE_TYPES
from app.schemas.llm.job import PosterInfo


def ev(id_, snippet, title=None, url="https://example.ai/team", source_type="search_result"):
    return EvidenceItem(id=id_, source_type=source_type, url=url, title=title, snippet=snippet)


def test_people_from_linkedin_search_title():
    items = [ev("e1", "Hiring for AI roles in Bengaluru.", title="Priya Sharma - Technical Recruiter - Example AI | LinkedIn",
                url="https://in.linkedin.com/in/priya-sharma-1")]
    out = classify_evidence(items, "Example AI", "example.ai", None).people
    assert len(out) == 1
    p = out[0]
    assert (p.name, p.designation, p.role_category) == ("Priya Sharma", "Technical Recruiter", "technical_recruiter")
    assert p.linkedin_url == "https://in.linkedin.com/in/priya-sharma-1"
    assert p.evidence_ids == ["e1"]


def test_people_from_company_page_are_verified():
    out = classify_evidence([ev("e2", "Rahul Mehta — Head of AI", source_type="company_page")], "Example AI", "example.ai", None).people
    assert out[0].role_category == "department_head" and out[0].current_company_verified


def test_people_skip_former_and_other_companies():
    items = [
        ev("e3", "x", title="Ana Gomez - Former Engineering Manager - Example AI | LinkedIn", url="https://linkedin.com/in/ana"),
        ev("e4", "x", title="John Doe - Recruiter - OtherCorp | LinkedIn", url="https://linkedin.com/in/john"),
    ]
    assert classify_evidence(items, "Example AI", "example.ai", None).people == []


def test_people_email_only_if_verbatim_and_on_company_domain():
    items = [ev("e5", "Anita Rao, Talent Acquisition at Example AI. Reach her at anita@example.ai or careers@gmail.com")]
    p = classify_evidence(items, "Example AI", "example.ai", None).people[0]
    assert p.public_email == "anita@example.ai"
    no_mail = classify_evidence([ev("e6", "Ravi Kumar, Engineering Manager at Example AI")], "Example AI", "example.ai", None)
    assert no_mail.people[0].public_email is None


def test_job_poster_from_post():
    poster = PosterInfo(name="Priya Sharma", headline="Technical Recruiter at Example AI", evidence="Priya Sharma")
    items = [ev("e7", "Priya Sharma\nTechnical Recruiter at Example AI", source_type="job_post", url="https://example.ai/job")]
    p = classify_evidence(items, "Example AI", "example.ai", poster).people[0]
    assert p.role_category == "job_poster" and p.current_company_verified


FACTS = [
    Fact("f1", "Built a RAG chatbot with LangChain and pgvector that reduced support tickets by 30%", "achievement"),
    Fact("f2", "Resume Matcher: resume ranking tool using embeddings and PostgreSQL", "project"),
]
OCTX = OutreachContext(
    candidate_name="Asha Verma", recipient_name="Priya Sharma", recipient_designation="Technical Recruiter",
    company="Example AI", job_title="AI Engineer", facts=FACTS, skills=["Python", "FastAPI", "RAG"],
    resume_label="GenAI / LLM Engineer", has_history=False, max_chars=200,
)


def test_outreach_all_types_pass_claim_check():
    drafts = write_drafts(list(MESSAGE_TYPES), OCTX).drafts
    assert {d.message_type for d in drafts} == set(MESSAGE_TYPES)
    ctx = ClaimContext(evidence_texts=[f.text for f in FACTS], candidate_skills={"Python", "FastAPI", "RAG", "LangChain", "pgvector",
                       "PostgreSQL", "Embeddings"}, has_relationship_history=False, recipient_verified_email=None,
                       company_name="Example AI", job_title="AI Engineer")
    for d in drafts:
        if d.message_type in ("linkedin_follow_up", "recruiter_follow_up", "thank_you"):
            continue  # follow-ups presuppose history; checked separately with history
        result = check_claims(d.body, d.subject, None, ctx)
        assert result.passed, (d.message_type, result.violations)


def test_connection_request_respects_char_limit_and_cites_facts():
    d = next(x for x in write_drafts(["linkedin_connection"], OCTX).drafts)
    assert len(d.body) <= 200
    emails = write_drafts(["recruiter_email"], OCTX).drafts[0]
    assert emails.subject and "f1" in emails.used_evidence_ids
    assert "attached" not in emails.body.lower()


def test_outreach_without_recipient_name():
    ctx = OutreachContext(**{**OCTX.__dict__, "recipient_name": None})
    assert write_drafts(["referral_request"], ctx).drafts[0].body.startswith("Hi there")


def test_answers_use_profile_and_leave_declarations_to_user():
    answers = draft_answers(
        ["Full name", "Email address", "Years of experience", "I certify that the information is true",
         "Why do you want to join us?", "Are you authorised to work in India?"],
        profile={"full_name": "Asha Verma", "preferred_email": "asha@example.com", "total_experience_months": 6},
        facts={},
    ).answers
    by_q = {a.question: a for a in answers}
    assert by_q["Full name"].answer == "Asha Verma" and by_q["Full name"].source_fact_ids == ["profile:full_name"]
    assert by_q["Years of experience"].answer == "0.5"
    for q in ("I certify that the information is true", "Why do you want to join us?", "Are you authorised to work in India?"):
        assert by_q[q].answer is None and by_q[q].needs_user_input


def test_improvements_never_invent_content():
    parsed = parse_resume(open(__file__.replace("unit/test_heuristics_agents.py", "fixtures/resume_asha.txt")).read())
    match = {"skill_breakdown": [
        {"skill": "FastAPI", "importance": "mandatory", "status": "strong"},
        {"skill": "SQL", "importance": "mandatory", "status": "listed_only"},
        {"skill": "Kubernetes", "importance": "preferred", "status": "no_evidence"},
    ]}
    imp = suggest_improvements(match, parsed, "AI Engineer")
    assert imp.missing_evidence == ["Kubernetes"]
    assert imp.skill_order[:2] == ["FastAPI", "SQL"]
    assert "Kubernetes" not in imp.skill_order
    assert all(c.after for c in imp.suggested_changes)
    assert imp.updated_summary is None


def test_outreach_picks_most_job_relevant_achievement():
    facts = [Fact("a1", "Won 1st place at Example Hackathon 2024", "achievement"),
             Fact("a2", "Built a RAG chatbot with LangChain that reduced support tickets by 30%", "achievement")]
    ctx = OutreachContext(**{**OCTX.__dict__, "facts": facts, "extra": {"job_skills": ["RAG", "LangChain", "Python"]}})
    d = write_drafts(["recruiter_email"], ctx).drafts[0]
    assert "30%" in d.body and d.used_evidence_ids[0] == "a2"
