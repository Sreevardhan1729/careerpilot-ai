from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SkillCategory = Literal[
    "programming_languages", "frameworks_libraries", "ai_ml", "llm_engineering", "retrieval_vector_db", "databases",
    "cloud", "devops_infra", "data_engineering", "system_design", "domain_knowledge", "soft_skills",
]


class LLMModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


Confidence = Field(default=0.5, ge=0, le=1)
