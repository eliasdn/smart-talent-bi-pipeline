"""Multi-factor weighted scoring engine evaluating candidate-job alignment."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Union
import unicodedata

from src.engine.extractor import ExtractedSkills, JobSkillProfile, SkillExtractor
from src.engine.semantic import SemanticMatcher
from src.engine.taxonomies import _strip_accents


@dataclass
class ScoreBreakdown:
    """Detailed multidimensional scoring breakdown and tier categorization."""

    overall_score: float
    technical_score: float
    experience_score: float
    education_score: float
    soft_skills_score: float
    semantic_similarity: float
    match_tier: str  # 'EXCELLENT', 'BON', 'PARTIEL', 'INSUFFISANT'
    recommendation: str  # 'strong_hire', 'hire', 'consider', 'reject'
    matched_required_skills: List[str] = field(default_factory=list)
    missing_required_skills: List[str] = field(default_factory=list)
    matched_preferred_skills: List[str] = field(default_factory=list)
    missing_preferred_skills: List[str] = field(default_factory=list)
    matched_soft_skills: List[str] = field(default_factory=list)
    missing_soft_skills: List[str] = field(default_factory=list)
    candidate_years_exp: float = 0.0
    job_min_years_exp: float = 0.0
    candidate_edu_level: int = 0
    job_edu_level: int = 0


def parse_degree_level(edu_text: Optional[str]) -> int:
    """Parse academic degree string into standardized numerical tier.

    Tiers:
        Level 8: PhD / Doctorat
        Level 5: Master / Ingénieur / Bac+5 / DEA / DESS
        Level 3: Bachelor / Licence / Bac+3
        Level 2: BTS / DUT / Associate / Bac+2
        Level 1: Baccalauréat / Secondary Education

    Args:
        edu_text: Raw degree text or title.

    Returns:
        Integer academic level (1 to 8). Defaults to 3 if unspecified.
    """
    if not edu_text:
        return 3

    norm = _strip_accents(edu_text)
    if any(term in norm for term in ["phd", "doctorat", "doctorate", "bac+8", "docteur"]):
        return 8
    if any(term in norm for term in ["master", "msc", "ingenieur", "bac+5", "dea", "dess", "diplome d'ingenieur"]):
        return 5
    if any(term in norm for term in ["bachelor", "licence", "bsc", "bac+3", "undergraduate"]):
        return 3
    if any(term in norm for term in ["dut", "bts", "associate", "deug", "bac+2"]):
        return 2
    if any(term in norm for term in ["baccalaureat", "bac", "high school", "secondaire"]):
        return 1

    return 3


def compute_domain_relevance(candidate_edu: Optional[str], job_edu: Optional[str]) -> float:
    """Evaluate academic domain alignment between candidate education and job vacancy.

    Args:
        candidate_edu: Candidate degree description.
        job_edu: Required degree description from job posting.

    Returns:
        Domain relevance score between 0.50 and 1.00.
    """
    if not candidate_edu:
        return 0.50

    cand_norm = _strip_accents(candidate_edu)
    job_norm = _strip_accents(job_edu) if job_edu else ""

    # Check direct word overlap on discipline keywords
    tech_keywords = [
        "informatique", "computer science", "data", "software", "genie logiciel",
        "intelligence artificielle", "machine learning", "ai", "systemes",
    ]
    stem_keywords = [
        "mathematiques", "mathematics", "statistiques", "statistics", "physique",
        "physics", "ingenierie", "engineering", "sciences",
    ]
    business_keywords = [
        "business analytics", "business intelligence", "economie", "economics",
        "finance", "gestion", "management", "marketing quantitatif",
    ]

    # Exact job domain match if job specifies target discipline
    if job_norm:
        cand_words = set(w for w in cand_norm.split() if len(w) > 3)
        job_words = set(w for w in job_norm.split() if len(w) > 3)
        if cand_words & job_words:
            return 1.0

    if any(k in cand_norm for k in tech_keywords):
        return 1.0
    if any(k in cand_norm for k in stem_keywords):
        return 0.85
    if any(k in cand_norm for k in business_keywords):
        return 0.70

    return 0.50


class MatchingScorer:
    """Computes multidimensional weighted match score between candidate and job profile."""

    def __init__(
        self,
        weight_tech: float = 0.45,
        weight_exp: float = 0.25,
        weight_edu: float = 0.15,
        weight_soft: float = 0.15,
    ) -> None:
        """Initialize scorer with dimensional weights.

        Args:
            weight_tech: Technical skills and semantic weight (default 0.45).
            weight_exp: Experience seniority weight (default 0.25).
            weight_edu: Academic level and domain weight (default 0.15).
            weight_soft: Soft skills weight (default 0.15).
        """
        total = weight_tech + weight_exp + weight_edu + weight_soft
        self.w_tech = weight_tech / total
        self.w_exp = weight_exp / total
        self.w_edu = weight_edu / total
        self.w_soft = weight_soft / total

        self.extractor = SkillExtractor()
        self.semantic = SemanticMatcher()

    def compute_technical_score(
        self,
        candidate_skills: ExtractedSkills,
        job_profile: JobSkillProfile,
        semantic_sim: float,
    ) -> tuple[float, List[str], List[str], List[str], List[str]]:
        """Compute technical dimension score combining required coverage, preferred coverage, and semantic similarity.

        Returns:
            Tuple of (score, matched_req, missing_req, matched_pref, missing_pref).
        """
        cand_hard_keys = candidate_skills.hard_skill_keys

        # Required hard skills
        req_keys = job_profile.required_hard_keys
        matched_req = sorted(list(cand_hard_keys & req_keys))
        missing_req = sorted(list(req_keys - cand_hard_keys))

        if req_keys:
            cov_req = len(matched_req) / len(req_keys)
        else:
            cov_req = 1.0

        # Preferred hard skills
        pref_keys = job_profile.preferred_hard_keys
        matched_pref = sorted(list(cand_hard_keys & pref_keys))
        missing_pref = sorted(list(pref_keys - cand_hard_keys))

        if pref_keys:
            cov_pref = len(matched_pref) / len(pref_keys)
            direct_alignment = 0.85 * cov_req + 0.15 * cov_pref
        else:
            cov_pref = 0.0
            direct_alignment = cov_req

        # Technical score: 70% direct skill alignment + 30% semantic similarity
        raw_tech_score = 100.0 * (0.70 * direct_alignment + 0.30 * semantic_sim)
        tech_score = max(0.0, min(100.0, raw_tech_score))

        return round(tech_score, 2), matched_req, missing_req, matched_pref, missing_pref

    def compute_experience_score(self, cand_exp: float, job_min_exp: float) -> float:
        """Compute seniority alignment score comparing candidate tenure to minimum job requirements.

        Args:
            cand_exp: Candidate professional experience in years.
            job_min_exp: Job requirement minimum years.

        Returns:
            Experience score bounded between 0.0 and 100.0.
        """
        cand_exp_f = max(0.0, float(cand_exp))
        job_min_exp_f = max(0.0, float(job_min_exp))

        if job_min_exp_f <= 0.0 or cand_exp_f >= job_min_exp_f:
            return 100.0

        ratio = cand_exp_f / max(job_min_exp_f, 1.0)
        score = 100.0 * max(0.0, min(1.0, ratio))
        return round(score, 2)

    def compute_education_score(
        self,
        candidate_edu: Optional[str],
        job_edu: Optional[str],
    ) -> tuple[float, int, int]:
        """Compute academic dimension score combining degree level ratio and domain relevance.

        Returns:
            Tuple of (score, candidate_level, job_level).
        """
        cand_level = parse_degree_level(candidate_edu)
        job_level = parse_degree_level(job_edu)

        if cand_level >= job_level:
            level_ratio = 1.0
        else:
            level_ratio = max(0.40, cand_level / max(job_level, 1))

        domain_rel = compute_domain_relevance(candidate_edu, job_edu)
        raw_edu = 100.0 * (0.60 * level_ratio + 0.40 * domain_rel)
        score = max(0.0, min(100.0, raw_edu))
        return round(score, 2), cand_level, job_level

    def compute_soft_skills_score(
        self,
        candidate_skills: ExtractedSkills,
        job_profile: JobSkillProfile,
    ) -> tuple[float, List[str], List[str]]:
        """Compute soft skills fit score based on target behavioral attributes.

        Returns:
            Tuple of (score, matched_soft_keys, missing_soft_keys).
        """
        cand_soft = candidate_skills.soft_skill_keys
        job_soft = job_profile.target_soft_keys

        if job_soft:
            matched = sorted(list(cand_soft & job_soft))
            missing = sorted(list(job_soft - cand_soft))
            score = 100.0 * (len(matched) / len(job_soft))
        else:
            matched = sorted(list(cand_soft))
            missing = []
            # Baseline expectation: having up to 4 soft skills yields full score
            score = 100.0 * min(1.0, len(matched) / 4.0)

        return round(max(0.0, min(100.0, score)), 2), matched, missing

    def classify_tier_and_recommendation(self, score: float) -> tuple[str, str]:
        """Map a composite score to standard evaluation tier and recommendation.

        Thresholds:
            EXCELLENT >= 85.0 -> strong_hire
            BON >= 70.0 and < 85.0 -> hire
            PARTIEL >= 50.0 and < 70.0 -> consider
            INSUFFISANT < 50.0 -> reject

        Args:
            score: Overall composite score in [0.0, 100.0].

        Returns:
            Tuple of (tier_name, recommendation_string).
        """
        if score >= 85.0:
            return "EXCELLENT", "strong_hire"
        if score >= 70.0:
            return "BON", "hire"
        if score >= 50.0:
            return "PARTIEL", "consider"
        return "INSUFFISANT", "reject"

    def score(
        self,
        candidate: Any,
        job: Any,
        candidate_skills: Optional[ExtractedSkills] = None,
        job_profile: Optional[JobSkillProfile] = None,
        semantic_sim: Optional[float] = None,
    ) -> ScoreBreakdown:
        """Execute full multidimensional scoring of candidate against job posting.

        Args:
            candidate: Candidate entity, DTO, or dict.
            job: JobDescription entity, DTO, or dict.
            candidate_skills: Pre-extracted candidate skills if available.
            job_profile: Pre-extracted job profile if available.
            semantic_sim: Pre-computed semantic similarity if available.

        Returns:
            ScoreBreakdown containing overall score, sub-scores, tier, and gap lists.
        """
        # Extract skills if not supplied
        if candidate_skills is None:
            candidate_skills = self.extractor.extract_candidate_skills(candidate)
        if job_profile is None:
            job_profile = self.extractor.extract_job_skills(job)

        # Semantic similarity
        if semantic_sim is None:
            semantic_sim = self.semantic.compare_candidate_and_job(candidate, job)

        # 1. Technical score
        tech_score, m_req, miss_req, m_pref, miss_pref = self.compute_technical_score(
            candidate_skills=candidate_skills,
            job_profile=job_profile,
            semantic_sim=semantic_sim,
        )

        # 2. Experience score
        if isinstance(candidate, dict):
            cand_exp = float(candidate.get("years_of_experience", 0.0) or 0.0)
            cand_edu = candidate.get("education_level")
        else:
            cand_exp_raw = getattr(candidate, "years_of_experience", 0.0) or 0.0
            cand_exp = float(cand_exp_raw)
            cand_edu = getattr(candidate, "education_level", None)

        if isinstance(job, dict):
            job_min_exp = float(job.get("experience_min_years", 0.0) or 0.0)
            job_edu = job.get("education_level_required")
        else:
            job_min_exp_raw = getattr(job, "experience_min_years", 0.0) or 0.0
            job_min_exp = float(job_min_exp_raw)
            job_edu = getattr(job, "education_level_required", None)

        exp_score = self.compute_experience_score(cand_exp, job_min_exp)

        # 3. Education score
        edu_score, cand_level, job_level = self.compute_education_score(cand_edu, job_edu)

        # 4. Soft skills score
        soft_score, m_soft, miss_soft = self.compute_soft_skills_score(
            candidate_skills=candidate_skills,
            job_profile=job_profile,
        )

        # Overall weighted composite score
        composite = (
            self.w_tech * tech_score
            + self.w_exp * exp_score
            + self.w_edu * edu_score
            + self.w_soft * soft_score
        )
        overall_score = round(max(0.0, min(100.0, composite)), 2)

        tier, rec = self.classify_tier_and_recommendation(overall_score)

        return ScoreBreakdown(
            overall_score=overall_score,
            technical_score=tech_score,
            experience_score=exp_score,
            education_score=edu_score,
            soft_skills_score=soft_score,
            semantic_similarity=round(semantic_sim, 4),
            match_tier=tier,
            recommendation=rec,
            matched_required_skills=m_req,
            missing_required_skills=miss_req,
            matched_preferred_skills=m_pref,
            missing_preferred_skills=miss_pref,
            matched_soft_skills=m_soft,
            missing_soft_skills=miss_soft,
            candidate_years_exp=cand_exp,
            job_min_years_exp=job_min_exp,
            candidate_edu_level=cand_level,
            job_edu_level=job_level,
        )
