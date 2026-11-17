"""Regression tests for the whole-branch review findings (I-2, I-3, I-5..I-8, I-12, R-1, R-2)."""

from __future__ import annotations

import io
import json
import logging
from datetime import UTC, datetime

import pytest

from app.domain.claims import ClaimContext, check_claims
from app.domain.dedup import ExistingJob, ListingKey, find_duplicate, normalize_title
from app.domain.job_verify import verify_extraction
from app.domain.normalize import detect_employment_type, detect_work_mode
from app.schemas.llm.job import EvidencedStr, ExperienceRange, JobExtraction, SalaryInfo

NOW = datetime(2026, 11, 17, tzinfo=UTC)

# ---------------------------------------------------------------- I-2: values must match the *source* span
SRC = """Acme Corp is hiring
Role: Senior Backend Engineer
Experience: 3-5 years
Compensation: 15-20 LPA
Location: Pune (onsite)"""


def test_llm_values_that_differ_from_source_are_rejected_or_corrected():
    x = JobExtraction(
        company=EvidencedStr(value="Google", evidence="Acme Corp is hiring"),
        job_title=EvidencedStr(value="Staff ML Engineer", evidence="Role: Senior Backend Engineer"),
        experience=ExperienceRange(minimum_years=0, maximum_years=5, evidence="Experience: 0-5 years", explicit=True),
        salary=SalaryInfo(minimum=1_800_000, maximum=2_000_000, currency="INR", period="annual", source_type="jd",
                          evidence="Compensation: 18-20 LPA"),
    )
    v = verify_extraction(x, SRC, now=NOW)
    assert v.company_name is None and v.title is None
    assert (v.experience_min, v.experience_max) == (3, 5)  # re-derived from the source span, not the LLM's numbers
    assert (v.salary_min, v.salary_max) == (1_500_000, 2_000_000)


# ---------------------------------------------------------------- I-5: claim-check coverage
CTX = ClaimContext(evidence_texts=["Built a RAG assistant that cut support time by 30%"], candidate_skills={"Python", "RAG"},
                   has_relationship_history=False, recipient_verified_email=None, company_name="Acme AI",
                   job_title="AI Engineer", job_skills={"Python", "RAG", "Kubernetes"})


@pytest.mark.parametrize("body,code", [
    ("I cut costs by 40 percent and served 2 million users.", "unsupported_metric"),
    ("Hands-on with Terraform and Rust. Saved $40,000 a year.", "unsupported_skill"),
    ("I'm excited about the Staff Engineer opening at Google.", "wrong_job_reference"),
    ("I have shipped Kubernetes operators in Go while learning Rust.", "unsupported_skill"),
])
def test_claim_check_blocks_common_invented_claims(body, code):
    r = check_claims(body, None, None, CTX)
    assert not r.passed and code in {v["code"] for v in r.violations}, r.violations


def test_claim_check_still_allows_honest_messages():
    assert check_claims("Your team uses Kubernetes, which I'm keen to learn.", None, None, CTX).passed
    assert check_claims("I built a RAG assistant in Python that cut support time by 30% and I'd love to join the AI Engineer team at Acme AI.",
                        None, None, CTX).passed


# ---------------------------------------------------------------- I-7: negation and labelled lines
@pytest.mark.parametrize("text,mode", [
    ("This is an onsite role in Pune. Remote work is not available.", "onsite"),
    ("Work from office, 5 days. No remote.", "onsite"),
    ("Location: Bengaluru (onsite)\nYou will collaborate with remote teams.", "onsite"),
    ("Fully remote role.", "remote"),
])
def test_work_mode_handles_negation_and_noun_modifiers(text, mode):
    assert detect_work_mode(text)[0] == mode


def test_employment_type_ignores_internship_as_prior_experience():
    assert detect_employment_type("Full-time role. Prior internship experience is a plus.")[0] == "full_time"
    assert detect_employment_type("6-month internship")[0] == "internship"


# ---------------------------------------------------------------- I-8: dedup titles
def test_title_suffix_only_stripped_when_it_is_a_location():
    assert normalize_title("Software Engineer - Backend") != normalize_title("Software Engineer - Frontend")
    assert normalize_title("AI Engineer - Bengaluru") == "ai engineer"
    assert normalize_title("Software Engineer (Backend)") != normalize_title("Software Engineer (Frontend)")


def test_same_source_different_listing_ids_never_merge_on_title_rule():
    import uuid

    cid = uuid.uuid4()
    k = dict(canonical_url=None, application_url=None, description_hash=None, company_id=cid, normalized_title="software engineer",
             location_key="pune", posted_at=NOW, source_name="greenhouse")
    existing = ExistingJob(uuid.uuid4(), [ListingKey(source_listing_id="1", **k)])
    assert find_duplicate(ListingKey(source_listing_id="2", **k), [existing]) is None


# ---------------------------------------------------------------- I-12: log redaction
def test_tracebacks_and_stdlib_logs_are_redacted(capsys):
    from app.core.logging import configure_logging, get_logger

    configure_logging("INFO")
    try:
        raise ValueError("boom for jane@example.com Bearer abc.def.ghi")
    except ValueError:
        get_logger("t").exception("failed")
    logging.getLogger("httpx").warning("HTTP Request: GET https://serpapi.com/search.json?q=x&api_key=SECRET123")
    out = capsys.readouterr().out
    assert "jane@example.com" not in out and "abc.def.ghi" not in out and "SECRET123" not in out


# ---------------------------------------------------------------- R-1: NAT64 / IPv4-compatible SSRF
@pytest.mark.parametrize("ip", ["64:ff9b::a9fe:a9fe", "::7f00:1", "2002:a9fe:a9fe::1"])
async def test_embedded_ipv4_private_addresses_rejected(ip):
    from app.core.errors import UnsafeUrl
    from app.integrations.fetch import SafeFetcher

    async def resolver(host):
        return [ip]

    with pytest.raises(UnsafeUrl):
        await SafeFetcher(resolver=resolver, pin_ips=False, min_interval=0).validate_target("https://example.com/")


# ---------------------------------------------------------------- R-2: production requires an owner allowlist
def test_production_supabase_requires_allowlist_or_explicit_open_signup():
    from app.core.config import Settings

    base = dict(app_env="production", auth_mode="supabase", supabase_url="https://x.supabase.co",
                database_url="postgresql://u:p@h/db", llm_provider="none")
    with pytest.raises(ValueError, match="ALLOWED_USER_EMAILS"):
        Settings(**base)
    assert Settings(**base, allowed_user_emails="me@example.com").allowed_emails == ["me@example.com"]
    assert Settings(**base, allow_open_signup=True).allow_open_signup


_ = (io, json)
