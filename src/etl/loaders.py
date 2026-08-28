"""Database loader module providing idempotent upsert operations."""

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.etl.transformers import normalize_skill_key
from src.models.entities import (
    Candidate,
    CandidateExperience,
    CandidateSkill,
    JobDescription,
    JobSkill,
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
from src.utils.logger import setup_logger

logger = setup_logger("smart_talent_bi.etl.loaders")


def upsert_skill(session: Session, name: str, category: str = "technical") -> Skill:
    """Retrieve an existing skill by normalized key or create a new one.

    Args:
        session: Active SQLAlchemy session.
        name: Raw skill name.
        category: Skill category (e.g. 'technical', 'soft_skill', 'methodology').

    Returns:
        Persisted Skill entity instance.
    """
    cleaned_name = name.strip()
    norm_key = normalize_skill_key(cleaned_name)

    stmt = select(Skill).where(Skill.normalized_key == norm_key)
    existing = session.execute(stmt).scalar_one_or_none()
    if existing:
        return existing

    skill = Skill(
        name=cleaned_name,
        category=category.strip() if category else "technical",
        normalized_key=norm_key,
    )
    session.add(skill)
    session.flush()
    return skill


def upsert_candidate(session: Session, schema: RawCandidateSchema) -> Candidate:
    """Idempotently insert or update a candidate profile and associated children.

    Uses email as natural collision key.

    Args:
        session: Active SQLAlchemy session.
        schema: Validated RawCandidateSchema instance.

    Returns:
        Persisted Candidate entity.
    """
    clean_email = schema.email.strip().lower()
    stmt = select(Candidate).where(Candidate.email == clean_email)
    candidate = session.execute(stmt).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if candidate:
        logger.debug("Updating existing candidate record for email: %s", clean_email)
        candidate.full_name = schema.full_name
        candidate.phone = schema.phone
        candidate.location = schema.location
        candidate.current_title = schema.current_title
        candidate.years_of_experience = schema.years_of_experience
        candidate.education_level = schema.education_level
        candidate.raw_cv_text = schema.raw_cv_text
        candidate.linkedin_url = schema.linkedin_url
        candidate.github_url = schema.github_url
        candidate.updated_at = now

        # Clear existing associations for clean re-population
        candidate.skills.clear()
        candidate.experiences.clear()
        session.flush()
    else:
        candidate_id = schema.candidate_id or str(uuid.uuid4())
        logger.debug("Creating new candidate record with id: %s", candidate_id)
        candidate = Candidate(
            candidate_id=candidate_id,
            full_name=schema.full_name,
            email=clean_email,
            phone=schema.phone,
            location=schema.location,
            current_title=schema.current_title,
            years_of_experience=schema.years_of_experience,
            education_level=schema.education_level,
            raw_cv_text=schema.raw_cv_text,
            linkedin_url=schema.linkedin_url,
            github_url=schema.github_url,
            created_at=now,
            updated_at=now,
        )
        session.add(candidate)
        session.flush()

    # Link candidate skills
    seen_skills = set()
    for sk_input in schema.skills:
        skill = upsert_skill(
            session=session,
            name=sk_input.name,
            category=sk_input.category or "technical",
        )
        if skill.skill_id in seen_skills:
            continue
        seen_skills.add(skill.skill_id)

        assoc = CandidateSkill(
            candidate_id=candidate.candidate_id,
            skill_id=skill.skill_id,
            proficiency_level=sk_input.proficiency_level or "intermediate",
            years_experience=sk_input.years_experience or Decimal("0.0"),
            is_primary=sk_input.is_primary or False,
        )
        candidate.skills.append(assoc)

    # Link candidate experiences
    for exp_input in schema.experiences:
        exp = CandidateExperience(
            candidate_id=candidate.candidate_id,
            company=exp_input.company,
            role_title=exp_input.role_title,
            start_date=exp_input.start_date,
            end_date=exp_input.end_date,
            is_current=exp_input.is_current,
            description=exp_input.description,
            technologies=exp_input.technologies,
        )
        candidate.experiences.append(exp)

    session.flush()
    return candidate


def upsert_job_description(session: Session, schema: RawJobDescriptionSchema) -> JobDescription:
    """Idempotently insert or update a job description and required skills.

    Uses job_code as natural collision key.

    Args:
        session: Active SQLAlchemy session.
        schema: Validated RawJobDescriptionSchema instance.

    Returns:
        Persisted JobDescription entity.
    """
    clean_code = schema.job_code.strip()
    stmt = select(JobDescription).where(JobDescription.job_code == clean_code)
    job = session.execute(stmt).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if job:
        logger.debug("Updating existing job description for job_code: %s", clean_code)
        job.title = schema.title
        job.department = schema.department
        job.location = schema.location
        job.employment_type = schema.employment_type
        job.experience_min_years = schema.experience_min_years
        job.education_level_required = schema.education_level_required
        job.salary_range_min = schema.salary_range_min
        job.salary_range_max = schema.salary_range_max
        job.currency = schema.currency
        job.status = schema.status
        job.raw_description = schema.raw_description
        job.updated_at = now

        job.skills.clear()
        session.flush()
    else:
        job_id = schema.job_id or str(uuid.uuid4())
        logger.debug("Creating new job description with id: %s", job_id)
        job = JobDescription(
            job_id=job_id,
            job_code=clean_code,
            title=schema.title,
            department=schema.department,
            location=schema.location,
            employment_type=schema.employment_type,
            experience_min_years=schema.experience_min_years,
            education_level_required=schema.education_level_required,
            salary_range_min=schema.salary_range_min,
            salary_range_max=schema.salary_range_max,
            currency=schema.currency,
            status=schema.status,
            raw_description=schema.raw_description,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.flush()

    # Link job skills
    seen_skills = set()
    for sk_input in schema.skills:
        skill = upsert_skill(
            session=session,
            name=sk_input.name,
            category=sk_input.category or "technical",
        )
        if skill.skill_id in seen_skills:
            continue
        seen_skills.add(skill.skill_id)

        assoc = JobSkill(
            job_id=job.job_id,
            skill_id=skill.skill_id,
            importance=sk_input.importance,
            weight=sk_input.weight,
            min_years=sk_input.min_years,
        )
        job.skills.append(assoc)

    session.flush()
    return job


def upsert_operational_metric(session: Session, schema: RawOperationalMetricSchema) -> OperationalMetric:
    """Idempotently insert or update a recruitment operational metric record.

    Resolves candidate and job references via natural keys if foreign keys are not directly provided.

    Args:
        session: Active SQLAlchemy session.
        schema: Validated RawOperationalMetricSchema instance.

    Returns:
        Persisted OperationalMetric entity.

    Raises:
        ValueError: If referencing candidate or job cannot be resolved.
    """
    candidate_id = schema.candidate_id
    if candidate_id:
        cand_stmt = select(Candidate.candidate_id).where(Candidate.candidate_id == candidate_id)
        if session.execute(cand_stmt).scalar_one_or_none() is None:
            raise ValueError(f"Candidate not found for candidate_id: {candidate_id}")
    elif schema.candidate_email:
        cand_stmt = select(Candidate.candidate_id).where(
            Candidate.email == schema.candidate_email.strip().lower()
        )
        candidate_id = session.execute(cand_stmt).scalar_one_or_none()
        if not candidate_id:
            raise ValueError(f"Candidate not found for email: {schema.candidate_email}")
    else:
        raise ValueError("Candidate reference missing (neither candidate_id nor candidate_email provided)")

    job_id = schema.job_id
    if job_id:
        job_stmt = select(JobDescription.job_id).where(JobDescription.job_id == job_id)
        if session.execute(job_stmt).scalar_one_or_none() is None:
            raise ValueError(f"Job description not found for job_id: {job_id}")
    elif schema.job_code:
        job_stmt = select(JobDescription.job_id).where(
            JobDescription.job_code == schema.job_code.strip()
        )
        job_id = session.execute(job_stmt).scalar_one_or_none()
        if not job_id:
            raise ValueError(f"Job description not found for code: {schema.job_code}")
    else:
        raise ValueError("Job description reference missing (neither job_id nor job_code provided)")

    metric_id = schema.metric_id or str(uuid.uuid4())

    # Look up by metric_id or candidate_id + job_id + application_date
    stmt = select(OperationalMetric).where(
        (OperationalMetric.metric_id == metric_id) |
        (
            (OperationalMetric.candidate_id == candidate_id) &
            (OperationalMetric.job_id == job_id) &
            (OperationalMetric.application_date == schema.application_date)
        )
    )
    metric = session.execute(stmt).scalar_one_or_none()

    if metric:
        metric.screening_date = schema.screening_date
        metric.technical_interview_date = schema.technical_interview_date
        metric.final_interview_date = schema.final_interview_date
        metric.offer_date = schema.offer_date
        metric.hiring_decision = schema.hiring_decision
        metric.time_to_screen_hours = schema.time_to_screen_hours
        metric.automated_screening_time_seconds = schema.automated_screening_time_seconds
        metric.manual_screening_estimated_minutes = schema.manual_screening_estimated_minutes
        metric.recruiter_name = schema.recruiter_name
        metric.sourcing_channel = schema.sourcing_channel
        metric.cost_per_applicant_eur = schema.cost_per_applicant_eur
    else:
        metric = OperationalMetric(
            metric_id=metric_id,
            candidate_id=candidate_id,
            job_id=job_id,
            application_date=schema.application_date,
            screening_date=schema.screening_date,
            technical_interview_date=schema.technical_interview_date,
            final_interview_date=schema.final_interview_date,
            offer_date=schema.offer_date,
            hiring_decision=schema.hiring_decision,
            time_to_screen_hours=schema.time_to_screen_hours,
            automated_screening_time_seconds=schema.automated_screening_time_seconds,
            manual_screening_estimated_minutes=schema.manual_screening_estimated_minutes,
            recruiter_name=schema.recruiter_name,
            sourcing_channel=schema.sourcing_channel,
            cost_per_applicant_eur=schema.cost_per_applicant_eur,
        )
        session.add(metric)

    session.flush()
    return metric


def save_matching_evaluation(session: Session, dto: MatchingEvaluationDTO) -> MatchingEvaluation:
    """Save or update candidate-to-job matching evaluation outcome.

    Args:
        session: Active SQLAlchemy session.
        dto: Validated MatchingEvaluationDTO.

    Returns:
        Persisted MatchingEvaluation entity.
    """
    stmt = select(MatchingEvaluation).where(
        (MatchingEvaluation.candidate_id == dto.candidate_id) &
        (MatchingEvaluation.job_id == dto.job_id)
    )
    evaluation = session.execute(stmt).scalar_one_or_none()

    eval_id = dto.evaluation_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    matched_json = json.dumps(dto.matched_skills, ensure_ascii=False)
    missing_json = json.dumps(dto.missing_skills, ensure_ascii=False)

    if evaluation:
        evaluation.overall_score = dto.overall_score
        evaluation.skills_score = dto.skills_score
        evaluation.experience_score = dto.experience_score
        evaluation.semantic_similarity = dto.semantic_similarity
        evaluation.recommendation = dto.recommendation
        evaluation.matched_skills = matched_json
        evaluation.missing_skills = missing_json
        evaluation.strengths_summary = dto.strengths_summary
        evaluation.gaps_summary = dto.gaps_summary
        evaluation.executive_summary = dto.executive_summary
        evaluation.evaluated_at = now
    else:
        evaluation = MatchingEvaluation(
            evaluation_id=eval_id,
            candidate_id=dto.candidate_id,
            job_id=dto.job_id,
            overall_score=dto.overall_score,
            skills_score=dto.skills_score,
            experience_score=dto.experience_score,
            semantic_similarity=dto.semantic_similarity,
            recommendation=dto.recommendation,
            matched_skills=matched_json,
            missing_skills=missing_json,
            strengths_summary=dto.strengths_summary,
            gaps_summary=dto.gaps_summary,
            executive_summary=dto.executive_summary,
            evaluated_at=now,
        )
        session.add(evaluation)

    session.flush()
    return evaluation
