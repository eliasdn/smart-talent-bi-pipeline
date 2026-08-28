"""Raw file extraction module for JSON and CSV datasets."""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Union

from src.utils.logger import setup_logger

logger = setup_logger("smart_talent_bi.etl.extractors")


class DataExtractionError(Exception):
    """Raised when an extraction operation fails to read or parse source data."""
    pass


def extract_json(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Extract and parse structured records from a UTF-8 JSON file.

    Args:
        file_path: Path to the JSON source file.

    Returns:
        List of raw dictionaries representing individual records.

    Raises:
        FileNotFoundError: If the target file does not exist.
        DataExtractionError: If the file contents cannot be parsed as valid JSON.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error("JSON file not found: %s", path)
        raise FileNotFoundError(f"Source JSON file not found: {path}")

    logger.info("Extracting records from JSON file: %s", path)
    try:
        with open(path, mode="r", encoding="utf-8") as f:
            content = json.load(f)
    except json.JSONDecodeError as exc:
        logger.error("JSON parsing error in %s: %s", path, exc)
        raise DataExtractionError(f"Malformed JSON content in {path}: {exc}") from exc
    except Exception as exc:
        logger.error("Unexpected error reading %s: %s", path, exc)
        raise DataExtractionError(f"Failed to read file {path}: {exc}") from exc

    if isinstance(content, list):
        return content
    elif isinstance(content, dict):
        # Allow wrapper dictionaries such as {"candidates": [...]}
        for key in ("candidates", "jobs", "job_descriptions", "metrics", "data", "records"):
            if key in content and isinstance(content[key], list):
                return content[key]
        return [content]
    else:
        raise DataExtractionError(f"Expected list or object at root of {path}, got {type(content).__name__}")


def extract_csv(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Extract and parse tabular records from a UTF-8 encoded CSV file.

    Args:
        file_path: Path to the CSV source file.

    Returns:
        List of raw dictionaries mapping header names to string values.

    Raises:
        FileNotFoundError: If the target file does not exist.
        DataExtractionError: If the CSV file is empty or corrupted.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error("CSV file not found: %s", path)
        raise FileNotFoundError(f"Source CSV file not found: {path}")

    logger.info("Extracting records from CSV file: %s", path)
    records: List[Dict[str, Any]] = []
    try:
        # utf-8-sig handles UTF-8 with or without Byte Order Mark (BOM)
        with open(path, mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise DataExtractionError(f"CSV file is empty or missing headers: {path}")

            # Clean header keys (strip leading/trailing whitespace)
            for row_idx, row in enumerate(reader, start=1):
                clean_row = {
                    (k.strip() if k else f"col_{idx}"): (v.strip() if isinstance(v, str) else v)
                    for idx, (k, v) in enumerate(row.items())
                    if k is not None
                }
                # Skip entirely empty rows
                if any(v for v in clean_row.values() if v is not None and v != ""):
                    records.append(clean_row)

    except (csv.Error, UnicodeDecodeError) as exc:
        logger.error("CSV read failure for %s: %s", path, exc)
        raise DataExtractionError(f"Failed to parse CSV file {path}: {exc}") from exc
    except DataExtractionError:
        raise
    except Exception as exc:
        logger.error("Unexpected error reading CSV %s: %s", path, exc)
        raise DataExtractionError(f"Failed to read CSV file {path}: {exc}") from exc

    logger.info("Successfully extracted %d records from %s", len(records), path)
    return records
