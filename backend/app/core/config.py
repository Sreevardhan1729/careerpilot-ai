"""Application settings (pydantic-settings). Validated at startup; see docs/DEPLOYMENT.md §9."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _csv(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore", env_ignore_empty=True)

    # Core
    app_env: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"
    frontend_origin: str = "http://localhost:3000"
    backend_public_url: str = "http://localhost:8000"

    # Database
    database_url: str = ""
    test_database_url: str = ""
    db_pool_size: int = 5
    embedded_pg_dir: Path = BACKEND_DIR / ".pgdata"

    # Auth
    auth_mode: Literal["supabase", "dev"] = "dev"
    allowed_user_emails: str = ""
    allow_open_signup: bool = False  # production requires ALLOWED_USER_EMAILS unless this is explicitly true
    supabase_url: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_secret: SecretStr | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_secret_key: SecretStr | None = None
    dev_auth_secret: SecretStr = SecretStr("careerpilot-dev-only-secret-do-not-use-in-production")
    dev_auth_email: str = "owner@careerpilot.local"

    # Storage
    storage_backend: Literal["local", "supabase"] = "local"
    storage_bucket_resumes: str = "resumes"
    local_storage_dir: Path = BACKEND_DIR / ".storage"
    max_upload_mb: int = 5
    max_resume_pages: int = 20

    # LLM
    llm_provider: Literal["none", "nvidia", "fake"] = "none"
    nvidia_api_key: SecretStr | None = None
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = ""
    llm_temperature: float = 0.1
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 3
    llm_structured_output_mode: Literal["auto", "native", "prompt"] = "auto"
    llm_daily_call_budget: int = 200
    llm_max_concurrency: int = 2

    # Embeddings
    embedding_provider: Literal["hashing", "nvidia"] = "hashing"
    nvidia_embedding_model: str = ""
    embedding_dimensions: int = 1024

    # Tasks / scheduler
    task_runner_enabled: bool = True
    task_runner_concurrency: int = 2
    task_lease_seconds: int = 300
    task_poll_seconds: float = 1.0
    scheduler_token: SecretStr | None = None
    default_timezone: str = "Asia/Kolkata"
    checkpointer: Literal["memory", "postgres"] = "memory"

    # Fetching / discovery
    crawler_user_agent: str = "CareerPilotBot/1.0 (+https://github.com/careerpilot-ai)"
    fetch_timeout_seconds: float = 15.0
    fetch_max_bytes: int = 2_097_152
    blocked_fetch_hosts: str = "linkedin.com"
    playwright_allowed_domains: str = ""
    discovery_max_sources_per_run: int = 20
    discovery_max_listings_per_source: int = 100
    discovery_max_new_jobs_analyzed_per_run: int = 40
    people_discovery_max_jobs_per_run: int = 5

    # People search
    search_provider: Literal["none", "brave", "tavily", "google_cse", "serpapi"] = "none"
    search_api_key: SecretStr | None = None
    search_cse_id: str = ""
    search_daily_query_budget: int = 30

    # Gmail
    google_oauth_client_id: str = ""
    google_oauth_client_secret: SecretStr | None = None
    token_encryption_keys: SecretStr | None = None

    # Outreach / limits
    linkedin_connection_note_max_chars: int = 200
    rate_limit_default_per_minute: int = 120
    rate_limit_llm_enqueue_per_hour: int = 30

    @field_validator("embedded_pg_dir", "local_storage_dir", mode="before")
    @classmethod
    def _resolve_path(cls, v: object) -> Path:
        p = Path(str(v))
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()

    @model_validator(mode="after")
    def _guard_production(self) -> Settings:
        if self.app_env == "production":
            problems = []
            if self.auth_mode == "dev":
                problems.append("AUTH_MODE=dev is not allowed in production")
            if not self.database_url:
                problems.append("DATABASE_URL is required in production")
            if self.llm_provider == "fake":
                problems.append("LLM_PROVIDER=fake is not allowed in production")
            if self.auth_mode == "supabase" and not (self.supabase_jwks_url or self.supabase_jwt_secret or self.supabase_url):
                problems.append("SUPABASE_URL (or JWKS URL / JWT secret) is required")
            if self.auth_mode == "supabase" and not self.allowed_user_emails.strip() and not self.allow_open_signup:
                problems.append("Set ALLOWED_USER_EMAILS (single-owner deployment) or ALLOW_OPEN_SIGNUP=true; otherwise "
                                "anyone who can sign up could spend your LLM and search quota")
            if problems:
                raise ValueError("; ".join(problems))
        if self.llm_provider == "nvidia" and not (self.nvidia_api_key and self.nvidia_model):
            raise ValueError("LLM_PROVIDER=nvidia requires NVIDIA_API_KEY and NVIDIA_MODEL")
        if self.embedding_provider == "nvidia" and not (self.nvidia_api_key and self.nvidia_embedding_model):
            raise ValueError("EMBEDDING_PROVIDER=nvidia requires NVIDIA_API_KEY and NVIDIA_EMBEDDING_MODEL")
        return self

    # Derived helpers
    @property
    def allowed_emails(self) -> list[str]:
        return [e.lower() for e in _csv(self.allowed_user_emails)]

    @property
    def blocked_hosts(self) -> list[str]:
        hosts = {h.lower() for h in _csv(self.blocked_fetch_hosts)}
        hosts.add("linkedin.com")
        return sorted(hosts)

    @property
    def jwks_url(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return self.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        return ""

    @property
    def jwt_issuer(self) -> str:
        return self.supabase_url.rstrip("/") + "/auth/v1" if self.supabase_url else ""

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider != "none"

    @property
    def llm_model_label(self) -> str:
        if self.llm_provider == "nvidia":
            return self.nvidia_model
        if self.llm_provider == "fake":
            return "fake-llm"
        return "heuristic-v1"

    @property
    def embedding_model_label(self) -> str:
        if self.embedding_provider == "nvidia":
            return self.nvidia_embedding_model
        return f"hashing-v1-{self.embedding_dimensions}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
