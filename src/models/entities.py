"""Relational database models using SQLAlchemy 2.0.

Defines the normalized third normal form (3NF) relational schema for candidates,
skills, job descriptions, matching evaluations, operational metrics, and ETL audit logging.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)


class Base(DeclarativeBase):
    """Declarative base class for all entity models."""
    pass


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    """Enforce SQLite foreign key constraints on every connection."""
    if hasattr(dbapi_connection, "execute"):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


class Skill(Base):
    """Canonical catalog of technical and functional skills."""

    __tablename__ = "skills"

    skill_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    normalized_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    candidate_associations: Mapped[List["CandidateSkill"]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
    )
    job_associations: Mapped[List["JobSkill"]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
    )


class Candidate(Base):
    """Candidate profile entity."""

    __tablename__ = "candidates"

    candidate_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    location: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    current_title: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    years_of_experience: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False, default=Decimal("0.0"))
    education_level: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_cv_text: Mapped[str] = mapped_column(Text, nullable=False)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    github_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    skills: Mapped[List["CandidateSkill"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    experiences: Mapped[List["CandidateExperience"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    evaluations: Mapped[List["MatchingEvaluation"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    operational_metrics: Mapped[List["OperationalMetric"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )


class CandidateSkill(Base):
    """Association between candidates and their verified skills."""

    __tablename__ = "candidate_skills"
    __table_args__ = (
        UniqueConstraint("candidate_id", "skill_id", name="uq_candidate_skill"),
        Index("idx_candidate_skills_cand", "candidate_id"),
        Index("idx_candidate_skills_skill", "skill_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.candidate_id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("skills.skill_id", ondelete="CASCADE"),
        nullable=False,
    )
    proficiency_level: Mapped[str] = mapped_column(String(30), default="intermediate")
    years_experience: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=Decimal("0.0"))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    candidate: Mapped["Candidate"] = relationship(back_populates="skills")
    skill: Mapped["Skill"] = relationship(back_populates="candidate_associations")


class CandidateExperience(Base):
    """Detailed work experience record for a candidate."""

    __tablename__ = "candidate_experiences"
    __table_args__ = (
        Index("idx_candidate_exp_cand", "candidate_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.candidate_id", ondelete="CASCADE"),
        nullable=False,
    )
    company: Mapped[str] = mapped_column(String(150), nullable=False)
    role_title: Mapped[str] = mapped_column(String(150), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    technologies: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="experiences")


class JobDescription(Base):
    """Job vacancy posting specification."""

    __tablename__ = "job_descriptions"
    __table_args__ = (
        Index("idx_job_code", "job_code"),
        Index("idx_job_department", "department"),
        Index("idx_job_status", "status"),
    )

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str] = mapped_column(String(100), nullable=False)
    employment_type: Mapped[str] = mapped_column(String(50), default="Full-time")
    experience_min_years: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=Decimal("0.0"))
    education_level_required: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    salary_range_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    salary_range_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    status: Mapped[str] = mapped_column(String(30), default="open")
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    skills: Mapped[List["JobSkill"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )
    evaluations: Mapped[List["MatchingEvaluation"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )
    operational_metrics: Mapped[List["OperationalMetric"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )


class JobSkill(Base):
    """Association of required and preferred skills for a job vacancy."""

    __tablename__ = "job_skills"
    __table_args__ = (
        UniqueConstraint("job_id", "skill_id", name="uq_job_skill"),
        Index("idx_job_skills_job", "job_id"),
        Index("idx_job_skills_skill", "skill_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("job_descriptions.job_id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("skills.skill_id", ondelete="CASCADE"),
        nullable=False,
    )
    importance: Mapped[str] = mapped_column(String(20), default="required")
    weight: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("1.00"))
    min_years: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=Decimal("0.0"))

    job: Mapped["JobDescription"] = relationship(back_populates="skills")
    skill: Mapped["Skill"] = relationship(back_populates="job_associations")


class MatchingEvaluation(Base):
    """Candidate-to-job matching scores, qualitative synthesis, and recommendations."""

    __tablename__ = "matching_evaluations"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_candidate_job_eval"),
        Index("idx_eval_candidate", "candidate_id"),
        Index("idx_eval_job", "job_id"),
        Index("idx_eval_score", "overall_score"),
    )

    evaluation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.candidate_id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("job_descriptions.job_id", ondelete="CASCADE"),
        nullable=False,
    )
    overall_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    skills_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    experience_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    semantic_similarity: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(30), nullable=False)
    matched_skills: Mapped[str] = mapped_column(Text, nullable=False)
    missing_skills: Mapped[str] = mapped_column(Text, nullable=False)
    strengths_summary: Mapped[str] = mapped_column(Text, nullable=False)
    gaps_summary: Mapped[str] = mapped_column(Text, nullable=False)
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    candidate: Mapped["Candidate"] = relationship(back_populates="evaluations")
    job: Mapped["JobDescription"] = relationship(back_populates="evaluations")


class OperationalMetric(Base):
    """Recruitment operational metrics tracking velocity, funnel progress, and cost."""

    __tablename__ = "operational_metrics"
    __table_args__ = (
        Index("idx_op_candidate", "candidate_id"),
        Index("idx_op_job", "job_id"),
        Index("idx_op_app_date", "application_date"),
        Index("idx_op_decision", "hiring_decision"),
        Index("idx_op_channel", "sourcing_channel"),
    )

    metric_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.candidate_id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("job_descriptions.job_id", ondelete="CASCADE"),
        nullable=False,
    )
    application_date: Mapped[date] = mapped_column(Date, nullable=False)
    screening_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    technical_interview_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    final_interview_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    offer_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    hiring_decision: Mapped[str] = mapped_column(String(30), default="in_progress")
    time_to_screen_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    automated_screening_time_seconds: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.0"))
    manual_screening_estimated_minutes: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("45.0"))
    recruiter_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sourcing_channel: Mapped[str] = mapped_column(String(50), default="Direct Application")
    cost_per_applicant_eur: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    candidate: Mapped["Candidate"] = relationship(back_populates="operational_metrics")
    job: Mapped["JobDescription"] = relationship(back_populates="operational_metrics")


class IngestionBatch(Base):
    """Audit record for an ETL ingestion batch run."""

    __tablename__ = "ingestion_batches"

    batch_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    records_extracted: Mapped[int] = mapped_column(Integer, default=0)
    records_validated: Mapped[int] = mapped_column(Integer, default=0)
    records_loaded: Mapped[int] = mapped_column(Integer, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="in_progress")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    errors: Mapped[List["IngestionError"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
    )


class IngestionError(Base):
    """Quarantined invalid record with error diagnostic information."""

    __tablename__ = "ingestion_errors"
    __table_args__ = (
        Index("idx_ingestion_errors_batch", "batch_id"),
    )

    error_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ingestion_batches.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_record_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw_data: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str] = mapped_column(String(100), nullable=False)
    error_details: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    batch: Mapped["IngestionBatch"] = relationship(back_populates="errors")


def create_db_engine(database_url: str = "sqlite:///data/output/talent_bi.db", echo: bool = False) -> Engine:
    """Create and return a configured SQLAlchemy engine.

    Args:
        database_url: Connection string URI.
        echo: Whether to emit SQL statement logs.

    Returns:
        SQLAlchemy Engine instance.
    """
    if database_url.startswith("sqlite:///") and ":memory:" not in database_url:
        db_file = database_url.replace("sqlite:///", "")
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, echo=echo)


def init_db(engine: Engine) -> None:
    """Create all relational database tables defined in metadata.

    Args:
        engine: Connected SQLAlchemy Engine instance.
    """
    Base.metadata.create_all(engine)


def get_session_factory(engine: Engine) -> sessionmaker:
    """Create and return a session factory for the provided engine.

    Args:
        engine: Configured SQLAlchemy Engine instance.

    Returns:
        Configured sessionmaker instance.
    """
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
