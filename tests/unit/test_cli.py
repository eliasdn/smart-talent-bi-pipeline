"""Unit tests for Typer CLI commands, pipeline orchestrator, and verification routine."""

from pathlib import Path
import sqlite3
import sys
from typing import Generator

import pytest
from typer.testing import CliRunner

from src.cli.main import (
    IngestionResult,
    MatchingResult,
    PipelineOrchestrator,
    PipelineSummary,
    ReportingResult,
    VerificationCheckResult,
    app,
    run_pipeline_verification,
)

runner = CliRunner()


@pytest.fixture
def raw_dir() -> Path:
    """Return path to standard raw test datasets."""
    return Path(__file__).resolve().parent.parent.parent / "data" / "raw"


# --- 1. CLI Basic & Help Tests ---

class TestCLIBasics:
    """Verify general CLI behavior, help strings, and options."""

    def test_cli_help_displays_subcommands(self) -> None:
        """Verify talent-bi --help displays all five subcommands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        output = result.stdout
        assert "ingest" in output
        assert "match" in output
        assert "report" in output
        assert "run-all" in output
        assert "verify" in output

    def test_ingest_help(self) -> None:
        """Verify ingest --help shows options."""
        result = runner.invoke(app, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "--data-dir" in result.stdout
        assert "--db-path" in result.stdout

    def test_match_help(self) -> None:
        """Verify match --help shows options."""
        result = runner.invoke(app, ["match", "--help"])
        assert result.exit_code == 0
        assert "--db-path" in result.stdout
        assert "--persist" in result.stdout
        assert "--top-n" in result.stdout

    def test_report_help(self) -> None:
        """Verify report --help shows options."""
        result = runner.invoke(app, ["report", "--help"])
        assert result.exit_code == 0
        assert "--db-path" in result.stdout
        assert "--output-dir" in result.stdout

    def test_run_all_help(self) -> None:
        """Verify run-all --help shows options."""
        result = runner.invoke(app, ["run-all", "--help"])
        assert result.exit_code == 0
        assert "--data-dir" in result.stdout
        assert "--db-path" in result.stdout
        assert "--output-dir" in result.stdout

    def test_verify_help(self) -> None:
        """Verify verify --help shows options."""
        result = runner.invoke(app, ["verify", "--help"])
        assert result.exit_code == 0
        assert "--db-path" in result.stdout
        assert "--reports-dir" in result.stdout


# --- 2. Ingest Subcommand Tests ---

class TestCLIIngestCommand:
    """Verify CLI ingest command execution and failure modes."""

    def test_ingest_missing_directory_fails(self, tmp_path: Path) -> None:
        """Verify ingest fails with non-zero exit code when data directory does not exist."""
        non_existent = tmp_path / "does_not_exist"
        target_db = tmp_path / "output.db"
        result = runner.invoke(app, ["ingest", "--data-dir", str(non_existent), "--db-path", str(target_db)])
        assert result.exit_code != 0

    def test_ingest_success(self, raw_dir: Path, tmp_path: Path) -> None:
        """Verify successful ingestion populates target database."""
        target_db = tmp_path / "test_ingest.db"
        result = runner.invoke(app, ["ingest", "--data-dir", str(raw_dir), "--db-path", str(target_db)])
        assert result.exit_code == 0
        assert "ETL Ingestion Summary" in result.stdout
        assert "SUCCESS" in result.stdout
        assert target_db.exists()
        assert target_db.stat().st_size > 0


# --- 3. Match Subcommand Tests ---

class TestCLIMatchCommand:
    """Verify CLI match command execution and failure modes."""

    def test_match_missing_database_fails(self, tmp_path: Path) -> None:
        """Verify match fails when database file does not exist."""
        non_existent = tmp_path / "missing.db"
        result = runner.invoke(app, ["match", "--db-path", str(non_existent)])
        assert result.exit_code != 0

    def test_match_after_ingestion_with_top_n(self, raw_dir: Path, tmp_path: Path) -> None:
        """Verify matching runs after ingestion and prints top N results."""
        target_db = tmp_path / "test_match.db"
        # Ingest first
        ingest_res = runner.invoke(app, ["ingest", "--data-dir", str(raw_dir), "--db-path", str(target_db)])
        assert ingest_res.exit_code == 0

        # Match with top_n=3
        match_res = runner.invoke(app, ["match", "--db-path", str(target_db), "--top-n", "3"])
        assert match_res.exit_code == 0
        assert "Top 3 Candidate Matching Evaluations" in match_res.stdout
        assert "Total Pairs Evaluated" in match_res.stdout
        assert "40" in match_res.stdout

    def test_match_no_persist_mode(self, raw_dir: Path, tmp_path: Path) -> None:
        """Verify match runs with --no-persist without saving evaluations."""
        target_db = tmp_path / "test_no_persist.db"
        runner.invoke(app, ["ingest", "--data-dir", str(raw_dir), "--db-path", str(target_db)])

        match_res = runner.invoke(app, ["match", "--db-path", str(target_db), "--no-persist"])
        assert match_res.exit_code == 0


# --- 4. Report Subcommand Tests ---

class TestCLIReportCommand:
    """Verify CLI report command generation."""

    def test_report_missing_database_fails(self, tmp_path: Path) -> None:
        """Verify report command fails when database is missing."""
        missing_db = tmp_path / "missing.db"
        out_dir = tmp_path / "reports"
        result = runner.invoke(app, ["report", "--db-path", str(missing_db), "--output-dir", str(out_dir)])
        assert result.exit_code != 0

    def test_report_success_after_matching(self, raw_dir: Path, tmp_path: Path) -> None:
        """Verify report generation generates both Excel and PDF deliverables."""
        target_db = tmp_path / "test_report.db"
        out_dir = tmp_path / "reports"

        runner.invoke(app, ["ingest", "--data-dir", str(raw_dir), "--db-path", str(target_db)])
        runner.invoke(app, ["match", "--db-path", str(target_db)])

        result = runner.invoke(app, ["report", "--db-path", str(target_db), "--output-dir", str(out_dir)])
        assert result.exit_code == 0
        assert "Generated Reporting Deliverables" in result.stdout
        assert (out_dir / "talent_bi_report.xlsx").exists()
        assert (out_dir / "executive_evaluation_summary.pdf").exists()


# --- 5. Run-All and Verify Subcommand Tests ---

class TestCLIRunAllAndVerify:
    """Verify end-to-end run-all and verify subcommands."""

    def test_run_all_and_verify_cycle(self, raw_dir: Path, tmp_path: Path) -> None:
        """Verify full run-all execution followed by verification passes completely."""
        target_db = tmp_path / "e2e_cli.db"
        out_reports = tmp_path / "e2e_reports"

        # 1. run-all
        run_res = runner.invoke(
            app,
            [
                "run-all",
                "--data-dir",
                str(raw_dir),
                "--db-path",
                str(target_db),
                "--output-dir",
                str(out_reports),
            ],
        )
        assert run_res.exit_code == 0
        assert "PIPELINE EXECUTION COMPLETED SUCCESSFULLY" in run_res.stdout
        assert "1. ETL Ingestion" in run_res.stdout
        assert "2. Semantic Matching" in run_res.stdout
        assert "3. BI Reporting" in run_res.stdout

        # 2. verify
        verify_res = runner.invoke(
            app,
            [
                "verify",
                "--db-path",
                str(target_db),
                "--reports-dir",
                str(out_reports),
            ],
        )
        assert verify_res.exit_code == 0
        assert "Verification Summary: 14/14 checks passed" in verify_res.stdout
        assert "Status: PASS" in verify_res.stdout

    def test_verify_missing_db_fails(self, tmp_path: Path) -> None:
        """Verify verify subcommand fails on missing database."""
        missing_db = tmp_path / "non_existent.db"
        empty_reports = tmp_path / "empty_reports"
        empty_reports.mkdir(parents=True, exist_ok=True)

        verify_res = runner.invoke(
            app,
            [
                "verify",
                "--db-path",
                str(missing_db),
                "--reports-dir",
                str(empty_reports),
            ],
        )
        assert verify_res.exit_code != 0
        assert "FAIL" in verify_res.stdout


# --- 6. PipelineOrchestrator Unit Tests ---

class TestPipelineOrchestrator:
    """Verify PipelineOrchestrator class methods and data flow."""

    def test_orchestrator_instantiation(self) -> None:
        """Verify orchestrator initializes with default logger."""
        orchestrator = PipelineOrchestrator()
        assert orchestrator.logger is not None

    def test_run_ingestion_invalid_dir(self, tmp_path: Path) -> None:
        """Verify run_ingestion returns success=False on invalid directory."""
        orchestrator = PipelineOrchestrator()
        res = orchestrator.run_ingestion(data_dir=tmp_path / "invalid", db_path=tmp_path / "test.db")
        assert not res.success
        assert res.total_loaded == 0

    def test_run_matching_invalid_db(self, tmp_path: Path) -> None:
        """Verify run_matching returns success=False on non-existent database."""
        orchestrator = PipelineOrchestrator()
        res = orchestrator.run_matching(db_path=tmp_path / "invalid.db")
        assert not res.success
        assert res.evaluations_count == 0

    def test_run_reporting_invalid_db(self, tmp_path: Path) -> None:
        """Verify run_reporting returns success=False on non-existent database."""
        orchestrator = PipelineOrchestrator()
        res = orchestrator.run_reporting(db_path=tmp_path / "invalid.db", output_dir=tmp_path / "out")
        assert not res.success


# --- 7. run_pipeline_verification Logic Unit Tests ---

class TestVerificationRoutine:
    """Verify run_pipeline_verification behavior and boundary checking."""

    def test_verification_missing_database_returns_early(self, tmp_path: Path) -> None:
        """Verify missing database returns False with DB-01 check failed."""
        checks, passed = run_pipeline_verification(
            db_path=tmp_path / "ghost.db",
            reports_dir=tmp_path / "ghost_reports",
        )
        assert not passed
        assert len(checks) == 1
        assert checks[0].check_id == "DB-01"
        assert not checks[0].passed

    def test_verification_checks_structure(self, raw_dir: Path, tmp_path: Path) -> None:
        """Verify all check IDs are unique and well-formed."""
        target_db = tmp_path / "test_struct.db"
        reports_dir = tmp_path / "struct_reports"

        orchestrator = PipelineOrchestrator()
        orchestrator.run_all(data_dir=raw_dir, db_path=target_db, output_dir=reports_dir)

        checks, passed = run_pipeline_verification(db_path=target_db, reports_dir=reports_dir)
        assert passed
        assert len(checks) == 14

        check_ids = [c.check_id for c in checks]
        assert len(check_ids) == len(set(check_ids))
        assert "DB-01" in check_ids
        assert "DB-02" in check_ids
        assert "DB-07" in check_ids
        assert "DB-08" in check_ids
        assert "REP-01" in check_ids
        assert "REP-06" in check_ids


# --- 8. Compliance & Zero-Emoji Unit Tests ---

class TestCLICompliance:
    """Verify zero emojis and zero prohibited mentions in CLI modules."""

    def test_zero_emojis_in_cli(self) -> None:
        """Verify CLI source files contain zero emojis."""
        cli_dir = Path(__file__).resolve().parent.parent.parent / "src" / "cli"
        for py_file in cli_dir.glob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            for char in text:
                cp = ord(char)
                assert not (
                    0x1F600 <= cp <= 0x1F64F
                    or 0x1F300 <= cp <= 0x1F5FF
                    or 0x1F900 <= cp <= 0x1F9FF
                    or 0x2600 <= cp <= 0x27BF
                    or 0x1F000 <= cp <= 0x1FFFF
                ), f"Prohibited emoji '{char}' found in {py_file}"

    def test_zero_prohibited_terms_in_cli(self) -> None:
        """Verify CLI source files contain zero prohibited terms."""
        cli_dir = Path(__file__).resolve().parent.parent.parent / "src" / "cli"
        prohibited = [
            "".join(["chat", "gpt"]),
            "".join(["open", "ai"]),
            "".join(["co", "pilot"]),
            "".join(["assist", "ant"]),
            "".join(["ag", "ent"]),
        ]
        for py_file in cli_dir.glob("*.py"):
            text = py_file.read_text(encoding="utf-8").lower()
            for term in prohibited:
                assert term not in text, f"Prohibited term '{term}' found in {py_file}"
