"""JobExtraction — output of prompt jd_extraction (spec §4.1 / §13.1)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.llm.common import LLMModel, SkillCategory

Seniority = Literal["intern", "graduate", "junior", "mid", "senior", "lead", "principal", "unknown"]
WorkMode = Literal["remote", "hybrid", "onsite", "unknown"]
EmploymentType = Literal["full_time", "part_time", "contract", "internship", "temporary", "unknown"]


class EvidencedStr(LLMModel):
    value: str | None = Field(default=None, max_length=300)
    evidence: str | None = Field(default=None, max_length=500)
    explicit: bool = True
    confidence: float = Field(default=0.5, ge=0, le=1)


class ExperienceRange(LLMModel):
    minimum_years: float | None = Field(default=None, ge=0, le=40)
    maximum_years: float | None = Field(default=None, ge=0, le=40)
    evidence: str | None = Field(default=None, max_length=500)
    explicit: bool = False
    confidence: float = Field(default=0.5, ge=0, le=1)


class SalaryInfo(LLMModel):
    minimum: float | None = Field(default=None, ge=0)
    maximum: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    period: Literal["annual", "monthly", "hourly", "unknown"] | None = None
    source_type: Literal["jd", "source_website", "third_party_estimate", "not_disclosed"] = "not_disclosed"
    is_base: bool | None = None
    evidence: str | None = Field(default=None, max_length=500)
    confidence: float = Field(default=0.5, ge=0, le=1)


class ExtractedSkill(LLMModel):
    name: str = Field(max_length=80)
    category: SkillCategory = "domain_knowledge"
    importance: Literal["mandatory", "preferred", "mentioned"] = "mentioned"
    evidence: str | None = Field(default=None, max_length=500)
    confidence: float = Field(default=0.5, ge=0, le=1)


class PosterInfo(LLMModel):
    name: str | None = Field(default=None, max_length=120)
    headline: str | None = Field(default=None, max_length=200)
    evidence: str | None = Field(default=None, max_length=500)


class JobExtraction(LLMModel):
    company: EvidencedStr = Field(default_factory=EvidencedStr)
    job_title: EvidencedStr = Field(default_factory=EvidencedStr)
    department: EvidencedStr = Field(default_factory=EvidencedStr)
    seniority: Seniority = "unknown"
    experience: ExperienceRange = Field(default_factory=ExperienceRange)
    location: list[str] = Field(default_factory=list, max_length=10)
    location_evidence: str | None = Field(default=None, max_length=500)
    work_mode: WorkMode = "unknown"
    work_mode_evidence: str | None = Field(default=None, max_length=500)
    employment_type: EmploymentType = "unknown"
    employment_type_evidence: str | None = Field(default=None, max_length=500)
    salary: SalaryInfo = Field(default_factory=SalaryInfo)
    education: list[EvidencedStr] = Field(default_factory=list, max_length=10)
    mandatory_skills: list[ExtractedSkill] = Field(default_factory=list, max_length=60)
    preferred_skills: list[ExtractedSkill] = Field(default_factory=list, max_length=60)
    mentioned_skills: list[ExtractedSkill] = Field(default_factory=list, max_length=60)
    responsibilities: list[str] = Field(default_factory=list, max_length=40)
    technical_requirements: list[str] = Field(default_factory=list, max_length=40)
    soft_skills: list[str] = Field(default_factory=list, max_length=20)
    business_domain: EvidencedStr = Field(default_factory=EvidencedStr)
    application_deadline: EvidencedStr = Field(default_factory=EvidencedStr)
    application_url: str | None = Field(default=None, max_length=1000)
    posted_date: EvidencedStr = Field(default_factory=EvidencedStr)
    posted_by: PosterInfo | None = None
    key_hiring_expectations: str | None = Field(default=None, max_length=1200)
    missing_information: list[str] = Field(default_factory=list, max_length=30)
