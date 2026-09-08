"""Edge cases and boundary tests for skill extraction and text matching engine."""

from decimal import Decimal
import random
import string
import time
import pytest

from src.engine.extractor import SkillExtractor
from src.engine.scorer import MatchingScorer, parse_degree_level, compute_domain_relevance
from src.engine.semantic import SemanticMatcher
from src.engine.service import MatchingEngine
from src.engine.taxonomies import lookup_canonical_skill


class TestEngineBoundaries:
    """Tests evaluating boundary conditions, special tokens, and variable length inputs."""

    @pytest.fixture
    def engine(self) -> MatchingEngine:
        return MatchingEngine()

    @pytest.fixture
    def extractor(self) -> SkillExtractor:
        return SkillExtractor()

    @pytest.fixture
    def scorer(self) -> MatchingScorer:
        return MatchingScorer()

    @pytest.fixture
    def semantic(self) -> SemanticMatcher:
        return SemanticMatcher()

    def test_extreme_empty_inputs_handling(self, engine: MatchingEngine) -> None:
        """Verify engine gracefully handles completely empty and null-like inputs without crashing."""
        cand_empty = {
            "candidate_id": "cand-empty-001",
            "full_name": "",
            "raw_cv_text": "",
            "skills": [],
            "experiences": [],
            "years_of_experience": 0,
            "education_level": "",
        }
        job_empty = {
            "job_id": "job-empty-001",
            "title": "",
            "raw_description": "",
            "skills": [],
            "experience_min_years": 0,
            "education_level_required": "",
        }

        eval_dto = engine.evaluate_pair(cand_empty, job_empty)

        assert 0.0 <= float(eval_dto.overall_score) <= 100.0
        assert 0.0 <= float(eval_dto.skills_score) <= 100.0
        assert 0.0 <= float(eval_dto.experience_score) <= 100.0
        assert 0.0 <= float(eval_dto.semantic_similarity) <= 1.0
        assert eval_dto.recommendation in ("strong_hire", "hire", "consider", "reject")
        assert isinstance(eval_dto.strengths_summary, str)
        assert isinstance(eval_dto.gaps_summary, str)
        assert isinstance(eval_dto.executive_summary, str)
        assert len(eval_dto.executive_summary) > 0

    def test_extreme_large_inputs_100k_characters(self, engine: MatchingEngine) -> None:
        """Verify performance and memory bounds when processing a 100,000 character CV."""
        repeated_block = (
            "Senior Software Architect experienced in Python, PostgreSQL, Docker, AWS, "
            "Kubernetes, and distributed data pipelines. Proven leadership and rigueur. "
        )
        huge_cv = (repeated_block * 1000)[:100000]

        cand_huge = {
            "candidate_id": "cand-huge-001",
            "full_name": "Maxime Grand",
            "raw_cv_text": huge_cv,
            "skills": [],
            "years_of_experience": 8,
            "education_level": "Master in Computer Science",
        }
        job_spec = {
            "job_id": "job-spec-001",
            "title": "Lead Cloud Engineer",
            "raw_description": "Seeking Lead Cloud Engineer with Python, Docker, and AWS.",
            "skills": [
                {"name": "Python", "importance": "required"},
                {"name": "Docker", "importance": "required"},
                {"name": "AWS", "importance": "preferred"},
            ],
            "experience_min_years": 5,
            "education_level_required": "Master in Computer Science",
        }

        t_start = time.perf_counter()
        eval_dto = engine.evaluate_pair(cand_huge, job_spec)
        t_elapsed = time.perf_counter() - t_start

        # Latency must remain within acceptable interactive threshold (< 3.0s)
        assert t_elapsed < 3.0, f"100k evaluation took {t_elapsed:.2f}s, expected < 3.0s"
        assert 0.0 <= float(eval_dto.overall_score) <= 100.0
        assert "Python" in eval_dto.matched_skills
        assert "Docker" in eval_dto.matched_skills
        assert "AWS" in eval_dto.matched_skills
        assert len(eval_dto.missing_skills) == 0
        assert eval_dto.recommendation in ("strong_hire", "hire")

    def test_zero_matching_skills_graceful_degradation(self, engine: MatchingEngine) -> None:
        """Verify candidate with zero overlapping skills is relegated to INSUFFISANT and reject."""
        cand_unrelated = {
            "candidate_id": "cand-unrelated-001",
            "full_name": "Arthur Pendelton",
            "raw_cv_text": "Experienced concert cellist and Latin literature teacher with sourdough baking mastery.",
            "skills": [{"name": "Violoncelle"}, {"name": "Latin"}],
            "years_of_experience": 15,
            "education_level": "Master of Classical Arts",
        }
        job_tech = {
            "job_id": "job-tech-001",
            "title": "Senior Kubernetes Administrator",
            "raw_description": "Production Kubernetes cluster deployment with Terraform and Linux.",
            "skills": [
                {"name": "Kubernetes", "importance": "required"},
                {"name": "Terraform", "importance": "required"},
                {"name": "Linux", "importance": "required"},
            ],
            "experience_min_years": 4,
            "education_level_required": "Master in Computer Science",
        }

        eval_dto = engine.evaluate_pair(cand_unrelated, job_tech)

        assert float(eval_dto.skills_score) <= 5.0
        assert len(eval_dto.matched_skills) == 0
        assert "Kubernetes" in eval_dto.missing_skills
        assert "Terraform" in eval_dto.missing_skills
        assert "Linux" in eval_dto.missing_skills
        assert float(eval_dto.overall_score) < 50.0
        assert eval_dto.recommendation == "reject"

    def test_identical_text_convergence(self, engine: MatchingEngine, semantic: SemanticMatcher) -> None:
        """Verify 100% identical document texts yield exact maximum similarity and bounded scores."""
        identical_text = (
            "Senior Backend Engineer with mastery of Python, SQL, PostgreSQL, Docker, and CI/CD pipelines. "
            "Excellente rigueur, esprit d'équipe, et autonomie reconnue."
        )
        sim = semantic.compute_similarity(identical_text, identical_text)
        assert sim == 1.0

        cand_id = {
            "candidate_id": "cand-ident-001",
            "full_name": "Claire Dupont",
            "raw_cv_text": identical_text,
            "skills": [
                {"name": "Python"},
                {"name": "SQL"},
                {"name": "PostgreSQL"},
                {"name": "Docker"},
                {"name": "CI/CD"},
                {"name": "Rigueur"},
                {"name": "Esprit d'équipe"},
                {"name": "Autonomie"},
            ],
            "years_of_experience": 6,
            "education_level": "Master in Computer Science",
        }
        job_id = {
            "job_id": "job-ident-001",
            "title": "Senior Backend Engineer",
            "raw_description": identical_text,
            "skills": [
                {"name": "Python", "importance": "required"},
                {"name": "SQL", "importance": "required"},
                {"name": "PostgreSQL", "importance": "required"},
                {"name": "Docker", "importance": "preferred"},
                {"name": "CI/CD", "importance": "preferred"},
            ],
            "experience_min_years": 4,
            "education_level_required": "Master in Computer Science",
        }

        eval_dto = engine.evaluate_pair(cand_id, job_id)
        assert 85.0 <= float(eval_dto.overall_score) <= 100.0
        assert eval_dto.recommendation == "strong_hire"

    def test_multilingual_foreign_character_resilience(self, engine: MatchingEngine) -> None:
        """Verify seamless processing of foreign Unicode scripts (Chinese, Arabic, Cyrillic, Greek, Japanese)."""
        multilingual_cv = (
            "Nous recherchons un développeur Python et Docker. "
            "我们正在寻找一位经验丰富的软件工程师 Python. "
            "مطور برمجيات متقدم مع بايثون و دوكر Docker. "
            "Разработчик Python с опытом работы в PostgreSQL. "
            "Μηχανικός λογισμικού Python. "
            "ソフトウェアエンジニア Python Docker."
        )
        cand_multi = {
            "candidate_id": "cand-multi-001",
            "full_name": "Li Wei / علي / Иван",
            "raw_cv_text": multilingual_cv,
            "skills": [{"name": "Python"}, {"name": "Docker"}, {"name": "PostgreSQL"}],
            "years_of_experience": 4,
            "education_level": "Diplôme d'ingénieur en génie logiciel",
        }
        job_multi = {
            "job_id": "job-multi-001",
            "title": "International Software Engineer",
            "raw_description": multilingual_cv,
            "skills": [
                {"name": "Python", "importance": "required"},
                {"name": "Docker", "importance": "required"},
            ],
            "experience_min_years": 3,
            "education_level_required": "Diplôme d'ingénieur",
        }

        eval_dto = engine.evaluate_pair(cand_multi, job_multi)
        assert 0.0 <= float(eval_dto.overall_score) <= 100.0
        assert "Python" in eval_dto.matched_skills
        assert "Docker" in eval_dto.matched_skills
        assert eval_dto.recommendation in ("strong_hire", "hire")

    def test_random_gibberish_noise_resilience(self, engine: MatchingEngine, extractor: SkillExtractor) -> None:
        """Verify noisy gibberish produces no ReDoS, bounded runtime, and appropriate rejection."""
        rng = random.Random(42)
        # Random word tokens that contain no valid taxonomy entries
        words = ["".join(rng.choices(string.ascii_lowercase, k=10)) for _ in range(500)]
        word_noise = " ".join(words)

        t0 = time.perf_counter()
        extracted = extractor.extract_from_text(word_noise)
        t1 = time.perf_counter()

        assert t1 - t0 < 1.0, f"Extraction from noise took {t1 - t0:.2f}s, potential ReDoS"
        assert len(extracted.all_keys) == 0

        # Dense character noise with punctuation
        dense_noise = "".join(rng.choices(string.ascii_letters + string.punctuation + string.digits, k=5000))
        cand_noise = {
            "candidate_id": "cand-noise-001",
            "raw_cv_text": dense_noise,
            "skills": [],
            "years_of_experience": 0,
            "education_level": dense_noise[:50],
        }
        job_target = {
            "job_id": "job-target-001",
            "title": "Data Analyst",
            "raw_description": "SQL and Python reporting with Power BI.",
            "skills": [{"name": "SQL", "importance": "required"}],
            "experience_min_years": 2,
            "education_level_required": "Licence",
        }
        eval_dto = engine.evaluate_pair(cand_noise, job_target)
        assert 0.0 <= float(eval_dto.overall_score) <= 30.0
        assert eval_dto.recommendation == "reject"

    def test_scoring_bounds_fuzzing(self, scorer: MatchingScorer) -> None:
        """Fuzz scoring logic over 500 permutations of edge values to guarantee mathematical invariance."""
        rng = random.Random(1337)
        exp_candidates = [-100.0, -1.0, 0.0, 0.5, 3.0, 10.0, 50.0, 1000.0]
        exp_jobs = [-50.0, 0.0, 1.0, 5.0, 15.0, 999.0]
        degrees = [None, "", "Bac", "BTS SIO", "Licence Informatique", "Master Data", "Doctorat IA", "Unknown Degree XYZ"]

        for _ in range(500):
            cand_exp = rng.choice(exp_candidates)
            job_exp = rng.choice(exp_jobs)
            c_deg = rng.choice(degrees)
            j_deg = rng.choice(degrees)

            exp_s = scorer.compute_experience_score(cand_exp, job_exp)
            assert 0.0 <= exp_s <= 100.0, f"Experience score out of bounds: {exp_s}"

            edu_s, c_lvl, j_lvl = scorer.compute_education_score(c_deg, j_deg)
            assert 0.0 <= edu_s <= 100.0, f"Education score out of bounds: {edu_s}"
            assert 1 <= c_lvl <= 8
            assert 1 <= j_lvl <= 8

    def test_tier_classification_exact_thresholds(self, scorer: MatchingScorer) -> None:
        """Verify strict classification tier transitions and boundary cutoffs."""
        # EXCELLENT: [85.0, 100.0]
        assert scorer.classify_tier_and_recommendation(100.0) == ("EXCELLENT", "strong_hire")
        assert scorer.classify_tier_and_recommendation(85.0001) == ("EXCELLENT", "strong_hire")
        assert scorer.classify_tier_and_recommendation(85.0) == ("EXCELLENT", "strong_hire")

        # BON: [70.0, 85.0)
        assert scorer.classify_tier_and_recommendation(84.9999) == ("BON", "hire")
        assert scorer.classify_tier_and_recommendation(84.9) == ("BON", "hire")
        assert scorer.classify_tier_and_recommendation(70.0001) == ("BON", "hire")
        assert scorer.classify_tier_and_recommendation(70.0) == ("BON", "hire")

        # PARTIEL: [50.0, 70.0)
        assert scorer.classify_tier_and_recommendation(69.9999) == ("PARTIEL", "consider")
        assert scorer.classify_tier_and_recommendation(69.9) == ("PARTIEL", "consider")
        assert scorer.classify_tier_and_recommendation(50.0001) == ("PARTIEL", "consider")
        assert scorer.classify_tier_and_recommendation(50.0) == ("PARTIEL", "consider")

        # INSUFFISANT: [0.0, 50.0)
        assert scorer.classify_tier_and_recommendation(49.9999) == ("INSUFFISANT", "reject")
        assert scorer.classify_tier_and_recommendation(49.9) == ("INSUFFISANT", "reject")
        assert scorer.classify_tier_and_recommendation(0.0) == ("INSUFFISANT", "reject")

    def test_tricky_token_c_cpp_csharp(self, extractor: SkillExtractor, scorer: MatchingScorer) -> None:
        """Verify disambiguation between C, C++, and C# without cross-contamination."""
        # 1. C++ in text must extract 'cpp' and NOT 'csharp'
        res_cpp = extractor.extract_from_text("Deep expertise in modern C++ and STL algorithms.")
        assert "cpp" in res_cpp.hard_skill_keys
        assert "csharp" not in res_cpp.hard_skill_keys

        # 2. C# in text must extract 'csharp' and NOT 'cpp'
        res_csharp = extractor.extract_from_text("Developing enterprise services using C# and .NET.")
        assert "csharp" in res_csharp.hard_skill_keys
        assert "cpp" not in res_csharp.hard_skill_keys

        # 3. Both in text
        res_both = extractor.extract_from_text("Porting codebase from C++ to C#.")
        assert "cpp" in res_both.hard_skill_keys
        assert "csharp" in res_both.hard_skill_keys

        # 4. Declared skill 'C' does not match job requiring 'C++' or 'C#'
        cand_c = {"skills": [{"name": "C"}], "years_of_experience": 5, "education_level": "Master"}
        job_cpp = {"skills": [{"name": "C++", "importance": "required"}], "experience_min_years": 3}
        job_csharp = {"skills": [{"name": "C#", "importance": "required"}], "experience_min_years": 3}

        score_cpp = scorer.score(cand_c, job_cpp)
        assert "cpp" not in score_cpp.matched_required_skills
        assert "cpp" in score_cpp.missing_required_skills

        score_csharp = scorer.score(cand_c, job_csharp)
        assert "csharp" not in score_csharp.matched_required_skills
        assert "csharp" in score_csharp.missing_required_skills

    def test_tricky_token_dotnet_variations(self, extractor: SkillExtractor, scorer: MatchingScorer) -> None:
        """Verify .NET variations and aliasing resolution."""
        # .NET in text
        res_dotnet = extractor.extract_from_text("Building cloud microservices with .NET and C#.")
        assert "dotnet" in res_dotnet.hard_skill_keys

        # dotnet in text
        res_raw_dotnet = extractor.extract_from_text("Modern dotnet core architecture.")
        assert "dotnet" in res_raw_dotnet.hard_skill_keys

        # Declared skill 'dot net' resolves to canonical 'dotnet' via lookup
        canonical = lookup_canonical_skill("dot net")
        assert canonical is not None
        assert canonical.key == "dotnet"

        # Declared 'dot net' matches job requiring '.NET'
        cand_dotnet = {"skills": [{"name": "dot net"}], "years_of_experience": 4, "education_level": "Master"}
        job_dotnet = {"skills": [{"name": ".NET", "importance": "required"}], "experience_min_years": 3}
        res_match = scorer.score(cand_dotnet, job_dotnet)
        assert "dotnet" in res_match.matched_required_skills
        assert len(res_match.missing_required_skills) == 0

    def test_tricky_token_java_vs_javascript(self, extractor: SkillExtractor) -> None:
        """Verify JavaScript does not trigger false positive Java extraction and vice versa."""
        # JavaScript text only
        res_js = extractor.extract_from_text("Front-end engineer specialized in JavaScript and React.")
        assert "javascript" in res_js.hard_skill_keys
        assert "java" not in res_js.hard_skill_keys

        # Java text only
        res_java = extractor.extract_from_text("Backend engineer specialized in Java and Spring Boot.")
        assert "java" in res_java.hard_skill_keys
        assert "javascript" not in res_java.hard_skill_keys

        # Both present
        res_both = extractor.extract_from_text("Full-stack engineer proficient in Java and JavaScript.")
        assert "java" in res_both.hard_skill_keys
        assert "javascript" in res_both.hard_skill_keys

    def test_tricky_token_single_letter_r_isolation(self, extractor: SkillExtractor) -> None:
        """Verify single letter R is extracted when isolated but not from words like Docker or Spark."""
        # Words containing 'r'
        res_words = extractor.extract_from_text("Deploying Docker containers, Apache Spark jobs, and Redis caches.")
        assert "r" not in res_words.hard_skill_keys
        assert "docker" in res_words.hard_skill_keys
        assert "apache_spark" in res_words.hard_skill_keys
        assert "redis" in res_words.hard_skill_keys

        # Isolated R language with statistics
        res_r = extractor.extract_from_text("Data scientist using R and Python for statistical analysis.")
        assert "r" in res_r.hard_skill_keys
        assert "python" in res_r.hard_skill_keys
        assert "statistics" in res_r.hard_skill_keys

    def test_text_cleanliness_in_synthesis(self, engine: MatchingEngine) -> None:
        """Verify that synthesis texts handle accents without corrupting character encodings."""
        cand_weird = {
            "candidate_id": "cand-weird-001",
            "full_name": "Zoé L'Étrange",
            "raw_cv_text": "Développeur C++ et SQL en reconversion.",
            "skills": [{"name": "C++"}],
            "years_of_experience": 1,
            "education_level": "Bac+2",
        }
        job_spec = {
            "job_id": "job-spec-002",
            "title": "Data Architect",
            "raw_description": "Data Architect with Python and AWS.",
            "skills": [{"name": "Python", "importance": "required"}],
            "experience_min_years": 8,
            "education_level_required": "Bac+5",
        }

        eval_dto = engine.evaluate_pair(cand_weird, job_spec)
        combined_text = " ".join([
            eval_dto.strengths_summary,
            eval_dto.gaps_summary,
            eval_dto.executive_summary,
        ])

        # Verify zero emojis
        for char in combined_text:
            cp = ord(char)
            assert not (0x1F600 <= cp <= 0x1F64F or 0x1F300 <= cp <= 0x1F5FF or 0x1F900 <= cp <= 0x1F9FF), (
                f"Prohibited emoji detected: {char} (U+{cp:X})"
            )
