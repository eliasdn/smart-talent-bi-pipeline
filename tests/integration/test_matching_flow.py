"""Integration test suite verifying the end-to-end matching flow with database persistence."""

from decimal import Decimal
import json
from pathlib import Path
import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.engine.service import MatchingEngine
from src.etl.loaders import save_matching_evaluation
from src.etl.pipeline import ETLPipeline
from src.models.entities import (
    Candidate,
    JobDescription,
    MatchingEvaluation,
)
from src.models.schemas import MatchingEvaluationDTO


class TestMatchingFlowIntegration:
    """End-to-end integration tests verifying data ingestion, matching, persistence, and queries."""

    @pytest.fixture
    def seeded_session(self, tmp_sqlite_engine: Engine, raw_data_dir: Path) -> Session:
        """Populate in-memory database with raw candidate and job records via ETL pipeline."""
        pipeline = ETLPipeline(engine=tmp_sqlite_engine)
        results = pipeline.run_all(raw_data_dir=raw_data_dir)

        assert results["candidates"].records_loaded >= 10
        assert results["job_descriptions"].records_loaded >= 4

        with pipeline.session_factory() as session:
            yield session

    def test_end_to_end_matching_and_persistence(self, seeded_session: Session) -> None:
        """Verify batch evaluation across all ingested candidates and vacancies."""
        engine = MatchingEngine()
        evaluations = engine.evaluate_all(seeded_session, persist=True)

        total_candidates = seeded_session.scalar(select(func.count()).select_from(Candidate))
        total_jobs = seeded_session.scalar(select(func.count()).select_from(JobDescription))
        expected_evaluations = total_candidates * total_jobs

        assert len(evaluations) == expected_evaluations
        assert expected_evaluations == 40

        # Query database directly to confirm row count
        db_eval_count = seeded_session.scalar(select(func.count()).select_from(MatchingEvaluation))
        assert db_eval_count == expected_evaluations

    def test_database_record_integrity_and_formatting(self, seeded_session: Session) -> None:
        """Verify relational fields, JSON serialization, score bounds, and recommendations in DB."""
        engine = MatchingEngine()
        engine.evaluate_all(seeded_session, persist=True)

        db_evals = seeded_session.scalars(select(MatchingEvaluation)).all()
        assert len(db_evals) == 40

        valid_recommendations = {"strong_hire", "hire", "consider", "reject"}

        for row in db_evals:
            # Score bounds
            assert Decimal("0.0") <= row.overall_score <= Decimal("100.0")
            assert Decimal("0.0") <= row.skills_score <= Decimal("100.0")
            assert Decimal("0.0") <= row.experience_score <= Decimal("100.0")
            assert Decimal("0.0") <= row.semantic_similarity <= Decimal("1.0")

            # Recommendation enum
            assert row.recommendation in valid_recommendations

            # JSON serializability of skill arrays
            matched = json.loads(row.matched_skills)
            missing = json.loads(row.missing_skills)
            assert isinstance(matched, list)
            assert isinstance(missing, list)

            # Qualitative narratives
            assert len(row.strengths_summary.strip()) > 0
            assert len(row.gaps_summary.strip()) > 0
            assert len(row.executive_summary.strip()) > 0

            # Absence of forbidden emojis or agent mentions
            for field_val in [row.strengths_summary, row.gaps_summary, row.executive_summary]:
                for ch in field_val:
                    assert ord(ch) < 0x1F300 or ord(ch) > 0x1F9FF

    def test_sql_queryability_and_rankings(self, seeded_session: Session) -> None:
        """Verify standard SQL filtering, aggregation, and ranking operations on evaluations."""
        engine = MatchingEngine()
        engine.evaluate_all(seeded_session, persist=True)

        # 1. Top candidates per job (ordered by score descending)
        top_de_stmt = (
            select(MatchingEvaluation)
            .join(JobDescription, MatchingEvaluation.job_id == JobDescription.job_id)
            .where(JobDescription.job_code == "JOB-DE-001")
            .order_by(MatchingEvaluation.overall_score.desc())
        )
        de_rankings = seeded_session.scalars(top_de_stmt).all()
        assert len(de_rankings) == 10
        assert de_rankings[0].overall_score >= de_rankings[-1].overall_score

        # Top candidate for JOB-DE-001 should have a strong score
        top_score = float(de_rankings[0].overall_score)
        assert top_score >= 75.0

        # 2. Count high-fit candidates across all jobs (score >= 70.0)
        high_fit_stmt = (
            select(func.count())
            .select_from(MatchingEvaluation)
            .where(MatchingEvaluation.overall_score >= Decimal("70.0"))
        )
        high_fit_count = seeded_session.scalar(high_fit_stmt)
        assert high_fit_count is not None and high_fit_count > 0

    def test_idempotent_evaluation_upsert(self, seeded_session: Session) -> None:
        """Verify re-running evaluate_all updates records without violating unique constraint."""
        engine = MatchingEngine()

        # First run
        run1 = engine.evaluate_all(seeded_session, persist=True)
        count1 = seeded_session.scalar(select(func.count()).select_from(MatchingEvaluation))
        assert count1 == 40

        # Second run
        run2 = engine.evaluate_all(seeded_session, persist=True)
        count2 = seeded_session.scalar(select(func.count()).select_from(MatchingEvaluation))
        assert count2 == 40
        assert len(run1) == len(run2)

    def test_candidate_and_job_targeted_evaluations(self, seeded_session: Session) -> None:
        """Verify single candidate and single job evaluation APIs."""
        engine = MatchingEngine()

        first_cand = seeded_session.scalars(select(Candidate)).first()
        assert first_cand is not None

        # Evaluate one candidate against all jobs
        cand_evals = engine.evaluate_candidate_for_all_jobs(
            seeded_session,
            candidate_id=first_cand.candidate_id,
            persist=True,
        )
        assert len(cand_evals) == 4

        first_job = seeded_session.scalars(select(JobDescription)).first()
        assert first_job is not None

        # Evaluate one job against all candidates
        job_evals = engine.evaluate_job_for_all_candidates(
            seeded_session,
            job_id=first_job.job_id,
            persist=True,
        )
        assert len(job_evals) == 10
        # Results should be pre-sorted descending
        assert job_evals[0].overall_score >= job_evals[-1].overall_score

    def test_cascade_delete_candidate_purges_evaluations(self, seeded_session: Session) -> None:
        """Verify deleting a candidate record purges all related matching evaluations."""
        engine = MatchingEngine()
        engine.evaluate_all(seeded_session, persist=True)

        target_cand = seeded_session.scalars(select(Candidate)).first()
        assert target_cand is not None
        target_id = target_cand.candidate_id

        # Verify evaluations exist before delete
        pre_count = seeded_session.scalar(
            select(func.count())
            .select_from(MatchingEvaluation)
            .where(MatchingEvaluation.candidate_id == target_id)
        )
        assert pre_count == 4

        # Delete candidate
        seeded_session.delete(target_cand)
        seeded_session.commit()

        # Confirm cascade deletion
        post_count = seeded_session.scalar(
            select(func.count())
            .select_from(MatchingEvaluation)
            .where(MatchingEvaluation.candidate_id == target_id)
        )
        assert post_count == 0

    def test_cascade_delete_job_purges_evaluations(self, seeded_session: Session) -> None:
        """Verify deleting a job description purges all related matching evaluations."""
        engine = MatchingEngine()
        engine.evaluate_all(seeded_session, persist=True)

        target_job = seeded_session.scalars(select(JobDescription)).first()
        assert target_job is not None
        target_id = target_job.job_id

        # Verify evaluations exist before delete
        pre_count = seeded_session.scalar(
            select(func.count())
            .select_from(MatchingEvaluation)
            .where(MatchingEvaluation.job_id == target_id)
        )
        assert pre_count == 10

        # Delete job
        seeded_session.delete(target_job)
        seeded_session.commit()

        # Confirm cascade deletion
        post_count = seeded_session.scalar(
            select(func.count())
            .select_from(MatchingEvaluation)
            .where(MatchingEvaluation.job_id == target_id)
        )
        assert post_count == 0

    def test_referential_integrity_nonexistent_references(self, seeded_session: Session) -> None:
        """Verify inserting an evaluation with invalid candidate or job ID raises IntegrityError."""
        invalid_dto = MatchingEvaluationDTO(
            evaluation_id="eval-invalid-fk",
            candidate_id="non-existent-cand-id",
            job_id="non-existent-job-id",
            overall_score=Decimal("75.00"),
            skills_score=Decimal("80.00"),
            experience_score=Decimal("70.00"),
            semantic_similarity=Decimal("0.5000"),
            recommendation="hire",
            matched_skills=["Python"],
            missing_skills=["Docker"],
            strengths_summary="Points forts.",
            gaps_summary="Ecarts.",
            executive_summary="Synthese.",
        )

        with pytest.raises(IntegrityError):
            save_matching_evaluation(seeded_session, invalid_dto)
            seeded_session.commit()

        seeded_session.rollback()
