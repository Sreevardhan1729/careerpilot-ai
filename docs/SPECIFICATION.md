# CareerPilot AI --- Complete Product Requirements & Technical Source of Truth

**Document type:** Product Requirements Document (PRD), Technical
Architecture, Implementation Plan\
**Project:** CareerPilot AI\
**Version:** 1.0\
**Date:** 17 November 2026\
**Status:** Proposed specification

------------------------------------------------------------------------

## 1. Executive summary

CareerPilot AI is a personal AI-powered job discovery, recruitment
intelligence, resume optimization, outreach generation, and application
preparation platform.

The platform should:

1.  Accept pasted LinkedIn posts, job descriptions, job URLs, PDFs, and
    DOCX files.
2.  Extract the role, company, experience requirements,
    responsibilities, mandatory skills, preferred skills, location,
    salary, and application details.
3.  Compare each job against a library of approximately 5--10 candidate
    resumes.
4.  Recommend the best resume and explain the match, missing evidence,
    and improvements.
5.  Discover up to 15 relevant, publicly verifiable people at the target
    company, prioritizing the original job poster, recruiters, talent
    acquisition professionals, hiring managers, engineering managers,
    team leads, and relevant employees.
6.  Collect LinkedIn profile URLs and professional email addresses only
    when publicly disclosed and verifiable.
7.  Generate personalized LinkedIn connection messages, follow-ups,
    referral requests, hiring-manager messages, and Gmail email drafts.
8.  Discover jobs automatically every day from permitted public sources
    and configured job feeds.
9.  Extract salary and experience information, rank opportunities, and
    display them in a dashboard.
10. Prepare future job applications using the candidate's fixed resume
    library, with explicit human approval before submission.
11. Run as a deployable web application with a Next.js frontend, FastAPI
    backend, LangChain/LangGraph orchestration, NVIDIA Nemotron
    inference, and free-tier infrastructure where feasible.

This is not intended to be a chatbot. It is a workflow-oriented
application with persistent data, deterministic processing, multiple AI
workflows, scheduled jobs, auditability, and human approval.

### 1.1 Non-negotiable product principles

-   Never invent jobs, people, email addresses, salaries, skills, or
    achievements.
-   Every important external fact must have source provenance.
-   Separate explicitly stated information from inferred information.
-   Treat scraped pages and job descriptions as untrusted data.
-   Do not bypass logins, CAPTCHAs, paywalls, anti-bot controls, or
    website access restrictions.
-   Respect source terms, robots directives, rate limits, privacy rules,
    and applicable laws.
-   Do not send messages or submit applications without explicit user
    approval.
-   Use deterministic code for parsing, scoring, deduplication, and
    validation where practical.
-   Use the LLM for extraction, classification, reasoning, and language
    generation.
-   Preserve original resumes and maintain version history.
-   Do not represent a match score as a probability of being
    shortlisted.

------------------------------------------------------------------------

## 2. Product goals and scope

### 2.1 Primary goals

**G1 --- Job intelligence:** Turn raw job posts into structured,
actionable job profiles.

**G2 --- Candidate intelligence:** Maintain a searchable profile from
the user's existing resumes and compare it against each role.

**G3 --- People intelligence:** Identify relevant company contacts using
verifiable public information.

**G4 --- Outreach assistance:** Generate personalized professional
messages and email drafts.

**G5 --- Daily discovery:** Collect and rank new jobs without requiring
the frontend to remain open.

**G6 --- Application preparation:** Prepare applications and track their
progress, with approval gates for external actions.

### 2.2 Out of scope for the initial MVP

-   Unrestricted crawling of every website.
-   Bypassing LinkedIn or other platforms' access controls.
-   Guessing or generating unverified email addresses.
-   Unsupervised mass messaging.
-   Automatic acceptance of legal declarations.
-   Automatic application submission on platforms that prohibit
    automation.
-   Guaranteed shortlist predictions.
-   Unlimited free-tier hosting or inference.

### 2.3 Two main entry points

#### A. Manual job intelligence

1.  User pastes a LinkedIn post, JD, or job URL, or uploads a document.
2.  Backend extracts and cleans content.
3.  Job Extraction workflow creates structured job data.
4.  Validation checks required fields and evidence.
5.  Resume Matching workflow compares all candidate resumes.
6.  People Discovery workflow searches for relevant contacts.
7.  Outreach workflow generates message and email drafts.
8.  User reviews and saves outputs.
9.  The job is added to the job tracker.

#### B. Automated daily job discovery

1.  Scheduler triggers configured sources.
2.  Source adapters collect permitted listings.
3.  Backend normalizes and deduplicates listings.
4.  Job Extraction workflow analyzes each job.
5.  Candidate Matching workflow evaluates resume fit.
6.  Ranking workflow prioritizes opportunities.
7.  People Discovery workflow finds relevant public contacts.
8.  Outreach workflow prepares drafts for selected jobs.
9.  Dashboard and notifications are updated.
10. User reviews and chooses next actions.

------------------------------------------------------------------------

## 3. User profile and candidate configuration

The application must maintain a candidate profile independently of any
single resume.

### 3.1 Candidate profile fields

-   Full name
-   Preferred email
-   Phone number, if the user chooses to store it
-   Current location
-   Preferred job locations
-   Preferred work modes
-   Education
-   Graduation year
-   Total experience
-   Preferred roles
-   Preferred industries
-   Core skills
-   Secondary skills
-   Projects
-   Work experience
-   Certifications
-   Achievements
-   Portfolio URL
-   GitHub URL
-   LinkedIn URL
-   Salary preference
-   Employment type preference
-   Notice period, if applicable
-   Work authorization information, only if needed and user supplied

### 3.2 Candidate profile requirements

-   User can edit every field.
-   Resume extraction may suggest profile updates but must not silently
    overwrite user-confirmed information.
-   Each fact should record its source: user-entered, resume-derived, or
    inferred.
-   Sensitive fields should be optional and access-controlled.
-   The user can export and delete their profile.

### 3.3 Initial candidate preferences

These are configurable defaults, not fixed assumptions:

**Roles** - AI Engineer - ML Engineer - GenAI Engineer - LLM Engineer -
Backend Engineer - Software Development Engineer - Data Engineer

**Experience** - Fresher - Graduate - 0--2 years - 0--3 years

**Locations** - Bengaluru - Hyderabad - Pune - Chennai - Mumbai - Remote
India

**Skills** - Python - LLMs - RAG - LangChain - LangGraph - FastAPI -
Machine Learning - AI - Vector databases - Backend engineering

The UI must allow the user to add, remove, and edit roles, locations,
experience bands, and skills.

------------------------------------------------------------------------

## 4. Functional requirements

## 4.1 Module 1 --- Job Post Intelligence

### Inputs

-   Pasted LinkedIn post text
-   Pasted job description
-   Public job URL
-   Company career page URL
-   PDF job description
-   DOCX job description
-   Manually entered job details

### Processing pipeline

1.  Identify input type.
2.  Retrieve content only through permitted methods.
3.  Parse HTML, PDF, DOCX, or plain text.
4.  Normalize whitespace and remove irrelevant navigation text.
5.  Preserve original text and source URL for audit.
6.  Send relevant content to the LLM with a strict extraction schema.
7.  Validate the response with Pydantic.
8.  Check whether values have evidence.
9.  Store normalized job and skill records.
10. Flag missing or uncertain fields.

### Required extracted fields

  -----------------------------------------------------------------------
  Field                               Description
  ----------------------------------- -----------------------------------
  Company                             Employer name

  Job title                           Exact role title

  Department                          AI, engineering, data, etc.

  Seniority                           Graduate, junior, mid, senior, etc.

  Minimum experience                  Explicit minimum years, if stated

  Maximum experience                  Explicit maximum years, if stated

  Experience evidence                 Source text supporting the range

  Location                            City, region, country

  Work mode                           Remote, hybrid, onsite, unknown

  Employment type                     Full-time, contract, internship,
                                      etc.

  Salary minimum                      Numeric amount, if stated

  Salary maximum                      Numeric amount, if stated

  Salary currency                     INR, USD, etc.

  Salary period                       Annual, monthly, hourly, etc.

  Salary source type                  JD, source website, third-party
                                      estimate, unknown

  Education                           Degree or qualification
                                      requirements

  Mandatory skills                    Explicitly required skills

  Preferred skills                    Nice-to-have skills

  Responsibilities                    Main duties

  Technical requirements              Languages, frameworks, databases,
                                      tools

  Soft skills                         Communication, ownership,
                                      collaboration, etc.

  Domain                              AI, fintech, e-commerce, etc.

  Deadline                            Application deadline, if available

  Application URL                     Direct application destination

  Posted date                         Source-reported date

  Source URL                          Original listing

  Hiring expectations                 Concise evidence-based summary
  -----------------------------------------------------------------------

### Skill taxonomy

Classify skills into:

-   Programming languages
-   Frameworks and libraries
-   AI/ML technologies
-   LLM engineering
-   Retrieval and vector databases
-   Databases
-   Cloud platforms
-   DevOps and infrastructure
-   Data engineering
-   System design
-   Domain knowledge
-   Soft skills

Each skill should include: - Name - Category - Importance: mandatory,
preferred, or mentioned - Evidence snippet - Confidence - Normalized
skill identifier, where available

### Extraction rules

-   Do not treat every mentioned skill as mandatory.
-   Distinguish explicit requirements from inferred expectations.
-   Do not infer experience years if not stated.
-   Do not invent salary.
-   Use `null` or `not_disclosed` when data is unavailable.
-   Store evidence for important fields.
-   Record confidence, but do not treat model confidence as proof.

### Output example

``` json
{
  "company": "Example AI Technologies",
  "job_title": "AI Engineer",
  "department": "AI/ML",
  "seniority": "Junior",
  "experience": {
    "minimum_years": 0,
    "maximum_years": 2,
    "explicitly_stated": true,
    "evidence": "0-2 years of experience"
  },
  "location": ["Bengaluru, India"],
  "work_mode": "unknown",
  "employment_type": "full_time",
  "salary": {
    "minimum": null,
    "maximum": null,
    "currency": null,
    "period": null,
    "source_type": "not_disclosed"
  },
  "mandatory_skills": ["Python", "LLMs", "RAG", "FastAPI"],
  "preferred_skills": ["LangChain", "Vector databases"],
  "responsibilities": ["Build and deploy AI applications"],
  "source_url": "https://example.com/jobs/123",
  "missing_information": ["Salary", "Work mode"]
}
```

The example is illustrative only.

## 4.2 Module 2 --- Resume Intelligence

### Inputs

-   5--10 PDF or DOCX resumes
-   Candidate profile
-   Existing project descriptions
-   User-confirmed skills and achievements

### Resume ingestion

1.  Validate file type and size.
2.  Store original document in private object storage.
3.  Extract text with PyMuPDF or python-docx.
4.  Preserve page/section boundaries where possible.
5.  Parse sections: summary, skills, experience, education, projects,
    certifications, achievements.
6.  Normalize technology names.
7.  Create structured resume data.
8.  Split relevant content into searchable chunks.
9.  Generate embeddings.
10. Store vectors in pgvector.
11. Let the user review and correct parsed information.

### Resume library

The user can maintain multiple resumes with labels such as:

-   AI Engineer
-   GenAI / LLM Engineer
-   Backend Engineer
-   Data Engineer
-   ML Engineer
-   Full Stack Engineer

These labels should be suggested from actual document content and
editable.

### Resume matching

Compare every available resume against a job.

Recommended initial score:

`Match Score = 0.35K + 0.25P + 0.15E + 0.15R + 0.10D`

Where: - K = technical skill coverage - P = project relevance - E =
experience relevance - R = responsibility alignment - D = domain
relevance

Each component is scored from 0 to 100.

The scoring implementation must: - Use explicit evidence. - Distinguish
missing evidence from a confirmed missing skill. - Avoid double-counting
synonyms. - Weight mandatory skills more heavily than preferred skills
within skill coverage. - Explain every component. - Be deterministic for
the same input and scoring configuration.

### Resume matching output

-   Ranked resume IDs
-   Best resume ID
-   Overall match score
-   Mandatory skill coverage
-   Preferred skill coverage
-   Relevant projects
-   Relevant experience
-   Missing skills
-   Weakly highlighted skills
-   Evidence snippets
-   Suggested summary
-   Suggested bullet rewrites
-   Score explanation
-   Confidence and limitations

### Resume optimization

Generate: 1. Professional summary suggestions. 2. Project bullet
improvements. 3. Work-experience bullet improvements. 4. Relevant skill
ordering. 5. ATS-friendly section ordering. 6. Keywords already
supported by the resume. 7. Keywords missing from the evidence. 8.
Before/after comparison.

Never add unsupported skills, technologies, metrics, responsibilities,
or experience. The original document must remain unchanged until the
user approves a new version.

### Resume versioning

Each modified resume must have: - Resume ID - Version number - Parent
version ID - File URL - Change summary - Created timestamp - Approval
status - Job ID, if tailored to a specific job

------------------------------------------------------------------------

## 4.3 Module 3 --- People and Recruiter Intelligence

### Objective

Identify up to 15 relevant people associated with a target company and
role.

### Priority order

1.  Original job poster
2.  Technical recruiter
3.  Talent acquisition specialist
4.  HR recruiter
5.  Hiring manager
6.  Engineering manager
7.  Team lead
8.  Department head
9.  Relevant senior engineers
10. Relevant team members
11. Talent partners
12. HR business partners
13. Relevant alumni connections
14. Relevant technical leaders
15. Other employees with a strong role connection

### Permitted discovery sources

-   Company team and leadership pages
-   Public company websites
-   Public professional profile pages
-   Public job posts
-   Public company blogs
-   Public conference speaker profiles
-   Search engine results
-   User-provided LinkedIn URLs
-   Permitted professional directories

### Contact record fields

-   Name
-   Current designation
-   Company
-   Department
-   Public LinkedIn URL
-   Public professional email, if explicitly disclosed
-   Source URL
-   Source title or evidence
-   Company association verification status
-   Relevance reason
-   Relevance score
-   Confidence
-   Discovery timestamp
-   Last verified timestamp
-   Contact status

### Contact scoring

`People Score = 0.35T + 0.30D + 0.20C + 0.15S`

Where: - T = job-title relevance - D = department relevance - C =
company association confidence - S = source reliability

### Strict rules

-   Fifteen is a target, not a guarantee.
-   Return fewer than 15 if fewer can be verified.
-   Never invent a person.
-   Never guess an email address from a naming pattern.
-   Never label an unverified profile as current.
-   Do not bypass login restrictions or scrape prohibited services.
-   Avoid duplicate people.
-   Retain source provenance for every result.
-   Mark uncertain associations clearly.

The LLM is not the search engine. Search/retrieval tools must first
gather evidence; the LLM then classifies and ranks the evidence.

------------------------------------------------------------------------

## 4.4 Module 4 --- Outreach Generation

### Message types

1.  LinkedIn connection request
2.  LinkedIn follow-up
3.  Referral request
4.  Hiring manager message
5.  Recruiter application email
6.  Recruiter follow-up
7.  Thank-you message after a response or interview

### Required context

-   Candidate profile
-   Relevant resume evidence
-   Job description
-   Company context
-   Recipient name and designation
-   Recipient relevance
-   Relevant project or achievement
-   Previous outreach history, if available

### Output fields

-   Channel
-   Recipient
-   Subject, for email
-   Message body
-   Recommended resume ID
-   Personalization evidence
-   Requires review
-   Draft status
-   Created timestamp

### Rules

-   Keep messages concise and natural.
-   Personalize based on verified facts.
-   Do not pretend to know the recipient.
-   Do not claim a referral relationship that does not exist.
-   Do not exaggerate experience.
-   Use a measurable achievement only when supported.
-   Generate drafts first.
-   Require explicit approval before sending.
-   LinkedIn messages should be manually sent unless an authorized
    integration exists.

### Gmail integration

Use OAuth. Initially request only the scopes needed to create drafts. Do
not collect Gmail passwords. Keep access tokens encrypted and
server-side. Sending must be a separate, approved action.

------------------------------------------------------------------------

## 4.5 Module 5 --- Automated Job Discovery

### Source adapter architecture

Create a common adapter interface so new sources can be added without
changing orchestration code.

Potential sources, subject to current access terms and permissions:

-   Public company career pages
-   Greenhouse job boards
-   Lever job boards
-   Wellfound public listings
-   YC job listings
-   Authorized job feeds
-   RSS feeds
-   Company recruitment pages
-   User-provided job URLs
-   Job alerts
-   Other permitted public sources

LinkedIn and other restricted platforms must be handled through
permitted access, user-provided content, alerts, or authorized
integrations. Do not bypass access controls.

### Adapter contract

Every adapter should expose a consistent operation such as:

``` python
class JobSourceAdapter:
    async def discover(self, config):
        """Return source listing records."""

    async def fetch_details(self, listing):
        """Fetch permitted public details."""

    async def health_check(self):
        """Return source health information."""
```

A normalized listing should include: - Source name - Source listing ID,
if available - Job title - Company - Location - Job URL - Application
URL - Posted date - Raw description - Collected timestamp - Source
metadata

### Discovery pipeline

1.  Load enabled sources.
2.  Load user search configuration.
3.  Execute adapters with source-specific limits.
4.  Normalize results.
5.  Validate URLs and required fields.
6.  Deduplicate.
7.  Fetch permitted details.
8.  Extract job information.
9.  Store job and source evidence.
10. Trigger resume matching.
11. Rank jobs.
12. Trigger people discovery for high-priority jobs.
13. Generate drafts where configured.
14. Record run metrics and errors.

### Deduplication

Use multiple signals: - Canonical source URL - Source-specific listing
ID - Company + normalized title + location - Description content hash -
Application URL

Do not rely only on title similarity. Keep a record of merged source
records so the system can retain multiple source URLs for the same job.

### Salary handling

Classify salary as: - Explicitly stated in JD - Reported by source
website - Third-party estimate - Not disclosed

Store: - Minimum - Maximum - Currency - Pay period - Source - Retrieval
date - Confidence - Whether the amount is base salary or total
compensation, if known

Never display an estimate as confirmed compensation.

### Source governance

-   Respect terms of service.
-   Respect robots directives where applicable.
-   Use reasonable rate limits.
-   Identify the crawler where appropriate.
-   Do not evade anti-bot measures.
-   Do not crawl private or authenticated content without authorization.
-   Retain only necessary data.
-   Provide a source disable switch.
-   Log source errors independently so one failed site does not stop all
    discovery.

------------------------------------------------------------------------

## 4.6 Module 6 --- Job Recommendation and Ranking

Recommended initial formula:

`Job Score = 0.50M + 0.20F + 0.15E + 0.10L + 0.05S`

Where: - M = candidate/resume match - F = freshness - E = experience
eligibility - L = location preference - S = salary preference

All components should be normalized to 0--100.

Initial configurable categories: - 85--100: Excellent - 70--84: Strong -
50--69: Moderate - Below 50: Low priority

The score is a prioritization heuristic, not a probability of getting
shortlisted.

Every recommendation should explain: - Why the role matches - Which
resume is best - Which requirements are supported - Which requirements
are missing or unclear - Whether experience eligibility is satisfied -
Whether salary is known - Whether the listing is recent - Any potential
disqualifying requirement

------------------------------------------------------------------------

## 4.7 Module 7 --- Application Preparation and Automation

This is a later phase. Design the data model now, but implement after
the discovery and matching workflows are reliable.

### Workflow

1.  User selects a job.
2.  System recommends a resume.
3.  System prepares a tailored resume draft.
4.  System drafts application answers from verified candidate data.
5.  System validates all factual claims.
6.  User reviews the application preview.
7.  User explicitly approves the action.
8.  Submission occurs only through a supported, authorized mechanism.
9.  System records confirmation evidence.
10. Application tracker is updated.

### Application statuses

-   Discovered
-   Analyzed
-   Interested
-   Resume selected
-   Draft prepared
-   Awaiting approval
-   Ready to submit
-   Applied
-   Recruiter contacted
-   Interview scheduled
-   Rejected
-   Offer received
-   Withdrawn

### Application record

-   Job ID
-   Company ID
-   User ID
-   Selected resume ID and version
-   Application URL
-   Status
-   Submission timestamp
-   Confirmation evidence
-   Answers submitted
-   Follow-up date
-   Notes
-   Last updated timestamp

### Safety and integrity

-   Never submit without explicit approval.
-   Never fabricate answers.
-   Do not automatically accept legal declarations.
-   Never apply twice to the same job.
-   Store the exact resume version used.
-   Do not claim submission without confirmation evidence.
-   Use manual completion when platform automation is not permitted.

------------------------------------------------------------------------

## 5. System architecture

### 5.1 Architectural style

Use a modular monolith initially. The backend can have independently
testable modules and separate worker processes without introducing
microservices prematurely.

### 5.2 High-level architecture

``` mermaid
flowchart TD
    UI["Next.js Frontend"] --> API["FastAPI Backend"]
    API --> AUTH["Authentication and Authorization"]
    API --> ROUTER["Workflow Router"]

    ROUTER --> JOB["Job Intelligence Graph"]
    ROUTER --> RESUME["Resume Intelligence Graph"]
    ROUTER --> PEOPLE["People Discovery Graph"]
    ROUTER --> OUTREACH["Outreach Graph"]
    ROUTER --> APP["Application Graph"]

    JOB --> LLM["NVIDIA Nemotron Endpoint"]
    RESUME --> LLM
    PEOPLE --> LLM
    OUTREACH --> LLM
    APP --> LLM

    DISC["Scheduled Discovery Worker"] --> SOURCES["Permitted Source Adapters"]
    SOURCES --> NORMAL["Normalize and Deduplicate"]
    NORMAL --> JOB

    JOB --> DB["Supabase PostgreSQL"]
    RESUME --> DB
    PEOPLE --> DB
    OUTREACH --> DB
    APP --> DB

    RESUME --> VECTOR["pgvector"]
    FILES["Supabase Storage"] --> RESUME
    ROUTER --> CHECK["LangGraph Checkpointer"]
    CHECK --> DB
```

### 5.3 Technology choices

  -----------------------------------------------------------------------
  Layer                   Technology              Purpose
  ----------------------- ----------------------- -----------------------
  Frontend                Next.js + TypeScript    User interface

  UI                      Tailwind CSS +          Components
                          shadcn/ui               

  Backend                 FastAPI                 APIs and orchestration
                                                  entry points

  Validation              Pydantic                Structured input/output

  ORM                     SQLAlchemy              Database access

  Migrations              Alembic                 Schema versioning

  AI orchestration        LangGraph               Stateful workflows

  LLM abstraction         LangChain               Model and prompt
                                                  integration

  Model                   NVIDIA Nemotron         Extraction, reasoning,
                                                  generation

  Database                Supabase PostgreSQL     Persistent structured
                                                  data

  Vector search           pgvector                Resume and job semantic
                                                  retrieval

  File storage            Supabase Storage        Private documents

  PDF parsing             PyMuPDF                 PDF text extraction

  DOCX parsing            python-docx             Word document
                                                  extraction

  HTTP                    httpx                   Async requests

  HTML parsing            BeautifulSoup           Permitted page parsing

  Browser rendering       Playwright              Permitted
                                                  JavaScript-rendered
                                                  pages

  Scheduler               GitHub Actions or       Daily triggers
                          persistent scheduler    

  Frontend hosting        Vercel                  Next.js deployment

  Backend hosting         Suitable free-tier      FastAPI deployment
                          Python host             
  -----------------------------------------------------------------------

### 5.4 NVIDIA model configuration

The exact model identifier must be verified against the NVIDIA endpoint
available to the user. Do not assume that a model label or context-size
description is an API model identifier.

Use configuration such as:

``` env
LLM_PROVIDER=nvidia
NVIDIA_API_KEY=
NVIDIA_BASE_URL=
NVIDIA_MODEL=
LLM_TEMPERATURE=0.1
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=3
```

Keep the model configurable so it can be replaced without rewriting
agents.

------------------------------------------------------------------------

## 6. LangGraph agent design

Do not build one giant agent with all tools. Implement separate
workflows with typed states and explicit transitions.

### 6.1 Proposed workflows

  Workflow                        Responsibility
  ------------------------------- ---------------------------------------
  Job Discovery Graph             Coordinate source collection
  Job Extraction Graph            Parse and validate job details
  Resume Matching Graph           Compare resumes with job requirements
  People Discovery Graph          Rank evidence-backed contacts
  Outreach Generation Graph       Draft personalized messages
  Application Preparation Graph   Prepare forms and documents
  Application Approval Graph      Pause for approval and record action

### 6.2 Main workflow diagram

``` mermaid
flowchart TD
    START["Manual Input or Daily Trigger"] --> ROUTER["Input Router"]
    ROUTER --> DISCOVER["Job Discovery"]
    ROUTER --> MANUAL["Manual JD Parser"]
    DISCOVER --> NORMAL["Normalize and Deduplicate"]
    MANUAL --> NORMAL
    NORMAL --> EXTRACT["Job Extraction"]
    EXTRACT --> VALIDATE["Validate Structured Data"]
    VALIDATE --> MATCH["Resume Matching"]
    MATCH --> RANK["Job Ranking"]
    RANK --> PEOPLE["People Discovery"]
    PEOPLE --> OUTREACH["Outreach Generation"]
    OUTREACH --> REVIEW["Human Review"]
    REVIEW --> SAVE["Save Job and Drafts"]
    SAVE --> PREP["Application Preparation"]
    PREP --> APPROVAL["Human Approval"]
    APPROVAL --> SUBMIT["Supported Submission or Manual Completion"]
    SUBMIT --> TRACK["Application Tracking"]
```

### 6.3 Workflow state

Use focused state models. An initial job-analysis state might look like:

``` python
from typing import TypedDict, Optional, Any

class JobWorkflowState(TypedDict, total=False):
    user_id: str
    input_text: Optional[str]
    source_url: Optional[str]
    job_details: dict[str, Any]
    required_skills: list[str]
    preferred_skills: list[str]
    resume_matches: list[dict[str, Any]]
    best_resume_id: Optional[str]
    people: list[dict[str, Any]]
    outreach_messages: list[dict[str, Any]]
    job_score: float
    validation_errors: list[str]
    approval_status: str
    final_status: str
```

Use separate typed state definitions for discovery, people, outreach,
and applications where that improves clarity.

### 6.4 Human-in-the-loop

Pause workflows before: - Saving a materially changed resume version -
Sending an email - Submitting an application - Performing any other
irreversible external action

Use LangGraph checkpoints and a persistent checkpointer. Resume a
workflow only after an authenticated user decision is recorded.

### 6.5 LLM versus deterministic logic

Use the LLM for: - JD classification and extraction - Skill taxonomy
normalization suggestions - Responsibility interpretation - Resume
evidence interpretation - Contact relevance explanation - Message
generation - Natural-language summaries

Use deterministic code for: - URL validation - Deduplication - Schema
validation - Score calculations - Eligibility rules - Date
normalization - Retry handling - Approval enforcement - Duplicate
application prevention - Audit logging

------------------------------------------------------------------------

## 7. Database design

### 7.1 Core entities

``` mermaid
erDiagram
    USERS ||--o{ RESUMES : owns
    USERS ||--o{ JOBS : saves
    USERS ||--o{ APPLICATIONS : creates
    USERS ||--o{ SEARCH_CONFIGS : configures

    COMPANIES ||--o{ JOBS : posts
    JOBS ||--o{ JOB_SKILLS : requires
    JOBS ||--o{ JOB_PEOPLE : identifies
    JOBS ||--o{ RESUME_MATCHES : matches
    JOBS ||--o{ APPLICATIONS : receives

    RESUMES ||--o{ RESUME_MATCHES : evaluated
    RESUMES ||--o{ APPLICATIONS : selected

    PEOPLE ||--o{ JOB_PEOPLE : associated
    PEOPLE ||--o{ OUTREACH : receives

    APPLICATIONS ||--o{ OUTREACH : generates
    APPLICATIONS ||--o{ APPLICATION_EVENTS : tracks
```

### 7.2 Tables

  -----------------------------------------------------------------------
  Table                   Purpose                 Important fields
  ----------------------- ----------------------- -----------------------
  users                   User account/profile    id, email, preferences

  resumes                 Original and tailored   id, user_id, file_url,
                          resumes                 name, category,
                                                  parsed_data, version

  resume_chunks           Searchable resume       id, resume_id, content,
                          sections                embedding

  companies               Company records         id, name, domain,
                                                  website

  jobs                    Normalized job listings id, company_id, title,
                                                  location, salary,
                                                  description, source_url

  job_skills              Extracted skills        id, job_id, skill,
                                                  category, importance,
                                                  evidence

  resume_matches          Match results           job_id, resume_id,
                                                  score, explanation

  people                  Public professional     id, name, designation,
                          contact records         linkedin_url,
                                                  public_email

  job_people              Job-contact             job_id, person_id,
                          associations            relevance_score

  outreach                Generated messages      person_id, job_id,
                                                  channel, message,
                                                  status

  applications            Application tracking    job_id, resume_id,
                                                  status, applied_at

  application_events      Application history     application_id,
                                                  event_type, metadata

  search_configs          User filters            user_id, role_filters,
                                                  locations, skills

  crawl_sources           Source configuration    domain, source_type,
                                                  enabled, last_crawled

  crawl_runs              Crawl execution history source_id, status,
                                                  started_at,
                                                  completed_at

  agent_runs              Workflow execution      workflow_id, state,
                          history                 status, error

  approvals               Approval audit          action_type,
                                                  reference_id, status,
                                                  approved_at
  -----------------------------------------------------------------------

Additional recommended tables: - `job_source_records` for multiple
source listings merged into one canonical job - `job_evidence` for
field-level source evidence - `candidate_profile_facts` for
user-confirmed profile facts - `notifications` for in-app alerts -
`oauth_connections` for encrypted provider tokens/metadata -
`scheduled_tasks` for persistent task scheduling - `audit_events` for
security-sensitive actions

### 7.3 Database requirements

-   UUID primary keys.
-   Foreign keys and appropriate delete behavior.
-   `created_at` and `updated_at`.
-   User ownership on private records.
-   Unique constraints for canonical URLs or source identifiers where
    appropriate.
-   Indexes on job date, company, status, user ID, and relationship
    keys.
-   pgvector index for embeddings.
-   Row Level Security on all user-owned tables.
-   Alembic migrations.
-   Database backup/export plan.
-   Retention policy for external source data.

### 7.4 Suggested indexes

-   `jobs.source_url` where canonical and unique
-   `jobs.company_id`
-   `jobs.created_at`
-   `jobs.status`
-   `people.linkedin_url` where present
-   `resume_matches.job_id`
-   `resume_matches.resume_id`
-   `applications.user_id, applications.job_id`
-   `job_skills.job_id, job_skills.skill`
-   Vector index on `resume_chunks.embedding`

Do not store full scraped HTML indefinitely. Store the minimum extracted
content and evidence needed for the product and audit trail.

------------------------------------------------------------------------

## 8. Backend API specification

All endpoints should be versioned under `/api/v1`.

  Method   Endpoint                       Purpose
  -------- ------------------------------ ------------------------------------
  POST     `/jobs/analyze`                Analyze pasted JD
  POST     `/jobs/analyze-url`            Analyze a permitted job URL
  GET      `/jobs`                        List jobs
  GET      `/jobs/{id}`                   Get job details
  POST     `/jobs/discover`               Trigger discovery
  GET      `/jobs/{id}/people`            Get related contacts
  POST     `/resumes/upload`              Upload resume
  GET      `/resumes`                     List resumes
  GET      `/resumes/{id}`                Get resume details
  POST     `/resumes/match/{job_id}`      Match resumes to a job
  POST     `/outreach/generate`           Generate messages
  POST     `/outreach/drafts`             Save a draft
  POST     `/outreach/{id}/approve`       Approve a supported sending action
  POST     `/applications/prepare`        Prepare application
  POST     `/applications/{id}/approve`   Approve a supported submission
  GET      `/applications`                List applications
  GET      `/dashboard/summary`           Dashboard metrics
  POST     `/scheduler/run`               Manually trigger discovery
  GET      `/agent-runs/{id}`             Workflow status
  GET      `/health`                      Health check

### API requirements

-   Pydantic request and response models.
-   Authentication and authorization.
-   User-level ownership checks.
-   Rate limiting.
-   Consistent error response format.
-   Structured logs.
-   Idempotency keys for actions that may be retried.
-   Pagination and filtering.
-   Async processing for long-running workflows.
-   Return `202 Accepted` and a workflow ID for background tasks.
-   Provide polling or Server-Sent Events for progress.

### Example job analysis request

``` json
{
  "input_type": "text",
  "text": "Paste the full job description here",
  "source_url": null
}
```

### Example asynchronous response

``` json
{
  "workflow_id": "uuid",
  "status": "queued",
  "status_url": "/api/v1/agent-runs/uuid"
}
```

------------------------------------------------------------------------

## 9. Frontend requirements

Build a responsive, accessible dashboard using Next.js, TypeScript,
Tailwind CSS, and shadcn/ui.

### Page 1 --- Dashboard

Display: - Total jobs discovered - New jobs today - Excellent and strong
matches - People discovered - Outreach drafts awaiting review -
Applications submitted - Upcoming follow-ups - Scheduler status - Latest
job opportunities - Recent workflow failures

### Page 2 --- Job Search

Filters: - Role - Company - Location - Experience - Salary - Source -
Skills - Posted date - Match score - Work mode

Actions: - Open job - Save job - Analyze job - Compare resumes - Find
people - Generate outreach

### Page 3 --- Job Intelligence

Display: - Full job description - Extracted company and role details -
Mandatory and preferred skills - Experience requirements - Salary and
source classification - Location and work mode - Responsibilities -
Evidence and confidence - Resume match - Missing evidence - Job source
and application link

### Page 4 --- Resume Library

Features: - Upload PDF/DOCX - Categorize resume - Preview extracted
information - Review parsing errors - Compare resumes - Select default
resume - View version history - Download original and approved tailored
versions

### Page 5 --- People Discovery

Display: - Name - Designation - Department - Public profile URL - Public
email, if verified - Source - Company association status - Relevance
score - Why the person is relevant - Outreach status

### Page 6 --- Outreach Center

Features: - LinkedIn connection message - Follow-up - Referral request -
Hiring manager message - Gmail draft - Editable message preview - Copy
action - Approval status - Contact history

### Page 7 --- Application Tracker

Use a Kanban or table view: - Interested - Preparing - Awaiting
approval - Applied - Recruiter contacted - Interview - Rejected - Offer

### Page 8 --- Settings

Manage: - Candidate profile - Resume preferences - Role filters -
Experience filters - Locations - Work modes - Salary preferences - LLM
configuration - Scheduler time - Source configuration - Gmail OAuth
connection - Notifications - Data export/deletion

### UX requirements

-   No fake or inert buttons.
-   Show loading and workflow states.
-   Display clear errors and retry actions.
-   Show evidence and source links.
-   Make approval actions explicit.
-   Use accessible forms and keyboard navigation.
-   Do not expose secret keys in client-side code.

------------------------------------------------------------------------

## 10. Scheduling and background processing

### 10.1 Daily schedule

Default: 8:00 AM Asia/Kolkata.

Illustrative execution sequence:

  Time    Task
  ------- ------------------------------------
  08:00   Trigger source discovery
  08:15   Extract and normalize listings
  08:30   Deduplicate and save
  08:45   Resume matching
  09:00   Rank opportunities
  09:15   Discover people for priority jobs
  09:30   Generate outreach drafts
  09:45   Update dashboard and notifications

Actual duration depends on source count, rate limits, and model latency.
Do not assume fixed completion times.

### 10.2 Scheduler architecture

The frontend must not be responsible for keeping schedules alive.

Use: - GitHub Actions scheduled workflows, or - A persistent
scheduler/worker, or - Supabase Cron where supported by current project
limits.

A scheduled trigger should create or claim a durable task. A worker
executes it and writes progress to PostgreSQL.

### 10.3 Reliability requirements

-   Persistent execution records
-   Task locking
-   Idempotency
-   Retry with exponential backoff
-   Maximum retry count
-   Source-specific rate limits
-   Dead-letter or failed-task status
-   Manual reruns
-   Execution logs
-   Failure alerts
-   UTC storage and Asia/Kolkata display

Avoid relying on an in-memory scheduler as the only production
scheduler. A sleeping or restarted backend can miss in-memory schedules.

### 10.4 Job run states

-   queued
-   running
-   partially_completed
-   completed
-   failed
-   cancelled

Each source should fail independently so one unavailable website does
not stop the entire discovery run.

------------------------------------------------------------------------

## 11. Deployment and free-tier strategy

The objective is to keep the initial deployment within free allowances.
Zero-cost operation cannot be guaranteed indefinitely because free
quotas, model availability, and provider policies can change.

### Proposed stack

  -------------------------------------------------------------------------
  Component               Option                  Notes
  ----------------------- ----------------------- -------------------------
  Frontend                Vercel Hobby            Intended for
                                                  personal/non-commercial
                                                  use; check current terms

  Database                Supabase Free           Managed PostgreSQL

  Vector search           pgvector                Use same PostgreSQL
                                                  database

  File storage            Supabase Storage        Private bucket and access
                                                  policies

  Scheduler               GitHub Actions          Subject to
                                                  account/repository usage
                                                  limits

  Backend                 Render Free or another  Check sleeping, restart,
                          suitable free Python    and runtime limits
                          host                    

  LLM                     NVIDIA inference        Check exact model and
                          endpoint                free quota

  Source control          GitHub                  Keep secrets out of
                                                  repository
  -------------------------------------------------------------------------

### Cost controls

-   Set usage limits where provider controls allow.
-   Do not enable paid overages without approval.
-   Cache model outputs where appropriate.
-   Avoid repeated analysis of unchanged jobs.
-   Use deterministic preprocessing before calling the LLM.
-   Batch requests only where provider rules permit.
-   Limit daily source count.
-   Limit page fetches and retries.
-   Store only necessary content.
-   Monitor storage and bandwidth.
-   Provide a graceful degraded mode when a free quota is exhausted.

### Important hosting considerations

-   Free web hosts may sleep or restart.
-   Free databases may pause or expire under provider policies.
-   Scheduled jobs may have delays.
-   LLM free quotas may change or be exhausted.
-   A free deployment is suitable for an MVP, not a guarantee of
    always-on production reliability.

Verify provider terms and quotas immediately before deployment.

------------------------------------------------------------------------

## 12. Security, privacy, and AI safety

### 12.1 Application security

-   Supabase authentication.
-   Row Level Security on user-owned data.
-   Server-side secret management.
-   OAuth for Gmail.
-   Encrypted provider tokens.
-   CORS restrictions.
-   API rate limits.
-   File type and size validation.
-   Safe HTML parsing.
-   Secure session handling.
-   Audit logs.
-   Data export and deletion.
-   Minimal collection and retention.

### 12.2 Prompt injection protection

Job descriptions and public webpages are untrusted input.

Requirements: - Treat retrieved content as data, never as
instructions. - Separate system prompts from external content. - Do not
allow retrieved content to change tool permissions. - Do not give
extraction agents email-send or application-submit tools. - Validate
tool arguments server-side. - Keep privileged actions behind approval
services. - Sanitize HTML and reject unsafe URLs. - Restrict outbound
network access where possible.

### 12.3 Approval controls

Mandatory approval before: - Sending Gmail messages - Submitting
applications - Publishing or sharing personal information - Saving a
materially changed resume as the active version - Any irreversible
external action

Record: - User ID - Action - Target - Payload or payload hash - Approval
timestamp - Execution result - External confirmation evidence

------------------------------------------------------------------------

## 13. Prompt library

Prompts should live in version-controlled files, not be scattered across
Python code. Use structured output schemas and validate every model
response.

### 13.1 Job Description Extraction Agent

``` text
SYSTEM ROLE:
You are an expert technical recruitment intelligence analyst.

OBJECTIVE:
Analyze a provided job description and extract hiring requirements
into a structured JSON object.

RULES:
1. Never invent missing information.
2. Separate mandatory skills from preferred skills.
3. Extract exact experience requirements.
4. Identify technical and non-technical responsibilities.
5. Identify languages, frameworks, databases, cloud platforms,
   AI/ML frameworks and infrastructure tools.
6. Identify role seniority.
7. Identify location and work arrangement.
8. Extract salary only when supported by source evidence.
9. Distinguish explicitly stated facts from inferred information.
10. Assign confidence to important extracted fields.
11. Return null when information is unavailable.
12. Do not infer that a skill is mandatory merely because it appears.

INPUT:
Company: {company}
Job URL: {job_url}
Job Description: {job_description}

OUTPUT:
Return valid JSON matching the application's Pydantic schema.

Required keys:
company, job_title, department, seniority, experience,
location, work_mode, employment_type, salary, education,
mandatory_skills, preferred_skills, responsibilities,
technical_requirements, soft_skills, business_domain,
application_deadline, job_source_url, key_hiring_expectations,
missing_information, evidence, confidence.
```

### 13.2 Resume Matching Agent

``` text
SYSTEM ROLE:
You are an expert technical recruiter and ATS resume evaluator.

OBJECTIVE:
Compare a candidate's existing resumes against a job description.

INPUT:
Job Description: {job_description}
Extracted Skills: {job_skills}
Candidate Profile: {candidate_profile}
Available Resumes: {resume_data}

TASK:
1. Evaluate every resume independently.
2. Calculate mandatory skill coverage.
3. Evaluate preferred skill coverage.
4. Identify relevant projects.
5. Identify relevant work experience.
6. Evaluate achievement relevance.
7. Identify missing skills.
8. Identify skills present but poorly highlighted.
9. Select the most suitable resume.
10. Recommend honest improvements.

SCORING:
Technical skills: 35%
Project relevance: 25%
Experience relevance: 15%
Responsibilities: 15%
Domain relevance: 10%

STRICT RULES:
- Never fabricate skills.
- Never invent project achievements.
- Never invent years of experience.
- Do not infer a skill without evidence.
- Explain every score with evidence.
- Distinguish missing evidence from a genuinely missing skill.

OUTPUT:
Return structured JSON containing:
resume_rankings, best_resume_id, overall_match_score,
mandatory_skill_coverage, preferred_skill_coverage,
missing_skills, weakly_highlighted_skills, relevant_projects,
recommended_bullet_changes, recommended_summary,
score_explanation, confidence.
```

### 13.3 People Discovery Agent

``` text
SYSTEM ROLE:
You are a professional company and recruitment research analyst.

OBJECTIVE:
Identify up to 15 relevant publicly discoverable people associated
with the target company and job opening.

INPUT:
Company: {company}
Company Domain: {domain}
Job Title: {job_title}
Department: {department}
Job URL: {job_url}
Retrieved Evidence: {retrieved_people_evidence}

DISCOVER:
- Original job poster
- Recruiters
- Talent acquisition specialists
- HR professionals
- Hiring managers
- Engineering managers
- Team leads
- Department heads
- Relevant employees

RULES:
- Only include people supported by retrieved evidence.
- Do not fabricate names or profiles.
- Do not guess email addresses.
- Only return publicly disclosed professional email addresses.
- Include source URLs for every person.
- Confirm current company association where possible.
- Prefer people associated with the target team.
- Avoid duplicates.
- Explain relevance.
- Return fewer than 15 if fewer are verified.
- Do not bypass access restrictions.

OUTPUT:
Return structured JSON with:
company, people, verified_count, unavailable_count.

Each person must include:
name, designation, department, linkedin_url, public_email,
source_url, current_company_verified, relevance_reason,
relevance_score, confidence.
```

### 13.4 LinkedIn Outreach Agent

``` text
SYSTEM ROLE:
You are an expert professional networking and recruitment
communication assistant.

INPUT:
Candidate Profile: {candidate_profile}
Candidate Achievements: {achievements}
Job Description: {job_description}
Recruiter Information: {recruiter}
Relevant Company Information: {company_context}

GENERATE:
1. LinkedIn connection request.
2. LinkedIn follow-up message.
3. Referral request.
4. Hiring manager message.

RULES:
- Sound natural and professional.
- Avoid generic AI-generated phrases.
- Do not exaggerate experience.
- Mention one relevant achievement.
- Explain why the candidate fits the role.
- Keep the connection request concise.
- Personalize using verified information.
- Never pretend to know the recipient.
- Never claim an existing referral relationship without evidence.

OUTPUT:
Return structured JSON:
connection_request, follow_up_message, referral_request,
hiring_manager_message, personalization_evidence.
```

### 13.5 Gmail Email Generation Agent

``` text
SYSTEM ROLE:
You are an expert professional recruitment email writer.

INPUT:
Candidate Profile: {candidate_profile}
Company: {company}
Job Title: {job_title}
Recipient: {recipient}
Relevant Skills: {skills}
Relevant Achievement: {achievement}
Selected Resume: {resume_name}

GENERATE:
- Subject
- Professional greeting
- Short candidate introduction
- Explanation of role alignment
- One measurable achievement
- Relevant project experience
- Polite request for consideration
- Professional closing

RULES:
- Keep the email concise.
- Do not fabricate information.
- Do not invent recipient email addresses.
- Do not claim an attachment exists unless attached.
- Produce a draft only.

OUTPUT:
Return structured JSON:
recipient, subject, body, recommended_resume_id,
requires_review.
```

### 13.6 Daily Job Recommendation Agent

``` text
SYSTEM ROLE:
You are an AI job recommendation analyst.

INPUT:
Candidate Preferences: {preferences}
Candidate Resumes: {resumes}
Collected Jobs: {jobs}

TASK:
1. Filter jobs by experience eligibility.
2. Identify suitable job titles.
3. Evaluate technical skills.
4. Evaluate project relevance.
5. Evaluate location preferences.
6. Evaluate salary preferences when disclosed.
7. Identify recently posted opportunities.
8. Deduplicate opportunities.
9. Rank relevant jobs.
10. Explain recommendations.

OUTPUT:
Return structured JSON:
recommended_jobs, rejected_jobs, summary.

Each recommended job should contain:
job_id, job_title, company, match_score, best_resume_id,
reason_for_recommendation, missing_skills, priority,
application_url.
```

### 13.7 Resume Improvement Agent

``` text
SYSTEM ROLE:
You are an expert ATS resume editor for software engineering
and AI engineering positions.

INPUT:
Original Resume: {resume}
Job Description: {job_description}
Job Keywords: {keywords}
Resume Analysis: {resume_analysis}

TASK:
1. Identify important keywords missing from the resume.
2. Identify relevant existing achievements.
3. Improve bullet points using action, technology and impact.
4. Improve project descriptions.
5. Improve professional summary.
6. Recommend section ordering.
7. Improve clarity and ATS readability.

STRICT RULES:
- Never create fictional experience.
- Never add unsupported technologies.
- Never invent performance metrics.
- Preserve factual accuracy.
- Show every suggested modification.
- Keep the original resume unchanged.

OUTPUT:
Return structured JSON:
updated_summary, updated_bullets, keywords_to_highlight,
missing_evidence, suggested_changes, factual_validation_required.
```

### 13.8 Prompt engineering requirements

-   Version every prompt.
-   Store prompts in `backend/app/prompts/`.
-   Use Pydantic schemas for outputs.
-   Validate JSON and retry only when appropriate.
-   Keep retrieved external content clearly delimited.
-   Do not place secrets or unnecessary personal data in prompts.
-   Record model ID and prompt version for each agent run.
-   Build a small evaluation dataset with expected outputs.
-   Track extraction accuracy and hallucination rates.

------------------------------------------------------------------------

## 14. Suggested repository structure

``` text
careerpilot-ai/
│
├── frontend/
│   ├── app/
│   │   ├── dashboard/
│   │   ├── jobs/
│   │   ├── resumes/
│   │   ├── people/
│   │   ├── outreach/
│   │   ├── applications/
│   │   └── settings/
│   ├── components/
│   ├── hooks/
│   ├── lib/
│   └── types/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   └── v1/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── agents/
│   │   ├── graphs/
│   │   ├── scrapers/
│   │   ├── scheduler/
│   │   ├── prompts/
│   │   └── utils/
│   ├── tests/
│   ├── alembic/
│   ├── requirements.txt
│   └── Dockerfile
│
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DATABASE_SCHEMA.md
│   ├── API_SPEC.md
│   ├── AGENT_DESIGN.md
│   ├── SECURITY.md
│   └── DEPLOYMENT.md
│
├── .github/
│   └── workflows/
│       └── daily-discovery.yml
│
├── .env.example
├── .gitignore
└── README.md
```

------------------------------------------------------------------------

## 15. Development roadmap

Build incrementally. Do not ask a coding model to generate the entire
product in one pass.

### Phase 1 --- Foundation and job intelligence

Deliver: - Repository setup - FastAPI application - Next.js
application - Supabase connection - Authentication - Database
migrations - Resume upload and parsing - Candidate profile - Manual JD
input - Job extraction - Resume matching - Job score explanation - Job
detail UI

Acceptance: - Upload 5 resumes. - Paste a job description. - Extract
structured requirements. - Rank all available resumes. - Save and
retrieve results after restart.

### Phase 2 --- Job discovery and people intelligence

Deliver: - Source adapter interface - Initial permitted source
adapters - Daily discovery - Normalization - Deduplication - Job
ranking - Company information - Public contact discovery - Contact
provenance - Up-to-15 contact target

Acceptance: - A scheduled run completes without the frontend open. - One
source failure does not stop other sources. - Duplicate jobs are not
duplicated. - Contacts contain evidence-backed source links.

### Phase 3 --- Outreach generation

Deliver: - LinkedIn connection drafts - Follow-up drafts - Referral
drafts - Hiring manager messages - Gmail draft generation - Gmail OAuth
and draft integration - Resume optimization suggestions - Draft review
and approval UI

Acceptance: - Drafts use verified candidate facts. - Unknown emails
remain null. - User can edit drafts. - No message is sent without
approval.

### Phase 4 --- LangGraph orchestration

Deliver: - Separate workflow graphs - Typed states - PostgreSQL
checkpointer - Workflow status tracking - Retry and recovery - Human
approval pauses - Agent run history - Error monitoring

Acceptance: - Workflow resumes after interruption. - Failed nodes can
retry safely. - Approval is enforced server-side. - Agent state is
persisted.

### Phase 5 --- Application preparation

Deliver: - Application answer generation - Resume selection - Tailored
resume versioning - Application preview - Approval workflow - Supported
authorized submission - Manual completion fallback - Application tracker

Acceptance: - No duplicate applications. - No submission without
approval. - Exact resume version is recorded. - Submission status is
backed by confirmation evidence.

### Phase 6 --- Deployment and production hardening

Deliver: - Frontend deployment - Backend deployment - Database
configuration - Scheduler configuration - Health checks - Logs and
monitoring - Security review - Load and failure tests - Documentation

Acceptance: - Production environment variables are configured. - Secrets
are not exposed. - Scheduled execution is observable. - Data access is
user-isolated. - Recovery procedures are documented.

### Estimated timeline

  Phase                          Estimated effort
  ---------------------------- ------------------
  Foundation and JD analysis            4--5 days
  Resume intelligence                   3--4 days
  Job discovery                         4--5 days
  People intelligence                   3--5 days
  Outreach generation                   2--3 days
  LangGraph integration                 3--4 days
  Application preparation               4--6 days
  Deployment and testing                2--3 days
  **Total**                       **25--35 days**

These are planning estimates for one developer, not guaranteed delivery
dates.

------------------------------------------------------------------------

## 16. Acceptance criteria and evaluation

### Functional acceptance tests

  Test                    Expected result
  ----------------------- ----------------------------------------------
  Paste a JD              Structured extraction succeeds
  Paste a LinkedIn post   Extracts information from user-provided text
  Upload five resumes     All five are parsed and stored
  Analyze one job         All available resumes are ranked
  Missing skill           Correctly identified with evidence
  Recruiter search        Only evidence-backed contacts returned
  Contact target          Up to 15 verified people
  Unknown email           Returned as null
  Outreach generation     Personalized drafts created
  Duplicate job           Not saved twice
  Daily scheduler         Runs without frontend open
  Source failure          Logged and isolated
  Salary unavailable      Shown as not disclosed
  Application approval    Submission blocked without approval
  Resume update           Original version preserved
  User isolation          User cannot access another user's data

### Quality metrics

Track: - JD extraction field accuracy - Mandatory-skill precision and
recall - Resume ranking agreement with manual review - Duplicate job
rate - Verified-contact rate - Contact source coverage - Email
hallucination rate --- target zero - Scheduler success rate - Failed
workflow recovery rate - Duplicate application rate --- target zero -
Cost and token usage per analyzed job

Create a manually reviewed evaluation dataset before claiming quality
improvements.

------------------------------------------------------------------------

## 17. Risks and mitigations

  -----------------------------------------------------------------------
  Risk                                Mitigation
  ----------------------------------- -----------------------------------
  Restricted source blocks crawling   Use permitted feeds, public career
                                      pages, alerts, and user-provided
                                      URLs

  Job data is stale                   Store posted and retrieved
                                      timestamps; recheck before
                                      application

  Duplicate listings                  Canonical URLs, source IDs, content
                                      hashes, and merge records

  Hallucinated salary                 Evidence-backed salary
                                      classification; otherwise unknown

  Fake recruiter contacts             Require source URLs and
                                      verification state

  Guessed email addresses             Never generate or label guessed
                                      addresses as verified

  Resume hallucinations               Evidence-only rewriting and user
                                      approval

  Prompt injection                    Treat external content as untrusted
                                      data

  LLM quota exhausted                 Rate limits, caching, queueing,
                                      graceful failure

  Free host sleeps                    External scheduled trigger and
                                      persistent task state

  Database free-tier limit            Monitor storage and retention

  Duplicate application               Unique constraints and idempotency

  Accidental email/application        Server-side human approval gates
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 18. Expected finished-product experience

Example input:

> Company: Example AI Technologies\
> Role: AI Engineer\
> Looking for Python, LLMs, RAG, LangChain, vector databases, and
> FastAPI. Candidates should have experience building production AI
> applications. Experience: 0--2 years.

Expected application output:

### Job summary

-   Company: Example AI Technologies
-   Role: AI Engineer
-   Experience: 0--2 years
-   Location: Extracted from source or unknown
-   Salary: Disclosed range or not disclosed

### Skills

-   Mandatory: Only skills explicitly required
-   Preferred: Skills identified as desirable
-   Responsibilities: Extracted from the JD
-   Evidence: Source snippets

### Resume intelligence

-   All uploaded resumes ranked
-   Best resume recommended
-   Match score and scoring explanation
-   Missing evidence
-   Suggested bullet improvements
-   Original resume preserved

### People intelligence

-   Up to 15 verified contacts
-   Public LinkedIn profile links
-   Public professional email only when disclosed
-   Designation and relevance
-   Evidence and verification status

### Outreach

-   LinkedIn connection request
-   Follow-up message
-   Referral request
-   Hiring manager message
-   Gmail draft

### Application

-   Selected resume
-   Application answer drafts
-   Approval status
-   Application tracking record

All sample data must be clearly labeled as illustrative until actual
research and processing have been completed.

------------------------------------------------------------------------

## 19. Master implementation instruction for a coding AI

Use this section as the instruction prompt for Claude Code, Cursor,
Codex, or another coding model.

### ROLE

Act as a Senior AI Architect, Staff Backend Engineer, Full-Stack
Developer, and AI Agent Engineer.

Design and implement CareerPilot AI according to this complete
specification.

Do not build a basic chatbot. Build a complete application with real
backend workflows, persistent storage, LangGraph orchestration,
scheduled jobs, and a functional frontend.

### TECHNOLOGY

Frontend: - Next.js - TypeScript - Tailwind CSS - shadcn/ui

Backend: - Python - FastAPI - Pydantic - SQLAlchemy - Alembic

AI: - LangChain - LangGraph - NVIDIA Nemotron through a configurable
inference endpoint

Storage: - Supabase PostgreSQL - pgvector - Supabase Storage

Processing: - PyMuPDF - python-docx - httpx - BeautifulSoup - Playwright
where permitted

Scheduling: - GitHub Actions or persistent scheduler/worker

Deployment: - Vercel - Supabase - Suitable free-tier Python host

### REQUIRED MODULES

1.  Job description intelligence
2.  Resume intelligence
3.  People and recruiter intelligence
4.  LinkedIn and Gmail outreach generation
5.  Automated job discovery
6.  Job recommendation and ranking
7.  Application preparation and tracking

### ENGINEERING RULES

1.  Use modular, maintainable code.
2.  Separate business logic from API routes.
3.  Follow SOLID principles where appropriate.
4.  Add type hints.
5.  Use Pydantic validation.
6.  Use structured logging.
7.  Implement proper exception handling.
8.  Write unit and integration tests.
9.  Create database migrations.
10. Provide Docker configuration.
11. Create `.env.example`.
12. Document APIs.
13. Never commit secrets.
14. Avoid unnecessary microservices.
15. Prefer deterministic algorithms over LLM calls where possible.
16. Never use mock data as real results.
17. Never claim an application was submitted without confirmation.
18. Never claim a contact is verified without evidence.
19. Respect website terms and access restrictions.
20. Require approval for external actions.

### DEVELOPMENT PROCESS

Do not generate the whole application at once.

First inspect the repository and identify existing code. Do not
overwrite working code without understanding it.

Then produce: 1. Architecture 2. Database schema 3. API design 4. Agent
workflow design 5. Folder structure 6. Implementation plan

Wait for approval before implementation if the user has not authorized
coding.

Implement Phase 1 first.

At the end of each phase: - Run tests. - Fix errors. - Verify APIs. -
Verify database persistence. - Update documentation. - List completed
functionality. - List remaining work. - Identify risks and assumptions.

Do not proceed if critical functionality is broken.

### INITIAL DELIVERABLES

Before implementation, produce: 1. `PRD.md` 2. `ARCHITECTURE.md` 3.
`DATABASE_SCHEMA.md` 4. `API_SPEC.md` 5. `AGENT_DESIGN.md` 6.
`SECURITY.md` 7. `DEPLOYMENT.md` 8. Repository folder structure 9.
Environment variable list 10. Phase-by-phase implementation plan

The final goal is a reliable personal AI recruitment assistant, not a
collection of disconnected agents or a scraper that merely collects
listings.

------------------------------------------------------------------------

## 20. Recommended first milestone

The first working version should achieve this complete flow:

**Paste job description → Extract requirements → Compare 5--10 resumes →
Recommend the best resume → Find evidence-backed company contacts →
Generate LinkedIn and Gmail drafts → Save everything.**

Only after this works reliably should the project add daily job
discovery at scale and application automation.

This sequencing creates useful functionality early, keeps the system
testable, and reduces the risk of spending substantial time on a crawler
before the candidate intelligence and job matching features are
reliable.

------------------------------------------------------------------------

## 21. Final architecture decisions

  Decision               Recommendation
  ---------------------- ----------------------------------------------
  Product architecture   Modular monolith
  Backend                FastAPI
  Frontend               Next.js + TypeScript
  AI orchestration       Multiple LangGraph workflows
  LLM                    Configurable NVIDIA Nemotron endpoint
  Database               Supabase PostgreSQL
  Vector search          pgvector
  Document storage       Supabase Storage
  Job discovery          Modular, permitted source adapters
  Scheduling             Persistent task records + scheduled trigger
  Resume scoring         Deterministic weighted scoring with evidence
  People discovery       Evidence-backed public research
  Outreach               Draft-first workflow
  Applications           Human-approved workflow
  Deployment             Free-tier-first, quota-aware

**Core principle:** Build a trustworthy job intelligence system first.
Automation should come only after the system can reliably explain where
its information came from, why a job matches, which resume is
appropriate, and what action it proposes.
