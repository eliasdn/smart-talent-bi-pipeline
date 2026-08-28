"""Transformation, cleansing, and normalization module for extracted data records."""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Union

from src.models.schemas import (
    RawCandidateSchema,
    RawJobDescriptionSchema,
    RawOperationalMetricSchema,
)
from src.utils.logger import setup_logger

logger = setup_logger("smart_talent_bi.etl.transformers")


def normalize_skill_key(raw_name: str) -> str:
    """Normalize a skill name into a canonical, collision-resistant identifier key.

    Examples:
        '  PostgreSQL ' -> 'postgresql'
        'C++' -> 'cpp'
        'C#' -> 'csharp'
        '.NET' -> 'dotnet'
        'Node.js' -> 'node_js'
        'CI/CD' -> 'ci_cd'
        'Scikit-Learn' -> 'scikit_learn'

    Args:
        raw_name: Raw skill name from resume, job posting, or input data.

    Returns:
        Canonical normalized string key.
    """
    key = raw_name.strip().lower()

    # Pre-replace known programming language / framework symbols
    symbol_map = {
        "c++": "cpp",
        "c#": "csharp",
        ".net": "dotnet",
        "ci/cd": "ci_cd",
        "node.js": "node_js",
        "vue.js": "vue_js",
        "react.js": "react_js",
        "angular.js": "angular_js",
        "next.js": "next_js",
        "nuxt.js": "nuxt_js",
        "nest.js": "nest_js",
    }
    if key in symbol_map:
        return symbol_map[key]

    # Replace dots, dashes, slashes, and spaces with underscores
    key = re.sub(r"[\.\-\/\s]+", "_", key)
    # Remove any character that is not alphanumeric or underscore
    key = re.sub(r"[^\w]", "", key)
    # Remove consecutive underscores and trim
    key = re.sub(r"_+", "_", key).strip("_")

    return key or "unnamed_skill"


def parse_date(value: Union[str, date, datetime, None]) -> Optional[date]:
    """Parse various date formats into a standard Python date object.

    Supports:
        - date or datetime instances
        - ISO format: 'YYYY-MM-DD'
        - Slash format: 'YYYY/MM/DD' or 'DD/MM/YYYY'
        - Month-Year format: 'YYYY-MM'

    Args:
        value: Input value representing a date.

    Returns:
        Standard date object, or None if value is empty or unparseable.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    val_str = str(value).strip()
    if not val_str:
        return None

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m",
        "%m/%Y",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(val_str, fmt)
            return parsed.date()
        except ValueError:
            continue

    logger.warning("Unrecognized date format encountered: '%s'", val_str)
    return None


def calculate_experience_years(
    start_date: date,
    end_date: Optional[date] = None,
    is_current: bool = False,
) -> Decimal:
    """Calculate professional tenure in decimal years.

    Args:
        start_date: Role commencement date.
        end_date: Optional role termination date.
        is_current: Flag indicating whether employment is ongoing.

    Returns:
        Tenure in years rounded to one decimal place.
    """
    effective_end = date.today() if (is_current or end_date is None) else end_date
    if effective_end < start_date:
        return Decimal("0.0")

    days = (effective_end - start_date).days
    years = Decimal(days) / Decimal("365.25")
    return round(years, 1)


def transform_candidate(raw: Dict[str, Any]) -> RawCandidateSchema:
    """Cleanse, validate, and structure a raw candidate record.

    Args:
        raw: Raw candidate dictionary extracted from source file.

    Returns:
        Validated RawCandidateSchema model.
    """
    data = dict(raw)
    if not data.get("candidate_id"):
        data["candidate_id"] = str(uuid.uuid4())

    # Ensure numeric years of experience is valid Decimal
    if "years_of_experience" in data:
        try:
            data["years_of_experience"] = Decimal(str(data["years_of_experience"]))
        except (InvalidOperation, TypeError):
            data["years_of_experience"] = Decimal("0.0")

    # Validate against Pydantic schema
    return RawCandidateSchema.model_validate(data)


def transform_job_description(raw: Dict[str, Any]) -> RawJobDescriptionSchema:
    """Cleanse, validate, and structure a raw job description record.

    Args:
        raw: Raw job vacancy dictionary extracted from source file.

    Returns:
        Validated RawJobDescriptionSchema model.
    """
    data = dict(raw)
    if not data.get("job_id"):
        data["job_id"] = str(uuid.uuid4())

    if "experience_min_years" in data:
        try:
            data["experience_min_years"] = Decimal(str(data["experience_min_years"]))
        except (InvalidOperation, TypeError):
            data["experience_min_years"] = Decimal("0.0")

    return RawJobDescriptionSchema.model_validate(data)


def transform_operational_metric(raw: Dict[str, Any]) -> RawOperationalMetricSchema:
    """Cleanse, validate, and structure a raw operational metric record from CSV or JSON.

    Args:
        raw: Raw tabular dictionary extracted from operational records.

    Returns:
        Validated RawOperationalMetricSchema model.
    """
    data = dict(raw)
    if not data.get("metric_id"):
        data["metric_id"] = str(uuid.uuid4())

    # Clean empty strings from CSV rows to None or default values
    date_fields = [
        "application_date",
        "screening_date",
        "technical_interview_date",
        "final_interview_date",
        "offer_date",
    ]
    for field in date_fields:
        raw_val = data.get(field)
        if raw_val is not None:
            if isinstance(raw_val, str) and not raw_val.strip():
                data[field] = None
            else:
                data[field] = parse_date(raw_val)

    # Clean numeric fields
    decimal_fields = [
        ("time_to_screen_hours", None),
        ("automated_screening_time_seconds", Decimal("0.0")),
        ("manual_screening_estimated_minutes", Decimal("45.0")),
        ("cost_per_applicant_eur", Decimal("0.0")),
    ]
    for field, default in decimal_fields:
        val = data.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            data[field] = default
        else:
            try:
                data[field] = Decimal(str(val))
            except (InvalidOperation, TypeError):
                data[field] = default

    return RawOperationalMetricSchema.model_validate(data)
