"""Unit tests for SQLAlchemy 2.0 entity models and Pydantic validation schemas."""

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.entities import (
    Candidate,
    CandidateExperience,
    CandidateSkill,
    IngestionBatch,
    IngestionError,
    JobDescription,
    JobSkill,
    MatchingEvaluation,
    OperationalMetric,
    Skill,
)
from src.models.schemas import (
    CandidateProfileDTO,
    MatchingEvaluationDTO,
    RawCandidateSchema,
    RawExperienceInput,
    RawJobDescriptionSchema,
    RawJobSkillInput,
    RawOperationalMetricSchema,
    RawSkillInput,
)


# --- Entity Model Database Tests ---

def test_skill_creation_and_uniqueness(db_session: Session) -> None:
    """Verify skill creation and unique constraint on normalized_key."""
    skill1 = Skill(name="Python", category="technical", normalized_key="python")
    db_session.add(skill1)
    db_session.commit()

    assert skill1.skill_id is not None
    assert skill1.name == "Python"
    assert skill1.normalized_key == "python"

    # Attempt inserting duplicate normalized_key
    skill2 = Skill(name="Python 3", category="technical", normalized_key="python")
    db_session.add(skill2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_candidate_creation_and_email_uniqueness(db_session: Session) -> None:
    """Verify candidate creation and unique constraint on email."""
    cand1 = Candidate(
        candidate_id="c-test-01",
        full_name="Alice Martin",
        email="alice.martin@example.com",
        location="Paris, France",
        years_of_experience=Decimal("5.0"),
        education_level="Master in CS",
        raw_cv_text="Detailed resume text with more than twenty characters.",
    )
    db_session.add(cand1)
    db_session.commit()

    # Attempt duplicate email
    cand2 = Candidate(
        candidate_id="c-test-02",
        full_name="Alice Duplicate",
        email="alice.martin@example.com",
        location="Lyon, France",
        years_of_experience=Decimal("2.0"),
        education_level="Bachelor in CS",
        raw_cv_text="Another detailed resume text with more than twenty characters.",
    )
    db_session.add(cand2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_candidate_skills_relationship_and_cascade(db_session: Session) -> None:
    """Verify candidate-skills association and cascade deletion."""
    cand = Candidate(
        candidate_id="c-test-03",
        full_name="Bob Dupont",
        email="bob.dupont@example.com",
        location="Bordeaux, France",
        years_of_experience=Decimal("3.0"),
        education_level="Master",
        raw_cv_text="Software engineer with strong background in backend systems.",
    )
    skill = Skill(name="FastAPI", category="technical", normalized_key="fastapi")
    db_session.add_all([cand, skill])
    db_session.commit()

    assoc = CandidateSkill(
        candidate_id=cand.candidate_id,
        skill_id=skill.skill_id,
        proficiency_level="expert",
        years_experience=Decimal("3.0"),
        is_primary=True,
    )
    db_session.add(assoc)
    db_session.commit()

    # Assert relation loaded
    assert len(cand.skills) == 1
    assert cand.skills[0].skill.name == "FastAPI"

    # Delete candidate and check cascade
    db_session.delete(cand)
    db_session.commit()

    assert db_session.get(CandidateSkill, assoc.id) is None
    # Skill catalog itself should remain
    assert db_session.get(Skill, skill.skill_id) is not None


def test_candidate_experiences_cascade(db_session: Session) -> None:
    """Verify candidate experience association and cascade deletion."""
    cand = Candidate(
        candidate_id="c-test-04",
        full_name="Charles Blanc",
        email="charles.blanc@example.com",
        location="Nantes, France",
        years_of_experience=Decimal("2.0"),
        education_level="Bachelor",
        raw_cv_text="Junior developer with web and backend application experience.",
    )
    db_session.add(cand)
    db_session.commit()

    exp = CandidateExperience(
        candidate_id=cand.candidate_id,
        company="Tech Ouest",
        role_title="Backend Developer",
        start_date=date(2022, 1, 1),
        end_date=date(2023, 1, 1),
        is_current=False,
        description="Built REST APIs.",
        technologies="Python, SQL",
    )
    cand.experiences.append(exp)
    db_session.commit()

    exp_id = exp.id
    assert exp_id is not None
    assert len(cand.experiences) == 1

    # Delete candidate
    db_session.delete(cand)
    db_session.commit()
    assert db_session.get(CandidateExperience, exp_id) is None


def test_job_description_skills_cascade(db_session: Session) -> None:
    """Verify job description skills association and cascade deletion."""
    job = JobDescription(
        job_id="j-test-01",
        job_code="JOB-TEST-001",
        title="Data Engineer",
        department="Data",
        location="Paris, France",
        employment_type="Full-time",
        experience_min_years=Decimal("3.0"),
        raw_description="Looking for a data engineer proficient in distributed pipelines.",
    )
    skill = Skill(name="Airflow", category="technical", normalized_key="airflow")
    db_session.add_all([job, skill])
    db_session.commit()

    job_skill = JobSkill(
        job_id=job.job_id,
        skill_id=skill.skill_id,
        importance="required",
        weight=Decimal("1.00"),
        min_years=Decimal("2.0"),
    )
    job.skills.append(job_skill)
    db_session.commit()

    js_id = job_skill.id
    assert js_id is not None

    # Delete job description
    db_session.delete(job)
    db_session.commit()
    assert db_session.get(JobSkill, js_id) is None


def test_matching_evaluation_persistence_and_uniqueness(db_session: Session) -> None:
    """Verify matching evaluation persistence and uniqueness constraint on candidate and job."""
    cand = Candidate(
        candidate_id="c-test-eval",
        full_name="David Moreau",
        email="david.moreau@example.com",
        location="Paris, France",
        years_of_experience=Decimal("4.0"),
        education_level="Master",
        raw_cv_text="Data specialist with experience in machine learning and analytics.",
    )
    job = JobDescription(
        job_id="j-test-eval",
        job_code="JOB-EVAL-01",
        title="ML Engineer",
        department="AI",
        location="Paris, France",
        raw_description="Machine learning engineer vacancy with deep learning focus.",
    )
    db_session.add_all([cand, job])
    db_session.commit()

    eval_1 = MatchingEvaluation(
        evaluation_id="eval-01",
        candidate_id=cand.candidate_id,
        job_id=job.job_id,
        overall_score=Decimal("85.50"),
        skills_score=Decimal("90.00"),
        experience_score=Decimal("80.00"),
        semantic_similarity=Decimal("0.8450"),
        recommendation="hire",
        matched_skills=json.dumps(["Python", "Scikit-Learn"]),
        missing_skills=json.dumps(["Kubernetes"]),
        strengths_summary="Solid core machine learning experience.",
        gaps_summary="Missing container orchestration experience.",
        executive_summary="Candidate demonstrates strong fit for the position.",
    )
    db_session.add(eval_1)
    db_session.commit()

    assert eval_1.evaluation_id == "eval-01"
    assert eval_1.candidate.full_name == "David Moreau"

    # Attempt inserting duplicate evaluation for identical (candidate_id, job_id)
    eval_duplicate = MatchingEvaluation(
        evaluation_id="eval-02",
        candidate_id=cand.candidate_id,
        job_id=job.job_id,
        overall_score=Decimal("70.00"),
        skills_score=Decimal("70.00"),
        experience_score=Decimal("70.00"),
        semantic_similarity=Decimal("0.7000"),
        recommendation="consider",
        matched_skills="[]",
        missing_skills="[]",
        strengths_summary="Average.",
        gaps_summary="Some gaps.",
        executive_summary="Re-evaluated.",
    )
    db_session.add(eval_duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_operational_metrics_referential_integrity(db_session: Session) -> None:
    """Verify foreign key enforcement on operational metrics via PRAGMA foreign_keys."""
    metric_orphan = OperationalMetric(
        metric_id="met-orphan",
        candidate_id="non-existent-cand",
        job_id="non-existent-job",
        application_date=date(2024, 1, 1),
        hiring_decision="applied",
    )
    db_session.add(metric_orphan)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_ingestion_batch_and_error_cascade(db_session: Session) -> None:
    """Verify batch audit and error quarantine cascade deletion."""
    batch = IngestionBatch(
        batch_id="batch-test-01",
        source_filename="test_candidates.json",
        source_type="candidates_json",
        records_extracted=5,
        records_validated=4,
        records_loaded=4,
        records_rejected=1,
        status="partial",
    )
    db_session.add(batch)
    db_session.commit()

    err = IngestionError(
        batch_id=batch.batch_id,
        raw_record_index=4,
        raw_data='{"invalid": "data"}',
        error_type="ValidationError",
        error_details="Email missing",
    )
    batch.errors.append(err)
    db_session.commit()

    err_id = err.error_id
    assert err_id is not None
    assert len(batch.errors) == 1

    # Delete batch
    db_session.delete(batch)
    db_session.commit()
    assert db_session.get(IngestionError, err_id) is None


# --- Pydantic v2 Schema Validation Tests ---

def test_raw_candidate_schema_validation_success(sample_candidate_dict: dict) -> None:
    """Verify valid candidate dictionary passes Pydantic validation."""
    schema = RawCandidateSchema.model_validate(sample_candidate_dict)
    assert schema.full_name == "Claire Bernard"
    assert schema.email == "claire.bernard.test@example.com"
    assert len(schema.skills) == 3
    assert len(schema.experiences) == 1


def test_raw_candidate_schema_invalid_email(sample_candidate_dict: dict) -> None:
    """Verify invalid email syntax raises ValidationError."""
    sample_candidate_dict["email"] = "not-an-email"
    with pytest.raises(ValidationError) as exc:
        RawCandidateSchema.model_validate(sample_candidate_dict)
    assert "email" in str(exc.value)


def test_raw_candidate_schema_negative_experience(sample_candidate_dict: dict) -> None:
    """Verify negative years of experience raises ValidationError."""
    sample_candidate_dict["years_of_experience"] = -2.5
    with pytest.raises(ValidationError):
        RawCandidateSchema.model_validate(sample_candidate_dict)


def test_raw_candidate_schema_short_cv(sample_candidate_dict: dict) -> None:
    """Verify excessively short CV text (<20 characters) raises ValidationError."""
    sample_candidate_dict["raw_cv_text"] = "Too short."
    with pytest.raises(ValidationError):
        RawCandidateSchema.model_validate(sample_candidate_dict)


def test_raw_experience_invalid_dates() -> None:
    """Verify end_date preceding start_date raises ValidationError."""
    data = {
        "company": "Enterprise SAS",
        "role_title": "Software Engineer",
        "start_date": "2023-01-01",
        "end_date": "2022-01-01",
        "is_current": False,
    }
    with pytest.raises(ValidationError):
        RawExperienceInput.model_validate(data)


def test_raw_job_description_salary_bounds(sample_job_dict: dict) -> None:
    """Verify salary_range_max lower than salary_range_min raises ValidationError."""
    sample_job_dict["salary_range_min"] = 80000.0
    sample_job_dict["salary_range_max"] = 50000.0
    with pytest.raises(ValidationError):
        RawJobDescriptionSchema.model_validate(sample_job_dict)


def test_raw_job_description_status_enum(sample_job_dict: dict) -> None:
    """Verify invalid status literal raises ValidationError."""
    sample_job_dict["status"] = "unknown_status"
    with pytest.raises(ValidationError):
        RawJobDescriptionSchema.model_validate(sample_job_dict)


def test_raw_operational_metric_missing_identifiers() -> None:
    """Verify metric without candidate or job reference raises ValidationError."""
    data = {
        "application_date": "2024-01-01",
        "hiring_decision": "applied",
    }
    with pytest.raises(ValidationError):
        RawOperationalMetricSchema.model_validate(data)


def test_raw_operational_metric_decision_enum(sample_metric_dict: dict) -> None:
    """Verify invalid hiring decision literal raises ValidationError."""
    sample_metric_dict["hiring_decision"] = "promoted"
    with pytest.raises(ValidationError):
        RawOperationalMetricSchema.model_validate(sample_metric_dict)


def test_skill_whitespace_validation() -> None:
    """Verify skill name with only whitespace raises ValidationError."""
    with pytest.raises(ValidationError):
        RawSkillInput.model_validate({"name": "   "})
