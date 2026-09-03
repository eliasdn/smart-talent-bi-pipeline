"""Multi-tab Excel workbook reporting generator using OpenPyXL.

Generates executive-level spreadsheets formatted to corporate standards:
- Sheet 1: Executive Dashboard (KPI cards, score distributions, department performance)
- Sheet 2: Candidates Ranking (Ranked evaluations, sub-scores, tiers, recommendations)
- Sheet 3: Gap Analysis (Matched competencies, missing skills, experience delta, qualitative strengths)
- Sheet 4: Operational Metrics (Stage velocity, applicant volume, sourcing channel conversion)
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from src.reporting.metrics import (
    BIMetricsCalculator,
    KPISummaryDTO,
)
from src.utils.logger import setup_logger

logger = setup_logger("smart_talent_bi.reporting.excel_generator")

# Corporate Color Palette
NAVY_HEADER_FILL = "1F4E79"
WHITE_TEXT = "FFFFFF"
ICE_BLUE_CARD_FILL = "D9E1F2"
CARD_BORDER_COLOR = "8EA9DB"
ZEBRA_LIGHT_FILL = "F2F4F8"
GRID_BORDER_COLOR = "D9D9D9"
SECTION_TITLE_COLOR = "1F4E79"

# Tier Color Fills
TIER_EXCELLENT_FILL = "E2EFDA"
TIER_EXCELLENT_TEXT = "276A3C"
TIER_BON_FILL = "D9E1F2"
TIER_BON_TEXT = "1F4E79"
TIER_PARTIEL_FILL = "FFF2CC"
TIER_PARTIEL_TEXT = "8A5300"
TIER_INSUFFISANT_FILL = "FCE4D6"
TIER_INSUFFISANT_TEXT = "A61C1C"


class ExcelReportGenerator:
    """Produces multi-tab corporate executive Excel workbooks from talent pipeline metrics."""

    def __init__(self, calculator: BIMetricsCalculator) -> None:
        """Initialize generator with BI metrics calculator instance.

        Args:
            calculator: BIMetricsCalculator attached to database session.
        """
        self.calculator = calculator

    def generate(self, output_path: Union[str, Path]) -> Path:
        """Generate complete 4-tab workbook and write to target path.

        Args:
            output_path: Destination .xlsx file path.

        Returns:
            Resolved Path of the written Excel workbook.
        """
        target = Path(output_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        wb = Workbook()
        # Remove default sheet
        wb.remove(wb.active)

        kpi = self.calculator.compute_kpi_summary()
        rankings_df = self.calculator.get_rankings_dataframe()
        gap_df = self.calculator.get_gap_analysis_dataframe()
        op_df = self.calculator.get_operational_metrics_dataframe()

        # Build 4 Sheets
        self._build_dashboard_sheet(wb, kpi)
        self._build_rankings_sheet(wb, rankings_df)
        self._build_gap_analysis_sheet(wb, gap_df)
        self._build_operational_metrics_sheet(wb, op_df, kpi)

        wb.save(target)
        logger.info("Successfully generated Excel report at %s (%d bytes)", target, target.stat().st_size)
        return target

    # --- Sheet 1: Executive Dashboard ---

    def _build_dashboard_sheet(self, wb: Workbook, kpi: KPISummaryDTO) -> None:
        """Construct the Executive Dashboard worksheet."""
        ws = wb.create_sheet(title="Executive Dashboard")
        ws.views.sheetView[0].showGridLines = True

        thin_border = self._thin_border()
        header_fill = PatternFill(start_color=NAVY_HEADER_FILL, end_color=NAVY_HEADER_FILL, fill_type="solid")
        title_font = Font(name="Calibri", size=15, bold=True, color=WHITE_TEXT)

        # Title Block
        ws.merge_cells("A1:H1")
        cell_title = ws["A1"]
        cell_title.value = "SMART TALENT BI - TABLEAU DE BORD DECISIONNEL RECRUTEMENT"
        cell_title.fill = header_fill
        cell_title.font = title_font
        cell_title.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 36

        ws.merge_cells("A2:H2")
        cell_sub = ws["A2"]
        cell_sub.value = (
            f"Synthese de performance, ROI et alignement des profils - "
            f"Mise a jour le {datetime.now().strftime('%d/%m/%Y')} - Perimetre : {kpi.total_candidates} profils"
        )
        cell_sub.font = Font(name="Calibri", size=10, italic=True, color="595959")
        cell_sub.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 20

        # KPI Summary Cards (2 rows of 4 cards)
        # Card definitions: (title, value, (start_col, end_col, start_row, end_row))
        cards_row1 = [
            ("PROFILS ANALYSES", f"{kpi.total_candidates}", "A", "B", 4, 5),
            ("POSTES OUVERTS", f"{kpi.total_jobs}", "C", "D", 4, 5),
            ("EVALUATIONS REALISEES", f"{kpi.total_evaluations}", "E", "F", 4, 5),
            ("SCORE MOYEN GLOBAL", f"{kpi.average_matching_score:.1f}%", "G", "H", 4, 5),
        ]
        cards_row2 = [
            ("PROFILS A FORT FIT (>=70%)", f"{kpi.high_fit_count} ({kpi.high_fit_rate:.1f}%)", "A", "B", 7, 8),
            ("CHARGE MANUELLE INITIALE", f"{kpi.roi.total_manual_hours:.1f} h", "C", "D", 7, 8),
            ("HEURES RECRUTEUR GAGNEES", f"{kpi.roi.total_hours_saved:.1f} h ({kpi.roi.time_savings_percentage:.1f}%)", "E", "F", 7, 8),
            ("ECONOMIES FINANCIERES", f"${kpi.roi.total_cost_saved:,.2f}", "G", "H", 7, 8),
        ]

        for card in cards_row1 + cards_row2:
            self._render_kpi_card(ws, card[0], card[1], card[2], card[3], card[4], card[5])

        ws.row_dimensions[4].height = 18
        ws.row_dimensions[5].height = 28
        ws.row_dimensions[7].height = 18
        ws.row_dimensions[8].height = 28

        # Section: Score Distribution Breakdown
        ws["A10"].value = "Distribution des Scores par Segment d'Adequation"
        ws["A10"].font = Font(name="Calibri", size=12, bold=True, color=SECTION_TITLE_COLOR)

        headers_dist = ["Segment d'Adequation", "Intervalle de Score", "Effectif Candidats", "Part de la Cohorte (%)"]
        for col_idx, h in enumerate(headers_dist, start=1):
            cell = ws.cell(row=11, column=col_idx, value=h)
            self._apply_header_style(cell)
        ws.row_dimensions[11].height = 24

        curr_row = 12
        for dist in kpi.score_distribution:
            is_alt = (curr_row % 2 == 1)
            row_vals = [dist.tier_name, dist.score_range, dist.count, dist.percentage / 100.0]
            for col_idx, val in enumerate(row_vals, start=1):
                cell = ws.cell(row=curr_row, column=col_idx, value=val)
                self._apply_data_style(cell, is_alt=is_alt, is_percent=(col_idx == 4), align_center=(col_idx in (2, 3)))
            ws.row_dimensions[curr_row].height = 20
            curr_row += 1

        curr_row += 1

        # Section: Department Performance Summary
        ws.cell(row=curr_row, column=1, value="Synthese Recrutement par Departement").font = Font(
            name="Calibri", size=12, bold=True, color=SECTION_TITLE_COLOR
        )
        curr_row += 1

        dept_headers = ["Departement", "Postes Vacants", "Candidats Evalues", "Score Moyen", "Meilleur Score", "Candidat de Tete"]
        for col_idx, h in enumerate(dept_headers, start=1):
            cell = ws.cell(row=curr_row, column=col_idx, value=h)
            self._apply_header_style(cell)
        ws.row_dimensions[curr_row].height = 24
        curr_row += 1

        for dept in kpi.department_summaries:
            is_alt = (curr_row % 2 == 1)
            row_vals = [
                dept.department,
                dept.vacancies_count,
                dept.candidates_evaluated,
                dept.average_score / 100.0,
                dept.highest_score / 100.0,
                dept.top_candidate_name,
            ]
            for col_idx, val in enumerate(row_vals, start=1):
                cell = ws.cell(row=curr_row, column=col_idx, value=val)
                self._apply_data_style(cell, is_alt=is_alt, is_percent=(col_idx in (4, 5)), align_center=(col_idx in (2, 3)))
            ws.row_dimensions[curr_row].height = 20
            curr_row += 1

        self._auto_fit_columns(ws, max_width=35)

    def _render_kpi_card(
        self,
        ws: Any,
        title: str,
        value: str,
        col_start: str,
        col_end: str,
        row_start: int,
        row_end: int,
    ) -> None:
        """Format a bounded rectangular KPI summary card."""
        card_fill = PatternFill(start_color=ICE_BLUE_CARD_FILL, end_color=ICE_BLUE_CARD_FILL, fill_type="solid")
        card_border = Border(
            left=Side(style="thin", color=CARD_BORDER_COLOR),
            right=Side(style="thin", color=CARD_BORDER_COLOR),
            top=Side(style="thin", color=CARD_BORDER_COLOR),
            bottom=Side(style="thin", color=CARD_BORDER_COLOR),
        )

        ws.merge_cells(f"{col_start}{row_start}:{col_end}{row_start}")
        top_cell = ws[f"{col_start}{row_start}"]
        top_cell.value = title
        top_cell.font = Font(name="Calibri", size=9, bold=True, color=NAVY_HEADER_FILL)
        top_cell.alignment = Alignment(horizontal="center", vertical="center")
        top_cell.fill = card_fill

        ws.merge_cells(f"{col_start}{row_end}:{col_end}{row_end}")
        bot_cell = ws[f"{col_start}{row_end}"]
        bot_cell.value = value
        bot_cell.font = Font(name="Calibri", size=14, bold=True, color=NAVY_HEADER_FILL)
        bot_cell.alignment = Alignment(horizontal="center", vertical="center")
        bot_cell.fill = card_fill

        # Set borders on perimeter cells
        for c in (col_start, col_end):
            for r in (row_start, row_end):
                ws[f"{c}{r}"].border = card_border

    # --- Sheet 2: Candidates Ranking ---

    def _build_rankings_sheet(self, wb: Workbook, rankings_df: Any) -> None:
        """Construct the Candidates Ranking worksheet."""
        ws = wb.create_sheet(title="Candidates Ranking")
        ws.views.sheetView[0].showGridLines = True

        # Header Title
        ws["A1"].value = "Classement General des Candidatures par Adequation au Poste"
        ws["A1"].font = Font(name="Calibri", size=13, bold=True, color=SECTION_TITLE_COLOR)

        headers = [
            "Rang", "Candidat", "Poste Cible", "Departement", "Score Global",
            "Score Technique", "Score Experience", "Score Formation", "Score Soft Skills",
            "Segment", "Recommandation",
        ]
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=3, column=col_idx, value=h)
            self._apply_header_style(cell)
        ws.row_dimensions[3].height = 26

        curr_row = 4
        for _, row in rankings_df.iterrows():
            is_alt = (curr_row % 2 == 1)
            tier_str = str(row.get("Tier", "")).upper()
            rec_str = str(row.get("Recommendation", ""))

            vals = [
                int(row.get("Rank", curr_row - 3)),
                str(row.get("Candidate Name", "")),
                str(row.get("Job Title", "")),
                str(row.get("Department", "")),
                float(row.get("Overall Score", 0.0)) / 100.0,
                float(row.get("Technical Score", 0.0)) / 100.0,
                float(row.get("Experience Score", 0.0)) / 100.0,
                float(row.get("Education Score", 0.0)) / 100.0,
                float(row.get("Soft Skills Score", 0.0)) / 100.0,
                tier_str,
                self._format_recommendation(rec_str),
            ]

            for col_idx, val in enumerate(vals, start=1):
                cell = ws.cell(row=curr_row, column=col_idx, value=val)
                is_pct = col_idx in (5, 6, 7, 8, 9)
                is_ctr = col_idx in (1, 10, 11)
                self._apply_data_style(cell, is_alt=is_alt, is_percent=is_pct, align_center=is_ctr)

                # Tier badge styling
                if col_idx == 10:
                    self._apply_tier_badge(cell, tier_str)

            ws.row_dimensions[curr_row].height = 20
            curr_row += 1

        self._auto_fit_columns(ws)

    # --- Sheet 3: Gap Analysis ---

    def _build_gap_analysis_sheet(self, wb: Workbook, gap_df: Any) -> None:
        """Construct the Gap Analysis worksheet."""
        ws = wb.create_sheet(title="Gap Analysis")
        ws.views.sheetView[0].showGridLines = True

        ws["A1"].value = "Analyse Detaillee des Ecarts de Competences et Points Forts"
        ws["A1"].font = Font(name="Calibri", size=13, bold=True, color=SECTION_TITLE_COLOR)

        headers = [
            "Candidat", "Poste Cible", "Competences Validees", "Competences Manquantes",
            "Exp. Candidat (ans)", "Exp. Requise (ans)", "Delta Exp. (ans)",
            "Points Forts", "Ecarts Cles", "Recommandation",
        ]
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=3, column=col_idx, value=h)
            self._apply_header_style(cell)
        ws.row_dimensions[3].height = 26

        curr_row = 4
        for _, row in gap_df.iterrows():
            is_alt = (curr_row % 2 == 1)
            vals = [
                str(row.get("Candidate Name", "")),
                str(row.get("Job Title", "")),
                str(row.get("Matched Skills", "")),
                str(row.get("Missing Required Skills", "")),
                float(row.get("Candidate Experience Years", 0.0)),
                float(row.get("Job Required Experience Years", 0.0)),
                float(row.get("Experience Delta Years", 0.0)),
                str(row.get("Key Strengths", "")),
                str(row.get("Key Gaps", "")),
                self._format_recommendation(str(row.get("Recommendation", ""))),
            ]

            for col_idx, val in enumerate(vals, start=1):
                cell = ws.cell(row=curr_row, column=col_idx, value=val)
                is_ctr = col_idx in (5, 6, 7, 10)
                self._apply_data_style(cell, is_alt=is_alt, align_center=is_ctr)
                if col_idx in (3, 4, 8, 9):
                    cell.alignment = Alignment(wrap_text=True, vertical="center")

            ws.row_dimensions[curr_row].height = 24
            curr_row += 1

        self._auto_fit_columns(ws, max_width=45)

    # --- Sheet 4: Operational Metrics ---

    def _build_operational_metrics_sheet(self, wb: Workbook, op_df: Any, kpi: KPISummaryDTO) -> None:
        """Construct the Operational Metrics worksheet."""
        ws = wb.create_sheet(title="Operational Metrics")
        ws.views.sheetView[0].showGridLines = True

        ws["A1"].value = "Indicateurs de Performance Operationnelle et Suivi du Funnel"
        ws["A1"].font = Font(name="Calibri", size=13, bold=True, color=SECTION_TITLE_COLOR)

        headers = [
            "ID Metrique", "Candidat", "Poste", "Canal de Sourcing",
            "Date Candidature", "Screening", "Entretien Tech", "Offre",
            "Statut", "Temps Screening (h)", "Screening Auto (s)", "Cout (EUR)", "Delai Embauche (Jours)",
        ]
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=3, column=col_idx, value=h)
            self._apply_header_style(cell)
        ws.row_dimensions[3].height = 26

        curr_row = 4
        for _, row in op_df.iterrows():
            is_alt = (curr_row % 2 == 1)
            vals = [
                str(row.get("Metric ID", "")),
                str(row.get("Candidate Name", "")),
                str(row.get("Job Title", "")),
                str(row.get("Sourcing Channel", "")),
                str(row.get("Application Date", "")),
                str(row.get("Screening Date", "")),
                str(row.get("Technical Interview Date", "")),
                str(row.get("Offer Date", "")),
                str(row.get("Hiring Decision", "")),
                float(row.get("Time to Screen (Hours)", 0.0)),
                float(row.get("Automated Screening (Sec)", 0.0)),
                float(row.get("Cost (EUR)", 0.0)),
                row.get("Total Days to Offer"),
            ]

            for col_idx, val in enumerate(vals, start=1):
                cell = ws.cell(row=curr_row, column=col_idx, value=val if val is not None else "")
                is_ctr = col_idx in (1, 5, 6, 7, 8, 9, 13)
                is_curr = (col_idx == 12)
                self._apply_data_style(cell, is_alt=is_alt, is_currency=is_curr, align_center=is_ctr)

            ws.row_dimensions[curr_row].height = 20
            curr_row += 1

        curr_row += 2

        # Sourcing Channel Performance Table
        ws.cell(row=curr_row, column=1, value="Performance par Canal de Sourcing").font = Font(
            name="Calibri", size=12, bold=True, color=SECTION_TITLE_COLOR
        )
        curr_row += 1

        ch_headers = [
            "Canal de Sourcing", "Volume Candidatures", "Recrutements",
            "Taux de Conversion (%)", "Cout Moyen par Candidat (EUR)",
        ]
        for col_idx, h in enumerate(ch_headers, start=1):
            cell = ws.cell(row=curr_row, column=col_idx, value=h)
            self._apply_header_style(cell)
        ws.row_dimensions[curr_row].height = 24
        curr_row += 1

        for ch in kpi.channel_metrics:
            is_alt = (curr_row % 2 == 1)
            row_vals = [
                ch.channel,
                ch.applicant_count,
                ch.hired_count,
                ch.conversion_rate_percentage / 100.0,
                ch.average_cost_eur,
            ]
            for col_idx, val in enumerate(row_vals, start=1):
                cell = ws.cell(row=curr_row, column=col_idx, value=val)
                self._apply_data_style(
                    cell,
                    is_alt=is_alt,
                    is_percent=(col_idx == 4),
                    is_currency=(col_idx == 5),
                    align_center=(col_idx in (2, 3)),
                )
            ws.row_dimensions[curr_row].height = 20
            curr_row += 1

        curr_row += 2

        # Funnel Stage Velocity Table
        ws.cell(row=curr_row, column=1, value="Delais Moyens par Etape de Recrutement").font = Font(
            name="Calibri", size=12, bold=True, color=SECTION_TITLE_COLOR
        )
        curr_row += 1

        stg_headers = ["Etape du Funnel", "Duree Moyenne (Jours)", "Candidats Traites"]
        for col_idx, h in enumerate(stg_headers, start=1):
            cell = ws.cell(row=curr_row, column=col_idx, value=h)
            self._apply_header_style(cell)
        ws.row_dimensions[curr_row].height = 24
        curr_row += 1

        for stg in kpi.stage_durations:
            is_alt = (curr_row % 2 == 1)
            row_vals = [stg.stage_name, stg.average_days, stg.completed_count]
            for col_idx, val in enumerate(row_vals, start=1):
                cell = ws.cell(row=curr_row, column=col_idx, value=val)
                self._apply_data_style(cell, is_alt=is_alt, align_center=(col_idx in (2, 3)))
            ws.row_dimensions[curr_row].height = 20
            curr_row += 1

        self._auto_fit_columns(ws)

    # --- Styling Helpers ---

    def _thin_border(self) -> Border:
        """Return standardized thin gray cell border."""
        side = Side(style="thin", color=GRID_BORDER_COLOR)
        return Border(left=side, right=side, top=side, bottom=side)

    def _apply_header_style(self, cell: Any) -> None:
        """Apply corporate navy header styling to table header cell."""
        cell.fill = PatternFill(start_color=NAVY_HEADER_FILL, end_color=NAVY_HEADER_FILL, fill_type="solid")
        cell.font = Font(name="Calibri", size=10, bold=True, color=WHITE_TEXT)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = self._thin_border()

    def _apply_data_style(
        self,
        cell: Any,
        is_alt: bool = False,
        is_percent: bool = False,
        is_currency: bool = False,
        align_center: bool = False,
    ) -> None:
        """Apply corporate data cell styling with alternating fill and formatting."""
        if is_alt:
            cell.fill = PatternFill(start_color=ZEBRA_LIGHT_FILL, end_color=ZEBRA_LIGHT_FILL, fill_type="solid")
        cell.font = Font(name="Calibri", size=10)
        cell.border = self._thin_border()

        if is_percent:
            cell.number_format = "0.0%"
            cell.alignment = Alignment(horizontal="right", vertical="center")
        elif is_currency:
            cell.number_format = "$#,##0.00"
            cell.alignment = Alignment(horizontal="right", vertical="center")
        elif align_center:
            cell.alignment = Alignment(horizontal="center", vertical="center")
        else:
            cell.alignment = Alignment(horizontal="left", vertical="center")

    def _apply_tier_badge(self, cell: Any, tier_str: str) -> None:
        """Apply color-coded highlight fill and font to tier cell."""
        tier = tier_str.upper()
        if tier == "EXCELLENT":
            cell.fill = PatternFill(start_color=TIER_EXCELLENT_FILL, end_color=TIER_EXCELLENT_FILL, fill_type="solid")
            cell.font = Font(name="Calibri", size=10, bold=True, color=TIER_EXCELLENT_TEXT)
        elif tier == "BON":
            cell.fill = PatternFill(start_color=TIER_BON_FILL, end_color=TIER_BON_FILL, fill_type="solid")
            cell.font = Font(name="Calibri", size=10, bold=True, color=TIER_BON_TEXT)
        elif tier == "PARTIEL":
            cell.fill = PatternFill(start_color=TIER_PARTIEL_FILL, end_color=TIER_PARTIEL_FILL, fill_type="solid")
            cell.font = Font(name="Calibri", size=10, bold=True, color=TIER_PARTIEL_TEXT)
        elif tier == "INSUFFISANT":
            cell.fill = PatternFill(start_color=TIER_INSUFFISANT_FILL, end_color=TIER_INSUFFISANT_FILL, fill_type="solid")
            cell.font = Font(name="Calibri", size=10, bold=False, color=TIER_INSUFFISANT_TEXT)

    def _format_recommendation(self, rec: str) -> str:
        """Convert recommendation enum string to formal display label."""
        labels = {
            "strong_hire": "Recruter en priorite",
            "hire": "Profil recommande",
            "consider": "A evaluer en entretien",
            "reject": "Non retenu",
        }
        return labels.get(rec.lower(), rec.replace("_", " ").title())

    def _auto_fit_columns(self, ws: Any, min_width: int = 12, max_width: int = 50) -> None:
        """Adjust column widths dynamically based on cell content length."""
        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = 0
            for cell in col:
                val = str(cell.value or "")
                lines = val.split("\n")
                line_len = max(len(l) for l in lines) if lines else 0
                if line_len > max_len:
                    max_len = line_len
            ws.column_dimensions[col_letter].width = max(min_width, min(max_width, max_len + 3))
