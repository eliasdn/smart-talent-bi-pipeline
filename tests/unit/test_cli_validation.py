"""Validation test suite for CLI robustness and error handling.

Tests edge cases and failure modes:
- Non-existent input data directories and database paths
- Corrupted JSON and CSV source input files
- Empty data directory and file-as-directory handling
- Invalid argument types, unknown flags, and invalid subcommands
- Deliverables corruption (missing, empty, or corrupted Excel and PDF)
- Uninitialized and 0-byte SQLite databases (stack trace detection)
"""

import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Generator

import pytest
from typer.testing import CliRunner

from src.cli.main import (
    PipelineOrchestrator,
    app,
    run_pipeline_verification,
)

runner = CliRunner()
PYTHON_EXE = sys.executable
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_pipeline.py"


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide an isolated temporary directory cleaned up after test."""
    td = tempfile.mkdtemp(prefix="test_cli_stress_")
    yield Path(td)
    shutil.rmtree(td, ignore_errors=True)


class TestCLIRobustnessNonExistentPaths:
    """Stress-test CLI behavior when supplied non-existent file or directory paths."""

    def test_ingest_non_existent_data_dir_clean_exit_code_1(self, temp_dir: Path) -> None:
        """Verify ingest fails with code 1 and no unhandled traceback on missing directory."""
        non_existent = temp_dir / "does_not_exist"
        target_db = temp_dir / "test.db"

        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "ingest", "--data-dir", str(non_existent), "--db-path", str(target_db)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr
        assert "Raw data directory does not exist" in proc.stderr or "FAILED" in proc.stdout

    def test_run_all_non_existent_data_dir_clean_exit_code_1(self, temp_dir: Path) -> None:
        """Verify run-all fails with code 1 and no unhandled traceback on missing directory."""
        non_existent = temp_dir / "does_not_exist"
        target_db = temp_dir / "test.db"
        reports_dir = temp_dir / "reports"

        proc = subprocess.run(
            [
                PYTHON_EXE,
                "-m",
                "src.cli.main",
                "run-all",
                "--data-dir",
                str(non_existent),
                "--db-path",
                str(target_db),
                "--output-dir",
                str(reports_dir),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr
        assert "FAILED" in proc.stdout

    def test_match_non_existent_db_clean_exit_code_1(self, temp_dir: Path) -> None:
        """Verify match fails with code 1 and no unhandled traceback on missing database."""
        missing_db = temp_dir / "ghost.db"

        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "match", "--db-path", str(missing_db)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr
        assert "Database file does not exist" in proc.stderr or "failed" in proc.stdout.lower()

    def test_report_non_existent_db_clean_exit_code_1(self, temp_dir: Path) -> None:
        """Verify report fails with code 1 and no unhandled traceback on missing database."""
        missing_db = temp_dir / "ghost.db"
        reports_dir = temp_dir / "reports"

        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "report", "--db-path", str(missing_db), "--output-dir", str(reports_dir)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr
        assert "Database file does not exist" in proc.stderr or "failed" in proc.stdout.lower()

    def test_verify_non_existent_db_clean_exit_code_1(self, temp_dir: Path) -> None:
        """Verify verify fails with code 1 and no unhandled traceback on missing database."""
        missing_db = temp_dir / "ghost.db"
        reports_dir = temp_dir / "reports"

        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "verify", "--db-path", str(missing_db), "--reports-dir", str(reports_dir)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr
        assert "FAIL" in proc.stdout

    def test_standalone_script_non_existent_db_clean_exit_code_1(self, temp_dir: Path) -> None:
        """Verify verify_pipeline.py standalone script fails with code 1 on missing database."""
        missing_db = temp_dir / "ghost.db"
        reports_dir = temp_dir / "reports"

        proc = subprocess.run(
            [PYTHON_EXE, str(VERIFY_SCRIPT), "--db-path", str(missing_db), "--reports-dir", str(reports_dir)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr
        assert "FAIL" in proc.stdout


class TestCLIRobustnessCorruptedInputs:
    """Stress-test CLI behavior when input source files are malformed or invalid."""

    def test_ingest_corrupted_json_syntax_in_candidates(self, temp_dir: Path) -> None:
        """Verify ingestion fails cleanly when candidates.json has invalid JSON syntax."""
        data_dir = temp_dir / "corrupt_raw"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "candidates.json").write_text("{ unclosed invalid json syntax", encoding="utf-8")
        (data_dir / "job_descriptions.json").write_text("[]", encoding="utf-8")
        (data_dir / "operational_metrics.csv").write_text("stage,date\n", encoding="utf-8")
        target_db = temp_dir / "out.db"

        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "ingest", "--data-dir", str(data_dir), "--db-path", str(target_db)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr
        assert "FAILED" in proc.stdout

    def test_ingest_corrupted_json_syntax_in_jobs(self, temp_dir: Path) -> None:
        """Verify ingestion fails cleanly when job_descriptions.json has invalid syntax."""
        data_dir = temp_dir / "corrupt_raw_jobs"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "candidates.json").write_text("[]", encoding="utf-8")
        (data_dir / "job_descriptions.json").write_text("NOT_JSON_AT_ALL", encoding="utf-8")
        (data_dir / "operational_metrics.csv").write_text("stage,date\n", encoding="utf-8")
        target_db = temp_dir / "out.db"

        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "ingest", "--data-dir", str(data_dir), "--db-path", str(target_db)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr
        assert "FAILED" in proc.stdout

    def test_ingest_empty_data_directory(self, temp_dir: Path) -> None:
        """Verify ingestion fails cleanly when data directory contains zero files."""
        empty_dir = temp_dir / "empty_dir"
        empty_dir.mkdir(parents=True, exist_ok=True)
        target_db = temp_dir / "out.db"

        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "ingest", "--data-dir", str(empty_dir), "--db-path", str(target_db)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr
        assert "FAILED" in proc.stdout

    def test_ingest_file_passed_as_directory(self, temp_dir: Path) -> None:
        """Verify ingestion fails cleanly when a file path is passed as data directory."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("dummy text", encoding="utf-8")
        target_db = temp_dir / "out.db"

        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "ingest", "--data-dir", str(file_path), "--db-path", str(target_db)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr


class TestCLIRobustnessInvalidArguments:
    """Stress-test CLI behavior on unknown flags, invalid options, and bad argument types."""

    def test_cli_unknown_option_flag(self) -> None:
        """Verify CLI rejects unrecognized options with non-zero code and no Python traceback."""
        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "ingest", "--non-existent-flag"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0
        assert "Traceback" not in proc.stderr
        assert "No such option" in proc.stderr or "Error" in proc.stderr

    def test_cli_unknown_subcommand(self) -> None:
        """Verify CLI rejects unrecognized subcommands cleanly."""
        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "invalid_subcommand"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0
        assert "Traceback" not in proc.stderr

    def test_cli_match_invalid_top_n_string(self) -> None:
        """Verify CLI match rejects non-integer top-n parameter cleanly."""
        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "match", "--top-n", "not_a_number"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0
        assert "Traceback" not in proc.stderr
        assert "is not a valid integer" in proc.stderr or "Error" in proc.stderr

    def test_standalone_verify_unknown_argument(self) -> None:
        """Verify standalone script rejects unknown arguments with code 2."""
        proc = subprocess.run(
            [PYTHON_EXE, str(VERIFY_SCRIPT), "--unrecognized-option"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 2
        assert "Traceback" not in proc.stderr
        assert "unrecognized arguments" in proc.stderr


class TestCLIRobustnessDeliverablesVerification:
    """Stress-test verification logic against corrupted or missing deliverables."""

    @pytest.fixture
    def populated_db(self, temp_dir: Path) -> Path:
        """Generate a valid populated database using standard raw datasets."""
        raw_dir = REPO_ROOT / "data" / "raw"
        db_path = temp_dir / "valid_talent.db"
        reports_dir = temp_dir / "valid_reports"
        orchestrator = PipelineOrchestrator()
        orchestrator.run_all(data_dir=raw_dir, db_path=db_path, output_dir=reports_dir)
        return db_path

    def test_verify_detects_missing_excel(self, populated_db: Path, temp_dir: Path) -> None:
        """Verify missing Excel report is reported as REP-01 FAIL with exit code 1."""
        empty_reports = temp_dir / "empty_reports"
        empty_reports.mkdir(parents=True, exist_ok=True)

        checks, passed = run_pipeline_verification(db_path=populated_db, reports_dir=empty_reports)
        assert not passed
        rep_01 = next(c for c in checks if c.check_id == "REP-01")
        assert not rep_01.passed

    def test_verify_detects_corrupted_excel(self, populated_db: Path, temp_dir: Path) -> None:
        """Verify corrupt non-zip file named .xlsx is caught gracefully."""
        reports_dir = temp_dir / "corrupt_excel_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "talent_bi_report.xlsx").write_text("NOT AN EXCEL WORKBOOK", encoding="utf-8")

        checks, passed = run_pipeline_verification(db_path=populated_db, reports_dir=reports_dir)
        assert not passed
        rep_01 = next(c for c in checks if c.check_id == "REP-01")
        assert not rep_01.passed
        assert "Error reading workbook" in rep_01.observed

    def test_verify_detects_corrupted_pdf_header(self, populated_db: Path, temp_dir: Path) -> None:
        """Verify non-PDF file named .pdf is caught gracefully."""
        reports_dir = temp_dir / "corrupt_pdf_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "talent_bi_report.xlsx").touch()
        (reports_dir / "executive_evaluation_summary.pdf").write_text("NOT A PDF HEADER", encoding="utf-8")

        checks, passed = run_pipeline_verification(db_path=populated_db, reports_dir=reports_dir)
        assert not passed
        rep_05 = next(c for c in checks if c.check_id == "REP-05")
        assert not rep_05.passed


class TestCLIRobustnessFlawReproduction:
    """Empirical reproduction of unhandled stack traces on edge case databases.

    These tests document the failure modes where the CLI crashes with uncaught
    tracebacks when interacting with 0-byte, corrupt, or uninitialized databases.
    """

    def test_reproduce_match_on_zero_byte_db_stack_trace(self, temp_dir: Path) -> None:
        """Verify match on 0-byte DB fails cleanly with code 1 and NO stack trace."""
        zero_db = temp_dir / "zero.db"
        zero_db.touch()

        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "match", "--db-path", str(zero_db)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr, f"Unhandled traceback detected:\n{proc.stderr}"

    def test_reproduce_report_on_zero_byte_db_stack_trace(self, temp_dir: Path) -> None:
        """Verify report on 0-byte DB fails cleanly with code 1 and NO stack trace."""
        zero_db = temp_dir / "zero.db"
        zero_db.touch()
        reports_dir = temp_dir / "reports"

        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "report", "--db-path", str(zero_db), "--output-dir", str(reports_dir)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr, f"Unhandled traceback detected:\n{proc.stderr}"

    def test_reproduce_verify_on_corrupt_db_stack_trace(self, temp_dir: Path) -> None:
        """Verify verify on corrupt DB fails cleanly with code 1 and NO stack trace."""
        corrupt_db = temp_dir / "corrupt.db"
        corrupt_db.write_bytes(b"NON_SQLITE_BINARY_DATA_CORRUPTION_12345")
        reports_dir = temp_dir / "reports"

        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "verify", "--db-path", str(corrupt_db), "--reports-dir", str(reports_dir)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr, f"Unhandled traceback detected:\n{proc.stderr}"

    def test_reproduce_verify_on_uninitialized_db_stack_trace(self, temp_dir: Path) -> None:
        """Verify verify on uninitialized DB fails cleanly with code 1 and NO stack trace."""
        uninit_db = temp_dir / "uninit.db"
        con = sqlite3.connect(str(uninit_db))
        con.execute("PRAGMA user_version = 1")
        con.commit()
        con.close()
        reports_dir = temp_dir / "reports"

        proc = subprocess.run(
            [PYTHON_EXE, "-m", "src.cli.main", "verify", "--db-path", str(uninit_db), "--reports-dir", str(reports_dir)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr, f"Unhandled traceback detected:\n{proc.stderr}"
