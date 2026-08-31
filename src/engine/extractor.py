"""Boundary-aware and symbol-aware skill extraction engine for resumes and job postings."""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Union

from src.engine.taxonomies import (
    SkillTaxonomyItem,
    _strip_accents,
    get_all_taxonomy_items,
    get_taxonomy_registry,
    lookup_canonical_skill,
)
from src.etl.transformers import normalize_skill_key


@dataclass
class ExtractedSkill:
    """Descriptor for an extracted skill with provenance metadata."""

    key: str
    name: str
    category: str
    subcategory: str
    source: str  # 'declared', 'text', or 'both'
    matched_alias: str


@dataclass
class ExtractedSkills:
    """Container holding partitioned technical and behavioral extracted skills."""

    hard_skills: Dict[str, ExtractedSkill] = field(default_factory=dict)
    soft_skills: Dict[str, ExtractedSkill] = field(default_factory=dict)

    @property
    def all_keys(self) -> Set[str]:
        """Return combined set of canonical skill keys."""
        return set(self.hard_skills.keys()) | set(self.soft_skills.keys())

    @property
    def hard_skill_keys(self) -> Set[str]:
        """Return set of canonical hard skill keys."""
        return set(self.hard_skills.keys())

    @property
    def soft_skill_keys(self) -> Set[str]:
        """Return set of canonical soft skill keys."""
        return set(self.soft_skills.keys())

    @property
    def hard_skill_names(self) -> List[str]:
        """Return sorted list of canonical hard skill display names."""
        return sorted([s.name for s in self.hard_skills.values()])

    @property
    def soft_skill_names(self) -> List[str]:
        """Return sorted list of canonical soft skill display names."""
        return sorted([s.name for s in self.soft_skills.values()])


@dataclass
class JobSkillProfile:
    """Categorized skill requirements extracted from a job posting."""

    required_hard_keys: Set[str] = field(default_factory=set)
    preferred_hard_keys: Set[str] = field(default_factory=set)
    target_soft_keys: Set[str] = field(default_factory=set)
    required_hard_names: List[str] = field(default_factory=list)
    preferred_hard_names: List[str] = field(default_factory=list)
    target_soft_names: List[str] = field(default_factory=list)
    all_extracted: ExtractedSkills = field(default_factory=ExtractedSkills)


class SkillExtractor:
    """Extracts hard and soft skills from structured fields and raw text."""

    def __init__(self) -> None:
        """Compile boundary-aware regex patterns from taxonomy items."""
        self.taxonomy = get_taxonomy_registry()
        self._compiled_patterns: List[tuple[re.Pattern, str, SkillTaxonomyItem]] = []
        self._build_pattern_index()

    def _build_pattern_index(self) -> None:
        """Compile regex patterns ordered by term length descending to prioritize multi-word n-grams."""
        alias_entries: List[tuple[str, SkillTaxonomyItem]] = []
        for item in get_all_taxonomy_items():
            # Include canonical key and display name
            alias_entries.append((_strip_accents(item.key), item))
            alias_entries.append((_strip_accents(item.name), item))
            for alias in item.aliases:
                alias_entries.append((_strip_accents(alias), item))

        # Deduplicate and sort longest first to prevent shadow matching
        seen_aliases: Set[str] = set()
        sorted_entries: List[tuple[str, SkillTaxonomyItem]] = []
        for term, item in sorted(alias_entries, key=lambda x: len(x[0]), reverse=True):
            if term and term not in seen_aliases:
                seen_aliases.add(term)
                sorted_entries.append((term, item))

        for term, item in sorted_entries:
            escaped_term = re.escape(term)
            # Boundary-aware pattern supporting symbols like C++, C#, .NET, CI/CD, Node.js
            pattern_str = (
                rf'(?:(?<=[\s,;:()\[\]/\-])|(?<=^))'
                rf'{escaped_term}'
                rf'(?:(?=[\s,;:()\[\]/.\-])|(?=$))'
            )
            compiled = re.compile(pattern_str, re.IGNORECASE)
            self._compiled_patterns.append((compiled, term, item))

    def extract_from_text(self, text: Optional[str]) -> ExtractedSkills:
        """Extract canonical skills present in raw text.

        Args:
            text: Resume summary, job description, or experience description.

        Returns:
            ExtractedSkills instance with identified skills.
        """
        result = ExtractedSkills()
        if not text or not text.strip():
            return result

        normalized_text = _strip_accents(text)

        for pattern, alias, item in self._compiled_patterns:
            if pattern.search(normalized_text):
                extracted = ExtractedSkill(
                    key=item.key,
                    name=item.name,
                    category=item.category,
                    subcategory=item.subcategory,
                    source="text",
                    matched_alias=alias,
                )
                if item.category == "hard_skill":
                    if item.key not in result.hard_skills:
                        result.hard_skills[item.key] = extracted
                else:
                    if item.key not in result.soft_skills:
                        result.soft_skills[item.key] = extracted

        return result

    def extract_from_declared_skills(
        self,
        declared_skills: Iterable[Union[str, Dict[str, Any], Any]],
    ) -> ExtractedSkills:
        """Map a collection of declared skill descriptors into canonical taxonomy skills.

        Args:
            declared_skills: List of skill names, dictionaries, or ORM/DTO objects.

        Returns:
            ExtractedSkills populated with declared items.
        """
        result = ExtractedSkills()
        for skill_item in declared_skills:
            name: str = ""
            category_hint: Optional[str] = None

            if isinstance(skill_item, str):
                name = skill_item
            elif isinstance(skill_item, dict):
                name = str(skill_item.get("name", ""))
                category_hint = skill_item.get("category")
            elif hasattr(skill_item, "name"):
                name = str(getattr(skill_item, "name", ""))
                category_hint = getattr(skill_item, "category", None)
            elif hasattr(skill_item, "skill") and hasattr(skill_item.skill, "name"):
                name = str(skill_item.skill.name)
                category_hint = getattr(skill_item.skill, "category", None)

            if not name.strip():
                continue

            taxonomy_match = lookup_canonical_skill(name)
            if taxonomy_match:
                extracted = ExtractedSkill(
                    key=taxonomy_match.key,
                    name=taxonomy_match.name,
                    category=taxonomy_match.category,
                    subcategory=taxonomy_match.subcategory,
                    source="declared",
                    matched_alias=name.strip(),
                )
                if taxonomy_match.category == "hard_skill":
                    result.hard_skills[taxonomy_match.key] = extracted
                else:
                    result.soft_skills[taxonomy_match.key] = extracted
            else:
                # Uncatalogued declared skill fallback using normalized key
                norm_key = normalize_skill_key(name)
                is_soft = category_hint in ("soft_skill", "behavioral", "methodology")
                cat = "soft_skill" if is_soft else "hard_skill"
                extracted = ExtractedSkill(
                    key=norm_key,
                    name=name.strip(),
                    category=cat,
                    subcategory="uncatalogued",
                    source="declared",
                    matched_alias=name.strip(),
                )
                if cat == "hard_skill":
                    result.hard_skills[norm_key] = extracted
                else:
                    result.soft_skills[norm_key] = extracted

        return result

    def extract_candidate_skills(self, candidate: Any) -> ExtractedSkills:
        """Extract and merge all skills from candidate profile text and structured associations.

        Args:
            candidate: Candidate entity, CandidateProfileDTO, or raw dictionary.

        Returns:
            Unified ExtractedSkills representing candidate capabilities.
        """
        raw_text = ""
        declared: List[Any] = []

        if isinstance(candidate, dict):
            raw_text = candidate.get("raw_cv_text", "")
            declared = candidate.get("skills", [])
            # Append experience descriptions if present
            for exp in candidate.get("experiences", []):
                if isinstance(exp, dict):
                    raw_text += " " + str(exp.get("description", ""))
                    raw_text += " " + str(exp.get("technologies", ""))
        else:
            raw_text = getattr(candidate, "raw_cv_text", "") or ""
            declared = getattr(candidate, "skills", []) or []
            experiences = getattr(candidate, "experiences", []) or []
            for exp in experiences:
                desc = getattr(exp, "description", "") or ""
                tech = getattr(exp, "technologies", "") or ""
                raw_text += f" {desc} {tech}"

        from_text = self.extract_from_text(raw_text)
        from_declared = self.extract_from_declared_skills(declared)

        # Merge hard skills
        merged_hard: Dict[str, ExtractedSkill] = dict(from_declared.hard_skills)
        for key, sk in from_text.hard_skills.items():
            if key in merged_hard:
                merged_hard[key] = ExtractedSkill(
                    key=sk.key,
                    name=merged_hard[key].name,
                    category=sk.category,
                    subcategory=sk.subcategory,
                    source="both",
                    matched_alias=sk.matched_alias,
                )
            else:
                merged_hard[key] = sk

        # Merge soft skills
        merged_soft: Dict[str, ExtractedSkill] = dict(from_declared.soft_skills)
        for key, sk in from_text.soft_skills.items():
            if key in merged_soft:
                merged_soft[key] = ExtractedSkill(
                    key=sk.key,
                    name=merged_soft[key].name,
                    category=sk.category,
                    subcategory=sk.subcategory,
                    source="both",
                    matched_alias=sk.matched_alias,
                )
            else:
                merged_soft[key] = sk

        return ExtractedSkills(hard_skills=merged_hard, soft_skills=merged_soft)

    def extract_job_skills(self, job: Any) -> JobSkillProfile:
        """Extract and categorize required and preferred skills from a job posting.

        Args:
            job: JobDescription entity, JobPostingDTO, or raw dictionary.

        Returns:
            JobSkillProfile detailing required vs preferred hard skills and soft skills.
        """
        raw_text = ""
        declared_skills: List[Any] = []

        if isinstance(job, dict):
            raw_text = job.get("raw_description", "") or job.get("job_description_text", "")
            declared_skills = job.get("skills", [])
        else:
            raw_text = getattr(job, "raw_description", "") or getattr(job, "job_description_text", "")
            declared_skills = getattr(job, "skills", []) or []

        text_skills = self.extract_from_text(raw_text)

        required_hard_keys: Set[str] = set()
        preferred_hard_keys: Set[str] = set()
        target_soft_keys: Set[str] = set()

        required_hard_names: List[str] = []
        preferred_hard_names: List[str] = []
        target_soft_names: List[str] = []

        # Process declared skills with importance levels
        for sk_item in declared_skills:
            name: str = ""
            importance: str = "required"
            cat_hint: Optional[str] = None

            if isinstance(sk_item, dict):
                name = str(sk_item.get("name", ""))
                importance = str(sk_item.get("importance", "required")).lower()
                cat_hint = sk_item.get("category")
            elif hasattr(sk_item, "name"):
                name = str(getattr(sk_item, "name", ""))
                importance = str(getattr(sk_item, "importance", "required")).lower()
                cat_hint = getattr(sk_item, "category", None)
            elif hasattr(sk_item, "skill") and hasattr(sk_item.skill, "name"):
                name = str(sk_item.skill.name)
                importance = str(getattr(sk_item, "importance", "required")).lower()
                cat_hint = getattr(sk_item.skill, "category", None)

            if not name.strip():
                continue

            taxonomy_match = lookup_canonical_skill(name)
            key = taxonomy_match.key if taxonomy_match else normalize_skill_key(name)
            display_name = taxonomy_match.name if taxonomy_match else name.strip()
            is_soft = (
                (taxonomy_match and taxonomy_match.category == "soft_skill")
                or cat_hint in ("soft_skill", "behavioral")
            )

            if is_soft:
                target_soft_keys.add(key)
                if display_name not in target_soft_names:
                    target_soft_names.append(display_name)
            elif importance == "preferred" or importance == "nice_to_have":
                preferred_hard_keys.add(key)
                if display_name not in preferred_hard_names:
                    preferred_hard_names.append(display_name)
            else:
                required_hard_keys.add(key)
                if display_name not in required_hard_names:
                    required_hard_names.append(display_name)

        # Merge soft skills extracted from job text description into target soft skills
        for key, sk in text_skills.soft_skills.items():
            target_soft_keys.add(key)
            if sk.name not in target_soft_names:
                target_soft_names.append(sk.name)

        # Merge hard skills from text if not already declared: default to preferred
        for key, sk in text_skills.hard_skills.items():
            if key not in required_hard_keys and key not in preferred_hard_keys:
                preferred_hard_keys.add(key)
                if sk.name not in preferred_hard_names:
                    preferred_hard_names.append(sk.name)

        # Build merged ExtractedSkills
        merged_extracted = self.extract_candidate_skills(job)

        return JobSkillProfile(
            required_hard_keys=required_hard_keys,
            preferred_hard_keys=preferred_hard_keys,
            target_soft_keys=target_soft_keys,
            required_hard_names=required_hard_names,
            preferred_hard_names=preferred_hard_names,
            target_soft_names=target_soft_names,
            all_extracted=merged_extracted,
        )
