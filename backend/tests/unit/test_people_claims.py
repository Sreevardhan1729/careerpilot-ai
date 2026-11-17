import pytest

from app.domain.claims import ClaimContext, check_claims
from app.domain.people_scoring import c_score, classify_role, d_score, people_score, s_score, t_score


def test_t_score_follows_spec_priority_order():
    assert t_score("job_poster") == 100
    assert t_score("technical_recruiter") == 94
    assert t_score("other_employee") == 16


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Technical Recruiter", "technical_recruiter"),
        ("Talent Acquisition Specialist", "talent_acquisition"),
        ("HR Recruiter", "hr_recruiter"),
        ("Engineering Manager, ML Platform", "engineering_manager"),
        ("Hiring Manager - AI", "hiring_manager"),
        ("Head of AI", "department_head"),
        ("Tech Lead", "team_lead"),
        ("Senior Software Engineer", "senior_engineer"),
        ("HR Business Partner", "hr_business_partner"),
        ("Talent Partner", "talent_partner"),
        ("CTO", "technical_leader"),
        ("Software Engineer", "team_member"),
        ("Office Manager", "other_employee"),
    ],
)
def test_classify_role(title, expected):
    assert classify_role(title) == expected


def test_department_and_association_and_source_scores():
    assert d_score("AI/ML", "AI/ML") == 100
    assert d_score("Data Science", "AI/ML") == 60
    assert d_score("Talent Acquisition", "AI/ML") == 60
    assert d_score(None, "AI/ML") == 40
    assert d_score("Finance", "AI/ML") == 10
    assert c_score("verified_current") == 100 and c_score("likely_current") == 70 and c_score("unverified") == 30
    assert s_score(["search_result", "company_page"]) == 100
    assert s_score(["search_result"], linkedin=True) == 60
    assert s_score(["search_result"]) == 50


def test_people_score_weights():
    assert people_score(100, 100, 100, 100) == 100
    assert people_score(94, 60, 70, 60) == pytest.approx(0.35 * 94 + 0.3 * 60 + 0.2 * 70 + 0.15 * 60)


CTX = ClaimContext(
    evidence_texts=["Built a RAG assistant that cut support time by 30%", "AI Engineer, 0-2 years"],
    candidate_skills={"Python", "RAG", "FastAPI"},
    has_relationship_history=False,
    recipient_verified_email=None,
    company_name="Example AI",
    job_title="AI Engineer",
)


def codes(result):
    return {v["code"] for v in result.violations}


def test_clean_message_passes():
    body = "Hi Priya, I built a RAG assistant with Python and FastAPI that cut support time by 30%. Interested in the AI Engineer role at Example AI."
    r = check_claims(body, None, None, CTX)
    assert r.passed, r.violations


def test_invented_metric_blocked():
    r = check_claims("I improved latency by 45% at my last job.", None, None, CTX)
    assert "unsupported_metric" in codes(r) and not r.passed


def test_first_person_unsupported_skill_blocked_but_interest_allowed():
    assert "unsupported_skill" in codes(check_claims("I have production experience with Kubernetes.", None, None, CTX))
    with_job = ClaimContext(**{**CTX.__dict__, "job_skills": {"Kubernetes"}})
    assert check_claims("Your team uses Kubernetes, which I'm keen to learn.", None, None, with_job).passed


def test_relationship_claims_need_history():
    r = check_claims("Great chatting with you last week, as we discussed.", None, None, CTX)
    assert "unsupported_relationship" in codes(r)
    ok = ClaimContext(**{**CTX.__dict__, "has_relationship_history": True})
    assert check_claims("Following up on my earlier message.", None, None, ok).passed


def test_unverified_recipient_email_blocked():
    assert "unverified_recipient" in codes(check_claims("Hello", "Hi", "guess@example.com", CTX))
    verified = ClaimContext(**{**CTX.__dict__, "recipient_verified_email": "jobs@example.com"})
    assert check_claims("Hello there, short note.", "Hi", "jobs@example.com", verified).passed


def test_attachment_claim_blocked():
    assert "attachment_claim" in codes(check_claims("Please find my resume attached.", None, None, CTX))


def test_length_and_generic_phrase_warnings_do_not_block():
    ctx = ClaimContext(**{**CTX.__dict__, "max_chars": 20})
    r = check_claims("I hope this message finds you well and so on.", None, None, ctx)
    assert r.passed
    assert {"too_long", "generic_phrase"} <= codes(r)


def test_skills_inside_job_title_or_company_are_not_claims():
    ctx = ClaimContext(**{**CTX.__dict__, "job_title": "AI Engineer"})
    assert check_claims("I'm interested in the AI Engineer role at Example AI.", None, None, ctx).passed
