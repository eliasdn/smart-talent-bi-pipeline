"""Semantic AI matching engine package for skill extraction, scoring, and qualitative synthesis."""

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
from src.engine.semantic import SemanticMatcher
from src.engine.service import MatchingEngine
from src.engine.synthesizer import EvaluationSynthesis, MatchingSynthesizer
from src.engine.taxonomies import (
    SkillTaxonomyItem,
    get_all_taxonomy_items,
    get_hard_skills,
    get_soft_skills,
    get_taxonomy_registry,
    lookup_canonical_skill,
)

__all__ = [
    "SkillTaxonomyItem",
    "get_all_taxonomy_items",
    "get_taxonomy_registry",
    "get_hard_skills",
    "get_soft_skills",
    "lookup_canonical_skill",
    "ExtractedSkill",
    "ExtractedSkills",
    "JobSkillProfile",
    "SkillExtractor",
    "SemanticMatcher",
    "MatchingScorer",
    "ScoreBreakdown",
    "parse_degree_level",
    "compute_domain_relevance",
    "MatchingSynthesizer",
    "EvaluationSynthesis",
    "MatchingEngine",
]
