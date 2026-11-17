from pathlib import Path

from app.heuristics.job_extract import extract_job
from app.heuristics.resume_parse import parse_resume

FIX = Path(__file__).resolve().parents[1] / "fixtures"
JD = (FIX / "jd_ai_engineer.txt").read_text()
POST = (FIX / "linkedin_post.txt").read_text()
RESUME = (FIX / "resume_asha.txt").read_text()


def names(skills):
    return {s.name for s in skills}


def test_job_core_fields():
    x = extract_job(JD)
    assert x.company.value == "Example AI Technologies"
    assert x.job_title.value == "AI Engineer"
    assert (x.experience.minimum_years, x.experience.maximum_years) == (0, 2)
    assert x.experience.explicit and "0-2 years" in x.experience.evidence
    assert x.location == ["Bengaluru, India"]
    assert x.work_mode == "hybrid"
    assert x.employment_type == "full_time"


def test_job_salary_from_jd_with_evidence():
    s = extract_job(JD).salary
    assert (s.minimum, s.maximum, s.currency, s.period, s.source_type) == (1_200_000, 1_800_000, "INR", "annual", "jd")
    assert "LPA" in s.evidence


def test_job_skill_importance_by_section():
    x = extract_job(JD)
    assert {"Python", "LLMs", "RAG", "FastAPI"} <= names(x.mandatory_skills)
    assert {"LangChain", "LangGraph", "Vector Databases", "Pinecone"} <= names(x.preferred_skills)
    assert not names(x.mandatory_skills) & names(x.preferred_skills)
    assert all(s.evidence for s in x.mandatory_skills)


def test_job_lists_and_misc():
    x = extract_job(JD)
    assert x.responsibilities[0] == "Build and deploy LLM applications using RAG pipelines"
    assert len(x.responsibilities) == 3
    assert any("Bachelor" in (e.value or "") for e in x.education)
    assert x.business_domain.value == "ai_ml"
    assert x.application_deadline.value == "30 November 2026"
    assert x.application_url == "https://example.com/careers/ai-engineer"
    assert "Salary" not in x.missing_information


def test_linkedin_post_poster_and_missing_info():
    x = extract_job(POST)
    assert x.posted_by and x.posted_by.name == "Priya Sharma"
    assert x.job_title.value == "ML Engineer"
    assert x.experience.minimum_years == 2 and x.experience.maximum_years is None
    assert x.work_mode == "remote"
    assert "PyTorch" in names(x.mandatory_skills)
    assert x.salary.source_type == "not_disclosed"
    assert "Salary" in x.missing_information


def test_no_invention_on_sparse_text():
    x = extract_job("We build things. Join us.")
    assert x.experience.minimum_years is None
    assert x.salary.source_type == "not_disclosed"
    assert x.mandatory_skills == []
    assert {"Job title", "Experience", "Salary", "Location"} <= set(x.missing_information)


def test_resume_contact_and_sections():
    r = parse_resume(RESUME)
    assert r.contact.name == "Asha Verma"
    assert r.contact.email == "asha@example.com"
    assert r.contact.linkedin_url == "https://www.linkedin.com/in/asha-verma/"
    assert r.contact.location == "Bengaluru"
    assert r.section_order == ["summary", "skills", "experience", "projects", "education", "certifications", "achievements"]
    assert r.summary.startswith("AI engineer focused")


def test_resume_skills_with_sections():
    r = parse_resume(RESUME)
    by_section = {}
    for s in r.skills:
        by_section.setdefault(s.name, set()).add(s.section)
    assert {"Python", "SQL", "FastAPI", "LangChain", "LangGraph", "Docker", "Git", "PostgreSQL", "pgvector"} <= set(by_section)
    assert "skills" in by_section["FastAPI"]
    assert "experience" in by_section["AWS"]
    assert "project" in by_section["XGBoost"]


def test_resume_experience_entry():
    r = parse_resume(RESUME)
    assert len(r.experience) == 1
    e = r.experience[0]
    assert (e.title, e.company) == ("AI Engineering Intern", "Example Labs")
    assert e.months == 6 and e.is_internship
    assert {"RAG", "LangChain", "pgvector", "FastAPI", "AWS"} <= set(e.technologies)
    assert len(e.bullets) == 2 and "30%" in e.bullets[0]


def test_resume_projects_education_certs():
    r = parse_resume(RESUME)
    assert [p.title for p in r.projects] == ["Resume Matcher", "Fintech Fraud Detector"]
    assert {"Python", "FastAPI", "PostgreSQL"} <= set(r.projects[0].technologies)
    assert "fintech" in r.projects[1].domains
    assert "B.Tech" in r.education[0].degree
    assert r.education[0].year == "2025"
    assert r.certifications == ["AWS Certified Cloud Practitioner"]
    assert r.achievements[0].text.startswith("Won 1st place")


PARAGRAPH = ("Acme AI Technologies is hiring an AI Engineer in Bengaluru, India (hybrid). Full time. Experience: 0-2 years. "
             "Responsibilities: build LLM-powered features and RAG pipelines, ship FastAPI services, evaluate prompts. "
             "Requirements: strong Python, FastAPI, LangChain, vector databases such as pgvector. Nice to have: Kubernetes, "
             "Docker, AWS. Salary: INR 12-18 LPA. Apply at https://boards.greenhouse.io/acme/jobs/123. "
             "Education: B.Tech in Computer Science or related field.")


def test_single_paragraph_jd_is_split_into_sections_with_sentence_evidence():
    from app.domain.job_verify import verify_extraction

    x = extract_job(PARAGRAPH)
    v = verify_extraction(x, PARAGRAPH)
    assert (v.salary_source_type, v.salary_min, v.salary_max) == ("jd", 1_200_000, 1_800_000)
    assert v.education == ["Education: B.Tech in Computer Science or related field."]
    by = {s["name"]: s["importance"] for s in v.skills}
    assert by["Python"] == "mandatory" and by["Kubernetes"] == "preferred"
    assert v.responsibilities and v.responsibilities[0].startswith("build LLM-powered features")
    from app.domain.skills import get_taxonomy

    tax = get_taxonomy()
    for s in v.skills:  # evidence is a short sentence that names the skill (or one of its aliases)
        assert len(s["evidence_text"]) <= 300
        assert s["name"] in {e.canonical for e in tax.skills_in(s["evidence_text"])}, s


def test_resume_header_drops_empty_brackets():
    from app.heuristics.resume_parse import parse_resume

    r = parse_resume("Jo Lee\nEXPERIENCE\nIntern | Example Labs () | Jan 2025 - Mar 2025\n- Built things\n")
    assert r.experience[0].company == "Example Labs"
