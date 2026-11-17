from datetime import UTC, datetime

import pytest

from app.domain.evidence import importance_cue, numbers_in, verify_snippet
from app.domain.normalize import (
    annualize,
    detect_employment_type,
    detect_seniority,
    detect_work_mode,
    find_locations,
    normalize_location,
    parse_date,
    parse_experience,
    parse_salary,
)

SOURCE = """Senior-ish AI Engineer – Bengaluru
We need 0–2 years’ experience building LLM apps.
Requirements: Python, FastAPI, RAG (must have).
Nice to have: LangGraph.
Compensation: ₹12 - 18 LPA. Hybrid (3 days in office)."""


def test_verify_snippet_exact_and_normalised():
    assert verify_snippet("0-2 years' experience", SOURCE)
    assert verify_snippet("Compensation: ₹12 - 18 LPA", SOURCE)


def test_verify_snippet_rejects_invented_text_and_tiny_snippets():
    assert not verify_snippet("5+ years of Kubernetes", SOURCE)
    assert not verify_snippet("AI", SOURCE)
    assert not verify_snippet("", SOURCE)


def test_verify_snippet_tolerates_small_ocr_differences():
    assert verify_snippet("We need 0-2 years experience building LLM apps", SOURCE)


def test_numbers_in_handles_ranges_and_decimals():
    assert numbers_in("0-2 years, 3.5 LPA, 1,20,000") == [0.0, 2.0, 3.5, 120000.0]


@pytest.mark.parametrize(
    "context,expected",
    [
        ("Requirements: Python (must have)", "mandatory"),
        ("Strong experience in FastAPI is required", "mandatory"),
        ("Nice to have: LangGraph", "preferred"),
        ("Bonus points for Kubernetes", "preferred"),
        ("Our stack includes Redis", None),
    ],
)
def test_importance_cue(context, expected):
    assert importance_cue(context) == expected


@pytest.mark.parametrize(
    "text,lo,hi",
    [
        ("0-2 years of experience", 0, 2),
        ("0 to 3 yrs experience", 0, 3),
        ("2+ years experience in Python", 2, None),
        ("Minimum 3 years of experience", 3, None),
        ("at least 4 years in backend", 4, None),
        ("Freshers are welcome to apply", 0, None),
        ("6 months of internship experience", 0.5, None),
    ],
)
def test_parse_experience(text, lo, hi):
    exp = parse_experience(text)
    assert exp is not None and exp.minimum_years == lo and exp.maximum_years == hi
    assert exp.evidence and exp.evidence.lower() in text.lower()


def test_parse_experience_none_when_not_stated():
    assert parse_experience("Join our AI team and build great things") is None
    assert parse_experience("We have been around for 10 years") is None


@pytest.mark.parametrize(
    "text,mn,mx,cur,period",
    [
        ("₹12 - 18 LPA", 1_200_000, 1_800_000, "INR", "annual"),
        ("CTC: 15 lakh per annum", 1_500_000, 1_500_000, "INR", "annual"),
        ("INR 12,00,000 - 18,00,000 per annum", 1_200_000, 1_800_000, "INR", "annual"),
        ("$120k - $150k", 120_000, 150_000, "USD", "annual"),
        ("USD 120,000–150,000 per year", 120_000, 150_000, "USD", "annual"),
        ("₹50,000/month stipend", 50_000, 50_000, "INR", "monthly"),
        ("$60/hour", 60, 60, "USD", "hourly"),
    ],
)
def test_parse_salary(text, mn, mx, cur, period):
    s = parse_salary(text)
    assert s is not None
    assert (s.minimum, s.maximum, s.currency, s.period) == (mn, mx, cur, period)


def test_parse_salary_ignores_non_salary_numbers():
    assert parse_salary("We have 500 employees and 3 offices") is None
    assert parse_salary("0-2 years experience") is None


def test_annualize():
    assert annualize(50_000, "monthly") == 600_000
    assert annualize(60, "hourly") == 124_800
    assert annualize(1_000, "annual") == 1_000
    assert annualize(1_000, "unknown") is None


def test_location_aliases_and_remote():
    assert normalize_location("Bangalore")["city"] == "Bengaluru"
    assert normalize_location("Gurgaon, Haryana")["city"] == "Gurugram"
    remote = normalize_location("Remote (India)")
    assert remote["remote"] is True and remote["country"] == "India"
    assert [loc["city"] for loc in find_locations("Offices in Pune and Hyderabad")] == ["Pune", "Hyderabad"]


def test_work_mode_employment_seniority():
    assert detect_work_mode(SOURCE)[0] == "hybrid"
    assert detect_work_mode("This is a fully remote role")[0] == "remote"
    assert detect_work_mode("Work from office, 5 days")[0] == "onsite"
    assert detect_work_mode("Great team")[0] == "unknown"
    assert detect_employment_type("Full-time position")[0] == "full_time"
    assert detect_employment_type("6-month internship")[0] == "internship"
    assert detect_seniority("Senior Backend Engineer") == "senior"
    assert detect_seniority("Graduate Engineer Trainee") == "graduate"
    assert detect_seniority("AI Engineer") == "unknown"


def test_parse_date_relative_and_absolute():
    base = datetime(2026, 11, 17, 6, 0, tzinfo=UTC)
    assert parse_date("3 days ago", base=base).date().isoformat() == "2026-11-14"
    assert parse_date("2026-12-01", prefer="future", base=base).date().isoformat() == "2026-12-01"
    assert parse_date("not a date at all", base=base) is None
