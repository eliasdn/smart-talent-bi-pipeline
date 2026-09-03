"""Reporting service coordinating Excel and PDF document generation from database metrics."""

from pathlib import Path
from typing import Dict, Optional, Union

from sqlalchemy.orm import Session

from src.models.entities import create_db_engine, get_session_factory
from src.reporting.excel_generator import ExcelReportGenerator
from src.reporting.metrics import BIMetricsCalculator
from src.reporting.pdf_generator import PDFReportGenerator
from src.utils.logger import setup_logger

logger = setup_logger("smart_talent_bi.reporting.service")


class ReportingService:
    """Coordinates calculation of BI metrics and compilation of all reporting artifacts."""

    def __init__(
        self,
        calculator: Optional[BIMetricsCalculator] = None,
        session: Optional[Session] = None,
    ) -> None:
        """Initialize reporting service with either a calculator or database session.

        Args:
            calculator: Optional pre-configured BIMetricsCalculator instance.
            session: Optional active SQLAlchemy session.
        """
        if calculator is not None:
            self.calculator = calculator
        elif session is not None:
            self.calculator = BIMetricsCalculator(session)
        else:
            raise ValueError("Either calculator or session must be provided to ReportingService.")

        self.excel_generator = ExcelReportGenerator(self.calculator)
        self.pdf_generator = PDFReportGenerator(self.calculator)

    @classmethod
    def from_db_path(cls, db_path: Union[str, Path]) -> "ReportingService":
        """Instantiate reporting service directly from SQLite database path.

        Args:
            db_path: File path to SQLite database.

        Returns:
            Configured ReportingService instance.
        """
        calc = BIMetricsCalculator.from_db_path(db_path)
        return cls(calculator=calc)

    def generate_excel_report(self, target_path: Union[str, Path]) -> Path:
        """Generate executive multi-tab Excel report workbook.

        Args:
            target_path: Destination path for .xlsx file.

        Returns:
            Resolved Path of generated file.
        """
        return self.excel_generator.generate(target_path)

    def generate_pdf_report(self, target_path: Union[str, Path]) -> Path:
        """Generate executive evaluation PDF summary report.

        Args:
            target_path: Destination path for .pdf file.

        Returns:
            Resolved Path of generated file.
        """
        return self.pdf_generator.generate(target_path)

    def generate_all(
        self,
        output_dir: Union[str, Path],
        excel_filename: str = "talent_bi_report.xlsx",
        pdf_filename: str = "executive_evaluation_summary.pdf",
    ) -> Dict[str, Path]:
        """Generate both Excel workbook and PDF dossier in target directory.

        Args:
            output_dir: Target output directory.
            excel_filename: Name of the generated Excel workbook file.
            pdf_filename: Name of the generated PDF dossier file.

        Returns:
            Dictionary containing 'excel' and 'pdf' file paths.
        """
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        excel_path = out_dir / excel_filename
        pdf_path = out_dir / pdf_filename

        logger.info("Generating full reporting suite in %s", out_dir)
        written_excel = self.generate_excel_report(excel_path)
        written_pdf = self.generate_pdf_report(pdf_path)

        return {
            "excel": written_excel,
            "pdf": written_pdf,
        }


def generate_all_reports(
    db_path: Union[str, Path],
    output_dir: Union[str, Path],
    excel_filename: str = "talent_bi_report.xlsx",
    pdf_filename: str = "executive_evaluation_summary.pdf",
) -> Dict[str, Path]:
    """High-level functional coordinator generating all document deliverables from database.

    Args:
        db_path: Path to relational SQLite database.
        output_dir: Directory where report artifacts will be saved.
        excel_filename: Custom filename for Excel report (default: talent_bi_report.xlsx).
        pdf_filename: Custom filename for PDF report (default: executive_evaluation_summary.pdf).

    Returns:
        Dictionary mapping deliverable format keys ('excel', 'pdf') to resolved Path objects.
    """
    service = ReportingService.from_db_path(db_path)
    return service.generate_all(
        output_dir=output_dir,
        excel_filename=excel_filename,
        pdf_filename=pdf_filename,
    )
