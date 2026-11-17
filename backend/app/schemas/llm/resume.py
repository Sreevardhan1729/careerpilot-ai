"""ResumeParsed — output of prompt resume_parse (spec §4.2)."""

from __future__ import annotations

from pydantic import Field

from app.schemas.llm.common import LLMModel


class ResumeSkill(LLMModel):
    name: str = Field(max_length=80)
    section: str = "skills"  # skills | project | experience | summary
    evidence: str | None = Field(default=None, max_length=300)


class ResumeExperience(LLMModel):
    title: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    start: str | None = Field(default=None, max_length=40)
    end: str | None = Field(default=None, max_length=40)
    months: float | None = Field(default=None, ge=0, le=600)
    is_internship: bool = False
    bullets: list[str] = Field(default_factory=list, max_length=30)
    technologies: list[str] = Field(default_factory=list, max_length=40)
    domains: list[str] = Field(default_factory=list, max_length=10)


class ResumeProject(LLMModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=1500)
    bullets: list[str] = Field(default_factory=list, max_length=20)
    technologies: list[str] = Field(default_factory=list, max_length=40)
    domains: list[str] = Field(default_factory=list, max_length=10)
    links: list[str] = Field(default_factory=list, max_length=5)


class ResumeEducation(LLMModel):
    degree: str | None = Field(default=None, max_length=200)
    institution: str | None = Field(default=None, max_length=200)
    year: str | None = Field(default=None, max_length=20)
    details: str | None = Field(default=None, max_length=300)


class ResumeAchievement(LLMModel):
    text: str = Field(max_length=400)
    metric: str | None = Field(default=None, max_length=80)


class ResumeContact(LLMModel):
    name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=120)
    linkedin_url: str | None = Field(default=None, max_length=300)
    github_url: str | None = Field(default=None, max_length=300)
    portfolio_url: str | None = Field(default=None, max_length=300)


class ResumeParsed(LLMModel):
    contact: ResumeContact = Field(default_factory=ResumeContact)
    summary: str | None = Field(default=None, max_length=2000)
    skills: list[ResumeSkill] = Field(default_factory=list, max_length=150)
    experience: list[ResumeExperience] = Field(default_factory=list, max_length=20)
    projects: list[ResumeProject] = Field(default_factory=list, max_length=20)
    education: list[ResumeEducation] = Field(default_factory=list, max_length=10)
    certifications: list[str] = Field(default_factory=list, max_length=20)
    achievements: list[ResumeAchievement] = Field(default_factory=list, max_length=20)
    domains: list[str] = Field(default_factory=list, max_length=10)
    section_order: list[str] = Field(default_factory=list, max_length=12)
