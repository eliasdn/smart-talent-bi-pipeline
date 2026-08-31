"""Matching service coordinating skill extraction, semantic matching, scoring, and persistence."""

from decimal import Decimal
from typing import Any, List, Optional, Union
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.engine.extractor import JobSkillProfile, SkillExtractor
from src.engine.scorer import MatchingScorer, ScoreBreakdown
from src.engine.semantic import SemanticMatcher
from src.engine.synthesizer import EvaluationSynthesis, MatchingSynthesizer
from src.etl.loaders import save_matching_evaluation
from src.models.entities import Candidate, JobDescription, MatchingEvaluation
from src.models.schemas import (
    CandidateProfileDTO,
    JobPostingDTO,
    MatchingEvaluationDTO,
)
from src.utils.logger import setup_logger

logger = setup_logger("smart_talent_bi.engine.service")


class MatchingEngine:
    """Orchestrates candidate-to-job semantic evaluation and database persistence."""

    def __init__(
        self,
        extractor: Optional[SkillExtractor] = None,
        semantic_matcher: Optional[SemanticMatcher] = None,
        scorer: Optional[MatchingScorer] = None,
        synthesizer: Optional[MatchingSynthesizer] = None,
    ) -> None:
        """Initialize matching engine with domain subcomponents.

        Args:
            extractor: Optional custom SkillExtractor instance.
            semantic_matcher: Optional custom SemanticMatcher instance.
            scorer: Optional custom MatchingScorer instance.
            synthesizer: Optional custom MatchingSynthesizer instance.
        """
        self.extractor = extractor or SkillExtractor()
        self.semantic = semantic_matcher or SemanticMatcher()
        self.scorer = scorer or MatchingScorer()
        self.synthesizer = synthesizer or MatchingSynthesizer()

    def evaluate_pair(
        self,
        candidate: Union[Candidate, CandidateProfileDTO, dict],
        job: Union[JobDescription, JobPostingDTO, dict],
        evaluation_id: Optional[str] = None,
    ) -> MatchingEvaluationDTO:
        """Evaluate a single candidate against a job vacancy specification.

        Args:
            candidate: Candidate profile representation.
            job: Job vacancy posting representation.
            evaluation_id: Optional explicit UUID identifier for evaluation record.

        Returns:
            Validated MatchingEvaluationDTO containing scores and qualitative analysis.
        """
        cand_id = (
            candidate.get("candidate_id")
            if isinstance(candidate, dict)
            else getattr(candidate, "candidate_id", str(uuid.uuid4()))
        )
        job_id = (
            job.get("job_id")
            if isinstance(job, dict)
            else getattr(job, "job_id", str(uuid.uuid4()))
        )

        # 1. Skill extraction
        cand_skills = self.extractor.extract_candidate_skills(candidate)
        job_profile = self.extractor.extract_job_skills(job)

        # 2. Semantic matching
        semantic_sim = self.semantic.compare_candidate_and_job(candidate, job)

        # 3. Multi-factor scoring
        breakdown = self.scorer.score(
            candidate=candidate,
            job=job,
            candidate_skills=cand_skills,
            job_profile=job_profile,
            semantic_sim=semantic_sim,
        )

        # 4. Qualitative synthesis
        synthesis = self.synthesizer.synthesize(
            candidate=candidate,
            job=job,
            breakdown=breakdown,
        )

        # Skill display lists
        matched_keys = breakdown.matched_required_skills + breakdown.matched_preferred_skills
        missing_keys = breakdown.missing_required_skills + breakdown.missing_preferred_skills

        matched_names = self.synthesizer._resolve_names(matched_keys)
        missing_names = self.synthesizer._resolve_names(missing_keys)

        eval_id = evaluation_id or str(uuid.uuid4())

        return MatchingEvaluationDTO(
            evaluation_id=eval_id,
            candidate_id=cand_id,
            job_id=job_id,
            overall_score=Decimal(str(breakdown.overall_score)),
            skills_score=Decimal(str(breakdown.technical_score)),
            experience_score=Decimal(str(breakdown.experience_score)),
            semantic_similarity=Decimal(str(breakdown.semantic_similarity)),
            recommendation=breakdown.recommendation,  # type: ignore
            matched_skills=matched_names,
            missing_skills=missing_names,
            strengths_summary=synthesis.strengths_summary,
            gaps_summary=synthesis.gaps_summary,
            executive_summary=synthesis.executive_summary,
        )

    def evaluate_all(
        self,
        session: Session,
        persist: bool = True,
    ) -> List[MatchingEvaluationDTO]:
        """Evaluate all candidate-job combinations available in the relational database.

        Args:
            session: Active SQLAlchemy session.
            persist: Whether to commit evaluations to matching_evaluations table.

        Returns:
            List of generated MatchingEvaluationDTO records.
        """
        candidates = session.scalars(select(Candidate)).all()
        jobs = session.scalars(select(JobDescription)).all()

        if not candidates:
            logger.warning("No candidate records found in database for matching evaluation.")
            return []
        if not jobs:
            logger.warning("No job descriptions found in database for matching evaluation.")
            return []

        logger.info(
            "Starting matching evaluation for %d candidates and %d job postings (%d total pairs)",
            len(candidates),
            len(jobs),
            len(candidates) * len(jobs),
        )

        evaluations: List[MatchingEvaluationDTO] = []

        for cand in candidates:
            for job in jobs:
                eval_dto = self.evaluate_pair(candidate=cand, job=job)
                evaluations.append(eval_dto)
                if persist:
                    save_matching_evaluation(session, eval_dto)

        if persist:
            session.commit()
            logger.info("Successfully persisted %d matching evaluations to database.", len(evaluations))

        return evaluations

    def evaluate_candidate_for_all_jobs(
        self,
        session: Session,
        candidate_id: str,
        persist: bool = True,
    ) -> List[MatchingEvaluationDTO]:
        """Evaluate a specific candidate against all vacancies in the database.

        Args:
            session: Active SQLAlchemy session.
            candidate_id: Target candidate identifier.
            persist: Whether to save outcomes to database.

        Returns:
            List of MatchingEvaluationDTO records for target candidate.
        """
        cand_stmt = select(Candidate).where(Candidate.candidate_id == candidate_id)
        candidate = session.execute(cand_stmt).scalar_one_or_none()
        if not candidate:
            raise ValueError(f"Candidate not found for identifier: {candidate_id}")

        jobs = session.scalars(select(JobDescription)).all()
        evaluations: List[MatchingEvaluationDTO] = []

        for job in jobs:
            eval_dto = self.evaluate_pair(candidate=candidate, job=job)
            evaluations.append(eval_dto)
            if persist:
                save_matching_evaluation(session, eval_dto)

        if persist:
            session.commit()

        return evaluations

    def evaluate_job_for_all_candidates(
        self,
        session: Session,
        job_id: str,
        persist: bool = True,
    ) -> List[MatchingEvaluationDTO]:
        """Evaluate all candidates against a specific job vacancy.

        Args:
            session: Active SQLAlchemy session.
            job_id: Target job description identifier.
            persist: Whether to save outcomes to database.

        Returns:
            List of MatchingEvaluationDTO records sorted by overall score descending.
        """
        job_stmt = select(JobDescription).where(JobDescription.job_id == job_id)
        job = session.execute(job_stmt).scalar_one_or_none()
        if not job:
            raise ValueError(f"Job description not found for identifier: {job_id}")

        candidates = session.scalars(select(Candidate)).all()
        evaluations: List[MatchingEvaluationDTO] = []

        for cand in candidates:
            eval_dto = self.evaluate_pair(candidate=cand, job=job)
            evaluations.append(eval_dto)
            if persist:
                save_matching_evaluation(session, eval_dto)

        if persist:
            session.commit()

        evaluations.sort(key=lambda e: e.overall_score, reverse=True)
        return evaluations
