from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.matching import load_scoring_config
from app.domain.ranking import RankingInput, band, score_job

CFG = load_scoring_config()
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


def inp(**kw):
    base = dict(
        match_score=80.0, posted_at=NOW - timedelta(hours=6), collected_at=NOW, now=NOW,
        experience_min=0, experience_max=2, candidate_years=1.0,
        job_locations=[{"city": "Bengaluru", "country": "India"}], work_mode="hybrid",
        preferred_cities=["Bengaluru", "Pune"], remote_ok=True, candidate_country="India",
        salary_min=None, salary_max=None, salary_currency=None, salary_period=None, salary_source_type="not_disclosed",
        pref_salary_min=None, pref_salary_currency="INR",
        employment_type="full_time", preferred_employment_types=["full_time"],
        mandatory_texts=[], work_authorization=None, deadline=None,
    )
    base.update(kw)
    return RankingInput(**base)


def comp(result, name):
    return result.components[name]["score"]


@pytest.mark.parametrize(
    "posted_days,expected",
    [(0.5, 100), (15.5, 50), (31, 0)],
)
def test_freshness(posted_days, expected):
    r = score_job(inp(posted_at=NOW - timedelta(days=posted_days)), CFG)
    assert comp(r, "F") == pytest.approx(expected, abs=0.01)


def test_unknown_posted_date_capped_at_70_and_flagged():
    r = score_job(inp(posted_at=None, collected_at=NOW - timedelta(days=2)), CFG)
    assert comp(r, "F") == 70
    assert any("posting date" in lim.lower() for lim in r.limitations)


@pytest.mark.parametrize(
    "years,lo,hi,expected,flag",
    [
        (None, 0, 2, 70, None),
        (1, None, None, 70, None),
        (1, 0, 2, 100, None),
        (0, 1, None, 60, None),
        (0, 2, None, 30, None),
        (0, 3, None, 0, "requires"),
        (3, 0, 2, 80, None),
        (5, 0, 2, 50, "overqualified"),
    ],
)
def test_experience_eligibility(years, lo, hi, expected, flag):
    r = score_job(inp(candidate_years=years, experience_min=lo, experience_max=hi), CFG)
    assert comp(r, "E_elig") == expected
    if flag:
        assert any(flag in d.lower() for d in r.disqualifiers)


@pytest.mark.parametrize(
    "locations,mode,expected",
    [
        ([], "remote", 100),
        ([{"city": "Bengaluru", "country": "India"}], "onsite", 100),
        ([{"city": "Mumbai", "country": "India"}], "onsite", 40),
        ([], "unknown", 50),
        ([{"city": "London", "country": "United Kingdom"}], "onsite", 0),
    ],
)
def test_location(locations, mode, expected):
    r = score_job(inp(job_locations=locations, work_mode=mode), CFG)
    assert comp(r, "L") == expected


def test_location_outside_preferences_is_flagged_not_filtered():
    r = score_job(inp(job_locations=[{"city": "London", "country": "United Kingdom"}], work_mode="onsite"), CFG)
    assert any("location" in d.lower() for d in r.disqualifiers)
    assert r.score > 0


@pytest.mark.parametrize(
    "smin,smax,period,source,pref,expected",
    [
        (None, None, None, "not_disclosed", 1_000_000, 50),
        (1_200_000, 1_800_000, "annual", "third_party_estimate", 1_000_000, 50),
        (1_200_000, 1_800_000, "annual", "jd", 1_000_000, 100),
        (800_000, 1_200_000, "annual", "jd", 1_000_000, 85),
        (500_000, 750_000, "annual", "jd", 1_000_000, 42.5),
        (100_000, 100_000, "monthly", "jd", 1_000_000, 100),
    ],
)
def test_salary(smin, smax, period, source, pref, expected):
    r = score_job(inp(salary_min=smin, salary_max=smax, salary_currency="INR", salary_period=period,
                      salary_source_type=source, pref_salary_min=pref), CFG)
    assert comp(r, "S") == pytest.approx(expected)


def test_salary_currency_mismatch_neutral_with_limitation():
    r = score_job(inp(salary_min=100_000, salary_max=150_000, salary_currency="USD", salary_period="annual",
                      salary_source_type="jd", pref_salary_min=1_000_000, pref_salary_currency="INR"), CFG)
    assert comp(r, "S") == 50
    assert any("currency" in lim.lower() for lim in r.limitations)


def test_total_is_weighted_sum_and_band():
    r = score_job(inp(), CFG)
    expected = 0.5 * 80 + 0.2 * 100 + 0.15 * 100 + 0.1 * 100 + 0.05 * 50
    assert r.score == pytest.approx(expected)
    assert r.priority == "excellent"
    assert band(84.9, CFG) == "strong" and band(50, CFG) == "moderate" and band(49.9, CFG) == "low"


def test_disqualifier_flags():
    r = score_job(
        inp(mandatory_texts=["Must be a US citizen with active security clearance"],
            employment_type="internship", deadline=date(2026, 11, 1)),
        CFG,
    )
    text = " ".join(r.disqualifiers).lower()
    assert "citizenship" in text or "clearance" in text
    assert "employment type" in text
    assert "deadline" in text


def test_missing_match_score_counts_as_zero_with_limitation():
    r = score_job(inp(match_score=None), CFG)
    assert comp(r, "M") == 0
    assert any("resume" in lim.lower() for lim in r.limitations)
