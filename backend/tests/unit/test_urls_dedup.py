import uuid
from datetime import UTC, datetime, timedelta

from app.domain.dedup import ExistingJob, ListingKey, find_duplicate, location_key, normalize_title
from app.domain.urls import (
    ats_key,
    canonical_job_key,
    canonicalize_url,
    is_blocked_host,
    normalize_linkedin_profile,
    registrable_domain,
)


def test_canonicalize_strips_tracking_fragment_www_and_sorts_params():
    url = "HTTPS://WWW.Example.com:443/careers/job/?utm_source=x&b=2&a=1&ref=li#apply"
    assert canonicalize_url(url) == "https://example.com/careers/job?a=1&b=2"


def test_canonicalize_keeps_greenhouse_job_param_and_rejects_non_http():
    assert canonicalize_url("https://acme.com/careers?gh_jid=123&gh_src=abc") == "https://acme.com/careers?gh_jid=123"
    assert canonicalize_url("javascript:alert(1)") is None
    assert canonicalize_url("not a url") is None


def test_ats_keys_collapse_url_variants():
    assert ats_key("https://boards.greenhouse.io/acme/jobs/4012345") == "greenhouse:acme:4012345"
    assert ats_key("https://job-boards.greenhouse.io/acme/jobs/4012345?gh_src=1") == "greenhouse:acme:4012345"
    assert ats_key("https://jobs.lever.co/acme/1a2b3c4d-0000-1111-2222-333344445555/apply") == (
        "lever:acme:1a2b3c4d-0000-1111-2222-333344445555"
    )
    assert ats_key("https://jobs.ashbyhq.com/acme/9f9f9f9f-aaaa-bbbb-cccc-dddddddddddd") == (
        "ashby:acme:9f9f9f9f-aaaa-bbbb-cccc-dddddddddddd"
    )
    assert ats_key("https://example.com/jobs/1") is None
    assert canonical_job_key("https://boards.greenhouse.io/acme/jobs/4012345") == "greenhouse:acme:4012345"


def test_linkedin_profile_normalisation():
    assert normalize_linkedin_profile("http://in.linkedin.com/in/Jane-Doe-123?trk=abc") == "https://www.linkedin.com/in/jane-doe-123/"
    assert normalize_linkedin_profile("https://www.linkedin.com/company/acme") is None
    assert normalize_linkedin_profile("https://evil.com/in/jane") is None


def test_registrable_domain_and_blocked_hosts():
    assert registrable_domain("https://careers.acme.co.in/jobs") == "acme.co.in"
    assert registrable_domain("jobs.example.com") == "example.com"
    assert is_blocked_host("https://www.linkedin.com/posts/x", ["linkedin.com"])
    assert is_blocked_host("https://in.linkedin.com/jobs/view/1", ["linkedin.com"])
    assert not is_blocked_host("https://notlinkedin.com/x", ["linkedin.com"])


def test_normalize_title_keeps_seniority_drops_req_ids_and_location_notes():
    assert normalize_title("Senior AI Engineer (R-10234) [Remote]") == "senior ai engineer"
    assert normalize_title("AI Engineer - Bengaluru") == "ai engineer"
    assert normalize_title("Senior AI Engineer") != normalize_title("AI Engineer")


NOW = datetime(2026, 11, 17, tzinfo=UTC)
COMPANY = uuid.uuid4()


def _key(**kw):
    base = dict(
        canonical_url=None, source_name="greenhouse", source_listing_id=None, application_url=None,
        description_hash="h-new", company_id=COMPANY, normalized_title="ai engineer", location_key="bengaluru",
        posted_at=NOW,
    )
    base.update(kw)
    return ListingKey(**base)


def _existing(**kw):
    return ExistingJob(job_id=uuid.uuid4(), keys=[_key(description_hash="h-old", **kw)])


def test_dedup_signal_order():
    job = _existing(canonical_url="greenhouse:acme:1", source_listing_id="1")
    assert find_duplicate(_key(canonical_url="greenhouse:acme:1"), [job]) == (job.job_id, "canonical_url")
    assert find_duplicate(_key(source_listing_id="1"), [job]) == (job.job_id, "source_listing_id")
    app = _existing(application_url="https://acme.com/apply/9")
    assert find_duplicate(_key(application_url="https://acme.com/apply/9"), [app])[1] == "application_url"
    h = ExistingJob(job_id=uuid.uuid4(), keys=[_key(description_hash="same", normalized_title="x")])
    assert find_duplicate(_key(description_hash="same"), [h])[1] == "content_hash"


def test_company_title_location_needs_all_three_within_window():
    job = _existing()
    assert find_duplicate(_key(), [job])[1] == "company_title_location"
    assert find_duplicate(_key(location_key="pune"), [job]) is None
    assert find_duplicate(_key(company_id=uuid.uuid4()), [job]) is None
    assert find_duplicate(_key(posted_at=NOW + timedelta(days=60)), [job]) is None


def test_title_alone_never_merges():
    job = ExistingJob(job_id=uuid.uuid4(), keys=[_key(company_id=None, location_key=None, description_hash="z")])
    assert find_duplicate(_key(company_id=None, location_key=None), [job]) is None


def test_source_listing_id_only_matches_same_source():
    job = _existing(source_listing_id="1")
    assert find_duplicate(_key(source_name="lever", source_listing_id="1", normalized_title="other"), [job]) is None


def test_location_key():
    assert location_key([{"city": "Bengaluru"}], "onsite") == "bengaluru"
    assert location_key([], "remote") == "remote"
    assert location_key([], "unknown") is None
