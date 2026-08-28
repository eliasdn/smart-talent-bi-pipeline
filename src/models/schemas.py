"""Pydantic v2 validation schemas and Data Transfer Objects (DTOs).

Defines validation rules for raw candidate, job description, and operational metric
inputs, as well as strongly typed DTOs shared across pipeline modules.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


class RawSkillInput(BaseModel):
    """Raw skill requirement or possession descriptor."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=1, max_length=100)
    category: Optional[str] = Field("technical", max_length=50)
    proficiency_level: Optional[Literal["beginner", "intermediate", "advanced", "expert"]] = "intermediate"
    years_experience: Optional[Decimal] = Field(Decimal("0.0"), ge=0, le=50)
    is_primary: Optional[bool] = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Skill name cannot be empty or whitespace only")
        return cleaned


class RawExperienceInput(BaseModel):
    """Raw professional experience record from candidate profile."""

    model_config = ConfigDict(extra="ignore")

    company: str = Field(..., min_length=1, max_length=150)
    role_title: str = Field(..., min_length=1, max_length=150)
    start_date: date
    end_date: Optional[date] = None
    is_current: bool = False
    description: Optional[str] = None
    technologies: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self) -> "RawExperienceInput":
        if not self.is_current and self.end_date is not None:
            if self.end_date < self.start_date:
                raise ValueError(
                    f"end_date ({self.end_date}) cannot precede start_date ({self.start_date})"
                )
        return self


class RawCandidateSchema(BaseModel):
    """Schema for validating ingested candidate records."""

    model_config = ConfigDict(extra="ignore")

    candidate_id: Optional[str] = None
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=50)
    location: str = Field(..., min_length=2, max_length=100)
    current_title: Optional[str] = Field(None, max_length=150)
    years_of_experience: Decimal = Field(default=Decimal("0.0"), ge=0, le=50)
    education_level: str = Field(..., min_length=2, max_length=100)
    raw_cv_text: str = Field(..., min_length=20)
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    skills: List[RawSkillInput] = Field(default_factory=list)
    experiences: List[RawExperienceInput] = Field(default_factory=list)

    @field_validator("full_name", "location")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class RawJobSkillInput(BaseModel):
    """Raw skill requirement within a job posting."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=1, max_length=100)
    category: Optional[str] = "technical"
    importance: Literal["required", "preferred", "nice_to_have"] = "required"
    weight: Decimal = Field(Decimal("1.00"), ge=0, le=5)
    min_years: Decimal = Field(Decimal("0.0"), ge=0, le=50)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Skill name cannot be empty or whitespace only")
        return cleaned


class RawJobDescriptionSchema(BaseModel):
    """Schema for validating ingested job description records."""

    model_config = ConfigDict(extra="ignore")

    job_id: Optional[str] = None
    job_code: str = Field(..., min_length=3, max_length=50)
    title: str = Field(..., min_length=2, max_length=150)
    department: str = Field(..., min_length=2, max_length=100)
    location: str = Field(..., min_length=2, max_length=100)
    employment_type: str = Field("Full-time", max_length=50)
    experience_min_years: Decimal = Field(Decimal("0.0"), ge=0, le=50)
    education_level_required: Optional[str] = None
    salary_range_min: Optional[Decimal] = Field(None, ge=0)
    salary_range_max: Optional[Decimal] = Field(None, ge=0)
    currency: str = Field("EUR", max_length=3)
    status: Literal["open", "interviewing", "closed", "cancelled"] = "open"
    raw_description: str = Field(..., min_length=20)
    skills: List[RawJobSkillInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_salaries(self) -> "RawJobDescriptionSchema":
        if self.salary_range_min is not None and self.salary_range_max is not None:
            if self.salary_range_max < self.salary_range_min:
                raise ValueError("salary_range_max cannot be lower than salary_range_min")
        return self


class RawOperationalMetricSchema(BaseModel):
    """Schema for validating recruitment operational funnel records."""

    model_config = ConfigDict(extra="ignore")

    metric_id: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_id: Optional[str] = None
    job_code: Optional[str] = None
    job_id: Optional[str] = None
    application_date: date
    screening_date: Optional[date] = None
    technical_interview_date: Optional[date] = None
    final_interview_date: Optional[date] = None
    offer_date: Optional[date] = None
    hiring_decision: Literal[
        "applied", "screened", "interviewed", "offered", "hired", "rejected", "withdrawn", "in_progress"
    ] = "applied"
    time_to_screen_hours: Optional[Decimal] = Field(None, ge=0)
    automated_screening_time_seconds: Decimal = Field(Decimal("0.0"), ge=0)
    manual_screening_estimated_minutes: Decimal = Field(Decimal("45.0"), ge=0)
    recruiter_name: Optional[str] = None
    sourcing_channel: str = Field("Direct Application", max_length=50)
    cost_per_applicant_eur: Decimal = Field(Decimal("0.0"), ge=0)

    @model_validator(mode="after")
    def validate_identifying_keys(self) -> "RawOperationalMetricSchema":
        if not self.candidate_id and not self.candidate_email:
            raise ValueError("Either candidate_id or candidate_email must be provided")
        if not self.job_id and not self.job_code:
            raise ValueError("Either job_id or job_code must be provided")
        return self


# --- Data Transfer Objects (DTOs) for downstream modules ---

class CandidateSkillDTO(BaseModel):
    """DTO representing an individual skill possessed by a candidate."""

    name: str
    category: str
    proficiency_level: str
    years_experience: Decimal
    is_primary: bool


class CandidateProfileDTO(BaseModel):
    """DTO representing candidate profile information for matching and analysis."""

    candidate_id: str
    full_name: str
    email: str
    location: str
    current_title: Optional[str] = None
    years_of_experience: Decimal
    education_level: str
    raw_cv_text: str
    skills: List[CandidateSkillDTO] = Field(default_factory=list)

    @property
    def years_experience(self) -> Decimal:
        """Alias for years_of_experience matching interface contract."""
        return self.years_of_experience


class JobSkillRequirementDTO(BaseModel):
    """DTO representing a required or preferred skill for a vacancy."""

    name: str
    category: str
    importance: str
    weight: Decimal
    min_years: Decimal


class JobPostingDTO(BaseModel):
    """DTO representing job vacancy specifications for matching."""

    job_id: str
    job_code: str
    title: str
    department: str
    location: str
    experience_min_years: Decimal
    education_level_required: Optional[str] = None
    raw_description: str
    skills: List[JobSkillRequirementDTO] = Field(default_factory=list)


class MatchingEvaluationDTO(BaseModel):
    """DTO representing candidate-to-job matching results."""

    evaluation_id: Optional[str] = None
    candidate_id: str
    job_id: str
    overall_score: Decimal
    skills_score: Decimal
    experience_score: Decimal
    semantic_similarity: Decimal
    recommendation: Literal["strong_hire", "hire", "consider", "reject"]
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    strengths_summary: str
    gaps_summary: str
    executive_summary: str


class IngestionBatchSummaryDTO(BaseModel):
    """DTO summarizing an ETL ingestion batch result."""

    batch_id: str
    source_filename: str
    source_type: str
    records_extracted: int
    records_validated: int
    records_loaded: int
    records_rejected: int
    status: str
    error_summary: Optional[str] = None
