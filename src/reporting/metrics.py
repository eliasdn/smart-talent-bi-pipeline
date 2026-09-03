"""Business Intelligence metrics and KPI calculation engine for talent analytics.

Queries the relational database to compute recruitment KPIs, score distributions,
stage velocity metrics, sourcing channel conversion rates, recruitment ROI savings,
and structured DataFrames for reporting deliverables.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.engine.extractor import SkillExtractor
from src.engine.scorer import MatchingScorer
from src.engine.taxonomies import get_taxonomy_registry
from src.models.entities import (
    Candidate,
    JobDescription,
    MatchingEvaluation,
    OperationalMetric,
    create_db_engine,
    get_session_factory,
)
from src.utils.logger import setup_logger

logger = setup_logger("smart_talent_bi.reporting.metrics")


@dataclass
class ScoreQuartilesDTO:
    """Statistical quartiles and interquartile range for matching scores."""

    q1: float
    median: float
    q3: float
    iqr: float


@dataclass
class ScoreDistributionDTO:
    """Distribution bracket for score cohort classification."""

    tier_name: str
    score_range: str
    count: int
    percentage: float


@dataclass
class RecruitmentROIDTO:
    """Recruitment time and cost savings metrics comparing manual baseline to automated pipeline."""

    total_candidates: int
    manual_hours_per_candidate: float
    total_manual_hours: float
    automated_execution_seconds: float
    total_automated_hours: float
    total_hours_saved: float
    recruiter_hourly_rate: float
    total_cost_saved: float
    time_savings_percentage: float


@dataclass
class StageDurationDTO:
    """Average duration and sample volume for a recruitment funnel stage."""

    stage_name: str
    average_days: float
    completed_count: int


@dataclass
class SourcingChannelMetricDTO:
    """Performance and conversion metrics by candidate sourcing channel."""

    channel: str
    applicant_count: int
    hired_count: int
    conversion_rate_percentage: float
    average_cost_eur: float


@dataclass
class DepartmentSummaryDTO:
    """Recruitment performance summary grouped by organizational department."""

    department: str
    vacancies_count: int
    candidates_evaluated: int
    average_score: float
    highest_score: float
    top_candidate_name: str


@dataclass
class KPISummaryDTO:
    """Comprehensive Business Intelligence KPI summary for executive decision-making."""

    total_candidates: int
    total_jobs: int
    total_evaluations: int
    average_matching_score: float
    median_matching_score: float
    score_std_dev: float
    score_quartiles: ScoreQuartilesDTO
    high_fit_count: int
    high_fit_rate: float
    roi: RecruitmentROIDTO
    stage_durations: List[StageDurationDTO] = field(default_factory=list)
    channel_metrics: List[SourcingChannelMetricDTO] = field(default_factory=list)
    score_distribution: List[ScoreDistributionDTO] = field(default_factory=list)
    department_summaries: List[DepartmentSummaryDTO] = field(default_factory=list)


class BIMetricsCalculator:
    """Calculates Business Intelligence metrics, operational KPIs, and reporting tables from database."""

    def __init__(self, session: Session) -> None:
        """Initialize calculator with active SQLAlchemy session.

        Args:
            session: Active database session.
        """
        self.session = session
        self.scorer = MatchingScorer()
        self.extractor = SkillExtractor()
        self.taxonomy = get_taxonomy_registry()

        self._cand_skills_cache: Dict[str, Any] = {}
        self._job_profile_cache: Dict[str, Any] = {}

    @classmethod
    def from_db_path(cls, db_path: Union[str, Path]) -> "BIMetricsCalculator":
        """Factory method to instantiate calculator from a SQLite database file path.

        Args:
            db_path: Path to SQLite database file.

        Returns:
            BIMetricsCalculator instance connected to target database.
        """
        path_str = str(db_path)
        if not path_str.startswith("sqlite:///"):
            db_url = f"sqlite:///{Path(db_path).resolve()}"
        else:
            db_url = path_str
        engine = create_db_engine(db_url)
        factory = get_session_factory(engine)
        return cls(factory())

    # --- Standalone Calculation Utilities ---

    @staticmethod
    def calculate_score_statistics(
        scores: Sequence[float],
    ) -> Tuple[float, float, float, ScoreQuartilesDTO]:
        """Compute mean, median, sample standard deviation, and quartiles from a score series.

        Args:
            scores: Sequence of numerical scores (0.0 to 100.0).

        Returns:
            Tuple of (mean, median, std_dev, ScoreQuartilesDTO).
        """
        if not scores:
            zero_quartiles = ScoreQuartilesDTO(q1=0.0, median=0.0, q3=0.0, iqr=0.0)
            return 0.0, 0.0, 0.0, zero_quartiles

        arr = np.array(scores, dtype=float)
        mean_val = round(float(np.mean(arr)), 2)
        median_val = round(float(np.median(arr)), 2)
        q1_val = round(float(np.percentile(arr, 25)), 2)
        q3_val = round(float(np.percentile(arr, 75)), 2)
        iqr_val = round(q3_val - q1_val, 2)

        if len(arr) >= 2:
            std_val = round(float(np.std(arr, ddof=1)), 2)
        else:
            std_val = 0.0

        quartiles = ScoreQuartilesDTO(
            q1=q1_val,
            median=median_val,
            q3=q3_val,
            iqr=iqr_val,
        )
        return mean_val, median_val, std_val, quartiles

    @staticmethod
    def calculate_roi(
        candidate_count: int,
        automated_execution_seconds: float,
        hourly_rate: float = 65.0,
        manual_baseline_hours: float = 0.75,
    ) -> RecruitmentROIDTO:
        """Compute recruitment time and cost reduction ROI against manual screening baseline.

        Args:
            candidate_count: Number of candidate profiles processed.
            automated_execution_seconds: Total pipeline automated execution time in seconds.
            hourly_rate: Standard blended hourly rate for Talent Acquisition Specialist ($65.00/hr).
            manual_baseline_hours: Baseline manual screening time per candidate (0.75 hr / 45 min).

        Returns:
            RecruitmentROIDTO with complete savings metrics.
        """
        total_cand = max(0, candidate_count)
        rate = max(0.0, float(hourly_rate))
        manual_hours = max(0.0, float(manual_baseline_hours))

        total_manual = round(total_cand * manual_hours, 2)
        auto_sec = max(0.0, float(automated_execution_seconds))
        total_auto = round(auto_sec / 3600.0, 4)

        hours_saved = max(0.0, round(total_manual - total_auto, 2))
        cost_saved = round(hours_saved * rate, 2)

        if total_manual > 0.0:
            time_savings_pct = round((hours_saved / total_manual) * 100.0, 1)
        else:
            time_savings_pct = 0.0

        return RecruitmentROIDTO(
            total_candidates=total_cand,
            manual_hours_per_candidate=manual_hours,
            total_manual_hours=total_manual,
            automated_execution_seconds=round(auto_sec, 2),
            total_automated_hours=total_auto,
            total_hours_saved=hours_saved,
            recruiter_hourly_rate=rate,
            total_cost_saved=cost_saved,
            time_savings_percentage=time_savings_pct,
        )

    @staticmethod
    def calculate_score_distribution(scores: Sequence[float]) -> List[ScoreDistributionDTO]:
        """Classify scores into 4 standard talent tier brackets and compute relative percentages.

        Brackets:
            [0.0, 40.0)   -> Unmatched / Faible
            [40.0, 60.0)  -> Low Fit / Partiel
            [60.0, 80.0)  -> Moderate Fit / Bon
            [80.0, 100.0] -> High Fit / Excellent

        Args:
            scores: Sequence of scores.

        Returns:
            List of ScoreDistributionDTO items.
        """
        total = len(scores)
        b_unmatched = 0
        b_low = 0
        b_mod = 0
        b_high = 0

        for s in scores:
            if s < 40.0:
                b_unmatched += 1
            elif s < 60.0:
                b_low += 1
            elif s < 80.0:
                b_mod += 1
            else:
                b_high += 1

        def pct(c: int) -> float:
            return round((c / total) * 100.0, 1) if total > 0 else 0.0

        return [
            ScoreDistributionDTO(
                tier_name="Faible Fit",
                score_range="[0% - 40%)",
                count=b_unmatched,
                percentage=pct(b_unmatched),
            ),
            ScoreDistributionDTO(
                tier_name="Fit Partiel",
                score_range="[40% - 60%)",
                count=b_low,
                percentage=pct(b_low),
            ),
            ScoreDistributionDTO(
                tier_name="Bon Fit",
                score_range="[60% - 80%)",
                count=b_mod,
                percentage=pct(b_mod),
            ),
            ScoreDistributionDTO(
                tier_name="Fit Excellent",
                score_range="[80% - 100%]",
                count=b_high,
                percentage=pct(b_high),
            ),
        ]

    @staticmethod
    def calculate_stage_durations(metrics: Sequence[OperationalMetric]) -> List[StageDurationDTO]:
        """Compute average days elapsed between consecutive stages of the hiring funnel.

        Args:
            metrics: Sequence of operational metric entities.

        Returns:
            List of StageDurationDTO items for each funnel stage.
        """
        stage_deltas: Dict[str, List[float]] = {
            "Candidature a Screening": [],
            "Screening a Entretien Technique": [],
            "Entretien Technique a Entretien Final": [],
            "Entretien Final a Offre": [],
            "Cycle Complet d'Embauche": [],
        }

        for m in metrics:
            app_d = m.application_date
            scr_d = m.screening_date
            tech_d = m.technical_interview_date
            fin_d = m.final_interview_date
            off_d = m.offer_date

            if app_d and scr_d and scr_d >= app_d:
                stage_deltas["Candidature a Screening"].append(float((scr_d - app_d).days))

            if scr_d and tech_d and tech_d >= scr_d:
                stage_deltas["Screening a Entretien Technique"].append(float((tech_d - scr_d).days))

            if tech_d and fin_d and fin_d >= tech_d:
                stage_deltas["Entretien Technique a Entretien Final"].append(float((fin_d - tech_d).days))

            if fin_d and off_d and off_d >= fin_d:
                stage_deltas["Entretien Final a Offre"].append(float((off_d - fin_d).days))

            if app_d and off_d and off_d >= app_d:
                stage_deltas["Cycle Complet d'Embauche"].append(float((off_d - app_d).days))

        results: List[StageDurationDTO] = []
        for name, deltas in stage_deltas.items():
            if deltas:
                avg = round(float(np.mean(deltas)), 1)
                cnt = len(deltas)
            else:
                avg = 0.0
                cnt = 0
            results.append(StageDurationDTO(stage_name=name, average_days=avg, completed_count=cnt))

        return results

    @staticmethod
    def calculate_channel_metrics(metrics: Sequence[OperationalMetric]) -> List[SourcingChannelMetricDTO]:
        """Group operational metrics by sourcing channel and calculate conversion rates and costs.

        Args:
            metrics: Sequence of operational metric entities.

        Returns:
            List of SourcingChannelMetricDTO sorted by applicant volume descending.
        """
        channels: Dict[str, Dict[str, Any]] = {}

        for m in metrics:
            ch = m.sourcing_channel or "Direct Application"
            if ch not in channels:
                channels[ch] = {
                    "total": 0,
                    "hired": 0,
                    "costs": [],
                }
            channels[ch]["total"] += 1
            if m.hiring_decision == "hired":
                channels[ch]["hired"] += 1
            if m.cost_per_applicant_eur is not None:
                channels[ch]["costs"].append(float(m.cost_per_applicant_eur))

        results: List[SourcingChannelMetricDTO] = []
        for ch, data in channels.items():
            tot = data["total"]
            hired = data["hired"]
            conv = round((hired / tot) * 100.0, 1) if tot > 0 else 0.0
            avg_cost = round(float(np.mean(data["costs"])), 2) if data["costs"] else 0.0
            results.append(
                SourcingChannelMetricDTO(
                    channel=ch,
                    applicant_count=tot,
                    hired_count=hired,
                    conversion_rate_percentage=conv,
                    average_cost_eur=avg_cost,
                )
            )

        results.sort(key=lambda x: x.applicant_count, reverse=True)
        return results

    def calculate_department_summaries(
        self,
        evaluations: Sequence[MatchingEvaluation],
    ) -> List[DepartmentSummaryDTO]:
        """Aggregate candidate evaluations by organizational department.

        Args:
            evaluations: Sequence of matching evaluation records.

        Returns:
            List of DepartmentSummaryDTO items.
        """
        dept_data: Dict[str, Dict[str, Any]] = {}

        for ev in evaluations:
            job = ev.job
            dept = job.department if job and job.department else "General"
            job_id = job.job_id if job else ev.job_id
            score = float(ev.overall_score)
            cand_name = ev.candidate.full_name if ev.candidate else "Candidat"

            if dept not in dept_data:
                dept_data[dept] = {
                    "jobs": set(),
                    "scores": [],
                    "top_score": -1.0,
                    "top_candidate": "",
                }

            dept_data[dept]["jobs"].add(job_id)
            dept_data[dept]["scores"].append(score)
            if score > dept_data[dept]["top_score"]:
                dept_data[dept]["top_score"] = score
                dept_data[dept]["top_candidate"] = cand_name

        summaries: List[DepartmentSummaryDTO] = []
        for dept, data in dept_data.items():
            scores = data["scores"]
            avg_score = round(float(np.mean(scores)), 2) if scores else 0.0
            top_score = round(data["top_score"], 2) if data["top_score"] >= 0 else 0.0
            summaries.append(
                DepartmentSummaryDTO(
                    department=dept,
                    vacancies_count=len(data["jobs"]),
                    candidates_evaluated=len(scores),
                    average_score=avg_score,
                    highest_score=top_score,
                    top_candidate_name=data["top_candidate"],
                )
            )

        summaries.sort(key=lambda x: x.candidates_evaluated, reverse=True)
        return summaries

    # --- Primary KPI Calculation Coordinator ---

    def compute_kpi_summary(self) -> KPISummaryDTO:
        """Execute full aggregation over relational tables to produce overall executive KPI summary.

        Returns:
            Fully populated KPISummaryDTO.
        """
        # 1. Total counts
        cand_count = self.session.scalar(select(func.count(Candidate.candidate_id))) or 0
        job_count = self.session.scalar(select(func.count(JobDescription.job_id))) or 0
        eval_count = self.session.scalar(select(func.count(MatchingEvaluation.evaluation_id))) or 0

        # 2. Evaluations query
        evaluations = self.session.scalars(select(MatchingEvaluation)).all()
        scores = [float(e.overall_score) for e in evaluations]

        # 3. Score statistics & quartiles
        mean_score, median_score, std_dev, quartiles = self.calculate_score_statistics(scores)

        # 4. High-fit count (score >= 70.0)
        high_fit_count = sum(1 for s in scores if s >= 70.0)
        high_fit_rate = round((high_fit_count / len(scores)) * 100.0, 1) if scores else 0.0

        # 5. Operational metrics & automated time
        op_metrics = self.session.scalars(select(OperationalMetric)).all()
        total_auto_sec = sum(
            float(m.automated_screening_time_seconds or 0.0) for m in op_metrics
        )
        if total_auto_sec == 0.0 and cand_count > 0:
            total_auto_sec = round(cand_count * 0.1, 2)

        # 6. Recruitment ROI
        roi = self.calculate_roi(
            candidate_count=cand_count,
            automated_execution_seconds=total_auto_sec,
            hourly_rate=65.0,
            manual_baseline_hours=0.75,
        )

        # 7. Stage durations and channel conversion
        stage_durations = self.calculate_stage_durations(op_metrics)
        channel_metrics = self.calculate_channel_metrics(op_metrics)

        # 8. Score distribution brackets
        score_distribution = self.calculate_score_distribution(scores)

        # 9. Department summaries
        dept_summaries = self.calculate_department_summaries(evaluations)

        return KPISummaryDTO(
            total_candidates=cand_count,
            total_jobs=job_count,
            total_evaluations=eval_count,
            average_matching_score=mean_score,
            median_matching_score=median_score,
            score_std_dev=std_dev,
            score_quartiles=quartiles,
            high_fit_count=high_fit_count,
            high_fit_rate=high_fit_rate,
            roi=roi,
            stage_durations=stage_durations,
            channel_metrics=channel_metrics,
            score_distribution=score_distribution,
            department_summaries=dept_summaries,
        )

    # --- Sub-scores Helper for Detailed Rankings ---

    def _resolve_subscores(
        self,
        ev: MatchingEvaluation,
        cand: Optional[Candidate],
        job: Optional[JobDescription],
    ) -> Dict[str, Any]:
        """Compute or extract all score dimensions, tier, and recommendation for an evaluation."""
        tech_score = float(ev.skills_score)
        exp_score = float(ev.experience_score)
        overall_score = float(ev.overall_score)
        tier, rec = self.scorer.classify_tier_and_recommendation(overall_score)

        edu_score = 70.0
        soft_score = 70.0

        if cand and job:
            # Education sub-score
            try:
                edu_res = self.scorer.compute_education_score(
                    cand.education_level, job.education_level_required
                )
                edu_score = float(edu_res[0])
            except Exception:
                edu_score = 70.0

            # Soft skills sub-score
            try:
                if cand.candidate_id not in self._cand_skills_cache:
                    self._cand_skills_cache[cand.candidate_id] = self.extractor.extract_candidate_skills(cand)
                if job.job_id not in self._job_profile_cache:
                    self._job_profile_cache[job.job_id] = self.extractor.extract_job_skills(job)

                cand_sk = self._cand_skills_cache[cand.candidate_id]
                job_prof = self._job_profile_cache[job.job_id]
                soft_res = self.scorer.compute_soft_skills_score(cand_sk, job_prof)
                soft_score = float(soft_res[0])
            except Exception:
                derived = (overall_score - 0.45 * tech_score - 0.25 * exp_score - 0.15 * edu_score) / 0.15
                soft_score = round(max(0.0, min(100.0, derived)), 2)

        return {
            "overall_score": overall_score,
            "technical_score": tech_score,
            "experience_score": exp_score,
            "education_score": edu_score,
            "soft_skills_score": soft_score,
            "tier": tier,
            "recommendation": ev.recommendation or rec,
            "semantic_similarity": float(ev.semantic_similarity),
        }

    # --- DataFrame Generators for Reporting ---

    def get_rankings_dataframe(self) -> pd.DataFrame:
        """Generate structured rankings DataFrame sorted by overall score descending.

        Columns:
            Rank, Candidate ID, Candidate Name, Job ID, Job Title, Department,
            Overall Score, Technical Score, Experience Score, Education Score,
            Soft Skills Score, Tier, Recommendation, Semantic Similarity

        Returns:
            pandas DataFrame.
        """
        evaluations = self.session.scalars(
            select(MatchingEvaluation).order_by(MatchingEvaluation.overall_score.desc())
        ).all()

        rows: List[Dict[str, Any]] = []
        rank = 1

        for ev in evaluations:
            cand = ev.candidate
            job = ev.job

            cand_name = cand.full_name if cand else "Candidat Inconnu"
            cand_id = cand.candidate_id if cand else ev.candidate_id
            job_title = job.title if job else "Poste Non Renseigne"
            job_id = job.job_id if job else ev.job_id
            dept = job.department if job else "General"

            sub = self._resolve_subscores(ev, cand, job)

            rows.append({
                "Rank": rank,
                "Candidate ID": cand_id,
                "Candidate Name": cand_name,
                "Job ID": job_id,
                "Job Title": job_title,
                "Department": dept,
                "Overall Score": sub["overall_score"],
                "Technical Score": sub["technical_score"],
                "Experience Score": sub["experience_score"],
                "Education Score": sub["education_score"],
                "Soft Skills Score": sub["soft_skills_score"],
                "Tier": sub["tier"],
                "Recommendation": sub["recommendation"],
                "Semantic Similarity": sub["semantic_similarity"],
            })
            rank += 1

        df = pd.DataFrame(rows)
        if df.empty:
            cols = [
                "Rank", "Candidate ID", "Candidate Name", "Job ID", "Job Title", "Department",
                "Overall Score", "Technical Score", "Experience Score", "Education Score",
                "Soft Skills Score", "Tier", "Recommendation", "Semantic Similarity",
            ]
            return pd.DataFrame(columns=cols)
        return df

    def get_gap_analysis_dataframe(self) -> pd.DataFrame:
        """Generate detailed qualification and skill gap analysis DataFrame for all candidate-job pairs.

        Columns:
            Candidate Name, Job Title, Matched Skills, Missing Required Skills,
            Candidate Experience Years, Job Required Experience Years,
            Experience Delta Years, Key Strengths, Key Gaps, Recommendation

        Returns:
            pandas DataFrame.
        """
        evaluations = self.session.scalars(
            select(MatchingEvaluation).order_by(MatchingEvaluation.overall_score.desc())
        ).all()

        rows: List[Dict[str, Any]] = []

        for ev in evaluations:
            cand = ev.candidate
            job = ev.job

            cand_name = cand.full_name if cand else "Candidat Inconnu"
            job_title = job.title if job else "Poste Non Renseigne"

            # Parse skills JSON or comma string
            matched_list = self._decode_json_list(ev.matched_skills)
            missing_list = self._decode_json_list(ev.missing_skills)

            matched_display = ", ".join(matched_list) if matched_list else "Aucune"
            missing_display = ", ".join(missing_list) if missing_list else "Aucune"

            cand_exp = float(cand.years_of_experience) if cand and cand.years_of_experience is not None else 0.0
            job_exp = float(job.experience_min_years) if job and job.experience_min_years is not None else 0.0
            delta_exp = round(cand_exp - job_exp, 1)

            rows.append({
                "Candidate Name": cand_name,
                "Job Title": job_title,
                "Matched Skills": matched_display,
                "Missing Required Skills": missing_display,
                "Candidate Experience Years": cand_exp,
                "Job Required Experience Years": job_exp,
                "Experience Delta Years": delta_exp,
                "Key Strengths": ev.strengths_summary or "",
                "Key Gaps": ev.gaps_summary or "",
                "Recommendation": ev.recommendation or "",
            })

        df = pd.DataFrame(rows)
        if df.empty:
            cols = [
                "Candidate Name", "Job Title", "Matched Skills", "Missing Required Skills",
                "Candidate Experience Years", "Job Required Experience Years",
                "Experience Delta Years", "Key Strengths", "Key Gaps", "Recommendation",
            ]
            return pd.DataFrame(columns=cols)
        return df

    def get_operational_metrics_dataframe(self) -> pd.DataFrame:
        """Generate recruitment operational audit trail and stage telemetry DataFrame.

        Columns:
            Metric ID, Candidate Name, Job Title, Sourcing Channel, Application Date,
            Screening Date, Technical Interview Date, Final Interview Date, Offer Date,
            Hiring Decision, Time to Screen (Hours), Automated Screening (Sec), Cost (EUR),
            Days Application to Screen, Days Screen to Technical, Days Technical to Final,
            Days Final to Offer, Total Days to Offer

        Returns:
            pandas DataFrame.
        """
        metrics = self.session.scalars(
            select(OperationalMetric).order_by(OperationalMetric.application_date.desc())
        ).all()

        rows: List[Dict[str, Any]] = []

        for m in metrics:
            cand = m.candidate
            job = m.job

            cand_name = cand.full_name if cand else (m.candidate_id or "Inconnu")
            job_title = job.title if job else (m.job_id or "Inconnu")

            app_d = m.application_date
            scr_d = m.screening_date
            tech_d = m.technical_interview_date
            fin_d = m.final_interview_date
            off_d = m.offer_date

            d_app_scr = (scr_d - app_d).days if (app_d and scr_d and scr_d >= app_d) else None
            d_scr_tech = (tech_d - scr_d).days if (scr_d and tech_d and tech_d >= scr_d) else None
            d_tech_fin = (fin_d - tech_d).days if (tech_d and fin_d and fin_d >= tech_d) else None
            d_fin_off = (off_d - fin_d).days if (fin_d and off_d and off_d >= fin_d) else None
            d_tot = (off_d - app_d).days if (app_d and off_d and off_d >= app_d) else None

            rows.append({
                "Metric ID": m.metric_id,
                "Candidate Name": cand_name,
                "Job Title": job_title,
                "Sourcing Channel": m.sourcing_channel or "Direct Application",
                "Application Date": str(app_d) if app_d else "",
                "Screening Date": str(scr_d) if scr_d else "",
                "Technical Interview Date": str(tech_d) if tech_d else "",
                "Final Interview Date": str(fin_d) if fin_d else "",
                "Offer Date": str(off_d) if off_d else "",
                "Hiring Decision": m.hiring_decision or "applied",
                "Time to Screen (Hours)": float(m.time_to_screen_hours or 0.0),
                "Automated Screening (Sec)": float(m.automated_screening_time_seconds or 0.0),
                "Cost (EUR)": float(m.cost_per_applicant_eur or 0.0),
                "Days Application to Screen": d_app_scr,
                "Days Screen to Technical": d_scr_tech,
                "Days Technical to Final": d_tech_fin,
                "Days Final to Offer": d_fin_off,
                "Total Days to Offer": d_tot,
            })

        df = pd.DataFrame(rows)
        if df.empty:
            cols = [
                "Metric ID", "Candidate Name", "Job Title", "Sourcing Channel", "Application Date",
                "Screening Date", "Technical Interview Date", "Final Interview Date", "Offer Date",
                "Hiring Decision", "Time to Screen (Hours)", "Automated Screening (Sec)", "Cost (EUR)",
                "Days Application to Screen", "Days Screen to Technical", "Days Technical to Final",
                "Days Final to Offer", "Total Days to Offer",
            ]
            return pd.DataFrame(columns=cols)
        return df

    @staticmethod
    def _decode_json_list(val: Optional[str]) -> List[str]:
        """Safely deserialize a JSON array or parse a comma-separated string."""
        if not val:
            return []
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if item]
        except Exception:
            pass
        return [item.strip() for item in val.split(",") if item.strip()]
