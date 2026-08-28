"""Unit tests for ETL extractors, transformers, loaders, and orchestration pipeline."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.etl.extractors import (
    DataExtractionError,
    extract_csv,
    extract_json,
)
from src.etl.loaders import (
    save_matching_evaluation,
    upsert_candidate,
    upsert_job_description,
    upsert_operational_metric,
    upsert_skill,
)
from src.etl.pipeline import (
    ETLPipeline,
    ingest_candidates,
    ingest_job_descriptions,
    ingest_operational_metrics,
)
from src.etl.transformers import (
    calculate_experience_years,
    normalize_skill_key,
    parse_date,
    transform_candidate,
    transform_job_description,
    transform_operational_metric,
)
from src.models.entities import (
    Candidate,
    CandidateSkill,
    IngestionBatch,
    IngestionError,
    JobDescription,
    MatchingEvaluation,
    OperationalMetric,
    Skill,
)
from src.models.schemas import (
    MatchingEvaluationDTO,
    RawCandidateSchema,
    RawJobDescriptionSchema,
    RawOperationalMetricSchema,
)


# --- Extractor Tests ---

def test_extract_json_valid(tmp_path: Path) -> None:
    """Verify JSON extraction parses valid JSON arrays."""
    file = tmp_path / "valid.json"
    file.write_text(json.dumps([{"id": 1, "name": "Item A"}]), encoding="utf-8")
    data = extract_json(file)
    assert len(data) == 1
    assert data[0]["name"] == "Item A"


def test_extract_json_wrapper_dict(tmp_path: Path) -> None:
    """Verify JSON extraction handles wrapped payloads (e.g. {'candidates': [...]})."""
    file = tmp_path / "wrapped.json"
    file.write_text(json.dumps({"candidates": [{"id": "c1"}, {"id": "c2"}]}), encoding="utf-8")
    data = extract_json(file)
    assert len(data) == 2


def test_extract_json_missing_file() -> None:
    """Verify extract_json raises FileNotFoundError when target does not exist."""
    with pytest.raises(FileNotFoundError):
        extract_json("non_existent_path_404.json")


def test_extract_json_malformed(tmp_path: Path) -> None:
    """Verify extract_json raises DataExtractionError on malformed syntax."""
    file = tmp_path / "broken.json"
    file.write_text("{ broken: json", encoding="utf-8")
    with pytest.raises(DataExtractionError):
        extract_json(file)


def test_extract_csv_valid(tmp_path: Path) -> None:
    """Verify CSV extraction parses header and records."""
    file = tmp_path / "valid.csv"
    file.write_text("col_a,col_b\nval1,val2\nval3,val4\n", encoding="utf-8")
    data = extract_csv(file)
    assert len(data) == 2
    assert data[0]["col_a"] == "val1"


def test_extract_csv_missing_file() -> None:
    """Verify extract_csv raises FileNotFoundError for missing path."""
    with pytest.raises(FileNotFoundError):
        extract_csv("non_existent_file_404.csv")


def test_extract_csv_empty(tmp_path: Path) -> None:
    """Verify empty CSV raises DataExtractionError."""
    file = tmp_path / "empty.csv"
    file.write_text("", encoding="utf-8")
    with pytest.raises(DataExtractionError):
        extract_csv(file)


# --- Transformer Tests ---

@pytest.mark.parametrize(
    "raw_name, expected_key",
    [
        ("  PostgreSQL ", "postgresql"),
        ("C++", "cpp"),
        ("C#", "csharp"),
        ("Node.js", "node_js"),
        ("CI/CD", "ci_cd"),
        (".NET", "dotnet"),
        ("Scikit-Learn", "scikit_learn"),
        ("Apache Spark", "apache_spark"),
    ],
)
def test_normalize_skill_key(raw_name: str, expected_key: str) -> None:
    """Verify normalization turns diverse skill tokens into canonical keys."""
    assert normalize_skill_key(raw_name) == expected_key


def test_parse_date_formats() -> None:
    """Verify date parsing handles multiple representations."""
    assert parse_date("2024-03-15") == date(2024, 3, 15)
    assert parse_date("2024/03/15") == date(2024, 3, 15)
    assert parse_date("15/03/2024") == date(2024, 3, 15)
    assert parse_date(date(2024, 3, 15)) == date(2024, 3, 15)
    assert parse_date(None) is None
    assert parse_date("") is None
    assert parse_date("not-a-date") is None


def test_calculate_experience_years() -> None:
    """Verify tenure calculation in decimal years."""
    # 2 years span
    res = calculate_experience_years(date(2020, 1, 1), date(2022, 1, 1))
    assert res == Decimal("2.0")

    # Inverted dates should return 0.0
    res_inv = calculate_experience_years(date(2022, 1, 1), date(2020, 1, 1))
    assert res_inv == Decimal("0.0")


def test_transform_candidate_generates_id(sample_candidate_dict: dict) -> None:
    """Verify candidate transformation generates UUID if not provided."""
    sample_candidate_dict.pop("candidate_id", None)
    transformed = transform_candidate(sample_candidate_dict)
    assert transformed.candidate_id is not None
    assert len(transformed.candidate_id) > 10


def test_transform_job_description_generates_id(sample_job_dict: dict) -> None:
    """Verify job description transformation generates UUID if not provided."""
    sample_job_dict.pop("job_id", None)
    transformed = transform_job_description(sample_job_dict)
    assert transformed.job_id is not None
    assert len(transformed.job_id) > 10


def test_transform_operational_metric_cleans_empty_strings(sample_metric_dict: dict) -> None:
    """Verify operational metric cleans empty date/number strings to None or defaults."""
    sample_metric_dict["screening_date"] = ""
    sample_metric_dict["time_to_screen_hours"] = ""
    transformed = transform_operational_metric(sample_metric_dict)
    assert transformed.screening_date is None
    assert transformed.time_to_screen_hours is None


# --- Loader Tests ---

def test_upsert_skill_idempotent(db_session: Session) -> None:
    """Verify upsert_skill returns identical instance on multiple invocations."""
    sk1 = upsert_skill(db_session, "Python", "technical")
    sk2 = upsert_skill(db_session, " python ", "technical")
    assert sk1.skill_id == sk2.skill_id

    all_skills = db_session.execute(select(Skill)).scalars().all()
    assert len(all_skills) == 1


def test_upsert_candidate_insert_and_update(db_session: Session, sample_candidate_dict: dict) -> None:
    """Verify upsert_candidate correctly inserts then updates candidate record."""
    schema = RawCandidateSchema.model_validate(sample_candidate_dict)
    cand = upsert_candidate(db_session, schema)
    db_session.commit()

    assert cand.full_name == "Claire Bernard"
    assert len(cand.skills) == 3

    # Update title and reduce skills
    sample_candidate_dict["current_title"] = "Lead Data Engineer"
    sample_candidate_dict["skills"] = [
        {"name": "Python", "category": "technical", "proficiency_level": "expert", "years_experience": 5.0}
    ]
    schema2 = RawCandidateSchema.model_validate(sample_candidate_dict)
    cand_updated = upsert_candidate(db_session, schema2)
    db_session.commit()

    assert cand_updated.candidate_id == cand.candidate_id
    assert cand_updated.current_title == "Lead Data Engineer"
    assert len(cand_updated.skills) == 1
    assert cand_updated.skills[0].skill.name == "Python"


def test_upsert_job_description_insert_and_update(db_session: Session, sample_job_dict: dict) -> None:
    """Verify upsert_job_description inserts and updates vacancy records."""
    schema = RawJobDescriptionSchema.model_validate(sample_job_dict)
    job = upsert_job_description(db_session, schema)
    db_session.commit()

    assert job.title == "Senior Data Platform Engineer"
    assert len(job.skills) == 3

    # Update job
    sample_job_dict["title"] = "Principal Data Platform Engineer"
    schema2 = RawJobDescriptionSchema.model_validate(sample_job_dict)
    job_updated = upsert_job_description(db_session, schema2)
    db_session.commit()

    assert job_updated.job_id == job.job_id
    assert job_updated.title == "Principal Data Platform Engineer"


def test_upsert_operational_metric_natural_key_resolution(
    db_session: Session,
    sample_candidate_dict: dict,
    sample_job_dict: dict,
    sample_metric_dict: dict,
) -> None:
    """Verify operational metric resolves candidate_id and job_id from email and code."""
    upsert_candidate(db_session, RawCandidateSchema.model_validate(sample_candidate_dict))
    upsert_job_description(db_session, RawJobDescriptionSchema.model_validate(sample_job_dict))
    db_session.commit()

    metric_schema = RawOperationalMetricSchema.model_validate(sample_metric_dict)
    metric = upsert_operational_metric(db_session, metric_schema)
    db_session.commit()

    assert metric.candidate.email == "claire.bernard.test@example.com"
    assert metric.job.job_code == "JOB-TEST-DE"
    assert metric.hiring_decision == "hired"


def test_upsert_operational_metric_unresolvable_candidate(db_session: Session, sample_metric_dict: dict) -> None:
    """Verify attempting to upsert metric with non-existent candidate raises ValueError."""
    sample_metric_dict["candidate_email"] = "unknown@candidate.com"
    metric_schema = RawOperationalMetricSchema.model_validate(sample_metric_dict)
    with pytest.raises(ValueError) as exc:
        upsert_operational_metric(db_session, metric_schema)
    assert "Candidate not found" in str(exc.value)


def test_save_matching_evaluation_idempotent(
    db_session: Session,
    sample_candidate_dict: dict,
    sample_job_dict: dict,
) -> None:
    """Verify saving matching evaluations creates and updates evaluations."""
    cand = upsert_candidate(db_session, RawCandidateSchema.model_validate(sample_candidate_dict))
    job = upsert_job_description(db_session, RawJobDescriptionSchema.model_validate(sample_job_dict))
    db_session.commit()

    dto = MatchingEvaluationDTO(
        candidate_id=cand.candidate_id,
        job_id=job.job_id,
        overall_score=Decimal("88.00"),
        skills_score=Decimal("92.00"),
        experience_score=Decimal("85.00"),
        semantic_similarity=Decimal("0.8900"),
        recommendation="hire",
        matched_skills=["Python", "SQL"],
        missing_skills=["Kubernetes"],
        strengths_summary="High technical proficiency.",
        gaps_summary="Lacks orchestration.",
        executive_summary="Strong recommended candidate.",
    )

    ev1 = save_matching_evaluation(db_session, dto)
    db_session.commit()
    assert ev1.overall_score == Decimal("88.00")

    # Update score
    dto.overall_score = Decimal("91.50")
    ev2 = save_matching_evaluation(db_session, dto)
    db_session.commit()

    assert ev2.evaluation_id == ev1.evaluation_id
    assert ev2.overall_score == Decimal("91.50")


# --- Pipeline & Quarantine Orchestration Tests ---

def test_ingest_raw_datasets_complete(db_session: Session, raw_data_dir: Path) -> None:
    """Verify ingestion of the generated sample datasets in data/raw."""
    # 1. Candidates
    cand_summary = ingest_candidates(raw_data_dir / "candidates.json", db_session)
    assert cand_summary.status == "completed"
    assert cand_summary.records_loaded == 10
    assert cand_summary.records_rejected == 0

    # 2. Job Descriptions
    job_summary = ingest_job_descriptions(raw_data_dir / "job_descriptions.json", db_session)
    assert job_summary.status == "completed"
    assert job_summary.records_loaded == 4
    assert job_summary.records_rejected == 0

    # 3. Operational Metrics
    metric_summary = ingest_operational_metrics(raw_data_dir / "operational_metrics.csv", db_session)
    assert metric_summary.status == "completed"
    assert metric_summary.records_loaded == 36
    assert metric_summary.records_rejected == 0


def test_quarantine_malformed_records(db_session: Session, tmp_path: Path) -> None:
    """Verify malformed records are quarantined in ingestion_errors without aborting the batch."""
    records = [
        # Valid candidate
        {
            "full_name": "Valid Candidate",
            "email": "valid.candidate@example.com",
            "location": "Paris",
            "education_level": "Master",
            "years_of_experience": 3.0,
            "raw_cv_text": "Experienced data professional with complete background details.",
        },
        # Invalid 1: malformed email
        {
            "full_name": "Invalid Email",
            "email": "invalid-email-address",
            "location": "Paris",
            "education_level": "Master",
            "years_of_experience": 3.0,
            "raw_cv_text": "Experienced data professional with complete background details.",
        },
        # Invalid 2: negative experience
        {
            "full_name": "Negative Exp",
            "email": "negative.exp@example.com",
            "location": "Lyon",
            "education_level": "Bachelor",
            "years_of_experience": -5.0,
            "raw_cv_text": "Experienced data professional with complete background details.",
        },
    ]

    mock_file = tmp_path / "mixed_candidates.json"
    mock_file.write_text(json.dumps(records), encoding="utf-8")

    summary = ingest_candidates(mock_file, db_session)
    db_session.commit()

    assert summary.status == "partial"
    assert summary.records_extracted == 3
    assert summary.records_loaded == 1
    assert summary.records_rejected == 2

    # Check quarantine table contents
    errors = db_session.execute(
        select(IngestionError).where(IngestionError.batch_id == summary.batch_id)
    ).scalars().all()

    assert len(errors) == 2
    assert any("invalid-email-address" in err.raw_data for err in errors)
    assert any("negative.exp" in err.raw_data for err in errors)


def test_pipeline_run_all_idempotent(tmp_sqlite_engine, raw_data_dir: Path) -> None:
    """Verify full pipeline runs idempotently against raw data directory."""
    pipeline = ETLPipeline(engine=tmp_sqlite_engine)

    # First execution
    res1 = pipeline.run_all(raw_data_dir=raw_data_dir)
    assert res1["candidates"].records_loaded == 10
    assert res1["job_descriptions"].records_loaded == 4
    assert res1["operational_metrics"].records_loaded == 36

    # Second execution (idempotency check)
    res2 = pipeline.run_all(raw_data_dir=raw_data_dir)
    assert res2["candidates"].records_loaded == 10
    assert res2["job_descriptions"].records_loaded == 4
    assert res2["operational_metrics"].records_loaded == 36

    # Assert total counts in tables are strictly un-duplicated
    session_factory = pipeline.session_factory
    with session_factory() as session:
        assert session.query(Candidate).count() == 10
        assert session.query(JobDescription).count() == 4
        assert session.query(OperationalMetric).count() == 36


def test_upsert_operational_metric_direct_ids_success(
    db_session: Session,
    sample_candidate_dict: dict,
    sample_job_dict: dict,
    sample_metric_dict: dict,
) -> None:
    """Verify operational metric succeeds when referencing valid candidate_id and job_id directly."""
    cand = upsert_candidate(db_session, RawCandidateSchema.model_validate(sample_candidate_dict))
    job = upsert_job_description(db_session, RawJobDescriptionSchema.model_validate(sample_job_dict))
    db_session.commit()

    metric_data = sample_metric_dict.copy()
    metric_data.pop("candidate_email", None)
    metric_data.pop("job_code", None)
    metric_data["candidate_id"] = cand.candidate_id
    metric_data["job_id"] = job.job_id

    metric_schema = RawOperationalMetricSchema.model_validate(metric_data)
    metric = upsert_operational_metric(db_session, metric_schema)
    db_session.commit()

    assert metric.candidate_id == cand.candidate_id
    assert metric.job_id == job.job_id


def test_upsert_operational_metric_unresolvable_direct_candidate_id(
    db_session: Session,
    sample_job_dict: dict,
    sample_metric_dict: dict,
) -> None:
    """Verify attempting to upsert metric with non-existent direct candidate_id raises ValueError."""
    job = upsert_job_description(db_session, RawJobDescriptionSchema.model_validate(sample_job_dict))
    db_session.commit()

    metric_data = sample_metric_dict.copy()
    metric_data.pop("candidate_email", None)
    metric_data["candidate_id"] = "non-existent-candidate-id-001"
    metric_data["job_id"] = job.job_id

    metric_schema = RawOperationalMetricSchema.model_validate(metric_data)
    with pytest.raises(ValueError) as exc:
        upsert_operational_metric(db_session, metric_schema)
    assert "Candidate not found for candidate_id" in str(exc.value)


def test_upsert_operational_metric_unresolvable_direct_job_id(
    db_session: Session,
    sample_candidate_dict: dict,
    sample_metric_dict: dict,
) -> None:
    """Verify attempting to upsert metric with non-existent direct job_id raises ValueError."""
    cand = upsert_candidate(db_session, RawCandidateSchema.model_validate(sample_candidate_dict))
    db_session.commit()

    metric_data = sample_metric_dict.copy()
    metric_data.pop("job_code", None)
    metric_data["candidate_id"] = cand.candidate_id
    metric_data["job_id"] = "non-existent-job-id-001"

    metric_schema = RawOperationalMetricSchema.model_validate(metric_data)
    with pytest.raises(ValueError) as exc:
        upsert_operational_metric(db_session, metric_schema)
    assert "Job description not found for job_id" in str(exc.value)


def test_quarantine_database_flush_integrity_error(db_session: Session, tmp_path: Path) -> None:
    """Verify database-level integrity errors (PK conflict) are quarantined via savepoints without aborting batch."""
    records = [
        {
            "candidate_id": "cand-duplicate-pk-100",
            "full_name": "First Candidate",
            "email": "first.cand@example.com",
            "location": "Paris",
            "education_level": "Master",
            "years_of_experience": 5.0,
            "raw_cv_text": "Experienced software engineer with valid background details.",
        },
        {
            "candidate_id": "cand-duplicate-pk-100",
            "full_name": "Conflicting Candidate",
            "email": "conflicting.cand@example.com",
            "location": "Lyon",
            "education_level": "Master",
            "years_of_experience": 3.0,
            "raw_cv_text": "Another software engineer profile with duplicate candidate id.",
        },
        {
            "candidate_id": "cand-unique-pk-101",
            "full_name": "Third Candidate",
            "email": "third.cand@example.com",
            "location": "Nantes",
            "education_level": "Bachelor",
            "years_of_experience": 2.0,
            "raw_cv_text": "Third valid candidate profile in the same batch.",
        },
    ]

    mock_file = tmp_path / "pk_conflict_candidates.json"
    mock_file.write_text(json.dumps(records), encoding="utf-8")

    summary = ingest_candidates(mock_file, db_session)
    db_session.commit()

    assert summary.status == "partial"
    assert summary.records_extracted == 3
    assert summary.records_loaded == 2
    assert summary.records_rejected == 1

    errors = db_session.execute(
        select(IngestionError).where(IngestionError.batch_id == summary.batch_id)
    ).scalars().all()

    assert len(errors) == 1
    assert "IntegrityError" in errors[0].error_type
    assert "conflicting.cand@example.com" in errors[0].raw_data


def test_quarantine_job_description_db_integrity_error(db_session: Session, tmp_path: Path) -> None:
    """Verify job description PK collision triggers savepoint rollback and error quarantine."""
    records = [
        {
            "job_id": "job-duplicate-pk-200",
            "job_code": "JOB-SEC-01",
            "title": "Security Engineer",
            "department": "Security",
            "location": "Paris",
            "raw_description": "Comprehensive security role requirements description text.",
        },
        {
            "job_id": "job-duplicate-pk-200",
            "job_code": "JOB-SEC-02",
            "title": "Security Architect",
            "department": "Security",
            "location": "Paris",
            "raw_description": "Another security architecture role with duplicate job id.",
        },
    ]

    mock_file = tmp_path / "pk_conflict_jobs.json"
    mock_file.write_text(json.dumps(records), encoding="utf-8")

    summary = ingest_job_descriptions(mock_file, db_session)
    db_session.commit()

    assert summary.status == "partial"
    assert summary.records_extracted == 2
    assert summary.records_loaded == 1
    assert summary.records_rejected == 1

    errors = db_session.execute(
        select(IngestionError).where(IngestionError.batch_id == summary.batch_id)
    ).scalars().all()

    assert len(errors) == 1
    assert "IntegrityError" in errors[0].error_type
