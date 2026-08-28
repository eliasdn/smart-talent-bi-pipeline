"""End-to-end ETL orchestration pipeline with audit logging and error quarantine."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.config import get_settings
from src.etl.extractors import DataExtractionError, extract_csv, extract_json
from src.etl.loaders import (
    upsert_candidate,
    upsert_job_description,
    upsert_operational_metric,
)
from src.etl.transformers import (
    transform_candidate,
    transform_job_description,
    transform_operational_metric,
)
from src.models.entities import (
    IngestionBatch,
    IngestionError,
    create_db_engine,
    get_session_factory,
    init_db,
)
from src.models.schemas import IngestionBatchSummaryDTO
from src.utils.logger import setup_logger

logger = setup_logger("smart_talent_bi.etl.pipeline")


def _record_quarantine_error(
    session: Session,
    batch_id: str,
    record_index: int,
    raw_data: Any,
    error: Exception,
) -> IngestionError:
    """Persist an invalid payload and error trace to the ingestion quarantine table.

    Args:
        session: Active SQLAlchemy session.
        batch_id: Foreign key of active ingestion batch.
        record_index: Zero-based record index in the source file.
        raw_data: Raw unparsed record data.
        error: Captured validation or processing exception.

    Returns:
        Created IngestionError entity.
    """
    try:
        raw_str = json.dumps(raw_data, default=str, ensure_ascii=False)
    except Exception:
        raw_str = str(raw_data)

    quarantine_entry = IngestionError(
        batch_id=batch_id,
        raw_record_index=record_index,
        raw_data=raw_str,
        error_type=type(error).__name__,
        error_details=str(error),
        created_at=datetime.now(timezone.utc),
    )
    with session.begin_nested():
        session.add(quarantine_entry)
        session.flush()
    return quarantine_entry


def ingest_candidates(file_path: Path, session: Session) -> IngestionBatchSummaryDTO:
    """Extract, validate, cleanse, and load candidate profiles.

    Args:
        file_path: Path to candidates JSON file.
        session: Active SQLAlchemy session.

    Returns:
        IngestionBatchSummaryDTO containing execution metrics.
    """
    batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    batch = IngestionBatch(
        batch_id=batch_id,
        source_filename=str(file_path.name),
        source_type="candidates_json",
        records_extracted=0,
        records_validated=0,
        records_loaded=0,
        records_rejected=0,
        status="in_progress",
        started_at=now,
    )
    session.add(batch)
    session.flush()

    logger.info("Starting candidate ingestion batch: %s (%s)", batch_id, file_path)
    try:
        records = extract_json(file_path)
    except Exception as exc:
        batch.status = "failed"
        batch.finished_at = datetime.now(timezone.utc)
        batch.error_summary = f"Extraction failure: {exc}"
        session.flush()
        return IngestionBatchSummaryDTO(
            batch_id=batch.batch_id,
            source_filename=batch.source_filename,
            source_type=batch.source_type,
            records_extracted=0,
            records_validated=0,
            records_loaded=0,
            records_rejected=0,
            status=batch.status,
            error_summary=batch.error_summary,
        )

    batch.records_extracted = len(records)

    for idx, raw_record in enumerate(records):
        try:
            with session.begin_nested():
                validated = transform_candidate(raw_record)
                batch.records_validated += 1
                upsert_candidate(session, validated)
                batch.records_loaded += 1
        except (ValidationError, ValueError, Exception) as exc:
            logger.warning("Candidate record %d rejected: %s", idx, exc)
            batch.records_rejected += 1
            _record_quarantine_error(session, batch_id, idx, raw_record, exc)

    batch.finished_at = datetime.now(timezone.utc)
    if batch.records_rejected == 0:
        batch.status = "completed"
    elif batch.records_loaded > 0:
        batch.status = "partial"
        batch.error_summary = f"{batch.records_rejected} records quarantined"
    else:
        batch.status = "failed"
        batch.error_summary = f"All {batch.records_rejected} records quarantined"

    session.flush()
    logger.info(
        "Candidate ingestion batch %s finished: loaded=%d, rejected=%d",
        batch_id,
        batch.records_loaded,
        batch.records_rejected,
    )
    return IngestionBatchSummaryDTO(
        batch_id=batch.batch_id,
        source_filename=batch.source_filename,
        source_type=batch.source_type,
        records_extracted=batch.records_extracted,
        records_validated=batch.records_validated,
        records_loaded=batch.records_loaded,
        records_rejected=batch.records_rejected,
        status=batch.status,
        error_summary=batch.error_summary,
    )


def ingest_job_descriptions(file_path: Path, session: Session) -> IngestionBatchSummaryDTO:
    """Extract, validate, cleanse, and load job descriptions.

    Args:
        file_path: Path to job descriptions JSON file.
        session: Active SQLAlchemy session.

    Returns:
        IngestionBatchSummaryDTO containing execution metrics.
    """
    batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    batch = IngestionBatch(
        batch_id=batch_id,
        source_filename=str(file_path.name),
        source_type="job_descriptions_json",
        records_extracted=0,
        records_validated=0,
        records_loaded=0,
        records_rejected=0,
        status="in_progress",
        started_at=now,
    )
    session.add(batch)
    session.flush()

    logger.info("Starting job descriptions ingestion batch: %s (%s)", batch_id, file_path)
    try:
        records = extract_json(file_path)
    except Exception as exc:
        batch.status = "failed"
        batch.finished_at = datetime.now(timezone.utc)
        batch.error_summary = f"Extraction failure: {exc}"
        session.flush()
        return IngestionBatchSummaryDTO(
            batch_id=batch.batch_id,
            source_filename=batch.source_filename,
            source_type=batch.source_type,
            records_extracted=0,
            records_validated=0,
            records_loaded=0,
            records_rejected=0,
            status=batch.status,
            error_summary=batch.error_summary,
        )

    batch.records_extracted = len(records)

    for idx, raw_record in enumerate(records):
        try:
            with session.begin_nested():
                validated = transform_job_description(raw_record)
                batch.records_validated += 1
                upsert_job_description(session, validated)
                batch.records_loaded += 1
        except (ValidationError, ValueError, Exception) as exc:
            logger.warning("Job description record %d rejected: %s", idx, exc)
            batch.records_rejected += 1
            _record_quarantine_error(session, batch_id, idx, raw_record, exc)

    batch.finished_at = datetime.now(timezone.utc)
    if batch.records_rejected == 0:
        batch.status = "completed"
    elif batch.records_loaded > 0:
        batch.status = "partial"
        batch.error_summary = f"{batch.records_rejected} records quarantined"
    else:
        batch.status = "failed"
        batch.error_summary = f"All {batch.records_rejected} records quarantined"

    session.flush()
    logger.info(
        "Job descriptions ingestion batch %s finished: loaded=%d, rejected=%d",
        batch_id,
        batch.records_loaded,
        batch.records_rejected,
    )
    return IngestionBatchSummaryDTO(
        batch_id=batch.batch_id,
        source_filename=batch.source_filename,
        source_type=batch.source_type,
        records_extracted=batch.records_extracted,
        records_validated=batch.records_validated,
        records_loaded=batch.records_loaded,
        records_rejected=batch.records_rejected,
        status=batch.status,
        error_summary=batch.error_summary,
    )


def ingest_operational_metrics(file_path: Path, session: Session) -> IngestionBatchSummaryDTO:
    """Extract, validate, cleanse, and load recruitment operational metrics.

    Args:
        file_path: Path to operational metrics CSV file.
        session: Active SQLAlchemy session.

    Returns:
        IngestionBatchSummaryDTO containing execution metrics.
    """
    batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    batch = IngestionBatch(
        batch_id=batch_id,
        source_filename=str(file_path.name),
        source_type="operational_metrics_csv",
        records_extracted=0,
        records_validated=0,
        records_loaded=0,
        records_rejected=0,
        status="in_progress",
        started_at=now,
    )
    session.add(batch)
    session.flush()

    logger.info("Starting operational metrics ingestion batch: %s (%s)", batch_id, file_path)
    try:
        records = extract_csv(file_path)
    except Exception as exc:
        batch.status = "failed"
        batch.finished_at = datetime.now(timezone.utc)
        batch.error_summary = f"Extraction failure: {exc}"
        session.flush()
        return IngestionBatchSummaryDTO(
            batch_id=batch.batch_id,
            source_filename=batch.source_filename,
            source_type=batch.source_type,
            records_extracted=0,
            records_validated=0,
            records_loaded=0,
            records_rejected=0,
            status=batch.status,
            error_summary=batch.error_summary,
        )

    batch.records_extracted = len(records)

    for idx, raw_record in enumerate(records):
        try:
            with session.begin_nested():
                validated = transform_operational_metric(raw_record)
                batch.records_validated += 1
                upsert_operational_metric(session, validated)
                batch.records_loaded += 1
        except (ValidationError, ValueError, Exception) as exc:
            logger.warning("Operational metric record %d rejected: %s", idx, exc)
            batch.records_rejected += 1
            _record_quarantine_error(session, batch_id, idx, raw_record, exc)

    batch.finished_at = datetime.now(timezone.utc)
    if batch.records_rejected == 0:
        batch.status = "completed"
    elif batch.records_loaded > 0:
        batch.status = "partial"
        batch.error_summary = f"{batch.records_rejected} records quarantined"
    else:
        batch.status = "failed"
        batch.error_summary = f"All {batch.records_rejected} records quarantined"

    session.flush()
    logger.info(
        "Operational metrics ingestion batch %s finished: loaded=%d, rejected=%d",
        batch_id,
        batch.records_loaded,
        batch.records_rejected,
    )
    return IngestionBatchSummaryDTO(
        batch_id=batch.batch_id,
        source_filename=batch.source_filename,
        source_type=batch.source_type,
        records_extracted=batch.records_extracted,
        records_validated=batch.records_validated,
        records_loaded=batch.records_loaded,
        records_rejected=batch.records_rejected,
        status=batch.status,
        error_summary=batch.error_summary,
    )


class ETLPipeline:
    """Coordinator for running all ETL ingestion jobs."""

    def __init__(self, engine: Optional[Engine] = None) -> None:
        """Initialize pipeline with target database engine.

        Args:
            engine: Optional SQLAlchemy engine. Defaults to configured database_url.
        """
        if engine is None:
            settings = get_settings()
            engine = create_db_engine(settings.database_url)
        self.engine = engine
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)

    def run_all(self, raw_data_dir: Optional[Path] = None) -> Dict[str, IngestionBatchSummaryDTO]:
        """Execute complete ingestion sequence for candidates, jobs, and operational metrics.

        Args:
            raw_data_dir: Optional path to raw data folder. Defaults to config raw_data_dir.

        Returns:
            Dictionary mapping entity names to IngestionBatchSummaryDTO.
        """
        settings = get_settings()
        data_dir = Path(raw_data_dir or settings.raw_data_dir)

        results: Dict[str, IngestionBatchSummaryDTO] = {}

        candidates_file = data_dir / "candidates.json"
        jobs_file = data_dir / "job_descriptions.json"
        metrics_file = data_dir / "operational_metrics.csv"

        with self.session_factory() as session:
            # 1. Ingest candidates first
            if candidates_file.exists():
                results["candidates"] = ingest_candidates(candidates_file, session)
            else:
                logger.warning("Candidates file not found: %s", candidates_file)

            # 2. Ingest job descriptions second
            if jobs_file.exists():
                results["job_descriptions"] = ingest_job_descriptions(jobs_file, session)
            else:
                logger.warning("Job descriptions file not found: %s", jobs_file)

            # 3. Ingest operational metrics third (referencing candidates and jobs)
            if metrics_file.exists():
                results["operational_metrics"] = ingest_operational_metrics(metrics_file, session)
            else:
                logger.warning("Operational metrics file not found: %s", metrics_file)

            session.commit()

        return results
