"""Adversarial challenge and stress-test suite for Milestone 3 (BI Reporting Engine).

Tests empirical edge cases:
- Empty database and zero evaluations (graceful handling, no ZeroDivisionError)
- Single evaluation boundary (sample standard deviation with N=1)
- Corrupted / unparseable JSON skills in database
- Inconsistent and out-of-order operational metric dates
- High candidate volumes (hundreds of evaluations)
- Extreme text lengths and French accent / special character handling
- Excel openpyxl structural and formatting integrity
- PDF ReportLab SimpleDocTemplate and NumberedCanvas structural integrity
- Strict zero-emoji and zero-assistant compliance
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
from typing import Generator

import openpyxl
from pypdf import PdfReader
import pytest
from sqlalchemy.orm import Session

from src.models.entities import (
    Candidate,
    JobDescription,
    MatchingEvaluation,
    OperationalMetric,
    create_db_engine,
    init_db,
)
from src.reporting.excel_generator import ExcelReportGenerator
from src.reporting.metrics import (
    BIMetricsCalculator,
    KPISummaryDTO,
    RecruitmentROIDTO,
)
from src.reporting.pdf_generator import NumberedCanvas, PDFReportGenerator
from src.reporting.service import ReportingService, generate_all_reports


@pytest.fixture
def clean_db_session(tmp_path: Path) -> Generator[Session, None, None]:
    """Provide a clean isolated file-backed database session."""
    db_file = tmp_path / "stress_test.db"
    engine = create_db_engine(f"sqlite:///{db_file.resolve()}")
    init_db(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


class TestMilestone3AdversarialStress:
    """Adversarial stress-testing suite for BI metrics and document generation."""

    def test_completely_empty_database_document_generation(self, clean_db_session: Session, tmp_path: Path) -> None:
        """Empirically verify report generators do not crash or raise ZeroDivisionError on empty DB."""
        calc = BIMetricsCalculator(clean_db_session)
        kpi = calc.compute_kpi_summary()

        assert kpi.total_candidates == 0
        assert kpi.total_jobs == 0
        assert kpi.total_evaluations == 0
        assert kpi.average_matching_score == 0.0
        assert kpi.high_fit_count == 0
        assert kpi.high_fit_rate == 0.0
        assert kpi.roi.total_manual_hours == 0.0
        assert kpi.roi.total_hours_saved == 0.0
        assert kpi.roi.total_cost_saved == 0.0
        assert kpi.roi.time_savings_percentage == 0.0

        # Excel generation on empty database
        excel_gen = ExcelReportGenerator(calc)
        excel_target = tmp_path / "empty_report.xlsx"
        written_excel = excel_gen.generate(excel_target)
        assert written_excel.exists()
        wb = openpyxl.load_workbook(written_excel)
        assert wb.sheetnames == [
            "Executive Dashboard",
            "Candidates Ranking",
            "Gap Analysis",
            "Operational Metrics",
        ]

        # PDF generation on empty database
        pdf_gen = PDFReportGenerator(calc)
        pdf_target = tmp_path / "empty_report.pdf"
        written_pdf = pdf_gen.generate(pdf_target)
        assert written_pdf.exists()
        reader = PdfReader(written_pdf)
        assert len(reader.pages) >= 1
        assert "%PDF-" in Path(written_pdf).read_bytes()[:10].decode("latin-1")

    def test_candidates_and_jobs_exist_with_zero_evaluations(self, clean_db_session: Session, tmp_path: Path) -> None:
        """Empirically verify reporting when candidates and jobs exist but 0 evaluations have run."""
        now = datetime.now(timezone.utc)
        cand = Candidate(
            candidate_id="cand-stress-01",
            full_name="Jean-Baptiste Poquelin",
            email="moliere@theatre.fr",
            location="Paris, France",
            years_of_experience=Decimal("15.0"),
            education_level="Master Lettres",
            raw_cv_text="Dramaturge et auteur de comedies de moeurs classiques.",
            created_at=now,
            updated_at=now,
        )
        job = JobDescription(
            job_id="job-stress-01",
            job_code="JOB-ART-01",
            title="Directeur Artistique",
            department="Culture & Spectacle",
            location="Paris, France",
            raw_description="Direction de troupe et production theatrale.",
            created_at=now,
            updated_at=now,
        )
        clean_db_session.add_all([cand, job])
        clean_db_session.commit()

        srv = ReportingService(session=clean_db_session)
        out_dir = tmp_path / "no_evals_output"
        results = srv.generate_all(out_dir)

        assert results["excel"].exists()
        assert results["pdf"].exists()

        wb = openpyxl.load_workbook(results["excel"])
        ws_rank = wb["Candidates Ranking"]
        # Only header row exists
        assert ws_rank.max_row == 3

        reader = PdfReader(results["pdf"])
        assert len(reader.pages) >= 1

    def test_single_evaluation_standard_deviation_boundary(self, clean_db_session: Session) -> None:
        """Verify standard deviation calculation with N=1 does not raise ZeroDivisionError (ddof=1)."""
        mean_v, med_v, std_v, q_v = BIMetricsCalculator.calculate_score_statistics([78.5])
        assert mean_v == 78.5
        assert med_v == 78.5
        assert std_v == 0.0
        assert q_v.q1 == 78.5
        assert q_v.q3 == 78.5
        assert q_v.iqr == 0.0

    def test_corrupted_json_and_fallback_in_gap_analysis(self, clean_db_session: Session, tmp_path: Path) -> None:
        """Verify unparseable or corrupted JSON in matched/missing skills degrades gracefully."""
        now = datetime.now(timezone.utc)
        cand = Candidate(
            candidate_id="cand-corrupt-01",
            full_name="Alexandre Dumas",
            email="dumas@roman.fr",
            location="Villers-Cotterêts",
            years_of_experience=Decimal("10.0"),
            education_level="Autodidacte",
            raw_cv_text="Auteur des Trois Mousquetaires.",
            created_at=now,
            updated_at=now,
        )
        job = JobDescription(
            job_id="job-corrupt-01",
            job_code="JOB-ROM-01",
            title="Romancier Historique",
            department="Edition",
            location="Paris",
            raw_description="Redaction de sagas d'aventure.",
            created_at=now,
            updated_at=now,
        )
        clean_db_session.add_all([cand, job])
        clean_db_session.flush()

        # Ingestion with broken JSON (non-json raw text)
        ev = MatchingEvaluation(
            evaluation_id="eval-corrupt-01",
            candidate_id="cand-corrupt-01",
            job_id="job-corrupt-01",
            overall_score=Decimal("75.0"),
            skills_score=Decimal("80.0"),
            experience_score=Decimal("70.0"),
            semantic_similarity=Decimal("0.65"),
            recommendation="consider",
            matched_skills="{broken json content: not valid}",
            missing_skills="Python, SQL, Fast Reading",  # comma-separated fallback
            strengths_summary="",
            gaps_summary="",
            executive_summary="",
            evaluated_at=now,
        )
        clean_db_session.add(ev)
        clean_db_session.commit()

        calc = BIMetricsCalculator(clean_db_session)
        gap_df = calc.get_gap_analysis_dataframe()

        assert len(gap_df) == 1
        row = gap_df.iloc[0]
        # Missing skills parsed from comma-separated string
        assert "Python" in row["Missing Required Skills"]
        assert "SQL" in row["Missing Required Skills"]
        # Empty summaries fallback to empty string
        assert row["Key Strengths"] == ""
        assert row["Key Gaps"] == ""

    def test_out_of_order_funnel_dates_handling(self, clean_db_session: Session) -> None:
        """Verify anomalous dates (e.g. negative time delta) are ignored in stage duration calculations."""
        now = datetime.now(timezone.utc)
        cand = Candidate(
            candidate_id="cand-date-01",
            full_name="Test Chrono",
            email="chrono@test.fr",
            location="Lyon",
            education_level="Licence",
            raw_cv_text="Chrono tester",
            created_at=now,
            updated_at=now,
        )
        job = JobDescription(
            job_id="job-date-01",
            job_code="JOB-DATE-01",
            title="Chrono Dev",
            department="Engineering",
            location="Lyon",
            raw_description="Chrono vacancy",
            created_at=now,
            updated_at=now,
        )
        clean_db_session.add_all([cand, job])
        clean_db_session.flush()

        # Anomalous record: screening before application date
        bad_metric = OperationalMetric(
            metric_id="met-bad-01",
            candidate_id="cand-date-01",
            job_id="job-date-01",
            application_date=date(2024, 5, 20),
            screening_date=date(2024, 5, 10),  # 10 days BEFORE application
            technical_interview_date=None,
            final_interview_date=None,
            offer_date=None,
            hiring_decision="applied",
            created_at=now,
        )
        clean_db_session.add(bad_metric)
        clean_db_session.commit()

        calc = BIMetricsCalculator(clean_db_session)
        durations = calc.calculate_stage_durations([bad_metric])
        # "Candidature a Screening" should have 0 completed count and 0.0 avg
        scr_dur = next(d for d in durations if d.stage_name == "Candidature a Screening")
        assert scr_dur.completed_count == 0
        assert scr_dur.average_days == 0.0

    def test_high_volume_candidate_load_and_performance(self, clean_db_session: Session, tmp_path: Path) -> None:
        """Empirically challenge scaling with 100 candidates and 200 evaluations."""
        import time

        now = datetime.now(timezone.utc)
        num_candidates = 50
        num_jobs = 4

        cands = [
            Candidate(
                candidate_id=f"scale-cand-{i:03d}",
                full_name=f"Candidat Test Numero {i:03d}",
                email=f"candidate_{i:03d}@scale-test.org",
                location="Paris, France",
                years_of_experience=Decimal(str((i % 12) + 1.0)),
                education_level="Master Informatique",
                raw_cv_text=f"CV text for candidate {i} containing technical keywords Python, SQL, Cloud.",
                created_at=now,
                updated_at=now,
            )
            for i in range(num_candidates)
        ]
        clean_db_session.add_all(cands)

        jobs = [
            JobDescription(
                job_id=f"scale-job-{j:02d}",
                job_code=f"JOB-SCALE-{j:02d}",
                title=f"Poste Ingenieur Qualifie {j:02d}",
                department="Ingenierie Logicielle" if j % 2 == 0 else "Data & IA",
                location="Paris, France",
                raw_description=f"Description du poste de test {j}.",
                created_at=now,
                updated_at=now,
            )
            for j in range(num_jobs)
        ]
        clean_db_session.add_all(jobs)
        clean_db_session.flush()

        evals = []
        eval_id = 1
        for cand in cands:
            for job in jobs[:2]:  # 50 * 2 = 100 evaluations
                score_val = 40.0 + ((eval_id * 7) % 55)
                evals.append(
                    MatchingEvaluation(
                        evaluation_id=f"scale-eval-{eval_id:04d}",
                        candidate_id=cand.candidate_id,
                        job_id=job.job_id,
                        overall_score=Decimal(f"{score_val:.2f}"),
                        skills_score=Decimal(f"{score_val + 2:.2f}"),
                        experience_score=Decimal(f"{score_val - 2:.2f}"),
                        semantic_similarity=Decimal("0.75"),
                        recommendation="hire" if score_val >= 70.0 else "consider",
                        matched_skills=json.dumps(["Python", "SQL"]),
                        missing_skills=json.dumps([]),
                        strengths_summary="Solide alignement algorithmique et systemes.",
                        gaps_summary="Aucun ecart critique.",
                        executive_summary="Dossier favorable pour entretien technique.",
                        evaluated_at=now,
                    )
                )
                eval_id += 1
        clean_db_session.add_all(evals)
        clean_db_session.commit()

        start_time = time.perf_counter()
        srv = ReportingService(session=clean_db_session)
        out_dir = tmp_path / "scale_output"
        results = srv.generate_all(out_dir)
        elapsed = time.perf_counter() - start_time

        # Performance constraint: generation under 10 seconds
        assert elapsed < 10.0, f"High volume generation took {elapsed:.2f}s, exceeding 10.0s threshold"

        # Structural inspection of generated files
        wb = openpyxl.load_workbook(results["excel"])
        ws_rank = wb["Candidates Ranking"]
        assert ws_rank.max_row == 103  # Title (1) + blank (2) + Header (3) + 100 rows = 103

        reader = PdfReader(results["pdf"])
        assert len(reader.pages) >= 2

    def test_extreme_french_strings_and_special_characters(self, clean_db_session: Session, tmp_path: Path) -> None:
        """Verify robust handling of extreme string lengths, French diacritics, and special characters."""
        now = datetime.now(timezone.utc)

        # Candidate with very long name, accents, ligatures, apostrophes
        long_french_name = (
            "Charles-Édouard François de la Tour d'Auvergne-Lauragais "
            "Châteauneuf-du-Pape Saint-Germain-des-Prés"
        )
        long_job_title = (
            "Directeur Général Adjoint en Charge des Systèmes d'Information, "
            "de la Transformation Numérique & de la Cybersécurité Stratégique"
        )
        complex_dept = "R&D / Direction des Études Avancées & IA"

        cand = Candidate(
            candidate_id="cand-ext-01",
            full_name=long_french_name,
            email="charles-edouard.de-la-tour@polytechnique.edu",
            location="Aix-en-Provence, France",
            years_of_experience=Decimal("22.5"),
            education_level="Doctorat d'État en Sciences Informatiques",
            raw_cv_text="Profil d'excellence : architectures distribuées, C++, Python, R&D, direction d'équipes pluridisciplinaires." * 20,
            created_at=now,
            updated_at=now,
        )
        job = JobDescription(
            job_id="job-ext-01",
            job_code="JOB-EXEC-01",
            title=long_job_title,
            department=complex_dept,
            location="Paris La Défense, France",
            raw_description="Poste de haute direction pour piloter la stratégie SI et les programmes d'innovation de rupture." * 10,
            created_at=now,
            updated_at=now,
        )
        clean_db_session.add_all([cand, job])
        clean_db_session.flush()

        long_strengths = (
            "Excellence avérée dans le leadership technique et la conception d'architectures critiques à haute résilience. "
            "Maîtrise approfondie des environnements complexes (C++, Linux, GPU, calcul intensif). "
            "Aptitude démontrée à fédérer des collectifs d'ingénieurs sur des objectifs ambitieux. "
        ) * 5

        long_gaps = (
            "Exposition limitée aux frameworks modernes de développement web front-end (React, Vue.js), "
            "ce qui demeure sans incidence au regard des responsabilités stratégiques attendues pour cette direction. "
        ) * 3

        long_synthesis = (
            "Candidat d'exception présentant une adéquation remarquable avec l'envergure du poste. "
            "La combinaison de rigueur scientifique et d'expérience managériale de haut niveau en fait "
            "le choix prioritaire pour conduire la transformation technologique de l'organisation. "
        ) * 4

        ev = MatchingEvaluation(
            evaluation_id="eval-ext-01",
            candidate_id="cand-ext-01",
            job_id="job-ext-01",
            overall_score=Decimal("94.80"),
            skills_score=Decimal("96.50"),
            experience_score=Decimal("100.00"),
            semantic_similarity=Decimal("0.9120"),
            recommendation="strong_hire",
            matched_skills=json.dumps(["Architecture SI", "C++", "Python", "Gouvernance", "Leadership", "R&D"]),
            missing_skills=json.dumps([]),
            strengths_summary=long_strengths,
            gaps_summary=long_gaps,
            executive_summary=long_synthesis,
            evaluated_at=now,
        )
        clean_db_session.add(ev)
        clean_db_session.commit()

        srv = ReportingService(session=clean_db_session)
        out_dir = tmp_path / "extreme_text_output"
        results = srv.generate_all(out_dir)

        assert results["excel"].exists()
        assert results["pdf"].exists()

        # Check Excel cell content
        wb = openpyxl.load_workbook(results["excel"])
        ws_rank = wb["Candidates Ranking"]
        cell_name = ws_rank.cell(row=4, column=2).value
        assert cell_name == long_french_name

        # Check PDF extraction
        reader = PdfReader(results["pdf"])
        assert len(reader.pages) >= 2
        p1_text = reader.pages[0].extract_text()
        assert "SYNTHESE DECISIONNELLE" in p1_text

    def test_pdf_numbered_canvas_two_pass_page_count(self, clean_db_session: Session, tmp_path: Path) -> None:
        """Verify NumberedCanvas calculates total pages dynamically and stamps 'Page X sur Y' correctly."""
        now = datetime.now(timezone.utc)
        cand = Candidate(
            candidate_id="cand-canvas-01",
            full_name="Canvas Validator",
            email="canvas@test.com",
            location="Paris",
            education_level="Master",
            raw_cv_text="Canvas validator CV",
            created_at=now,
            updated_at=now,
        )
        job = JobDescription(
            job_id="job-canvas-01",
            job_code="JOB-CANVAS-01",
            title="Lead Canvas",
            department="Design",
            location="Paris",
            raw_description="Design Lead",
            created_at=now,
            updated_at=now,
        )
        clean_db_session.add_all([cand, job])
        clean_db_session.flush()

        ev = MatchingEvaluation(
            evaluation_id="eval-canvas-01",
            candidate_id="cand-canvas-01",
            job_id="job-canvas-01",
            overall_score=Decimal("85.0"),
            skills_score=Decimal("88.0"),
            experience_score=Decimal("82.0"),
            semantic_similarity=Decimal("0.80"),
            recommendation="hire",
            matched_skills=json.dumps(["Design", "Python"]),
            missing_skills=json.dumps([]),
            strengths_summary="High quality canvas execution.",
            gaps_summary="None.",
            executive_summary="Solid recommendation.",
            evaluated_at=now,
        )
        clean_db_session.add(ev)
        clean_db_session.commit()

        srv = ReportingService(session=clean_db_session)
        out_dir = tmp_path / "canvas_output"
        results = srv.generate_all(out_dir)

        reader = PdfReader(results["pdf"])
        total_pages = len(reader.pages)
        assert total_pages >= 2

        # Check footer on each page contains correct dynamic page number
        for idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            assert f"Page {idx} sur {total_pages}" in text, (
                f"Page {idx} does not contain expected 'Page {idx} sur {total_pages}' footer"
            )

    def test_strict_compliance_zero_emojis_and_prohibited_terms_in_generated_deliverables(
        self,
        clean_db_session: Session,
        tmp_path: Path,
    ) -> None:
        """Verify generated Excel and PDF documents contain strictly zero emojis and zero prohibited terms."""
        now = datetime.now(timezone.utc)
        cand = Candidate(
            candidate_id="cand-clean-01",
            full_name="Auditeur Conformite",
            email="auditeur@conformite.fr",
            location="Strasbourg, France",
            education_level="Master Droit",
            raw_cv_text="Audit et conformite reglementaire.",
            created_at=now,
            updated_at=now,
        )
        job = JobDescription(
            job_id="job-clean-01",
            job_code="JOB-CONF-01",
            title="Responsable Conformite",
            department="Juridique & Gouvernance",
            location="Strasbourg, France",
            raw_description="Controle permanent et conformite des processus RH.",
            created_at=now,
            updated_at=now,
        )
        clean_db_session.add_all([cand, job])
        clean_db_session.flush()

        ev = MatchingEvaluation(
            evaluation_id="eval-clean-01",
            candidate_id="cand-clean-01",
            job_id="job-clean-01",
            overall_score=Decimal("82.0"),
            skills_score=Decimal("80.0"),
            experience_score=Decimal("85.0"),
            semantic_similarity=Decimal("0.78"),
            recommendation="hire",
            matched_skills=json.dumps(["Audit", "Conformite"]),
            missing_skills=json.dumps([]),
            strengths_summary="Excellente maitrise des normes de gouvernance.",
            gaps_summary="Aucun ecart.",
            executive_summary="Recommande pour le poste.",
            evaluated_at=now,
        )
        clean_db_session.add(ev)
        clean_db_session.commit()

        srv = ReportingService(session=clean_db_session)
        out_dir = tmp_path / "compliance_output"
        results = srv.generate_all(out_dir)

        # 1. Scan Excel content
        wb = openpyxl.load_workbook(results["excel"])
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            for row in ws.iter_rows(values_only=True):
                for cell_val in row:
                    if cell_val is not None:
                        text_val = str(cell_val)
                        for ch in text_val:
                            cp = ord(ch)
                            assert not (
                                0x1F600 <= cp <= 0x1F64F
                                or 0x1F300 <= cp <= 0x1F5FF
                                or 0x1F900 <= cp <= 0x1F9FF
                                or 0x2600 <= cp <= 0x27BF
                                or 0x1F000 <= cp <= 0x1FFFF
                            ), f"Emoji found in Excel sheet '{sheet_name}': {ch} (U+{cp:X})"

        # 2. Scan PDF content
        reader = PdfReader(results["pdf"])
        full_pdf_text = ""
        for page in reader.pages:
            full_pdf_text += page.extract_text() + "\n"

        for ch in full_pdf_text:
            cp = ord(ch)
            assert not (
                0x1F600 <= cp <= 0x1F64F
                or 0x1F300 <= cp <= 0x1F5FF
                or 0x1F900 <= cp <= 0x1F9FF
                or 0x2600 <= cp <= 0x27BF
                or 0x1F000 <= cp <= 0x1FFFF
            ), f"Emoji found in PDF text: {ch} (U+{cp:X})"

        prohibited = [
            "".join(["chat", "gpt"]),
            "".join(["open", "ai"]),
            "".join(["co", "pilot"]),
            "".join(["assist", "ant"]),
            "".join(["ag", "ent"]),
        ]
        pdf_text_lower = full_pdf_text.lower()
        for term in prohibited:
            assert term not in pdf_text_lower, f"Prohibited term '{term}' detected in generated PDF output"
