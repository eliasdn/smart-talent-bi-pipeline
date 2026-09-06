"""Standalone automated verification script for data integrity and output deliverables."""

import argparse
from pathlib import Path
import sys

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rich import box
from rich.console import Console
from rich.table import Table

from src.cli.main import run_pipeline_verification

console = Console(highlight=False)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments for verification script."""
    parser = argparse.ArgumentParser(
        description="Verify talent analytics pipeline database integrity and reporting deliverables."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=REPO_ROOT / "data" / "output" / "talent_bi.db",
        help="Path to SQLite database file.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=REPO_ROOT / "data" / "output" / "reports",
        help="Path to directory containing generated reports.",
    )
    return parser.parse_args()


def main() -> int:
    """Execute pipeline verification checks and return exit code."""
    args = parse_arguments()
    db_path = args.db_path.resolve()
    reports_dir = args.reports_dir.resolve()

    console.print(
        "[bold cyan]============================================================[/bold cyan]\n"
        "[bold cyan]  TALENT BI PIPELINE - AUTOMATED END-TO-END VERIFICATION   [/bold cyan]\n"
        "[bold cyan]============================================================[/bold cyan]"
    )
    console.print(f"Target Database:   {db_path}")
    console.print(f"Reports Directory: {reports_dir}\n")

    checks, all_passed = run_pipeline_verification(db_path=db_path, reports_dir=reports_dir)

    table = Table(
        title="Verification Results Summary",
        box=box.ROUNDED,
        header_style="bold cyan",
    )
    table.add_column("ID", style="dim", justify="center")
    table.add_column("Category", style="bold")
    table.add_column("Check Description")
    table.add_column("Observed Measurement")
    table.add_column("Status", justify="center")

    for check in checks:
        status_styled = (
            "[bold green]PASS[/bold green]"
            if check.passed
            else "[bold red]FAIL[/bold red]"
        )
        table.add_row(
            check.check_id,
            check.category,
            check.description,
            check.observed,
            status_styled,
        )

    console.print(table)

    passed_count = sum(1 for c in checks if c.passed)
    total_count = len(checks)

    console.print(
        f"\nFinal Result: [bold]{passed_count}/{total_count}[/bold] checks passed. "
        f"Verdict: {'[bold green]PASSED[/bold green]' if all_passed else '[bold red]FAILED[/bold red]'}\n"
    )

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
