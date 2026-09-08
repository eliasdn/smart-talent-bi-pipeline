"""Integration stress tests for SQLite relational persistence, scaling, cascade deletion, and indexing."""

import random
import time
import tracemalloc
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Tuple

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.etl.loaders import (
    save_matching_evaluation,
    upsert_candidate,
    upsert_job_description,
    upsert_operational_metric,
    upsert_skill,
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
    MatchingEvaluationDTO,
    RawCandidateSchema,
    RawExperienceInput,
    RawJobDescriptionSchema,
    RawJobSkillInput,
    RawOperationalMetricSchema,
    RawSkillInput,
)

SAMPLE_SKILLS = [
    ("Python", "technical"),
    ("SQL", "technical"),
    ("PostgreSQL", "technical"),
    ("Apache Spark", "technical"),
    ("Docker", "technical"),
    ("Kubernetes", "technical"),
    ("AWS", "technical"),
    ("GCP", "technical"),
    ("Azure", "technical"),
    ("FastAPI", "technical"),
    ("Django", "technical"),
    ("Flask", "technical"),
    ("Git", "technical"),
    ("CI/CD", "technical"),
    ("Linux", "technical"),
    ("Scikit-Learn", "technical"),
    ("PyTorch", "technical"),
    ("TensorFlow", "technical"),
    ("Pandas", "technical"),
    ("NumPy", "technical"),
    ("Tableau", "technical"),
    ("Power BI", "technical"),
    ("Snowflake", "technical"),
    ("dbt", "technical"),
    ("Airflow", "technical"),
    ("Kafka", "technical"),
    ("Redis", "technical"),
    ("MongoDB", "technical"),
    ("Elasticsearch", "technical"),
    ("Terraform", "technical"),
    ("Communication", "soft_skill"),
    ("Leadership", "soft_skill"),
    ("Problem Solving", "soft_skill"),
    ("Agile Methodology", "methodology"),
    ("Scrum", "methodology"),
    ("Critical Thinking", "soft_skill"),
    ("Teamwork", "soft_skill"),
    ("Negotiation", "soft_skill"),
    ("Project Management", "methodology"),
    ("Data Modeling", "technical"),
]

DEPARTMENTS = ["Engineering", "Data", "Product", "Operations", "Finance"]
LOCATIONS = ["Paris, France", "Lyon, France", "Remote, France", "Bordeaux, France", "Nantes, France"]
DECISIONS = ["applied", "screened", "interviewed", "offered", "hired", "rejected", "withdrawn"]
CHANNELS = ["LinkedIn", "Direct Application", "Referral", "Indeed", "Job Board"]


def generate_scale_dataset(
    num_candidates: int = 500,
    num_jobs: int = 50,
    num_metrics: int = 2000,
) -> Tuple[List[RawCandidateSchema], List[RawJobDescriptionSchema], List[RawOperationalMetricSchema]]:
    """Generate synthetic typed schemas for scale stress testing."""
    rng = random.Random(42)

    # 1. Candidates
    candidates: List[RawCandidateSchema] = []
    for i in range(num_candidates):
        cid = f"cand-scale-{i:04d}"
        chosen_skills = rng.sample(SAMPLE_SKILLS, k=rng.randint(3, 8))
        skill_inputs = [
            RawSkillInput(
                name=sk_name,
                category=sk_cat,
                proficiency_level=rng.choice(["beginner", "intermediate", "advanced", "expert"]),
                years_experience=Decimal(str(round(rng.uniform(1.0, 10.0), 1))),
                is_primary=idx < 2,
            )
            for idx, (sk_name, sk_cat) in enumerate(chosen_skills)
        ]

        exp_inputs = [
            RawExperienceInput(
                company=f"TechCorp-{rng.randint(100, 999)} SAS",
                role_title=f"Role {rng.choice(['Junior', 'Senior', 'Lead', 'Staff'])} Specialist",
                start_date=date(2018 + exp_idx * 2, 1, 1),
                end_date=date(2019 + exp_idx * 2, 12, 31) if exp_idx < 1 else None,
                is_current=(exp_idx == 1),
                description=f"Developed robust enterprise pipelines and data models for company {exp_idx}.",
                technologies="Python, SQL, Cloud",
            )
            for exp_idx in range(rng.randint(1, 2))
        ]

        cand = RawCandidateSchema(
            candidate_id=cid,
            full_name=f"Candidate {i:04d} Benchmark",
            email=f"candidate.{i:04d}@benchmark.internal",
            phone=f"+33 6 {rng.randint(10, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)}",
            location=rng.choice(LOCATIONS),
            current_title=f"Engineer {i:04d}",
            years_of_experience=Decimal(str(round(rng.uniform(1.0, 15.0), 1))),
            education_level=rng.choice(["Bachelor", "Master", "PhD", "Engineering Diploma"]),
            raw_cv_text=(
                f"Curriculum Vitae for Candidate {i:04d}. Extensive experience in data engineering, "
                f"business intelligence, software development, relational database modeling, and team collaboration."
            ),
            skills=skill_inputs,
            experiences=exp_inputs,
        )
        candidates.append(cand)

    # 2. Job Descriptions
    jobs: List[RawJobDescriptionSchema] = []
    for j in range(num_jobs):
        jid = f"job-scale-{j:03d}"
        chosen_skills = rng.sample(SAMPLE_SKILLS, k=rng.randint(4, 8))
        job_skill_inputs = [
            RawJobSkillInput(
                name=sk_name,
                category=sk_cat,
                importance=rng.choice(["required", "preferred"]),
                weight=Decimal(str(round(rng.uniform(0.5, 1.5), 2))),
                min_years=Decimal(str(round(rng.uniform(1.0, 5.0), 1))),
            )
            for sk_name, sk_cat in chosen_skills
        ]

        job = RawJobDescriptionSchema(
            job_id=jid,
            job_code=f"JOB-SCALE-{j:03d}",
            title=f"Position Title {j:03d}",
            department=rng.choice(DEPARTMENTS),
            location=rng.choice(LOCATIONS),
            employment_type="Full-time",
            experience_min_years=Decimal(str(round(rng.uniform(2.0, 8.0), 1))),
            education_level_required="Master in Computer Science or equivalent",
            salary_range_min=Decimal(str(rng.randint(45, 65) * 1000)),
            salary_range_max=Decimal(str(rng.randint(70, 95) * 1000)),
            currency="EUR",
            status="open",
            raw_description=(
                f"Job specification for vacancy {j:03d}. Seeking talented professionals capable of "
                f"architecting scalable systems, designing clean database schemas, and executing BI analytics."
            ),
            skills=job_skill_inputs,
        )
        jobs.append(job)

    # 3. Operational Metrics
    metrics: List[RawOperationalMetricSchema] = []
    base_date = date(2024, 1, 1)
    for m in range(num_metrics):
        cand_idx = rng.randint(0, num_candidates - 1)
        job_idx = rng.randint(0, num_jobs - 1)
        cand_ref = candidates[cand_idx]
        job_ref = jobs[job_idx]

        app_date = base_date + timedelta(days=rng.randint(0, 180))
        screen_date = app_date + timedelta(days=rng.randint(1, 4))
        tech_date = screen_date + timedelta(days=rng.randint(3, 8))
        final_date = tech_date + timedelta(days=rng.randint(4, 10))
        decision = rng.choice(DECISIONS)
        offer_date = final_date + timedelta(days=rng.randint(2, 5)) if decision == "hired" else None

        metric = RawOperationalMetricSchema(
            metric_id=f"met-scale-{m:05d}",
            candidate_id=cand_ref.candidate_id,
            candidate_email=cand_ref.email,
            job_id=job_ref.job_id,
            job_code=job_ref.job_code,
            application_date=app_date,
            screening_date=screen_date,
            technical_interview_date=tech_date,
            final_interview_date=final_date,
            offer_date=offer_date,
            hiring_decision=decision,
            time_to_screen_hours=Decimal(str(round(rng.uniform(4.0, 48.0), 1))),
            automated_screening_time_seconds=Decimal(str(round(rng.uniform(0.5, 3.5), 2))),
            manual_screening_estimated_minutes=Decimal("45.0"),
            recruiter_name=f"Recruiter {rng.randint(1, 8)}",
            sourcing_channel=rng.choice(CHANNELS),
            cost_per_applicant_eur=Decimal(str(round(rng.uniform(15.0, 120.0), 2))),
        )
        metrics.append(metric)

    return candidates, jobs, metrics


def test_scale_workload_ingestion_and_memory(tmp_sqlite_engine: Engine) -> None:
    """Stress-test ingestion of 500 candidates, 50 jobs, and 2000 metrics in memory."""
    candidates, jobs, metrics = generate_scale_dataset(
        num_candidates=500,
        num_jobs=50,
        num_metrics=2000,
    )

    session_factory = get_session_factory(tmp_sqlite_engine)

    tracemalloc.start()
    t_start = time.perf_counter()

    with session_factory() as session:
        # 1. Ingest candidates
        for c in candidates:
            upsert_candidate(session, c)
        session.commit()

        # 2. Ingest jobs
        for j in jobs:
            upsert_job_description(session, j)
        session.commit()

        # 3. Ingest operational metrics
        for m in metrics:
            upsert_operational_metric(session, m)
        session.commit()

        # 4. Ingest 500 matching evaluations
        rng = random.Random(99)
        for i in range(500):
            cand = candidates[i]
            job = jobs[rng.randint(0, len(jobs) - 1)]
            eval_dto = MatchingEvaluationDTO(
                evaluation_id=f"eval-scale-{i:04d}",
                candidate_id=cand.candidate_id or f"cand-scale-{i:04d}",
                job_id=job.job_id or f"job-scale-{i % 50:03d}",
                overall_score=Decimal(str(round(rng.uniform(50.0, 95.0), 2))),
                skills_score=Decimal(str(round(rng.uniform(50.0, 98.0), 2))),
                experience_score=Decimal(str(round(rng.uniform(40.0, 95.0), 2))),
                semantic_similarity=Decimal(str(round(rng.uniform(0.6000, 0.9500), 4))),
                recommendation=rng.choice(["strong_hire", "hire", "consider", "reject"]),
                matched_skills=["Python", "SQL"],
                missing_skills=["Kubernetes"],
                strengths_summary="Demonstrates solid technical capabilities across multiple core disciplines.",
                gaps_summary="Lacks specialized cloud orchestrator experience.",
                executive_summary="Candidate exhibits strong cultural and technical fit for the role.",
            )
            save_matching_evaluation(session, eval_dto)
        session.commit()

    t_duration = time.perf_counter() - t_start
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mem_mb = peak_mem / (1024 * 1024)

    # Verify counts in DB
    with session_factory() as session:
        total_candidates = session.scalar(select(func.count()).select_from(Candidate))
        total_jobs = session.scalar(select(func.count()).select_from(JobDescription))
        total_metrics = session.scalar(select(func.count()).select_from(OperationalMetric))
        total_evals = session.scalar(select(func.count()).select_from(MatchingEvaluation))
        total_skills = session.scalar(select(func.count()).select_from(Skill))
        total_cand_skills = session.scalar(select(func.count()).select_from(CandidateSkill))
        total_job_skills = session.scalar(select(func.count()).select_from(JobSkill))

    assert total_candidates == 500
    assert total_jobs == 50
    assert total_metrics == 2000
    assert total_evals == 500
    assert total_skills > 30
    assert total_cand_skills > 1500
    assert total_job_skills > 200

    # Total entities loaded = 500 + 50 + 2000 + 500 + skills + cand_skills + job_skills + experiences (~6000 rows)
    # Target assertions
    assert t_duration < 35.0, f"Ingestion too slow: {t_duration:.2f}s"
    assert peak_mem_mb < 50.0, f"Peak memory footprint too high: {peak_mem_mb:.2f}MB"


def test_cascade_delete_candidate_orm(db_session: Session) -> None:
    """Verify ORM-level deletion of a candidate cascades to skills, experiences, evals, and metrics."""
    # Setup candidate with all relationships
    cand = Candidate(
        candidate_id="cand-casc-01",
        full_name="Target Candidate",
        email="target.cand@example.com",
        location="Paris, France",
        years_of_experience=Decimal("5.0"),
        education_level="Master",
        raw_cv_text="Experienced engineer in test cascade deletion.",
    )
    job = JobDescription(
        job_id="job-casc-01",
        job_code="JOB-CASC-01",
        title="Target Job",
        department="Engineering",
        location="Paris, France",
        raw_description="A role requiring robust database testing.",
    )
    skill = Skill(name="Rust", category="technical", normalized_key="rust")
    db_session.add_all([cand, job, skill])
    db_session.flush()

    c_skill = CandidateSkill(candidate_id=cand.candidate_id, skill_id=skill.skill_id)
    c_exp = CandidateExperience(
        candidate_id=cand.candidate_id,
        company="OldCo",
        role_title="Developer",
        start_date=date(2020, 1, 1),
    )
    c_eval = MatchingEvaluation(
        evaluation_id="eval-casc-01",
        candidate_id=cand.candidate_id,
        job_id=job.job_id,
        overall_score=Decimal("85.0"),
        skills_score=Decimal("80.0"),
        experience_score=Decimal("90.0"),
        semantic_similarity=Decimal("0.8500"),
        recommendation="match",
        matched_skills="[]",
        missing_skills="[]",
        strengths_summary="None",
        gaps_summary="None",
        executive_summary="None",
    )
    c_metric = OperationalMetric(
        metric_id="met-casc-01",
        candidate_id=cand.candidate_id,
        job_id=job.job_id,
        application_date=date(2024, 2, 1),
        hiring_decision="interviewed",
    )
    db_session.add_all([c_skill, c_exp, c_eval, c_metric])
    db_session.commit()

    # Verify all records exist
    assert db_session.get(Candidate, "cand-casc-01") is not None
    assert db_session.scalar(select(func.count()).select_from(CandidateSkill).where(CandidateSkill.candidate_id == "cand-casc-01")) == 1
    assert db_session.scalar(select(func.count()).select_from(CandidateExperience).where(CandidateExperience.candidate_id == "cand-casc-01")) == 1
    assert db_session.scalar(select(func.count()).select_from(MatchingEvaluation).where(MatchingEvaluation.candidate_id == "cand-casc-01")) == 1
    assert db_session.scalar(select(func.count()).select_from(OperationalMetric).where(OperationalMetric.candidate_id == "cand-casc-01")) == 1

    # Delete candidate via ORM
    db_session.delete(cand)
    db_session.commit()

    # Verify candidate is gone
    assert db_session.get(Candidate, "cand-casc-01") is None

    # Verify children cascaded to 0
    assert db_session.scalar(select(func.count()).select_from(CandidateSkill).where(CandidateSkill.candidate_id == "cand-casc-01")) == 0
    assert db_session.scalar(select(func.count()).select_from(CandidateExperience).where(CandidateExperience.candidate_id == "cand-casc-01")) == 0
    assert db_session.scalar(select(func.count()).select_from(MatchingEvaluation).where(MatchingEvaluation.candidate_id == "cand-casc-01")) == 0
    assert db_session.scalar(select(func.count()).select_from(OperationalMetric).where(OperationalMetric.candidate_id == "cand-casc-01")) == 0

    # Parent skill and job should remain intact
    assert db_session.get(Skill, skill.skill_id) is not None
    assert db_session.get(JobDescription, "job-casc-01") is not None


def test_cascade_delete_job_orm(db_session: Session) -> None:
    """Verify ORM-level deletion of a job cascades to job_skills, evaluations, and operational metrics."""
    cand = Candidate(
        candidate_id="cand-casc-02",
        full_name="Target Candidate 2",
        email="target2@example.com",
        location="Lyon, France",
        years_of_experience=Decimal("3.0"),
        education_level="Bachelor",
        raw_cv_text="Candidate description text.",
    )
    job = JobDescription(
        job_id="job-casc-02",
        job_code="JOB-CASC-02",
        title="Target Job 2",
        department="Data",
        location="Lyon, France",
        raw_description="Role description text.",
    )
    skill = Skill(name="Go", category="technical", normalized_key="go")
    db_session.add_all([cand, job, skill])
    db_session.flush()

    j_skill = JobSkill(job_id=job.job_id, skill_id=skill.skill_id)
    j_eval = MatchingEvaluation(
        evaluation_id="eval-casc-02",
        candidate_id=cand.candidate_id,
        job_id=job.job_id,
        overall_score=Decimal("75.0"),
        skills_score=Decimal("70.0"),
        experience_score=Decimal("80.0"),
        semantic_similarity=Decimal("0.7500"),
        recommendation="potential",
        matched_skills="[]",
        missing_skills="[]",
        strengths_summary="None",
        gaps_summary="None",
        executive_summary="None",
    )
    j_metric = OperationalMetric(
        metric_id="met-casc-02",
        candidate_id=cand.candidate_id,
        job_id=job.job_id,
        application_date=date(2024, 3, 1),
        hiring_decision="applied",
    )
    db_session.add_all([j_skill, j_eval, j_metric])
    db_session.commit()

    # Delete job via ORM
    db_session.delete(job)
    db_session.commit()

    # Verify job is deleted and children cascaded
    assert db_session.get(JobDescription, "job-casc-02") is None
    assert db_session.scalar(select(func.count()).select_from(JobSkill).where(JobSkill.job_id == "job-casc-02")) == 0
    assert db_session.scalar(select(func.count()).select_from(MatchingEvaluation).where(MatchingEvaluation.job_id == "job-casc-02")) == 0
    assert db_session.scalar(select(func.count()).select_from(OperationalMetric).where(OperationalMetric.job_id == "job-casc-02")) == 0

    # Candidate and skill remain
    assert db_session.get(Candidate, "cand-casc-02") is not None
    assert db_session.get(Skill, skill.skill_id) is not None


def test_cascade_delete_raw_sql_foreign_keys_pragma(tmp_sqlite_engine: Engine) -> None:
    """Verify that SQLite engine-level foreign keys cascade deletes even on raw SQL execution."""
    session_factory = get_session_factory(tmp_sqlite_engine)

    with session_factory() as session:
        cand = Candidate(
            candidate_id="c-raw-01",
            full_name="Raw Candidate",
            email="raw.cand@example.com",
            location="Paris",
            years_of_experience=Decimal("4.0"),
            education_level="Master",
            raw_cv_text="Raw SQL cascade candidate test cv text.",
        )
        job = JobDescription(
            job_id="j-raw-01",
            job_code="JOB-RAW-01",
            title="Raw SQL Job",
            department="Engineering",
            location="Paris",
            raw_description="Raw SQL cascade job description text.",
        )
        skill = Skill(name="Scala", category="technical", normalized_key="scala")
        session.add_all([cand, job, skill])
        session.flush()

        cs = CandidateSkill(candidate_id=cand.candidate_id, skill_id=skill.skill_id)
        ce = CandidateExperience(candidate_id=cand.candidate_id, company="C1", role_title="R1", start_date=date(2021, 1, 1))
        js = JobSkill(job_id=job.job_id, skill_id=skill.skill_id)
        me = MatchingEvaluation(
            evaluation_id="eval-raw-01",
            candidate_id=cand.candidate_id,
            job_id=job.job_id,
            overall_score=Decimal("80"),
            skills_score=Decimal("80"),
            experience_score=Decimal("80"),
            semantic_similarity=Decimal("0.8"),
            recommendation="match",
            matched_skills="[]",
            missing_skills="[]",
            strengths_summary="S",
            gaps_summary="G",
            executive_summary="E",
        )
        om = OperationalMetric(
            metric_id="met-raw-01",
            candidate_id=cand.candidate_id,
            job_id=job.job_id,
            application_date=date(2024, 1, 1),
            hiring_decision="applied",
        )
        batch = IngestionBatch(batch_id="batch-raw-01", source_filename="f.json", source_type="t")
        session.add_all([cs, ce, js, me, om, batch])
        session.flush()

        err = IngestionError(
            batch_id=batch.batch_id,
            raw_record_index=0,
            raw_data="{}",
            error_type="ValueError",
            error_details="details",
        )
        session.add(err)
        session.commit()

        # 1. Execute RAW SQL DELETE on candidates
        session.execute(text("DELETE FROM candidates WHERE candidate_id = 'c-raw-01'"))
        session.commit()

        # Check candidate and children
        assert session.scalar(text("SELECT count(*) FROM candidates WHERE candidate_id = 'c-raw-01'")) == 0
        assert session.scalar(text("SELECT count(*) FROM candidate_skills WHERE candidate_id = 'c-raw-01'")) == 0
        assert session.scalar(text("SELECT count(*) FROM candidate_experiences WHERE candidate_id = 'c-raw-01'")) == 0
        assert session.scalar(text("SELECT count(*) FROM matching_evaluations WHERE candidate_id = 'c-raw-01'")) == 0
        assert session.scalar(text("SELECT count(*) FROM operational_metrics WHERE candidate_id = 'c-raw-01'")) == 0

        # 2. Execute RAW SQL DELETE on job_descriptions
        session.execute(text("DELETE FROM job_descriptions WHERE job_id = 'j-raw-01'"))
        session.commit()
        assert session.scalar(text("SELECT count(*) FROM job_descriptions WHERE job_id = 'j-raw-01'")) == 0
        assert session.scalar(text("SELECT count(*) FROM job_skills WHERE job_id = 'j-raw-01'")) == 0

        # 3. Execute RAW SQL DELETE on ingestion_batches
        session.execute(text("DELETE FROM ingestion_batches WHERE batch_id = 'batch-raw-01'"))
        session.commit()
        assert session.scalar(text("SELECT count(*) FROM ingestion_batches WHERE batch_id = 'batch-raw-01'")) == 0
        assert session.scalar(text("SELECT count(*) FROM ingestion_errors WHERE batch_id = 'batch-raw-01'")) == 0


def test_foreign_key_violation_rejection(db_session: Session) -> None:
    """Verify SQLite rejects orphaned foreign key insertions when parent does not exist."""
    # Invalid candidate_id in CandidateSkill
    orphan_skill = CandidateSkill(
        candidate_id="non-existent-candidate",
        skill_id=99999,
        proficiency_level="beginner",
    )
    db_session.add(orphan_skill)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Invalid job_id in OperationalMetric
    orphan_metric = OperationalMetric(
        metric_id="met-orphan-01",
        candidate_id="non-existent-candidate",
        job_id="non-existent-job",
        application_date=date(2024, 1, 1),
    )
    db_session.add(orphan_metric)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_indexed_queries_performance_and_explain_plan(tmp_sqlite_engine: Engine) -> None:
    """Benchmark query performance and verify index usage via EXPLAIN QUERY PLAN."""
    candidates, jobs, metrics = generate_scale_dataset(
        num_candidates=500,
        num_jobs=50,
        num_metrics=2000,
    )
    session_factory = get_session_factory(tmp_sqlite_engine)

    with session_factory() as session:
        for c in candidates:
            upsert_candidate(session, c)
        for j in jobs:
            upsert_job_description(session, j)
        for m in metrics:
            upsert_operational_metric(session, m)

        rng = random.Random(42)
        for i in range(500):
            eval_dto = MatchingEvaluationDTO(
                evaluation_id=f"eval-idx-{i:04d}",
                candidate_id=candidates[i].candidate_id or f"cand-scale-{i:04d}",
                job_id=jobs[i % 50].job_id or f"job-scale-{i % 50:03d}",
                overall_score=Decimal(str(round(rng.uniform(40.0, 95.0), 2))),
                skills_score=Decimal("80.0"),
                experience_score=Decimal("80.0"),
                semantic_similarity=Decimal("0.8000"),
                recommendation="hire",
                matched_skills=["Python"],
                missing_skills=[],
                strengths_summary="S",
                gaps_summary="G",
                executive_summary="E",
            )
            save_matching_evaluation(session, eval_dto)
        session.commit()

    # Test Queries and EXPLAIN QUERY PLAN
    queries = [
        (
            "Candidate by Email",
            "SELECT * FROM candidates WHERE email = 'candidate.0250@benchmark.internal'",
            True,  # expect index
        ),
        (
            "Candidate by Location",
            "SELECT * FROM candidates WHERE location = 'Paris, France'",
            True,
        ),
        (
            "Job by Code",
            "SELECT * FROM job_descriptions WHERE job_code = 'JOB-SCALE-025'",
            True,
        ),
        (
            "Job by Department",
            "SELECT * FROM job_descriptions WHERE department = 'Engineering'",
            True,
        ),
        (
            "Job by Status",
            "SELECT * FROM job_descriptions WHERE status = 'open'",
            True,
        ),
        (
            "Skill by Normalized Key",
            "SELECT * FROM skills WHERE normalized_key = 'python'",
            True,
        ),
        (
            "Operational Metrics by Candidate",
            "SELECT * FROM operational_metrics WHERE candidate_id = 'cand-scale-0100'",
            True,
        ),
        (
            "Operational Metrics by Job",
            "SELECT * FROM operational_metrics WHERE job_id = 'job-scale-010'",
            True,
        ),
        (
            "Operational Metrics by Sourcing Channel",
            "SELECT * FROM operational_metrics WHERE sourcing_channel = 'LinkedIn'",
            True,
        ),
        (
            "Operational Metrics by Hiring Decision",
            "SELECT * FROM operational_metrics WHERE hiring_decision = 'hired'",
            True,
        ),
        (
            "Evaluations by Score Threshold",
            "SELECT * FROM matching_evaluations WHERE overall_score >= 80.0",
            True,
        ),
    ]

    with session_factory() as session:
        for query_name, sql, expect_index in queries:
            # 1. Check EXPLAIN QUERY PLAN
            plan_rows = session.execute(text(f"EXPLAIN QUERY PLAN {sql}")).fetchall()
            plan_text = " ".join(str(row) for row in plan_rows)

            if expect_index:
                assert (
                    "USING INDEX" in plan_text or "USING COVERING INDEX" in plan_text
                ), f"Query '{query_name}' does not use an index: {plan_text}"

            # 2. Benchmark execution latency over 50 iterations
            latencies = []
            for _ in range(50):
                t0 = time.perf_counter()
                session.execute(text(sql)).fetchall()
                t1 = time.perf_counter()
                latencies.append((t1 - t0) * 1000)  # ms

            avg_ms = sum(latencies) / len(latencies)
            p95_ms = sorted(latencies)[int(len(latencies) * 0.95)]
            assert p95_ms < 5.0, f"Query '{query_name}' p95 latency too high: {p95_ms:.3f}ms (avg: {avg_ms:.3f}ms)"
