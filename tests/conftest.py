"""Shared pytest configuration, fixtures, and mock test datasets."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Generator

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.models.entities import (
    Base,
    create_db_engine,
    get_session_factory,
    init_db,
)


@pytest.fixture
def tmp_sqlite_engine() -> Generator[Engine, None, None]:
    """Provide an isolated in-memory SQLite engine with PRAGMA foreign_keys enabled."""
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(tmp_sqlite_engine: Engine) -> Generator[Session, None, None]:
    """Provide an active database session for a single test."""
    session_factory = get_session_factory(tmp_sqlite_engine)
    with session_factory() as session:
        yield session
        session.rollback()


@pytest.fixture
def raw_data_dir() -> Path:
    """Return path to project raw data directory."""
    return Path(__file__).resolve().parent.parent / "data" / "raw"


@pytest.fixture
def sample_candidate_dict() -> Dict[str, Any]:
    """Return a valid raw candidate dictionary."""
    return {
        "candidate_id": "cand-test-01",
        "full_name": "Claire Bernard",
        "email": "claire.bernard.test@example.com",
        "phone": "+33 6 11 22 33 44",
        "location": "Paris, France",
        "current_title": "Data Engineer",
        "years_of_experience": 4.5,
        "education_level": "Master in Data Engineering",
        "raw_cv_text": "Experienced Data Engineer with 4.5 years developing batch and streaming pipelines using Python, SQL, and Apache Spark on AWS.",
        "linkedin_url": "https://linkedin.com/in/claire-bernard-test",
        "github_url": "https://github.com/cbernard-test",
        "skills": [
            {
                "name": "Python",
                "category": "technical",
                "proficiency_level": "advanced",
                "years_experience": 4.5,
                "is_primary": True,
            },
            {
                "name": "SQL",
                "category": "technical",
                "proficiency_level": "advanced",
                "years_experience": 4.5,
                "is_primary": True,
            },
            {
                "name": "Apache Spark",
                "category": "technical",
                "proficiency_level": "intermediate",
                "years_experience": 3.0,
                "is_primary": False,
            },
        ],
        "experiences": [
            {
                "company": "CloudAnalytics SAS",
                "role_title": "Data Engineer",
                "start_date": "2020-01-01",
                "end_date": None,
                "is_current": True,
                "description": "Constructed streaming ingestion using Kafka and Spark.",
                "technologies": "Python, Spark, Kafka, AWS",
            }
        ],
    }


@pytest.fixture
def sample_job_dict() -> Dict[str, Any]:
    """Return a valid raw job description dictionary."""
    return {
        "job_id": "job-test-01",
        "job_code": "JOB-TEST-DE",
        "title": "Senior Data Platform Engineer",
        "department": "Platform Engineering",
        "location": "Paris, France",
        "employment_type": "Full-time",
        "experience_min_years": 4.0,
        "education_level_required": "Master in Computer Science",
        "salary_range_min": 60000.0,
        "salary_range_max": 75000.0,
        "currency": "EUR",
        "status": "open",
        "raw_description": "We are seeking a Senior Data Platform Engineer to design and optimize data pipelines using Python, SQL, and Apache Spark on cloud infrastructure.",
        "skills": [
            {
                "name": "Python",
                "category": "technical",
                "importance": "required",
                "weight": 1.0,
                "min_years": 3.0,
            },
            {
                "name": "SQL",
                "category": "technical",
                "importance": "required",
                "weight": 1.0,
                "min_years": 3.0,
            },
            {
                "name": "Apache Spark",
                "category": "technical",
                "importance": "preferred",
                "weight": 0.8,
                "min_years": 2.0,
            },
        ],
    }


@pytest.fixture
def sample_metric_dict() -> Dict[str, Any]:
    """Return a valid raw operational metric dictionary."""
    return {
        "metric_id": "met-test-01",
        "candidate_email": "claire.bernard.test@example.com",
        "job_code": "JOB-TEST-DE",
        "application_date": "2024-01-10",
        "screening_date": "2024-01-11",
        "technical_interview_date": "2024-01-18",
        "final_interview_date": "2024-01-25",
        "offer_date": "2024-01-30",
        "hiring_decision": "hired",
        "time_to_screen_hours": 12.0,
        "automated_screening_time_seconds": 2.2,
        "manual_screening_estimated_minutes": 45.0,
        "recruiter_name": "Sarah Martin",
        "sourcing_channel": "LinkedIn",
        "cost_per_applicant_eur": 80.0,
    }
