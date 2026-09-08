"""Edge-case verification and error recovery test suite for ETL pipeline.

Verifies:
1. Malformed JSON/CSV, missing fields, extreme string lengths, French non-ASCII accents, empty datasets.
2. Foreign key violation attempts and CASCADE delete verification.
3. Concurrent and rapid successive upserts (race conditions, idempotency, session leakage).
4. Transaction error handling and quarantine resilience under DB-level exceptions.
"""

import json
import threading
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import tempfile
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, PendingRollbackError
from sqlalchemy.orm import Session

from src.etl.extractors import DataExtractionError, extract_csv, extract_json
from src.etl.loaders import (
    save_matching_evaluation,
    upsert_candidate,
    upsert_job_description,
    upsert_operational_metric,
    upsert_skill,
)
from src.etl.pipeline import ETLPipeline, _record_quarantine_error
from src.etl.transformers import (
    calculate_experience_years,
    normalize_skill_key,
    parse_date,
    transform_candidate,
    transform_job_description,
    transform_operational_metric,
)
from src.models.entities import (
    Base,
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
    create_db_engine,
    get_session_factory,
    init_db,
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


@pytest.fixture
def isolated_engine():
    """Create an isolated in-memory engine with Foreign Keys enabled."""
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def isolated_session(isolated_engine):
    """Provide a clean isolated session."""
    session_factory = get_session_factory(isolated_engine)
    with session_factory() as session:
        yield session
        session.rollback()


# ==============================================================================
# 1. FOREIGN KEY INTEGRITY & CASCADE STRESS TESTS
# ==============================================================================

def test_fk_candidate_skill_aborts_invalid_candidate(isolated_session: Session):
    """Verify SQLite foreign_keys=ON aborts candidate_skills insertion when candidate_id is missing."""
    sk = Skill(name="Rust", category="technical", normalized_key="rust")
    isolated_session.add(sk)
    isolated_session.commit()

    cs = CandidateSkill(candidate_id="non-existent-cand-id", skill_id=sk.skill_id)
    isolated_session.add(cs)
    with pytest.raises(IntegrityError):
        isolated_session.commit()
    isolated_session.rollback()


def test_fk_candidate_skill_aborts_invalid_skill(isolated_session: Session):
    """Verify SQLite foreign_keys=ON aborts candidate_skills insertion when skill_id is missing."""
    c = Candidate(
        candidate_id="c-valid-01",
        full_name="Valid Candidate",
        email="valid@example.com",
        location="Paris",
        education_level="MSc",
        raw_cv_text="Valid CV text with more than 20 characters.",
    )
    isolated_session.add(c)
    isolated_session.commit()

    cs = CandidateSkill(candidate_id=c.candidate_id, skill_id=999999)
    isolated_session.add(cs)
    with pytest.raises(IntegrityError):
        isolated_session.commit()
    isolated_session.rollback()


def test_fk_candidate_experience_aborts_invalid_candidate(isolated_session: Session):
    """Verify SQLite foreign_keys=ON aborts candidate_experiences insertion with missing candidate."""
    exp = CandidateExperience(
        candidate_id="non-existent-cand-id",
        company="TechCorp",
        role_title="Software Architect",
        start_date=date(2022, 1, 1),
    )
    isolated_session.add(exp)
    with pytest.raises(IntegrityError):
        isolated_session.commit()
    isolated_session.rollback()


def test_fk_job_skill_aborts_invalid_job_or_skill(isolated_session: Session):
    """Verify SQLite foreign_keys=ON aborts job_skills insertion with invalid references."""
    js = JobSkill(job_id="non-existent-job-id", skill_id=123)
    isolated_session.add(js)
    with pytest.raises(IntegrityError):
        isolated_session.commit()
    isolated_session.rollback()


def test_fk_matching_evaluation_aborts_invalid_references(isolated_session: Session):
    """Verify SQLite foreign_keys=ON aborts matching_evaluations insertion with invalid references."""
    me = MatchingEvaluation(
        evaluation_id="eval-01",
        candidate_id="bad-cand",
        job_id="bad-job",
        overall_score=Decimal("75.0"),
        skills_score=Decimal("80.0"),
        experience_score=Decimal("70.0"),
        semantic_similarity=Decimal("0.7500"),
        recommendation="hire",
        matched_skills="[]",
        missing_skills="[]",
        strengths_summary="None",
        gaps_summary="None",
        executive_summary="None",
    )
    isolated_session.add(me)
    with pytest.raises(IntegrityError):
        isolated_session.commit()
    isolated_session.rollback()


def test_fk_operational_metrics_aborts_invalid_references(isolated_session: Session):
    """Verify SQLite foreign_keys=ON aborts operational_metrics insertion with invalid references."""
    op = OperationalMetric(
        metric_id="metric-01",
        candidate_id="bad-cand",
        job_id="bad-job",
        application_date=date(2024, 1, 1),
    )
    isolated_session.add(op)
    with pytest.raises(IntegrityError):
        isolated_session.commit()
    isolated_session.rollback()


def test_fk_ingestion_errors_aborts_invalid_batch(isolated_session: Session):
    """Verify SQLite foreign_keys=ON aborts ingestion_errors insertion with invalid batch_id."""
    err = IngestionError(
        batch_id="bad-batch-id",
        raw_record_index=0,
        raw_data="{}",
        error_type="Error",
        error_details="details",
    )
    isolated_session.add(err)
    with pytest.raises(IntegrityError):
        isolated_session.commit()
    isolated_session.rollback()


def test_cascade_deletion_candidate_purges_all_relations(isolated_session: Session):
    """Verify CASCADE deletion cleans candidate_skills, experiences, evaluations, and operational_metrics."""
    c = Candidate(
        candidate_id="c-casc-01",
        full_name="Candidate Cascade",
        email="cascade@example.com",
        location="Paris",
        education_level="MSc",
        raw_cv_text="Valid CV text with more than 20 characters.",
    )
    j = JobDescription(
        job_id="j-casc-01",
        job_code="JOB-CASC-01",
        title="Cascade Engineer",
        department="Engineering",
        location="Paris",
        raw_description="Job description with more than 20 characters.",
    )
    sk = Skill(name="SQLAlchemy", category="technical", normalized_key="sqlalchemy")
    isolated_session.add_all([c, j, sk])
    isolated_session.commit()

    cs = CandidateSkill(candidate_id=c.candidate_id, skill_id=sk.skill_id)
    exp = CandidateExperience(
        candidate_id=c.candidate_id,
        company="CascadeCorp",
        role_title="Lead Engineer",
        start_date=date(2021, 1, 1),
    )
    me = MatchingEvaluation(
        evaluation_id="eval-casc-01",
        candidate_id=c.candidate_id,
        job_id=j.job_id,
        overall_score=Decimal("85.0"),
        skills_score=Decimal("90.0"),
        experience_score=Decimal("80.0"),
        semantic_similarity=Decimal("0.8500"),
        recommendation="hire",
        matched_skills="[]",
        missing_skills="[]",
        strengths_summary="High proficiency",
        gaps_summary="None",
        executive_summary="Solid match",
    )
    op = OperationalMetric(
        metric_id="met-casc-01",
        candidate_id=c.candidate_id,
        job_id=j.job_id,
        application_date=date(2024, 1, 15),
    )
    isolated_session.add_all([cs, exp, me, op])
    isolated_session.commit()

    # Delete candidate
    isolated_session.delete(c)
    isolated_session.commit()

    # Verify all children were deleted
    assert isolated_session.query(CandidateSkill).filter_by(candidate_id="c-casc-01").count() == 0
    assert isolated_session.query(CandidateExperience).filter_by(candidate_id="c-casc-01").count() == 0
    assert isolated_session.query(MatchingEvaluation).filter_by(candidate_id="c-casc-01").count() == 0
    assert isolated_session.query(OperationalMetric).filter_by(candidate_id="c-casc-01").count() == 0
    # Skill and Job still exist
    assert isolated_session.query(Skill).filter_by(name="SQLAlchemy").count() == 1
    assert isolated_session.query(JobDescription).filter_by(job_id="j-casc-01").count() == 1


# ==============================================================================
# 2. MALFORMED DATA, NON-ASCII ACCENTS, EXTREME STRINGS, EMPTY DATASETS
# ==============================================================================

def test_french_accents_and_non_ascii_preservation(isolated_engine):
    """Verify French characters (é, è, ç, à, etc.) are accurately ingested without encoding distortion."""
    pipeline = ETLPipeline(isolated_engine)

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_dir = Path(tmpdir)
        cand_data = [{
            "full_name": "Éléonore François d'Harcourt",
            "email": "eleonore.dharcourt@societe-francaise.fr",
            "phone": "+33 (0)4 77 12 34 56",
            "location": "Saint-Étienne, Région Auvergne-Rhône-Alpes, France",
            "current_title": "Responsable Ingénierie & Qualité Données",
            "years_of_experience": 7.5,
            "education_level": "Doctorat en Informatique Théorique & Mathématiques Appliquées",
            "raw_cv_text": "Spécialiste de la gouvernance des données, des systèmes distribués haute performance et de l'analyse statistique multidimensionnelle.",
            "skills": [
                {"name": "Développement Distribué", "category": "technique", "years_experience": 7.0},
                {"name": "Génie Logiciel Avancé", "category": "technique", "years_experience": 6.5},
                {"name": "Conduite du Changement", "category": "management", "years_experience": 4.0},
            ],
            "experiences": [
                {
                    "company": "Crédit Agricole d'Île-de-France",
                    "role_title": "Architecte de Données Sénior",
                    "start_date": "2018-09-01",
                    "end_date": "2024-03-31",
                    "description": "Migration vers une architecture micro-services sécurisée et découplée.",
                }
            ],
        }]
        (raw_dir / "candidates.json").write_text(json.dumps(cand_data, ensure_ascii=False), encoding="utf-8")

        res = pipeline.run_all(raw_dir)
        assert res["candidates"].status == "completed"
        assert res["candidates"].records_loaded == 1

        session_factory = get_session_factory(isolated_engine)
        with session_factory() as s:
            c = s.query(Candidate).filter_by(email="eleonore.dharcourt@societe-francaise.fr").one()
            assert c.full_name == "Éléonore François d'Harcourt"
            assert "Saint-Étienne" in c.location
            assert "Doctorat" in c.education_level
            skill_names = [cs.skill.name for cs in c.skills]
            assert "Développement Distribué" in skill_names
            assert "Génie Logiciel Avancé" in skill_names


def test_malformed_json_raises_extraction_error_without_crash(isolated_engine):
    """Verify malformed JSON syntax fails gracefully into failed batch status."""
    pipeline = ETLPipeline(isolated_engine)
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_dir = Path(tmpdir)
        (raw_dir / "candidates.json").write_text("{ unclosed json: bad syntax [", encoding="utf-8")

        res = pipeline.run_all(raw_dir)
        assert "candidates" in res
        assert res["candidates"].status == "failed"
        assert res["candidates"].records_extracted == 0
        assert "Malformed JSON" in (res["candidates"].error_summary or "")


def test_malformed_csv_raises_extraction_error_without_crash(isolated_engine):
    """Verify malformed CSV binary data fails gracefully into failed batch status."""
    pipeline = ETLPipeline(isolated_engine)
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_dir = Path(tmpdir)
        # Write corrupted null-byte binary stream pretending to be CSV
        (raw_dir / "operational_metrics.csv").write_bytes(b"\x00\xff\xfe\x00corrupted\x00data")

        res = pipeline.run_all(raw_dir)
        assert "operational_metrics" in res
        assert res["operational_metrics"].status == "failed"
        assert "Failed to parse CSV" in (res["operational_metrics"].error_summary or "")


def test_empty_datasets_handled_cleanly(isolated_engine):
    """Verify empty JSON lists and header-only CSVs complete with 0 loaded and 0 rejected."""
    pipeline = ETLPipeline(isolated_engine)
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_dir = Path(tmpdir)
        (raw_dir / "candidates.json").write_text("[]", encoding="utf-8")
        (raw_dir / "job_descriptions.json").write_text("[]", encoding="utf-8")
        (raw_dir / "operational_metrics.csv").write_text(
            "candidate_email,job_code,application_date\n", encoding="utf-8"
        )

        res = pipeline.run_all(raw_dir)
        for entity in ["candidates", "job_descriptions", "operational_metrics"]:
            assert res[entity].status == "completed"
            assert res[entity].records_loaded == 0
            assert res[entity].records_rejected == 0


def test_extreme_string_lengths_and_validation_bounds():
    """Verify length constraints enforce bounds on short/long fields and permit large CV texts."""
    # 1. full_name exceeding 150 characters
    with pytest.raises(ValidationError):
        RawCandidateSchema(
            full_name="A" * 151,
            email="extreme@example.com",
            location="Paris",
            education_level="Master",
            raw_cv_text="Valid CV text with more than 20 characters.",
        )

    # 2. location exceeding 100 characters
    with pytest.raises(ValidationError):
        RawCandidateSchema(
            full_name="Valid Name",
            email="extreme@example.com",
            location="L" * 101,
            education_level="Master",
            raw_cv_text="Valid CV text with more than 20 characters.",
        )

    # 3. Large raw_cv_text (100,000 chars) is permitted
    huge_cv = "Experienced Software Engineer. " * 3500  # ~105,000 characters
    cand = RawCandidateSchema(
        full_name="Valid Name",
        email="extreme@example.com",
        location="Paris",
        education_level="Master",
        raw_cv_text=huge_cv,
    )
    assert len(cand.raw_cv_text) > 100000


# ==============================================================================
# 3. CONCURRENT & RAPID SUCCESSIVE UPSERTS (IDEMPOTENCY & SESSION LEAKAGE)
# ==============================================================================

def test_rapid_successive_upserts_idempotent(isolated_engine):
    """Verify rapid consecutive executions of run_all produce stable, idempotent states."""
    pipeline = ETLPipeline(isolated_engine)
    raw_dir = Path("data/raw")

    # Run 5 times successively
    for run_idx in range(5):
        res = pipeline.run_all(raw_dir)
        assert res["candidates"].status == "completed"
        assert res["candidates"].records_loaded == 10
        assert res["job_descriptions"].records_loaded == 4
        assert res["operational_metrics"].records_loaded == 36

    # Verify exact database counts did not multiply
    session_factory = get_session_factory(isolated_engine)
    with session_factory() as s:
        assert s.query(Candidate).count() == 10
        assert s.query(JobDescription).count() == 4
        assert s.query(OperationalMetric).count() == 36


def test_concurrent_multithreaded_pipeline_execution():
    """Verify multi-threaded ETL pipeline runs against a shared SQLite file database without deadlock or corruption."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "concurrent_test.db"
        engine = create_db_engine(f"sqlite:///{db_path}")
        init_db(engine)

        raw_dir = Path("data/raw")
        errors = []

        def worker():
            try:
                p = ETLPipeline(engine)
                p.run_all(raw_dir)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent execution produced errors: {errors}"

        session_factory = get_session_factory(engine)
        with session_factory() as s:
            assert s.query(Candidate).count() == 10
            assert s.query(JobDescription).count() == 4
            assert s.query(OperationalMetric).count() == 36

        engine.dispose()


# ==============================================================================
# 4. EMPIRICAL VULNERABILITY REPRODUCTION: DB-LEVEL FLUSH FAILURE IN QUARANTINE
# ==============================================================================

def test_quarantine_recovers_from_validation_error(isolated_engine):
    """Verify pure validation errors (e.g. invalid email) quarantine cleanly without DB error."""
    pipeline = ETLPipeline(isolated_engine)
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_dir = Path(tmpdir)
        cand_data = [
            {
                "full_name": "Valid Candidate",
                "email": "valid@example.com",
                "location": "Paris",
                "education_level": "MSc",
                "raw_cv_text": "Valid CV text with more than 20 characters.",
            },
            {
                "full_name": "Invalid Candidate",
                "email": "invalid-email-no-at-sign",  # Pydantic ValidationError
                "location": "Paris",
                "education_level": "MSc",
                "raw_cv_text": "Valid CV text with more than 20 characters.",
            },
        ]
        (raw_dir / "candidates.json").write_text(json.dumps(cand_data), encoding="utf-8")

        res = pipeline.run_all(raw_dir)
        assert res["candidates"].status == "partial"
        assert res["candidates"].records_loaded == 1
        assert res["candidates"].records_rejected == 1

        session_factory = get_session_factory(isolated_engine)
        with session_factory() as s:
            assert s.query(Candidate).count() == 1
            assert s.query(IngestionError).count() == 1


def test_vulnerability_db_flush_integrity_error_crashes_pipeline_without_savepoints(isolated_engine):
    """Verify savepoint isolation catches database flush integrity errors and quarantines cleanly.

    When a record passes Pydantic validation but triggers a database-level IntegrityError
    during session.flush() (e.g., duplicate primary key candidate_id with different email),
    the inner savepoint rolls back without breaking the session transaction.
    The quarantine handler successfully records the error into ingestion_errors,
    and the pipeline batch finishes with partial status.
    """
    pipeline = ETLPipeline(isolated_engine)
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_dir = Path(tmpdir)
        cand_data = [
            {
                "candidate_id": "duplicate-pk-collision",
                "full_name": "Candidate Alpha",
                "email": "alpha@example.com",
                "location": "Paris",
                "education_level": "MSc",
                "raw_cv_text": "Valid CV text with more than 20 characters.",
            },
            {
                "candidate_id": "duplicate-pk-collision",
                "full_name": "Candidate Beta",
                "email": "beta@example.com",
                "location": "Lyon",
                "education_level": "BSc",
                "raw_cv_text": "Valid CV text with more than 20 characters.",
            },
        ]
        (raw_dir / "candidates.json").write_text(json.dumps(cand_data), encoding="utf-8")

        res = pipeline.run_all(raw_dir)
        assert res["candidates"].status == "partial"
        assert res["candidates"].records_loaded == 1
        assert res["candidates"].records_rejected == 1

        session_factory = get_session_factory(isolated_engine)
        with session_factory() as s:
            assert s.query(Candidate).count() == 1
            assert s.query(IngestionError).count() == 1
            quarantine = s.query(IngestionError).first()
            assert "IntegrityError" in quarantine.error_type
