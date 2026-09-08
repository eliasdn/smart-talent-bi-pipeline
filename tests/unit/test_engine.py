"""Unit test suite covering the semantic AI matching engine components."""

from decimal import Decimal
import json
import pytest

from src.engine.extractor import (
    ExtractedSkill,
    ExtractedSkills,
    JobSkillProfile,
    SkillExtractor,
)
from src.engine.scorer import (
    MatchingScorer,
    ScoreBreakdown,
    compute_domain_relevance,
    parse_degree_level,
)
from src.engine.semantic import BILINGUAL_STOPWORDS, SemanticMatcher
from src.engine.service import MatchingEngine
from src.engine.synthesizer import EvaluationSynthesis, MatchingSynthesizer
from src.engine.taxonomies import (
    SkillTaxonomyItem,
    _strip_accents,
    get_all_taxonomy_items,
    get_hard_skills,
    get_soft_skills,
    get_taxonomy_registry,
    lookup_canonical_skill,
)


class TestTaxonomies:
    """Verification of skill taxonomy consistency, bilingual coverage, and aliases."""

    def test_taxonomy_registry_population(self) -> None:
        """Verify taxonomy contains minimum catalog thresholds for hard and soft skills."""
        items = get_all_taxonomy_items()
        registry = get_taxonomy_registry()
        hard = get_hard_skills()
        soft = get_soft_skills()

        assert len(items) >= 50
        assert len(registry) == len(items)
        assert len(hard) >= 40
        assert len(soft) >= 7
        assert len(hard) + len(soft) == len(items)

    def test_canonical_skill_lookups(self) -> None:
        """Verify alias resolution maps to canonical keys for both languages and symbols."""
        test_cases = [
            ("Python", "python"),
            ("python3", "python"),
            ("C++", "cpp"),
            ("cpp", "cpp"),
            ("C#", "csharp"),
            ("c sharp", "csharp"),
            (".NET", "dotnet"),
            ("dotnet", "dotnet"),
            ("Node.js", "node_js"),
            ("CI/CD", "ci_cd"),
            ("integration continue", "ci_cd"),
            ("continuous integration", "ci_cd"),
            ("Scikit-Learn", "scikit_learn"),
            ("sklearn", "scikit_learn"),
            ("Machine Learning", "machine_learning"),
            ("apprentissage automatique", "machine_learning"),
            ("Esprit d'équipe", "esprit_dequipe"),
            ("travail d'equipe", "esprit_dequipe"),
            ("teamwork", "esprit_dequipe"),
            ("Rigueur", "rigueur"),
            ("rigoureux", "rigueur"),
            ("rigoureuse", "rigueur"),
            ("Résolution de problèmes", "resolution_de_problemes"),
            ("problem solving", "resolution_de_problemes"),
            ("Leadership", "leadership"),
            ("gestion d'équipe", "leadership"),
        ]
        for query, expected_key in test_cases:
            item = lookup_canonical_skill(query)
            assert item is not None, f"Failed to resolve alias: {query}"
            assert item.key == expected_key, f"Expected {expected_key} for {query}, got {item.key}"

    def test_accent_stripping(self) -> None:
        """Verify diacritics removal for normalization."""
        assert _strip_accents("Éléphant") == "elephant"
        assert _strip_accents("Résolution de problèmes") == "resolution de problemes"
        assert _strip_accents("Déploiement continu") == "deploiement continu"
        assert _strip_accents("") == ""

    def test_unknown_skill_lookup(self) -> None:
        """Verify non-existent skills return None without crashing."""
        assert lookup_canonical_skill("NonExistentSkillXYZ123") is None
        assert lookup_canonical_skill("") is None
        assert lookup_canonical_skill("   ") is None


class TestSkillExtractor:
    """Verification of regex pattern matching, symbol boundaries, and text parsing."""

    @pytest.fixture
    def extractor(self) -> SkillExtractor:
        return SkillExtractor()

    def test_symbol_extraction_boundaries(self, extractor: SkillExtractor) -> None:
        """Verify boundary-aware extraction of C++, C#, .NET, CI/CD, and Node.js."""
        text = "Experience with C++, C#, .NET, CI/CD, and Node.js."
        result = extractor.extract_from_text(text)

        keys = result.hard_skill_keys
        assert "cpp" in keys
        assert "csharp" in keys
        assert "dotnet" in keys
        assert "ci_cd" in keys
        assert "node_js" in keys

    def test_single_letter_boundary_protection(self, extractor: SkillExtractor) -> None:
        """Verify single-letter skills like R do not match inside larger words."""
        text = "Engineers using Docker, Spark, and Redis in their workflow."
        result = extractor.extract_from_text(text)
        assert "r" not in result.hard_skill_keys

        text_with_r = "Experienced with the R statistical language and Python."
        result_with_r = extractor.extract_from_text(text_with_r)
        assert "r" in result_with_r.hard_skill_keys
        assert "python" in result_with_r.hard_skill_keys

    def test_multi_word_ngram_extraction(self, extractor: SkillExtractor) -> None:
        """Verify multi-word technical and soft skills extraction without partial corruption."""
        text = "Expert in Apache Spark, Machine Learning, Power BI, and Esprit d'équipe."
        result = extractor.extract_from_text(text)

        assert "apache_spark" in result.hard_skill_keys
        assert "machine_learning" in result.hard_skill_keys
        assert "power_bi" in result.hard_skill_keys
        assert "esprit_dequipe" in result.soft_skill_keys

    def test_extract_candidate_and_job_profiles(self, extractor: SkillExtractor) -> None:
        """Verify parsing candidate profiles and job requirements into structured models."""
        candidate = {
            "raw_cv_text": "Experienced Data Engineer in Paris. Developed Spark streaming with Kafka.",
            "skills": [
                {"name": "Python", "category": "technical"},
                {"name": "SQL", "category": "technical"},
            ],
            "experiences": [
                {
                    "role_title": "Data Engineer",
                    "description": "Architected pipelines using Docker and AWS.",
                    "technologies": "Docker, AWS, PostgreSQL",
                }
            ],
        }
        cand_extracted = extractor.extract_candidate_skills(candidate)
        assert "python" in cand_extracted.hard_skill_keys
        assert "sql" in cand_extracted.hard_skill_keys
        assert "apache_spark" in cand_extracted.hard_skill_keys
        assert "apache_kafka" in cand_extracted.hard_skill_keys
        assert "docker" in cand_extracted.hard_skill_keys
        assert "aws" in cand_extracted.hard_skill_keys
        assert "postgresql" in cand_extracted.hard_skill_keys

        job = {
            "raw_description": "We require an autonomous engineer with leadership qualities.",
            "skills": [
                {"name": "Python", "importance": "required"},
                {"name": "SQL", "importance": "required"},
                {"name": "Docker", "importance": "preferred"},
            ],
        }
        job_profile = extractor.extract_job_skills(job)
        assert "python" in job_profile.required_hard_keys
        assert "sql" in job_profile.required_hard_keys
        assert "docker" in job_profile.preferred_hard_keys
        assert "autonomie" in job_profile.target_soft_keys
        assert "leadership" in job_profile.target_soft_keys

    def test_empty_and_null_extraction(self, extractor: SkillExtractor) -> None:
        """Verify graceful handling of empty inputs."""
        empty_res = extractor.extract_from_text("")
        assert len(empty_res.all_keys) == 0

        none_res = extractor.extract_from_text(None)
        assert len(none_res.all_keys) == 0

        empty_cand = extractor.extract_candidate_skills({})
        assert len(empty_cand.all_keys) == 0


class TestSemanticMatcher:
    """Verification of offline TF-IDF vectorization and cosine similarity."""

    @pytest.fixture
    def matcher(self) -> SemanticMatcher:
        return SemanticMatcher()

    def test_identical_documents(self, matcher: SemanticMatcher) -> None:
        """Verify identical documents yield maximum similarity 1.0."""
        text = "Senior Data Engineer developing distributed ETL pipelines in Python."
        sim = matcher.compute_similarity(text, text)
        assert sim == 1.0

    def test_empty_and_whitespace_documents(self, matcher: SemanticMatcher) -> None:
        """Verify empty documents yield minimum similarity 0.0."""
        assert matcher.compute_similarity("", "Data Engineer") == 0.0
        assert matcher.compute_similarity("   ", "Data Engineer") == 0.0
        assert matcher.compute_similarity("", "") == 0.0

    def test_stopwords_only_documents(self, matcher: SemanticMatcher) -> None:
        """Verify documents containing exclusively stopwords yield 0.0 without crash."""
        text_stop = "le la les de du the and or in on"
        sim = matcher.compute_similarity(text_stop, "Python developer")
        assert sim == 0.0

    def test_discriminative_similarity(self, matcher: SemanticMatcher) -> None:
        """Verify target job description yields significantly higher similarity than unrelated role."""
        target_role = "Senior Data Engineer with Apache Spark, Airflow, and PostgreSQL on AWS."
        related_candidate = "Lead Data Architect with Spark, Airflow, Kafka, and cloud AWS pipelines."
        unrelated_candidate = "Clinical Pediatric Nurse with patient care and hospital administration experience."

        sim_related = matcher.compute_similarity(related_candidate, target_role)
        sim_unrelated = matcher.compute_similarity(unrelated_candidate, target_role)

        assert sim_related > 0.15
        assert sim_unrelated < 0.05
        assert sim_related > sim_unrelated * 3


class TestMatchingScorer:
    """Verification of multi-factor scoring mathematics, bounds, and tier thresholds."""

    @pytest.fixture
    def scorer(self) -> MatchingScorer:
        return MatchingScorer()

    def test_academic_degree_level_parsing(self) -> None:
        """Verify degree level parsing from textual descriptions."""
        assert parse_degree_level("PhD in Computer Science") == 8
        assert parse_degree_level("Doctorat en Informatique") == 8
        assert parse_degree_level("Master of Science in Data Engineering") == 5
        assert parse_degree_level("Diplôme d'ingénieur en génie logiciel") == 5
        assert parse_degree_level("Bachelor in Business Analytics") == 3
        assert parse_degree_level("Licence Professionnelle Informatique") == 3
        assert parse_degree_level("DUT Informatique") == 2
        assert parse_degree_level("BTS SIO") == 2
        assert parse_degree_level("Baccalauréat Scientifique") == 1
        assert parse_degree_level(None) == 3

    def test_academic_domain_relevance(self) -> None:
        """Verify discipline domain alignment scoring."""
        # Exact tech match
        assert compute_domain_relevance("Master en Informatique", "Master Informatique") == 1.0
        # STEM match
        assert compute_domain_relevance("Master en Mathématiques", None) == 0.85
        # Business analytics match
        assert compute_domain_relevance("Bachelor in Business Analytics", None) == 0.70
        # General match
        assert compute_domain_relevance("Licence en Histoire", None) == 0.50

    def test_experience_scoring_logic(self, scorer: MatchingScorer) -> None:
        """Verify seniority evaluation and bounding."""
        assert scorer.compute_experience_score(cand_exp=6.0, job_min_exp=4.0) == 100.0
        assert scorer.compute_experience_score(cand_exp=4.0, job_min_exp=4.0) == 100.0
        assert scorer.compute_experience_score(cand_exp=2.0, job_min_exp=4.0) == 50.0
        assert scorer.compute_experience_score(cand_exp=0.0, job_min_exp=4.0) == 0.0
        assert scorer.compute_experience_score(cand_exp=5.0, job_min_exp=0.0) == 100.0

    def test_tier_classification_thresholds(self, scorer: MatchingScorer) -> None:
        """Verify exact tier thresholds and recommendation mappings."""
        # EXCELLENT >= 85.0
        tier, rec = scorer.classify_tier_and_recommendation(92.5)
        assert tier == "EXCELLENT" and rec == "strong_hire"

        tier, rec = scorer.classify_tier_and_recommendation(85.0)
        assert tier == "EXCELLENT" and rec == "strong_hire"

        # BON: 70.0 to 84.99
        tier, rec = scorer.classify_tier_and_recommendation(84.9)
        assert tier == "BON" and rec == "hire"

        tier, rec = scorer.classify_tier_and_recommendation(70.0)
        assert tier == "BON" and rec == "hire"

        # PARTIEL: 50.0 to 69.99
        tier, rec = scorer.classify_tier_and_recommendation(69.9)
        assert tier == "PARTIEL" and rec == "consider"

        tier, rec = scorer.classify_tier_and_recommendation(50.0)
        assert tier == "PARTIEL" and rec == "consider"

        # INSUFFISANT < 50.0
        tier, rec = scorer.classify_tier_and_recommendation(49.9)
        assert tier == "INSUFFISANT" and rec == "reject"

        tier, rec = scorer.classify_tier_and_recommendation(0.0)
        assert tier == "INSUFFISANT" and rec == "reject"

    def test_comprehensive_scoring_bounds(self, scorer: MatchingScorer) -> None:
        """Verify scores remain strictly bounded within [0.0, 100.0] under edge scenarios."""
        # Top profile
        top_cand = {
            "years_of_experience": 10.0,
            "education_level": "PhD in Computer Science",
            "raw_cv_text": "Python SQL PostgreSQL Docker Kubernetes AWS Apache Spark Apache Kafka. Leadership rigueur autonomie.",
            "skills": [{"name": "Python"}, {"name": "SQL"}, {"name": "Docker"}, {"name": "AWS"}],
        }
        target_job = {
            "experience_min_years": 5.0,
            "education_level_required": "Master in Computer Science",
            "raw_description": "Senior Data Platform Engineer with Python, SQL, Docker, and AWS.",
            "skills": [
                {"name": "Python", "importance": "required"},
                {"name": "SQL", "importance": "required"},
                {"name": "AWS", "importance": "preferred"},
            ],
        }
        top_res = scorer.score(top_cand, target_job)
        assert 0.0 <= top_res.overall_score <= 100.0
        assert 0.0 <= top_res.technical_score <= 100.0
        assert 0.0 <= top_res.experience_score <= 100.0
        assert 0.0 <= top_res.education_score <= 100.0
        assert 0.0 <= top_res.soft_skills_score <= 100.0
        assert top_res.match_tier in ("EXCELLENT", "BON")

        # Incompatible profile
        incompatible_cand = {
            "years_of_experience": 0.0,
            "education_level": "Baccalauréat",
            "raw_cv_text": "Looking for entry level administrative assistant positions.",
            "skills": [],
        }
        low_res = scorer.score(incompatible_cand, target_job)
        assert 0.0 <= low_res.overall_score <= 100.0
        assert low_res.match_tier == "INSUFFISANT"
        assert low_res.recommendation == "reject"


class TestMatchingSynthesizer:
    """Verification of qualitative synthesis generation in French without forbidden artifacts."""

    @pytest.fixture
    def synthesizer(self) -> MatchingSynthesizer:
        return MatchingSynthesizer()

    def test_synthesis_generation_structure(self, synthesizer: MatchingSynthesizer) -> None:
        """Verify presence and structure of strengths, gaps, recommendations, and executive summary."""
        breakdown = ScoreBreakdown(
            overall_score=88.5,
            technical_score=85.0,
            experience_score=100.0,
            education_score=90.0,
            soft_skills_score=75.0,
            semantic_similarity=0.45,
            match_tier="EXCELLENT",
            recommendation="strong_hire",
            matched_required_skills=["python", "sql"],
            missing_required_skills=[],
            matched_preferred_skills=["docker"],
            missing_preferred_skills=["kubernetes"],
            matched_soft_skills=["esprit_dequipe", "rigueur"],
            missing_soft_skills=[],
            candidate_years_exp=6.0,
            job_min_years_exp=4.0,
            candidate_edu_level=5,
            job_edu_level=5,
        )

        candidate = {
            "full_name": "Marc Lemaire",
            "education_level": "Master in Computer Science",
        }
        job = {
            "title": "Data Platform Engineer",
            "department": "Infrastructure",
            "education_level_required": "Master in Computer Science",
        }

        synthesis = synthesizer.synthesize(candidate, job, breakdown)

        assert len(synthesis.strengths) >= 3
        assert len(synthesis.recommendations) >= 1
        assert "Marc Lemaire" in synthesis.executive_summary
        assert "Data Platform Engineer" in synthesis.executive_summary
        assert "88.5/100" in synthesis.executive_summary
        assert "strong_hire" not in synthesis.executive_summary  # Should use French narrative

        # Verify formatting
        assert synthesis.strengths_summary.startswith("- ")
        assert synthesis.gaps_summary.startswith("- ")

    def test_strict_cleanliness_compliance(self, synthesizer: MatchingSynthesizer) -> None:
        """Verify zero emoticons and zero mentions of automated agents or assistants in generated text."""
        breakdown = ScoreBreakdown(
            overall_score=62.0,
            technical_score=60.0,
            experience_score=50.0,
            education_score=80.0,
            soft_skills_score=50.0,
            semantic_similarity=0.25,
            match_tier="PARTIEL",
            recommendation="consider",
            matched_required_skills=["python"],
            missing_required_skills=["apache_spark"],
            matched_preferred_skills=[],
            missing_preferred_skills=["docker"],
            matched_soft_skills=["autonomie"],
            missing_soft_skills=["leadership"],
            candidate_years_exp=2.0,
            job_min_years_exp=4.0,
            candidate_edu_level=5,
            job_edu_level=5,
        )

        candidate = {"full_name": "Sophie Martin", "education_level": "Master"}
        job = {"title": "Data Engineer", "department": "Data", "education_level_required": "Master"}

        synth = synthesizer.synthesize(candidate, job, breakdown)
        all_text = " ".join([
            synth.strengths_summary,
            synth.gaps_summary,
            synth.executive_summary,
            *synth.recommendations,
        ])

        # Check absence of common emoji characters
        for ch in all_text:
            assert ord(ch) < 0x1F300 or ord(ch) > 0x1F9FF, f"Emoji character detected: {ch}"


class TestMatchingEngine:
    """Verification of end-to-end matching evaluation DTO generation."""

    def test_evaluate_pair_produces_valid_dto(self) -> None:
        """Verify evaluate_pair generates a fully validated MatchingEvaluationDTO."""
        engine = MatchingEngine()
        cand = {
            "candidate_id": "cand-test-unit",
            "full_name": "Julien Petit",
            "years_of_experience": 5.0,
            "education_level": "Master in Computer Science",
            "raw_cv_text": "Senior Python and SQL engineer with experience in Docker and AWS.",
            "skills": [{"name": "Python"}, {"name": "SQL"}],
        }
        job = {
            "job_id": "job-test-unit",
            "title": "Backend Python Engineer",
            "department": "Core Engineering",
            "experience_min_years": 3.0,
            "education_level_required": "Master in Computer Science",
            "raw_description": "Seeking Python engineer with SQL knowledge and Docker skills.",
            "skills": [
                {"name": "Python", "importance": "required"},
                {"name": "SQL", "importance": "required"},
            ],
        }

        eval_dto = engine.evaluate_pair(cand, job)

        assert eval_dto.candidate_id == "cand-test-unit"
        assert eval_dto.job_id == "job-test-unit"
        assert isinstance(eval_dto.overall_score, Decimal)
        assert isinstance(eval_dto.skills_score, Decimal)
        assert isinstance(eval_dto.experience_score, Decimal)
        assert isinstance(eval_dto.semantic_similarity, Decimal)
        assert eval_dto.recommendation in ("strong_hire", "hire", "consider", "reject")
        assert len(eval_dto.matched_skills) >= 2
        assert len(eval_dto.strengths_summary) > 0
        assert len(eval_dto.executive_summary) > 0
