"""Importing the workflow modules registers their task handlers."""


def register_all() -> None:
    from app.graphs import (  # noqa: F401
        application_preparation,
        daily_pipeline,
        job_discovery,
        job_extraction,
        outreach_generation,
        people_discovery,
        resume_ingestion,
        resume_matching,
        resume_optimization,
    )
    from app.services import account  # noqa: F401  (export task handler)
