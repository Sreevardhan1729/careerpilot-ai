import uuid
from datetime import UTC, datetime

import pytest

from app.domain.matching import (
    JobForMatch,
    JobSkillIn,
    ProfileSkills,
    ResumeForMatch,
    ResumeItem,
    load_scoring_config,
    rank_results,
    score_resume,
    skill_status,
)

CFG = load_scoring_config()


def vec(*xs):
    return [float(x) for x in xs]


def job(**kw):
    base = dict(
        skills=[
            JobSkillIn("Python", "mandatory"),
            JobSkillIn("FastAPI", "mandatory"),
            JobSkillIn("RAG", "mandatory"),
            JobSkillIn("LangGraph", "preferred"),
        ],
        focus_embedding=vec(1, 0, 0),
        responsibility_embeddings=[vec(1, 0, 0), vec(0, 1, 0)],
        experience_min=0,
        experience_max=2,
        domain="ai_ml",
    )
    base.update(kw)
    return JobForMatch(**base)


def project(ref="projects[0]", tech=("Python", "RAG", "Docker"), emb=vec(1, 0, 0), domains=("ai_ml",)):
    return ResumeItem(ref=ref, kind="project", title="RAG app", technologies=set(tech), text="", embedding=emb,
                      months=None, is_internship=False, domains=set(domains))


def resume(**kw):
    base = dict(
        resume_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        skills_section={"Python", "FastAPI", "RAG", "Docker"},
        evidenced_skills={"Python": ["projects[0]"], "RAG": ["projects[0]"]},
        projects=[project()],
        experience=[],
        chunks=[("c1", vec(1, 0, 0)), ("c2", vec(0, 1, 0))],
        domains={"ai_ml"},
    )
    base.update(kw)
    return ResumeForMatch(**base)


NO_PROFILE = ProfileSkills(has=set(), missing=set())


def test_skill_status_rules():
    r = resume()
    assert skill_status("Python", r, NO_PROFILE) == "strong"
    assert skill_status("FastAPI", r, NO_PROFILE) == "listed_only"
    assert skill_status("LangChain", resume(skills_section={"LangGraph"}, evidenced_skills={}), NO_PROFILE) == "related"
    assert skill_status("Java", r, ProfileSkills(has={"Java"}, missing=set())) == "profile_only"
    assert skill_status("Java", r, NO_PROFILE) == "no_evidence"
    assert skill_status("Java", r, ProfileSkills(has=set(), missing={"Java"})) == "confirmed_missing"
    # Docker (skills section) is the taxonomy parent of Kubernetes -> partial "related" credit
    assert skill_status("Kubernetes", r, NO_PROFILE) == "related"


def test_k_weights_mandatory_over_preferred():
    res = score_resume(job(), resume(), NO_PROFILE, CFG, "hashing")
    # mandatory: Python strong 1.0, FastAPI listed 0.6, RAG strong 1.0 -> 2.6/3 ; preferred LangGraph none -> 0
    assert res.components["K"].score == pytest.approx(100 * (0.75 * 2.6 / 3 + 0.25 * 0), abs=0.05)
    assert res.mandatory_coverage == pytest.approx(2.6 / 3, abs=1e-4)
    assert res.preferred_coverage == 0
    assert "FastAPI" in res.weak_skills
    assert [m["skill"] for m in res.missing_skills] == ["LangGraph"]
    assert res.missing_skills[0]["status"] == "no_evidence"


def test_k_only_mandatory_uses_full_weight():
    j = job(skills=[JobSkillIn("Python", "mandatory")])
    assert score_resume(j, resume(), NO_PROFILE, CFG, "hashing").components["K"].score == 100


def test_no_skills_renormalises_and_records_limitation():
    j = job(skills=[])
    res = score_resume(j, resume(), NO_PROFILE, CFG, "hashing")
    assert res.components["K"].score is None
    assert any("skills" in lim.lower() for lim in res.limitations)
    weights = {k: c.weight for k, c in res.components.items() if c.score is not None}
    expected = sum(res.components[k].score * w for k, w in weights.items()) / sum(weights.values())
    assert res.score == pytest.approx(round(expected, 1))


def test_synonym_duplicates_are_not_double_counted():
    j = job(skills=[JobSkillIn("Python", "mandatory"), JobSkillIn("Python", "mandatory"), JobSkillIn("Java", "mandatory")])
    res = score_resume(j, resume(), NO_PROFILE, CFG, "hashing")
    assert res.mandatory_coverage == pytest.approx(0.5)


def test_no_projects_gives_zero_p_with_limitation():
    res = score_resume(job(), resume(projects=[]), NO_PROFILE, CFG, "hashing")
    assert res.components["P"].score == 0
    assert any("project" in lim.lower() for lim in res.limitations)


def test_project_score_combines_tech_overlap_and_similarity():
    res = score_resume(job(), resume(), NO_PROFILE, CFG, "hashing")
    # tech: Python+RAG = 2 of min(4,6)=4 job skills -> 0.5 ; sem: cos=1 -> 1.0 ; 100*(0.6*0.5+0.4*1)=70
    assert res.components["P"].score == pytest.approx(70.0)
    assert res.relevant_projects[0]["ref"] == "projects[0]"


@pytest.mark.parametrize(
    "months,lo,hi,expected_years_fit",
    [(0, 0, 2, 100), (12, 2, None, 60), (60, 0, 2, 55), (None, None, None, 70)],
)
def test_experience_years_fit(months, lo, hi, expected_years_fit):
    exp = [] if not months else [ResumeItem(ref="experience[0]", kind="experience", title="Engineer", technologies=set(),
                                            text="", embedding=vec(1, 0, 0), months=months, is_internship=False, domains=set())]
    res = score_resume(job(experience_min=lo, experience_max=hi), resume(experience=exp), NO_PROFILE, CFG, "hashing")
    assert res.components["E_rel"].detail["years_fit"] == pytest.approx(expected_years_fit)


def test_internship_months_count_half():
    exp = [ResumeItem(ref="experience[0]", kind="experience", title="Intern", technologies=set(), text="",
                      embedding=vec(1, 0, 0), months=24, is_internship=True, domains=set())]
    res = score_resume(job(experience_min=1, experience_max=3), resume(experience=exp), NO_PROFILE, CFG, "hashing")
    assert res.components["E_rel"].detail["relevant_years"] == pytest.approx(1.0)


def test_responsibility_alignment_uses_best_chunk_per_responsibility():
    res = score_resume(job(), resume(chunks=[("c1", vec(1, 0, 0))]), NO_PROFILE, CFG, "hashing")
    # resp1 cos 1 -> 1.0 ; resp2 cos 0 -> 0 ; mean 0.5
    assert res.components["R"].score == pytest.approx(50.0)


@pytest.mark.parametrize(
    "job_domain,resume_domains,expected",
    [("ai_ml", {"ai_ml"}, 100), ("ai_ml", {"data_platforms"}, 60), ("ai_ml", set(), 30), (None, {"ai_ml"}, 50), ("fintech", {"gaming"}, 0)],
)
def test_domain_component(job_domain, resume_domains, expected):
    r = resume(domains=resume_domains, projects=[project(domains=())])
    assert score_resume(job(domain=job_domain), r, NO_PROFILE, CFG, "hashing").components["D"].score == expected


def test_scoring_is_deterministic():
    j, r = job(), resume()
    a = score_resume(j, r, NO_PROFILE, CFG, "hashing")
    b = score_resume(j, r, NO_PROFILE, CFG, "hashing")
    assert a == b


def test_rank_tie_breaks_on_k_then_mandatory_then_newer_version():
    j = job()
    older = resume(created_at=datetime(2025, 1, 1, tzinfo=UTC))
    newer = resume(created_at=datetime(2026, 6, 1, tzinfo=UTC), resume_id=older.resume_id)
    a = score_resume(j, older, NO_PROFILE, CFG, "hashing")
    b = score_resume(j, newer, NO_PROFILE, CFG, "hashing")
    ranked = rank_results([a, b])
    assert ranked[0].version_id == newer.version_id
    assert [r.rank for r in ranked] == [1, 2]
    assert ranked[0].is_best and not ranked[1].is_best


def test_component_explanations_are_templated_with_counts():
    res = score_resume(job(), resume(), NO_PROFILE, CFG, "hashing")
    assert "2/3 mandatory skills with strong evidence" in res.components["K"].explanation
    assert "FastAPI" in res.components["K"].explanation
