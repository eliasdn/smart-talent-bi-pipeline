"""ETL ingestion pipeline package."""

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

__all__ = [
    "DataExtractionError",
    "extract_json",
    "extract_csv",
    "normalize_skill_key",
    "parse_date",
    "calculate_experience_years",
    "transform_candidate",
    "transform_job_description",
    "transform_operational_metric",
    "upsert_skill",
    "upsert_candidate",
    "upsert_job_description",
    "upsert_operational_metric",
    "save_matching_evaluation",
    "ingest_candidates",
    "ingest_job_descriptions",
    "ingest_operational_metrics",
    "ETLPipeline",
]
