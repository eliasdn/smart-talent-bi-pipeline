"""Stress and verification tests for savepoint isolation and error quarantine."""

import json
import tempfile
from pathlib import Path
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.etl.pipeline import ETLPipeline
from src.models.entities import (
    Candidate,
    IngestionBatch,
    IngestionError,
    JobDescription,
    OperationalMetric,
    create_db_engine,
    get_session_factory,
    init_db,
)


def test_interleaved_candidate_flush_integrity_errors():
    """Verify that multiple DB-level integrity errors interleaved with valid records are quarantined cleanly.

    Scenario:
    - Candidate 0: Valid (loaded)
    - Candidate 1: PK collision with Candidate 0 (rejected at DB flush)
    - Candidate 2: Valid (loaded)
    - Candidate 3: PK collision with Candidate 2 (rejected at DB flush)
    - Candidate 4: Valid (loaded)
    """
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    pipeline = ETLPipeline(engine)

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_dir = Path(tmpdir) / "raw"
        raw_dir.mkdir()

        cand_data = [
            {
                "candidate_id": "cand-uuid-001",
                "full_name": "Candidate Alpha",
                "email": "alpha@example.com",
                "location": "Paris",
                "education_level": "MSc",
                "raw_cv_text": "Valid CV text with more than 20 characters.",
            },
            {
                "candidate_id": "cand-uuid-001",  # Collision on candidate_id PK
                "full_name": "Candidate Conflict 1",
                "email": "conflict1@example.com",
                "location": "Lyon",
                "education_level": "BSc",
                "raw_cv_text": "Valid CV text with more than 20 characters.",
            },
            {
                "candidate_id": "cand-uuid-002",
                "full_name": "Candidate Beta",
                "email": "beta@example.com",
                "location": "Bordeaux",
                "education_level": "PhD",
                "raw_cv_text": "Valid CV text with more than 20 characters.",
            },
            {
                "candidate_id": "cand-uuid-002",  # Collision on candidate_id PK
                "full_name": "Candidate Conflict 2",
                "email": "conflict2@example.com",
                "location": "Lille",
                "education_level": "Master",
                "raw_cv_text": "Valid CV text with more than 20 characters.",
            },
            {
                "candidate_id": "cand-uuid-003",
                "full_name": "Candidate Gamma",
                "email": "gamma@example.com",
                "location": "Nantes",
                "education_level": "Engineering",
                "raw_cv_text": "Valid CV text with more than 20 characters.",
            },
        ]
        (raw_dir / "candidates.json").write_text(json.dumps(cand_data), encoding="utf-8")

        res = pipeline.run_all(raw_dir)

        # Batch summary assertions
        summary = res["candidates"]
        assert summary.status == "partial"
        assert summary.records_extracted == 5
        assert summary.records_loaded == 3
        assert summary.records_rejected == 2
        assert "2 records quarantined" in (summary.error_summary or "")

        # Persistent database assertions
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            # Candidates loaded: Alpha, Beta, Gamma
            candidates = session.scalars(select(Candidate).order_by(Candidate.candidate_id)).all()
            assert len(candidates) == 3
            assert [c.candidate_id for c in candidates] == ["cand-uuid-001", "cand-uuid-002", "cand-uuid-003"]
            assert [c.email for c in candidates] == ["alpha@example.com", "beta@example.com", "gamma@example.com"]

            # Quarantined errors
            quarantine = session.scalars(select(IngestionError).order_by(IngestionError.raw_record_index)).all()
            assert len(quarantine) == 2
            assert quarantine[0].raw_record_index == 1
            assert "IntegrityError" in quarantine[0].error_type
            assert "cand-uuid-001" in quarantine[0].raw_data

            assert quarantine[1].raw_record_index == 3
            assert "IntegrityError" in quarantine[1].error_type
            assert "cand-uuid-002" in quarantine[1].raw_data

            # Batch audit record in DB
            db_batch = session.scalars(select(IngestionBatch).where(IngestionBatch.batch_id == summary.batch_id)).one()
            assert db_batch.status == "partial"
            assert db_batch.records_loaded == 3
            assert db_batch.records_rejected == 2

    engine.dispose()


def test_interleaved_job_descriptions_and_metrics_failures():
    """Verify that job descriptions and operational metrics quarantine failures while preserving outer transactions."""
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    pipeline = ETLPipeline(engine)

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_dir = Path(tmpdir) / "raw"
        raw_dir.mkdir()

        # Seed 1 candidate and 1 job
        cand_data = [
            {
                "candidate_id": "c-valid-100",
                "full_name": "Valid Candidate",
                "email": "valid100@example.com",
                "location": "Paris",
                "education_level": "MSc",
                "raw_cv_text": "Valid CV text with more than 20 characters.",
            }
        ]
        (raw_dir / "candidates.json").write_text(json.dumps(cand_data), encoding="utf-8")

        # Jobs: 1 valid, 1 PK collision, 1 valid
        jobs_data = [
            {
                "job_id": "j-valid-100",
                "job_code": "JOB-100",
                "title": "Software Engineer",
                "department": "Engineering",
                "location": "Paris",
                "raw_description": "Valid job description text with more than 20 characters.",
            },
            {
                "job_id": "j-valid-100",  # PK collision
                "job_code": "JOB-101",
                "title": "DevOps Engineer",
                "department": "Infrastructure",
                "location": "Paris",
                "raw_description": "Valid job description text with more than 20 characters.",
            },
            {
                "job_id": "j-valid-102",
                "job_code": "JOB-102",
                "title": "Data Architect",
                "department": "Data",
                "location": "Paris",
                "raw_description": "Valid job description text with more than 20 characters.",
            },
        ]
        (raw_dir / "job_descriptions.json").write_text(json.dumps(jobs_data), encoding="utf-8")

        # Metrics: 1 valid, 1 bad candidate FK, 1 bad job FK, 1 valid
        csv_data = (
            "candidate_email,job_code,application_date,hiring_decision,recruiter_name\n"
            "valid100@example.com,JOB-100,2024-01-01,hired,Alice\n"
            "nonexistent@example.com,JOB-100,2024-01-02,rejected,Alice\n"
            "valid100@example.com,JOB-NONEXISTENT,2024-01-03,rejected,Alice\n"
            "valid100@example.com,JOB-102,2024-01-04,interviewed,Alice\n"
        )
        (raw_dir / "operational_metrics.csv").write_text(csv_data, encoding="utf-8")

        res = pipeline.run_all(raw_dir)

        # Candidates
        assert res["candidates"].status == "completed"
        assert res["candidates"].records_loaded == 1

        # Jobs
        assert res["job_descriptions"].status == "partial"
        assert res["job_descriptions"].records_loaded == 2
        assert res["job_descriptions"].records_rejected == 1

        # Metrics
        assert res["operational_metrics"].status == "partial"
        assert res["operational_metrics"].records_loaded == 2
        assert res["operational_metrics"].records_rejected == 2

        # Verify database
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            assert session.query(Candidate).count() == 1
            assert session.query(JobDescription).count() == 2
            assert session.query(OperationalMetric).count() == 2

            # Check quarantine errors count: 1 job error + 2 metric errors = 3
            errors = session.scalars(select(IngestionError)).all()
            assert len(errors) == 3

            job_err = [e for e in errors if "j-valid-100" in e.raw_data][0]
            assert "IntegrityError" in job_err.error_type

            metric_errs = [e for e in errors if "nonexistent" in e.raw_data or "JOB-NONEXISTENT" in e.raw_data]
            assert len(metric_errs) == 2
            for me in metric_errs:
                assert "ValueError" in me.error_type

    engine.dispose()

def test_dirty_unstructured_data_quarantine_e2e():
    """Verify that messy/dirty production-like data files are parsed with valid records loaded and corrupt records quarantined."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    dirty_cand_path = repo_root / "data" / "raw" / "candidates_unstructured_sample.json"
    dirty_metric_path = repo_root / "data" / "raw" / "operational_metrics_messy_sample.csv"

    assert dirty_cand_path.exists(), "Sample dirty candidate dataset must exist"
    assert dirty_metric_path.exists(), "Sample dirty metric dataset must exist"

    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    pipeline = ETLPipeline(engine)

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_dir = Path(tmpdir) / "raw"
        raw_dir.mkdir()
        
        # Copy dirty candidate file as candidates.json
        (raw_dir / "candidates.json").write_text(dirty_cand_path.read_text(encoding="utf-8"), encoding="utf-8")
        # Empty jobs to isolate candidate ingestion
        (raw_dir / "job_descriptions.json").write_text("[]", encoding="utf-8")
        res = pipeline.run_all(raw_dir)
        
        # 4 records in file: 2 valid (Jean-Baptiste with spaces/accents, Sophie with accents), 2 corrupt (invalid email, inverted dates)
        assert res["candidates"].status == "partial"
        assert res["candidates"].records_loaded == 2
        assert res["candidates"].records_rejected == 2

        session_factory = get_session_factory(engine)
        with session_factory() as session:
            # 2 candidates successfully persisted
            assert session.query(Candidate).count() == 2
            # 2 errors quarantined in ingestion_errors table
            errors = session.scalars(select(IngestionError)).all()
            assert len(errors) == 2
            error_types = [e.error_type for e in errors]
            assert any("ValidationError" in et for et in error_types)

    engine.dispose()
