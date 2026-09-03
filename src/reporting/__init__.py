"""Business Intelligence metrics calculation, analysis, and document reporting package."""

from src.reporting.excel_generator import ExcelReportGenerator
from src.reporting.metrics import (
    BIMetricsCalculator,
    DepartmentSummaryDTO,
    KPISummaryDTO,
    RecruitmentROIDTO,
    ScoreDistributionDTO,
    ScoreQuartilesDTO,
    SourcingChannelMetricDTO,
    StageDurationDTO,
)
from src.reporting.pdf_generator import NumberedCanvas, PDFReportGenerator
from src.reporting.service import ReportingService, generate_all_reports

__all__ = [
    "BIMetricsCalculator",
    "DepartmentSummaryDTO",
    "KPISummaryDTO",
    "RecruitmentROIDTO",
    "ScoreDistributionDTO",
    "ScoreQuartilesDTO",
    "SourcingChannelMetricDTO",
    "StageDurationDTO",
    "ExcelReportGenerator",
    "NumberedCanvas",
    "PDFReportGenerator",
    "ReportingService",
    "generate_all_reports",
]
