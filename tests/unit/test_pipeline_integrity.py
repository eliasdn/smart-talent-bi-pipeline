"""Edge-case and failure-injection test suite for pipeline verification.

Stress-tests scripts/verify_pipeline.py and run_pipeline_verification:
1. Missing and empty database files
2. Dropping each of the 10 relational schema tables
3. Low record count thresholds (candidates < 10, jobs < 4, metrics < 36, evals < 40)
4. Foreign key constraint violations (PRAGMA foreign_key_check)
5. Out-of-bounds score and similarity boundaries ([0.0, 100.0] and [0.0, 1.0])
6. Missing reports directory and missing report files
7. Corrupted Excel binary files and truncated payloads
8. Missing and empty Excel sheets
9. Corrupted PDF headers, truncated sizes, and invalid stream bodies
10. Exit code 1 verification across all defect injections via standalone subprocess
"""

import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Generator, Tuple

import openpyxl
import pytest

from src.cli.main import VerificationCheckResult, run_pipeline_verification

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROD_DB_PATH = REPO_ROOT / "data" / "output" / "talent_bi.db"
PROD_REPORTS_DIR = REPO_ROOT / "data" / "output" / "reports"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_pipeline.py"


@pytest.fixture
def sandbox_env(tmp_path: Path) -> Generator[Tuple[Path, Path], None, None]:
    """Provide isolated copies of valid database and generated reports."""
    sandbox_db = tmp_path / "talent_bi.db"
    sandbox_reports = tmp_path / "reports"
    sandbox_reports.mkdir(parents=True, exist_ok=True)

    # Copy production DB and reports to sandbox
    shutil.copy2(PROD_DB_PATH, sandbox_db)
    for report_file in PROD_REPORTS_DIR.iterdir():
        if report_file.is_file():
            shutil.copy2(report_file, sandbox_reports / report_file.name)

    yield sandbox_db, sandbox_reports


def run_verify_script(db_path: Path, reports_dir: Path) -> subprocess.CompletedProcess:
    """Execute standalone verification script via subprocess and return result."""
    cmd = [
        sys.executable,
        str(VERIFY_SCRIPT),
        "--db-path",
        str(db_path),
        "--reports-dir",
        str(reports_dir),
    ]
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )


class TestAdversarialDatabaseFailures:
    """Adversarial challenge tests targeting database-level failure modes."""

    def test_missing_database_file(self, sandbox_env: Tuple[Path, Path], tmp_path: Path) -> None:
        """Verify standalone script and verification routine fail on missing database."""
        _, reports_dir = sandbox_env
        missing_db = tmp_path / "non_existent_database.db"

        # Programmatic check
        checks, all_passed = run_pipeline_verification(missing_db, reports_dir)
        assert not all_passed
        assert len(checks) == 1
        assert checks[0].check_id == "DB-01"
        assert not checks[0].passed
        assert "File missing or 0 bytes" in checks[0].observed

        # Subprocess check
        proc = run_verify_script(missing_db, reports_dir)
        assert proc.returncode == 1
        assert "DB-01" in proc.stdout

    def test_zero_byte_empty_database_file(self, sandbox_env: Tuple[Path, Path], tmp_path: Path) -> None:
        """Verify standalone script fails when database is 0 bytes."""
        _, reports_dir = sandbox_env
        empty_db = tmp_path / "empty_zero_bytes.db"
        empty_db.touch()

        checks, all_passed = run_pipeline_verification(empty_db, reports_dir)
        assert not all_passed
        assert checks[0].check_id == "DB-01"
        assert not checks[0].passed

        proc = run_verify_script(empty_db, reports_dir)
        assert proc.returncode == 1

    @pytest.mark.parametrize(
        "table_to_drop",
        [
            "skills",
            "candidate_skills",
            "candidate_experiences",
            "job_skills",
            "ingestion_batches",
            "ingestion_errors",
            "matching_evaluations",
            "operational_metrics",
            "job_descriptions",
            "candidates",
        ],
    )
    def test_dropped_table_detection_all_10_tables(
        self, sandbox_env: Tuple[Path, Path], table_to_drop: str
    ) -> None:
        """Verify that dropping any of the 10 schema tables causes verify_pipeline to exit 1."""
        db_path, reports_dir = sandbox_env
        con = sqlite3.connect(str(db_path))
        con.execute(f"DROP TABLE {table_to_drop}")
        con.commit()
        con.close()

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1

    def test_low_candidate_count_threshold(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Verify detection of candidate count below minimum threshold (10)."""
        db_path, reports_dir = sandbox_env
        con = sqlite3.connect(str(db_path))
        con.execute("PRAGMA foreign_keys = OFF")
        # Keep only 5 candidates
        con.execute("DELETE FROM candidates WHERE candidate_id NOT IN (SELECT candidate_id FROM candidates LIMIT 5)")
        con.commit()
        con.close()

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        db03 = next(c for c in checks if c.check_id == "DB-03")
        assert not db03.passed
        assert "5 candidates present" in db03.observed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1
        assert "DB-03" in proc.stdout

    def test_low_job_count_threshold(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Verify detection of job vacancies count below minimum threshold (4)."""
        db_path, reports_dir = sandbox_env
        con = sqlite3.connect(str(db_path))
        con.execute("PRAGMA foreign_keys = OFF")
        # Keep only 2 jobs
        con.execute("DELETE FROM job_descriptions WHERE job_id NOT IN (SELECT job_id FROM job_descriptions LIMIT 2)")
        con.commit()
        con.close()

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        db04 = next(c for c in checks if c.check_id == "DB-04")
        assert not db04.passed
        assert "2 job vacancies present" in db04.observed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1
        assert "DB-04" in proc.stdout

    def test_low_operational_metrics_count_threshold(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Verify detection of operational metrics count below minimum threshold (36)."""
        db_path, reports_dir = sandbox_env
        con = sqlite3.connect(str(db_path))
        # Keep only 20 metrics
        con.execute("DELETE FROM operational_metrics WHERE metric_id NOT IN (SELECT metric_id FROM operational_metrics LIMIT 20)")
        con.commit()
        con.close()

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        db05 = next(c for c in checks if c.check_id == "DB-05")
        assert not db05.passed
        assert "20 operational metric records present" in db05.observed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1
        assert "DB-05" in proc.stdout

    def test_low_matching_evaluations_count_threshold(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Verify detection of matching evaluations count below minimum threshold (40)."""
        db_path, reports_dir = sandbox_env
        con = sqlite3.connect(str(db_path))
        # Keep only 25 evaluations
        con.execute("DELETE FROM matching_evaluations WHERE evaluation_id NOT IN (SELECT evaluation_id FROM matching_evaluations LIMIT 25)")
        con.commit()
        con.close()

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        db06 = next(c for c in checks if c.check_id == "DB-06")
        assert not db06.passed
        assert "25 matching evaluations present" in db06.observed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1
        assert "DB-06" in proc.stdout

    def test_foreign_key_violation_detection(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Verify that foreign key check detects orphaned relational records."""
        db_path, reports_dir = sandbox_env
        con = sqlite3.connect(str(db_path))
        con.execute("PRAGMA foreign_keys = OFF")
        # Insert candidate_skill referencing completely fictitious skill_id
        con.execute(
            """
            INSERT INTO candidate_skills (
                candidate_id, skill_id, proficiency_level, years_experience, is_primary
            ) VALUES (
                'cand-001', 999999, 'expert', 5.0, 1
            )
            """
        )
        con.commit()
        con.close()

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        db07 = next(c for c in checks if c.check_id == "DB-07")
        assert not db07.passed
        assert "FK violations found" in db07.observed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1
        assert "DB-07" in proc.stdout

    @pytest.mark.parametrize(
        "column,bad_value",
        [
            ("overall_score", 100.5),
            ("overall_score", -1.0),
            ("skills_score", 150.0),
            ("skills_score", -0.01),
            ("experience_score", 105.0),
            ("experience_score", -5.0),
            ("semantic_similarity", 1.0001),
            ("semantic_similarity", -0.0001),
        ],
    )
    def test_out_of_bounds_score_and_similarity(
        self, sandbox_env: Tuple[Path, Path], column: str, bad_value: float
    ) -> None:
        """Verify that scores outside [0.0, 100.0] or similarity outside [0.0, 1.0] are rejected."""
        db_path, reports_dir = sandbox_env
        con = sqlite3.connect(str(db_path))
        con.execute(
            f"UPDATE matching_evaluations SET {column} = ? WHERE evaluation_id = (SELECT evaluation_id FROM matching_evaluations LIMIT 1)",
            (bad_value,),
        )
        con.commit()
        con.close()

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        db08 = next(c for c in checks if c.check_id == "DB-08")
        assert not db08.passed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1
        assert "DB-08" in proc.stdout


class TestAdversarialDeliverablesFailures:
    """Adversarial challenge tests targeting report document failure modes."""

    def test_missing_reports_directory(self, sandbox_env: Tuple[Path, Path], tmp_path: Path) -> None:
        """Verify verification fails when reports directory does not exist."""
        db_path, _ = sandbox_env
        missing_reports_dir = tmp_path / "non_existent_reports"

        checks, all_passed = run_pipeline_verification(db_path, missing_reports_dir)
        assert not all_passed
        rep01 = next(c for c in checks if c.check_id == "REP-01")
        assert not rep01.passed
        rep04 = next(c for c in checks if c.check_id == "REP-04")
        assert not rep04.passed

        proc = run_verify_script(db_path, missing_reports_dir)
        assert proc.returncode == 1

    def test_missing_excel_file(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Verify failure when talent_bi_report.xlsx is absent."""
        db_path, reports_dir = sandbox_env
        excel_file = reports_dir / "talent_bi_report.xlsx"
        if excel_file.exists():
            excel_file.unlink()

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        rep01 = next(c for c in checks if c.check_id == "REP-01")
        assert not rep01.passed
        assert "File not found" in rep01.observed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1
        assert "REP-01" in proc.stdout

    def test_corrupted_excel_file_garbage_bytes(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Verify failure when Excel file contains arbitrary corrupted binary bytes."""
        db_path, reports_dir = sandbox_env
        excel_file = reports_dir / "talent_bi_report.xlsx"
        excel_file.write_bytes(b"\x00\xFF\xAA\x55CORRUPTED_EXCEL_PAYLOAD\x00\x01\x02\x03" * 50)

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        rep01 = next(c for c in checks if c.check_id == "REP-01")
        assert not rep01.passed
        assert "Error reading workbook" in rep01.observed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1

    def test_missing_excel_sheet(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Verify failure when one of the 4 required sheets is missing from workbook."""
        db_path, reports_dir = sandbox_env
        excel_file = reports_dir / "talent_bi_report.xlsx"
        wb = openpyxl.load_workbook(str(excel_file))
        assert "Gap Analysis" in wb.sheetnames
        del wb["Gap Analysis"]
        wb.save(str(excel_file))
        wb.close()

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        rep02 = next(c for c in checks if c.check_id == "REP-02")
        assert not rep02.passed
        assert "Missing sheets: Gap Analysis" in rep02.observed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1
        assert "REP-02" in proc.stdout

    def test_empty_excel_sheet_content(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Verify failure when a sheet has no structured data rows (max_row < 2)."""
        db_path, reports_dir = sandbox_env
        excel_file = reports_dir / "talent_bi_report.xlsx"
        wb = openpyxl.load_workbook(str(excel_file))
        del wb["Candidates Ranking"]
        new_ws = wb.create_sheet("Candidates Ranking")
        new_ws.cell(row=1, column=1, value="Only Title")
        wb.save(str(excel_file))
        wb.close()

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        rep03 = next(c for c in checks if c.check_id == "REP-03")
        assert not rep03.passed
        assert "Empty sheets detected: Candidates Ranking" in rep03.observed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1
        assert "REP-03" in proc.stdout

    def test_adversarial_styled_empty_rows_blind_spot(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Empirically test whether verify_pipeline catches sheets with styled but valueless cells.

        When cell values are None but styles (fills, borders) are present, openpyxl
        reports max_row >= 2 even though zero data is present. This test verifies that
        such a scenario bypasses the simple max_row < 2 check.
        """
        db_path, reports_dir = sandbox_env
        excel_file = reports_dir / "talent_bi_report.xlsx"
        wb = openpyxl.load_workbook(str(excel_file))
        ws = wb["Candidates Ranking"]
        for row in ws.iter_rows():
            for cell in row:
                cell.value = None
        wb.save(str(excel_file))
        wb.close()

        # Due to openpyxl storing styled cells in XML, ws.max_row remains > 1
        wb_check = openpyxl.load_workbook(str(excel_file))
        assert wb_check["Candidates Ranking"].max_row > 1
        wb_check.close()

        # REP-03 check currently inspects only max_row and max_column
        checks, _ = run_pipeline_verification(db_path, reports_dir)
        rep03 = next(c for c in checks if c.check_id == "REP-03")
        # Documented challenge finding: REP-03 passes because max_row reflects XML dimensions
        assert rep03.passed


    def test_missing_pdf_file(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Verify failure when executive_evaluation_summary.pdf is absent."""
        db_path, reports_dir = sandbox_env
        pdf_file = reports_dir / "executive_evaluation_summary.pdf"
        if pdf_file.exists():
            pdf_file.unlink()

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        rep04 = next(c for c in checks if c.check_id == "REP-04")
        assert not rep04.passed
        assert "File not found" in rep04.observed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1
        assert "REP-04" in proc.stdout

    def test_truncated_small_pdf_file(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Verify failure when PDF size is below minimum 5,120 bytes threshold."""
        db_path, reports_dir = sandbox_env
        pdf_file = reports_dir / "executive_evaluation_summary.pdf"
        # Write small payload under 5KB
        pdf_file.write_bytes(b"%PDF-1.4\n%small dummy pdf\n%%EOF\n")

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        rep04 = next(c for c in checks if c.check_id == "REP-04")
        assert not rep04.passed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1
        assert "REP-04" in proc.stdout

    def test_corrupted_pdf_magic_header(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Verify failure when PDF does not start with magic signature %PDF-."""
        db_path, reports_dir = sandbox_env
        pdf_file = reports_dir / "executive_evaluation_summary.pdf"
        data = bytearray(pdf_file.read_bytes())
        # Replace magic header
        data[0:5] = b"%NOTP"
        pdf_file.write_bytes(data)

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        rep05 = next(c for c in checks if c.check_id == "REP-05")
        assert not rep05.passed
        assert "Header: %NOTP" in rep05.observed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1
        assert "REP-05" in proc.stdout

    def test_corrupted_pdf_stream_and_structure(self, sandbox_env: Tuple[Path, Path]) -> None:
        """Verify failure when PDF header is present but stream data is completely unparseable."""
        db_path, reports_dir = sandbox_env
        pdf_file = reports_dir / "executive_evaluation_summary.pdf"
        # 6KB payload starting with %PDF- but followed by gibberish
        corrupt_body = b"%PDF-1.4\n" + b"\x00\xFF\xFE\xFDGARBAGE_STREAM" * 300
        pdf_file.write_bytes(corrupt_body)

        checks, all_passed = run_pipeline_verification(db_path, reports_dir)
        assert not all_passed
        rep06 = next(c for c in checks if c.check_id == "REP-06")
        assert not rep06.passed
        assert "Error extracting text stream" in rep06.observed

        proc = run_verify_script(db_path, reports_dir)
        assert proc.returncode == 1
        assert "REP-06" in proc.stdout


class TestAdversarialBaselineAndPolicy:
    """Baseline integrity and strict project compliance tests."""

    def test_baseline_clean_verification_succeeds(self) -> None:
        """Confirm that untouched production database and deliverables pass 14/14 checks."""
        checks, all_passed = run_pipeline_verification(PROD_DB_PATH, PROD_REPORTS_DIR)
        assert all_passed
        assert len(checks) == 14
        assert all(c.passed for c in checks)

        proc = run_verify_script(PROD_DB_PATH, PROD_REPORTS_DIR)
        assert proc.returncode == 0
        assert "14/14 checks passed" in proc.stdout
        assert "Verdict: PASSED" in proc.stdout
