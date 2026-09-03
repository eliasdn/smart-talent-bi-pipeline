"""Executive PDF evaluation summary document generator using ReportLab SimpleDocTemplate.

Produces formal, publication-ready recruitment dossier reports:
- Custom NumberedCanvas with running headers, footers, and dynamic page counts
- Executive KPI summary grid and recruitment ROI metrics
- Candidate rankings overview table
- Detailed candidate evaluation cards with sub-scores, strengths, gaps, and French narrative synthesis
- Methodological and governance notes
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, inch, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.reporting.metrics import BIMetricsCalculator, KPISummaryDTO
from src.utils.logger import setup_logger

logger = setup_logger("smart_talent_bi.reporting.pdf_generator")

# Corporate Color Palette
COLOR_NAVY_PRIMARY = colors.HexColor("#1A365D")
COLOR_NAVY_HEADER = colors.HexColor("#1F4E79")
COLOR_SLATE = colors.HexColor("#4A5568")
COLOR_CHARCOAL = colors.HexColor("#2D3748")
COLOR_LIGHT_BG = colors.HexColor("#F7FAFC")
COLOR_SUB_BG = colors.HexColor("#EDF2F7")
COLOR_BORDER = colors.HexColor("#CBD5E0")
COLOR_GREEN = colors.HexColor("#276A3C")
COLOR_RED = colors.HexColor("#A61C1C")
COLOR_ICE_BLUE = colors.HexColor("#D9E1F2")


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas that computes total pages and prints running header/footer."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, total_pages: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))

        # Running Header
        self.drawString(36, 812, "SMART TALENT BI - SYNTHESE DECISIONNELLE D'EVALUATION")
        date_str = datetime.now().strftime("%d/%m/%Y")
        self.drawRightString(559, 812, f"Mise a jour : {date_str}")
        self.setStrokeColor(COLOR_BORDER)
        self.setLineWidth(0.5)
        self.line(36, 806, 559, 806)

        # Running Footer
        self.line(36, 42, 559, 42)
        self.drawString(36, 30, "DOCUMENT CONFIDENTIEL - DIRECTION DU RECRUTEMENT")
        self.drawRightString(559, 30, f"Page {self._pageNumber} sur {total_pages}")
        self.restoreState()


class PDFReportGenerator:
    """Generates corporate executive evaluation PDF dossiers from talent pipeline data."""

    def __init__(self, calculator: BIMetricsCalculator) -> None:
        """Initialize generator with BI metrics calculator instance.

        Args:
            calculator: BIMetricsCalculator attached to database session.
        """
        self.calculator = calculator
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self) -> None:
        """Configure typography styles for the PDF report."""
        self.style_main_title = ParagraphStyle(
            "MainTitle",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=COLOR_NAVY_PRIMARY,
        )
        self.style_subtitle = ParagraphStyle(
            "Subtitle",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=COLOR_SLATE,
        )
        self.style_section_title = ParagraphStyle(
            "SectionTitle",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=COLOR_NAVY_PRIMARY,
            keepWithNext=True,
        )
        self.style_table_header = ParagraphStyle(
            "TableHeader",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.white,
            alignment=1,
        )
        self.style_table_cell = ParagraphStyle(
            "TableCell",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=COLOR_CHARCOAL,
        )
        self.style_table_cell_center = ParagraphStyle(
            "TableCellCenter",
            parent=self.style_table_cell,
            alignment=1,
        )
        self.style_table_cell_bold = ParagraphStyle(
            "TableCellBold",
            parent=self.style_table_cell,
            fontName="Helvetica-Bold",
            alignment=1,
        )
        self.style_card_title = ParagraphStyle(
            "CardTitle",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            textColor=COLOR_SLATE,
            alignment=1,
        )
        self.style_card_val = ParagraphStyle(
            "CardValue",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=COLOR_NAVY_PRIMARY,
            alignment=1,
        )
        self.style_narrative_heading_green = ParagraphStyle(
            "NarrativeHeadingGreen",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=COLOR_GREEN,
        )
        self.style_narrative_heading_red = ParagraphStyle(
            "NarrativeHeadingRed",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=COLOR_RED,
        )
        self.style_narrative_heading_navy = ParagraphStyle(
            "NarrativeHeadingNavy",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=COLOR_NAVY_HEADER,
        )
        self.style_narrative_body = ParagraphStyle(
            "NarrativeBody",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=COLOR_CHARCOAL,
        )

    def generate(self, output_path: Union[str, Path]) -> Path:
        """Compile executive PDF report and save to target path.

        Args:
            output_path: Destination .pdf file path.

        Returns:
            Resolved Path of the generated PDF file.
        """
        target = Path(output_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(target),
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=54,
            bottomMargin=54,
        )

        kpi = self.calculator.compute_kpi_summary()
        rankings_df = self.calculator.get_rankings_dataframe()

        story: List[Any] = []

        # 1. Title Banner
        story.extend(self._build_title_banner(kpi))
        story.append(Spacer(1, 10))

        # 2. Executive KPI Grid
        story.extend(self._build_kpi_grid(kpi))
        story.append(Spacer(1, 12))

        # 3. Candidate Rankings Table
        story.extend(self._build_rankings_table(rankings_df))
        story.append(Spacer(1, 12))

        # 4. Detailed Candidate Evaluation Dossiers (New Page)
        story.append(PageBreak())
        story.extend(self._build_detailed_dossiers(rankings_df))

        # 5. Governance & Methodology Note
        story.append(Spacer(1, 10))
        story.extend(self._build_governance_note())

        doc.build(story, canvasmaker=NumberedCanvas)
        logger.info("Successfully generated PDF report at %s (%d bytes)", target, target.stat().st_size)
        return target

    # --- Section Builders ---

    def _build_title_banner(self, kpi: KPISummaryDTO) -> List[Any]:
        """Construct document title and metadata block."""
        elements: List[Any] = []
        elements.append(Paragraph("SYNTHESE DECISIONNELLE DES EVALUATIONS", self.style_main_title))
        elements.append(Spacer(1, 4))
        sub_text = (
            f"Analyse de performance du pipeline, scoring multidimensionnel et dossiers d'adequation des profils cles. "
            f"Perimetre : {kpi.total_candidates} profils analyses, {kpi.total_jobs} postes ouverts, "
            f"{kpi.high_fit_count} profils retenus a fort potentiel."
        )
        elements.append(Paragraph(sub_text, self.style_subtitle))
        elements.append(Spacer(1, 6))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_NAVY_PRIMARY, spaceAfter=4))
        return elements

    def _build_kpi_grid(self, kpi: KPISummaryDTO) -> List[Any]:
        """Construct the 2x4 KPI summary grid table."""
        elements: List[Any] = []
        elements.append(Paragraph("1. INDICATEURS CLES DE PERFORMANCE & ROI RECRUTEMENT", self.style_section_title))
        elements.append(Spacer(1, 6))

        # 2 rows x 4 columns of cards
        data = [
            [
                [Paragraph("PROFILS ANALYSES", self.style_card_title), Paragraph(str(kpi.total_candidates), self.style_card_val)],
                [Paragraph("POSTES OUVERTS", self.style_card_title), Paragraph(str(kpi.total_jobs), self.style_card_val)],
                [Paragraph("PAIRES EVALUEES", self.style_card_title), Paragraph(str(kpi.total_evaluations), self.style_card_val)],
                [Paragraph("SCORE MOYEN", self.style_card_title), Paragraph(f"{kpi.average_matching_score:.1f}%", self.style_card_val)],
            ],
            [
                [Paragraph("RETENUS (>=70%)", self.style_card_title), Paragraph(f"{kpi.high_fit_count} ({kpi.high_fit_rate:.1f}%)", self.style_card_val)],
                [Paragraph("CHARGE MANUELLE", self.style_card_title), Paragraph(f"{kpi.roi.total_manual_hours:.1f} h", self.style_card_val)],
                [Paragraph("HEURES GAGNEES", self.style_card_title), Paragraph(f"{kpi.roi.total_hours_saved:.1f} h", self.style_card_val)],
                [Paragraph("ECONOMIES ESTIMEES", self.style_card_title), Paragraph(f"${kpi.roi.total_cost_saved:,.2f}", self.style_card_val)],
            ],
        ]

        col_w = [130, 131, 131, 131]
        t = Table(data, colWidths=col_w)
        t.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_BG),
                ("BOX", (0, 0), (-1, -1), 0.75, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elements.append(t)
        return elements

    def _build_rankings_table(self, rankings_df: Any) -> List[Any]:
        """Construct candidate rankings summary table."""
        elements: List[Any] = []
        elements.append(Paragraph("2. CLASSEMENT GENERAL DES PROFILS EVALUES", self.style_section_title))
        elements.append(Spacer(1, 6))

        headers = [
            Paragraph("Rang", self.style_table_header),
            Paragraph("Candidat", self.style_table_header),
            Paragraph("Poste Cible", self.style_table_header),
            Paragraph("Score", self.style_table_header),
            Paragraph("Tech", self.style_table_header),
            Paragraph("Exp", self.style_table_header),
            Paragraph("Recommandation", self.style_table_header),
        ]

        table_data = [headers]
        top_rows = rankings_df.head(10) if not rankings_df.empty else rankings_df

        for _, row in top_rows.iterrows():
            rec_display = self._format_recommendation_short(str(row.get("Recommendation", "")))
            table_data.append([
                Paragraph(str(row.get("Rank", "")), self.style_table_cell_center),
                Paragraph(str(row.get("Candidate Name", "")), self.style_table_cell),
                Paragraph(str(row.get("Job Title", "")), self.style_table_cell),
                Paragraph(f"{float(row.get('Overall Score', 0.0)):.1f}%", self.style_table_cell_bold),
                Paragraph(f"{float(row.get('Technical Score', 0.0)):.1f}%", self.style_table_cell_center),
                Paragraph(f"{float(row.get('Experience Score', 0.0)):.1f}%", self.style_table_cell_center),
                Paragraph(rec_display, self.style_table_cell_center),
            ])

        col_w = [30, 115, 145, 60, 55, 55, 63]
        t = Table(table_data, colWidths=col_w, repeatRows=1)

        t_style = [
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_NAVY_HEADER),
            ("BOX", (0, 0), (-1, -1), 0.75, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]

        for r_idx in range(1, len(table_data)):
            if r_idx % 2 == 0:
                t_style.append(("BACKGROUND", (0, r_idx), (-1, r_idx), COLOR_LIGHT_BG))

        t.setStyle(TableStyle(t_style))
        elements.append(t)
        return elements

    def _build_detailed_dossiers(self, rankings_df: Any) -> List[Any]:
        """Construct detailed dossier cards for top shortlisted candidate profiles."""
        elements: List[Any] = []
        elements.append(
            Paragraph("3. DOSSIERS D'EVALUATION APPROFONDIE - PROFILS DE TETE", self.style_section_title)
        )
        elements.append(Spacer(1, 8))

        if rankings_df.empty:
            elements.append(Paragraph("Aucune evaluation enregistree.", self.style_narrative_body))
            return elements

        # Evaluate top 3 candidate evaluations
        top_candidates = rankings_df.head(3)

        for _, row in top_candidates.iterrows():
            cand_id = str(row.get("Candidate ID", ""))
            job_id = str(row.get("Job ID", ""))
            card = self._build_candidate_card(row, cand_id, job_id)
            elements.append(card)
            elements.append(Spacer(1, 10))

        return elements

    def _build_candidate_card(self, row: Any, cand_id: str, job_id: str) -> KeepTogether:
        """Construct a complete bounded evaluation dossier card for an individual candidate."""
        cand_name = str(row.get("Candidate Name", "Candidat"))
        job_title = str(row.get("Job Title", "Poste"))
        dept = str(row.get("Department", "General"))
        overall_score = float(row.get("Overall Score", 0.0))
        tier = str(row.get("Tier", "BON")).upper()

        tech_s = float(row.get("Technical Score", 0.0))
        exp_s = float(row.get("Experience Score", 0.0))
        edu_s = float(row.get("Education Score", 0.0))
        soft_s = float(row.get("Soft Skills Score", 0.0))
        sem_s = float(row.get("Semantic Similarity", 0.0)) * 100.0

        # Query database for textual synthesis
        from src.models.entities import MatchingEvaluation
        from sqlalchemy import select

        ev = self.calculator.session.scalars(
            select(MatchingEvaluation).where(
                (MatchingEvaluation.candidate_id == cand_id) & (MatchingEvaluation.job_id == job_id)
            )
        ).first()

        strengths_text = ev.strengths_summary if ev and ev.strengths_summary else "Solide alignement sur les competences cles."
        gaps_text = ev.gaps_summary if ev and ev.gaps_summary else "Aucun ecart bloquant identifie."
        synth_text = ev.executive_summary if ev and ev.executive_summary else "Profil qualifie pour poursuite du processus."

        card_elements: List[Any] = []

        # 1. Header Bar Table
        hdr_left = Paragraph(
            f"<b>{cand_name}</b> - {job_title} ({dept})",
            ParagraphStyle("CardHdrL", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white),
        )
        hdr_right = Paragraph(
            f"Score : <b>{overall_score:.1f}%</b> [{tier}]",
            ParagraphStyle("CardHdrR", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white, alignment=2),
        )
        hdr_table = Table([[hdr_left, hdr_right]], colWidths=[360, 163])
        hdr_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_NAVY_HEADER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        card_elements.append(hdr_table)

        # 2. Sub-scores Breakdown Grid
        sub_data = [
            [
                Paragraph("Technique", self.style_card_title),
                Paragraph("Experience", self.style_card_title),
                Paragraph("Formation", self.style_card_title),
                Paragraph("Soft Skills", self.style_card_title),
                Paragraph("Semantique", self.style_card_title),
            ],
            [
                Paragraph(f"{tech_s:.1f}%", self.style_card_val),
                Paragraph(f"{exp_s:.1f}%", self.style_card_val),
                Paragraph(f"{edu_s:.1f}%", self.style_card_val),
                Paragraph(f"{soft_s:.1f}%", self.style_card_val),
                Paragraph(f"{sem_s:.1f}%", self.style_card_val),
            ],
        ]
        sub_table = Table(sub_data, colWidths=[104, 105, 104, 105, 105])
        sub_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_SUB_BG),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ])
        )
        card_elements.append(sub_table)

        # 3. Narrative Sections Box
        narrative_data = [
            [Paragraph("Points Forts Confirmes :", self.style_narrative_heading_green)],
            [Paragraph(strengths_text, self.style_narrative_body)],
            [Paragraph("Ecarts Identifies & Axes de Developpement :", self.style_narrative_heading_red)],
            [Paragraph(gaps_text, self.style_narrative_body)],
            [Paragraph("Synthese & Recommandation Recrutement :", self.style_narrative_heading_navy)],
            [Paragraph(synth_text, self.style_narrative_body)],
        ]
        narrative_table = Table(narrative_data, colWidths=[523])
        narrative_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        card_elements.append(narrative_table)

        return KeepTogether(card_elements)

    def _build_governance_note(self) -> List[Any]:
        """Construct methodological governance explanation block."""
        elements: List[Any] = []
        elements.append(Paragraph("4. METHODOLOGIE & GOUVERNANCE DU SCORING", self.style_section_title))
        elements.append(Spacer(1, 4))
        note = (
            "Ce document presente les resultats issus de l'analyse multidimensionnelle standardisee : "
            "Ponderation globale : 45% Competences Techniques & Alignement Semantique (TF-IDF Cosine), "
            "25% Experience Professionnelle, 15% Niveau Academique & Domaine, 15% Competences Relationnelles. "
            "Les donnees sont traitees conformement aux regles de gouvernance RH et d'integrite relationnelle (3NF)."
        )
        elements.append(Paragraph(note, self.style_subtitle))
        return [KeepTogether(elements)]

    def _format_recommendation_short(self, rec: str) -> str:
        """Format recommendation into concise badge string."""
        mapping = {
            "strong_hire": "A recruter",
            "hire": "Recommande",
            "consider": "A evaluer",
            "reject": "Non retenu",
        }
        return mapping.get(rec.lower(), rec.replace("_", " ").title())
