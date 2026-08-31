"""Qualitative synthesis engine generating explainable recruitment insights and executive summaries."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.engine.extractor import JobSkillProfile
from src.engine.scorer import ScoreBreakdown
from src.engine.taxonomies import get_taxonomy_registry


@dataclass
class EvaluationSynthesis:
    """Structured qualitative evaluation output."""

    strengths: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    strengths_summary: str = ""
    gaps_summary: str = ""
    executive_summary: str = ""


class MatchingSynthesizer:
    """Generates structured qualitative feedback, gap analysis, and executive summaries in French."""

    def __init__(self) -> None:
        """Initialize synthesizer with taxonomy metadata for label lookup."""
        self.taxonomy = get_taxonomy_registry()

    def _resolve_names(self, keys: List[str]) -> List[str]:
        """Convert a list of canonical skill keys to official display names."""
        names: List[str] = []
        for k in keys:
            if k in self.taxonomy:
                names.append(self.taxonomy[k].name)
            else:
                names.append(k.replace("_", " ").title())
        return names

    def generate_strengths(
        self,
        breakdown: ScoreBreakdown,
        candidate_name: str,
        cand_edu: Optional[str] = None,
    ) -> List[str]:
        """Generate structured points forts for the candidate."""
        strengths: List[str] = []

        matched_req_names = self._resolve_names(breakdown.matched_required_skills)
        if matched_req_names:
            strengths.append(
                f"Validation des compétences clés requises : {', '.join(matched_req_names)}."
            )

        matched_pref_names = self._resolve_names(breakdown.matched_preferred_skills)
        if matched_pref_names:
            strengths.append(
                f"Maîtrise de compétences complémentaires appréciées : {', '.join(matched_pref_names)}."
            )

        # Experience alignment
        if breakdown.candidate_years_exp > breakdown.job_min_years_exp:
            strengths.append(
                f"Ancienneté professionnelle supérieure aux prérequis : "
                f"{breakdown.candidate_years_exp:.1f} ans observés face à {breakdown.job_min_years_exp:.1f} ans demandés."
            )
        elif breakdown.candidate_years_exp == breakdown.job_min_years_exp and breakdown.job_min_years_exp > 0:
            strengths.append(
                f"Expérience professionnelle parfaitement alignée sur le seuil requis ({breakdown.candidate_years_exp:.1f} ans)."
            )

        # Academic fit
        if breakdown.candidate_edu_level >= breakdown.job_edu_level and breakdown.candidate_edu_level > 0:
            edu_display = cand_edu or "Niveau académique validé"
            strengths.append(
                f"Formation académique conforme aux critères de sélection : {edu_display}."
            )

        # Soft skills fit
        matched_soft_names = self._resolve_names(breakdown.matched_soft_skills)
        if matched_soft_names:
            strengths.append(
                f"Compétences comportementales et relationnelles démontrées : {', '.join(matched_soft_names)}."
            )

        # Semantic convergence
        if breakdown.semantic_similarity >= 0.30:
            sim_pct = int(round(breakdown.semantic_similarity * 100))
            strengths.append(
                f"Excellente cohérence sémantique et lexicale avec l'environnement du poste (indice {sim_pct}%)."
            )

        if not strengths:
            strengths.append("Profil disposant de prédispositions d'apprentissage sur le domaine.")

        return strengths

    def generate_gaps(
        self,
        breakdown: ScoreBreakdown,
        cand_edu: Optional[str] = None,
        job_edu: Optional[str] = None,
    ) -> List[str]:
        """Generate structured points de vigilance and technical deficits."""
        gaps: List[str] = []

        missing_req_names = self._resolve_names(breakdown.missing_required_skills)
        if missing_req_names:
            gaps.append(
                f"Compétences indispensables non identifiées : {', '.join(missing_req_names)}."
            )

        missing_pref_names = self._resolve_names(breakdown.missing_preferred_skills)
        if missing_pref_names:
            gaps.append(
                f"Compétences secondaires souhaitées absentes : {', '.join(missing_pref_names)}."
            )

        # Seniority gap
        if breakdown.candidate_years_exp < breakdown.job_min_years_exp:
            delta = breakdown.job_min_years_exp - breakdown.candidate_years_exp
            gaps.append(
                f"Écart de séniorité : déficit de {delta:.1f} an(s) par rapport aux exigences du poste "
                f"({breakdown.candidate_years_exp:.1f} ans observés vs {breakdown.job_min_years_exp:.1f} ans requis)."
            )

        # Education gap
        if breakdown.candidate_edu_level < breakdown.job_edu_level:
            c_desc = cand_edu or "Niveau actuel inférieur"
            j_desc = job_edu or "Niveau supérieur requis"
            gaps.append(
                f"Niveau de diplôme inférieur aux attentes initiales ({c_desc} face à {j_desc})."
            )

        if not gaps:
            gaps.append("Aucun écart critique relevé par rapport aux exigences formulées.")

        return gaps

    def generate_recommendations(
        self,
        breakdown: ScoreBreakdown,
    ) -> List[str]:
        """Produce operational next steps and development suggestions."""
        recommendations: List[str] = []
        tier = breakdown.match_tier
        missing_req_names = self._resolve_names(breakdown.missing_required_skills)

        if tier == "EXCELLENT":
            recommendations.append(
                "Prioriser la convocation en entretien technique approfondi et mise en situation réelle."
            )
            recommendations.append(
                "Valider l'adéquation culturelle et les attentes de rémunération en phase décisionnelle finale."
            )
        elif tier == "BON":
            recommendations.append(
                "Convoquer pour un entretien technique axé sur la validation des compétences à approfondir."
            )
            if missing_req_names:
                tech_list = ", ".join(missing_req_names[:3])
                recommendations.append(
                    f"Prévoir un module de formation ou une certification accélérée sur : {tech_list}."
                )
            else:
                recommendations.append(
                    "Évaluer la rapidité d'adaptation opérationnelle aux méthodologies internes."
                )
        elif tier == "PARTIEL":
            recommendations.append(
                "Explorer l'éligibilité du candidat sur des postes plus juniors ou transverses."
            )
            if missing_req_names:
                tech_list = ", ".join(missing_req_names[:3])
                recommendations.append(
                    f"Mise à niveau préalable requise sur les technologies indispensables ({tech_list})."
                )
            recommendations.append(
                "Conserver le profil dans le vivier de compétences pour des opportunités ultérieures."
            )
        else:  # INSUFFISANT
            recommendations.append(
                "Candidature non retenue pour ce poste en raison d'écarts substantiels sur les compétences fondamentales."
            )
            recommendations.append(
                "Archiver le dossier dans la CVthèque avec notification de courtoisie."
            )

        return recommendations

    def generate_executive_summary(
        self,
        candidate_name: str,
        job_title: str,
        job_dept: str,
        breakdown: ScoreBreakdown,
    ) -> str:
        """Compose a coherent, formal French narrative synthesis."""
        tier_label_fr = {
            "EXCELLENT": "Adéquation Excellente (Profil Prioritaire)",
            "BON": "Adéquation Favorable (Profil Éligible)",
            "PARTIEL": "Adéquation Partielle (Profil de Réserve)",
            "INSUFFISANT": "Adéquation Insuffisante (Profil Non Retenu)",
        }.get(breakdown.match_tier, breakdown.match_tier)

        total_req = len(breakdown.matched_required_skills) + len(breakdown.missing_required_skills)
        matched_count = len(breakdown.matched_required_skills)

        intro = (
            f"Évaluation de {candidate_name} pour le poste de {job_title} au sein du département {job_dept}. "
            f"Le dossier obtient une note globale de {breakdown.overall_score:.1f}/100, "
            f"le positionnant dans la catégorie '{tier_label_fr}'."
        )

        tech_desc = (
            f"Sur le plan technique, le candidat valide {matched_count} sur {total_req} compétences impératives "
            f"(score technique : {breakdown.technical_score:.1f}%)."
        )

        exp_desc = (
            f"L'expérience cumulée de {breakdown.candidate_years_exp:.1f} ans "
            f"{'dépasse' if breakdown.candidate_years_exp >= breakdown.job_min_years_exp else 'se situe en deçà de'} "
            f"l'exigence minimale fixée à {breakdown.job_min_years_exp:.1f} ans."
        )

        if breakdown.match_tier == "EXCELLENT":
            conclusion = (
                "Le profil offre toutes les garanties opérationnelles pour une prise de poste immédiate. "
                "Recommandation : Poursuite prioritaire du processus de recrutement."
            )
        elif breakdown.match_tier == "BON":
            conclusion = (
                "Le dossier témoigne d'un socle technique robuste avec un fort potentiel de progression. "
                "Recommandation : Entretien d'approfondissement technique recommandé."
            )
        elif breakdown.match_tier == "PARTIEL":
            conclusion = (
                "Des écarts notables sont relevés sur les compétences requises ou l'ancienneté. "
                "Recommandation : Profil à conserver en réserve ou à réorienter."
            )
        else:
            conclusion = (
                "Les compétences observées ne satisfont pas les critères d'éligibilité définis pour le rôle. "
                "Recommandation : Dossier non retenu pour ce poste."
            )

        return f"{intro} {tech_desc} {exp_desc} {conclusion}"

    def synthesize(
        self,
        candidate: Any,
        job: Any,
        breakdown: ScoreBreakdown,
    ) -> EvaluationSynthesis:
        """Produce full evaluation synthesis including strengths, gaps, recommendations, and executive summary.

        Args:
            candidate: Candidate profile representation.
            job: Job vacancy representation.
            breakdown: Multi-factor scoring results.

        Returns:
            EvaluationSynthesis containing formatted qualitative outputs.
        """
        if isinstance(candidate, dict):
            cand_name = candidate.get("full_name", "Candidat")
            cand_edu = candidate.get("education_level")
        else:
            cand_name = getattr(candidate, "full_name", "Candidat")
            cand_edu = getattr(candidate, "education_level", None)

        if isinstance(job, dict):
            job_title = job.get("title", "Poste")
            job_dept = job.get("department", "Direction")
            job_edu = job.get("education_level_required")
        else:
            job_title = getattr(job, "title", "Poste")
            job_dept = getattr(job, "department", "Direction")
            job_edu = getattr(job, "education_level_required", None)

        strengths = self.generate_strengths(breakdown, cand_name, cand_edu)
        gaps = self.generate_gaps(breakdown, cand_edu, job_edu)
        recommendations = self.generate_recommendations(breakdown)
        executive = self.generate_executive_summary(cand_name, job_title, job_dept, breakdown)

        return EvaluationSynthesis(
            strengths=strengths,
            gaps=gaps,
            recommendations=recommendations,
            strengths_summary="\n".join(f"- {s}" for s in strengths),
            gaps_summary="\n".join(f"- {g}" for g in gaps),
            executive_summary=executive,
        )
