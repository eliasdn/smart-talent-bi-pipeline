"""Offline semantic matching engine utilizing TF-IDF vectorization and cosine similarity."""

from typing import Any, List, Optional
import unicodedata

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.engine.taxonomies import _strip_accents

# Curated bilingual stopwords (French and English functional terms)
BILINGUAL_STOPWORDS: List[str] = [
    # French stopwords
    "a", "ai", "aie", "aient", "aies", "ait", "alors", "as", "au", "aucun", "aura",
    "aurai", "auraient", "aurais", "aurait", "auras", "aurez", "auriez", "aurions",
    "aurons", "auront", "aussi", "autre", "aux", "avaient", "avais", "avait", "avec",
    "avez", "aviez", "avions", "avoir", "avons", "ayant", "ayez", "ayons", "c", "ce",
    "ceci", "cela", "celui", "ces", "cet", "cette", "chez", "ci", "comme", "comment",
    "d", "dans", "de", "des", "du", "elle", "elles", "en", "es", "est", "et", "étaient",
    "étais", "était", "étant", "été", "êtes", "étiez", "étions", "être", "eu", "eue",
    "eues", "eurent", "eus", "eusse", "eussent", "eusses", "eussiez", "eussions", "eut",
    "eux", "furent", "fus", "fusse", "fussent", "fusses", "fussiez", "fussions", "fut",
    "ici", "il", "ils", "j", "je", "l", "la", "le", "les", "leur", "leurs", "lui",
    "m", "ma", "mais", "me", "même", "mes", "moi", "mon", "n", "ne", "nos", "notre",
    "nous", "on", "ont", "ou", "par", "pas", "pour", "qu", "que", "quel", "quelle",
    "quelles", "quels", "qui", "s", "sa", "sans", "se", "sera", "serai", "seraient",
    "serais", "serait", "seras", "serez", "seriez", "serions", "serons", "seront", "ses",
    "si", "soient", "sois", "soit", "sommes", "son", "sont", "soyez", "soyons", "suis",
    "sur", "t", "ta", "te", "tes", "toi", "ton", "tous", "tout", "toute", "toutes",
    "tu", "un", "une", "vos", "votre", "vous", "y",
    # English stopwords
    "about", "above", "after", "again", "against", "all", "am", "an", "and", "any",
    "are", "aren", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "cannot", "could", "couldn", "did", "didn",
    "do", "does", "doesn", "doing", "don", "down", "during", "each", "few", "for",
    "from", "further", "had", "hadn", "has", "hasn", "have", "haven", "having", "he",
    "her", "here", "hers", "herself", "him", "himself", "his", "how", "if", "in",
    "into", "is", "isn", "it", "its", "itself", "let", "me", "more", "most", "mustn",
    "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan",
    "she", "should", "shouldn", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they", "this", "those",
    "through", "to", "too", "under", "until", "up", "very", "was", "wasn", "we",
    "were", "weren", "what", "when", "where", "which", "while", "who", "whom", "why",
    "with", "won", "would", "wouldn", "you", "your", "yours", "yourself", "yourselves",
]

# Pre-strip accents from stopwords for consistent matching
_NORMALIZED_STOPWORDS: List[str] = list(
    set(_strip_accents(w) for w in BILINGUAL_STOPWORDS if len(_strip_accents(w)) > 1)
)


class SemanticMatcher:
    """Computes deterministic TF-IDF cosine similarity between profile and role texts."""

    def __init__(self, stop_words: Optional[List[str]] = None) -> None:
        """Initialize semantic matcher with stopwords configuration.

        Args:
            stop_words: Optional custom list of stop words. Defaults to bilingual list.
        """
        self.stop_words = stop_words if stop_words is not None else _NORMALIZED_STOPWORDS

    def _normalize_corpus_text(self, text: str) -> str:
        """Cleanse and normalize text for vectorization."""
        if not text:
            return ""
        return _strip_accents(text)

    def compute_similarity(self, text_a: str, text_b: str) -> float:
        """Calculate cosine similarity between two text passages.

        Args:
            text_a: First text document (e.g. candidate CV profile).
            text_b: Second text document (e.g. job description specification).

        Returns:
            Cosine similarity score strictly bounded within [0.0, 1.0].
        """
        norm_a = self._normalize_corpus_text(text_a)
        norm_b = self._normalize_corpus_text(text_b)

        if not norm_a.strip() or not norm_b.strip():
            return 0.0

        if norm_a.strip() == norm_b.strip():
            return 1.0

        try:
            vectorizer = TfidfVectorizer(
                ngram_range=(1, 2),
                sublinear_tf=True,
                stop_words=self.stop_words,
            )
            tfidf_matrix = vectorizer.fit_transform([norm_a, norm_b])
            similarity = float(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0])
            clamped = max(0.0, min(1.0, similarity))
            return round(clamped, 4)
        except (ValueError, ZeroDivisionError):
            # Handles cases where documents contain only stopwords or produce empty vocabulary
            return 0.0

    def extract_rich_candidate_text(self, candidate: Any) -> str:
        """Assemble a composite textual representation of a candidate profile.

        Args:
            candidate: Candidate entity, CandidateProfileDTO, or raw dictionary.

        Returns:
            Concatenated string including title, education, experiences, and skills.
        """
        parts: List[str] = []

        if isinstance(candidate, dict):
            if candidate.get("current_title"):
                parts.append(str(candidate["current_title"]))
            if candidate.get("education_level"):
                parts.append(str(candidate["education_level"]))
            if candidate.get("raw_cv_text"):
                parts.append(str(candidate["raw_cv_text"]))
            for exp in candidate.get("experiences", []):
                if isinstance(exp, dict):
                    if exp.get("role_title"):
                        parts.append(str(exp["role_title"]))
                    if exp.get("description"):
                        parts.append(str(exp["description"]))
                    if exp.get("technologies"):
                        parts.append(str(exp["technologies"]))
            for sk in candidate.get("skills", []):
                if isinstance(sk, dict) and sk.get("name"):
                    parts.append(str(sk["name"]))
        else:
            title = getattr(candidate, "current_title", None)
            if title:
                parts.append(str(title))
            edu = getattr(candidate, "education_level", None)
            if edu:
                parts.append(str(edu))
            cv = getattr(candidate, "raw_cv_text", None)
            if cv:
                parts.append(str(cv))
            for exp in getattr(candidate, "experiences", []) or []:
                role = getattr(exp, "role_title", None)
                if role:
                    parts.append(str(role))
                desc = getattr(exp, "description", None)
                if desc:
                    parts.append(str(desc))
                tech = getattr(exp, "technologies", None)
                if tech:
                    parts.append(str(tech))
            for sk in getattr(candidate, "skills", []) or []:
                sk_name = getattr(sk, "name", None)
                if not sk_name and hasattr(sk, "skill"):
                    sk_name = getattr(sk.skill, "name", None)
                if sk_name:
                    parts.append(str(sk_name))

        return " ".join(parts)

    def extract_rich_job_text(self, job: Any) -> str:
        """Assemble a composite textual representation of a job posting.

        Args:
            job: JobDescription entity, JobPostingDTO, or raw dictionary.

        Returns:
            Concatenated string including title, department, description, and requirements.
        """
        parts: List[str] = []

        if isinstance(job, dict):
            if job.get("title"):
                parts.append(str(job["title"]))
            if job.get("department"):
                parts.append(str(job["department"]))
            if job.get("education_level_required"):
                parts.append(str(job["education_level_required"]))
            raw_desc = job.get("raw_description", "") or job.get("job_description_text", "")
            if raw_desc:
                parts.append(str(raw_desc))
            for sk in job.get("skills", []):
                if isinstance(sk, dict) and sk.get("name"):
                    parts.append(str(sk["name"]))
        else:
            title = getattr(job, "title", None)
            if title:
                parts.append(str(title))
            dept = getattr(job, "department", None)
            if dept:
                parts.append(str(dept))
            edu = getattr(job, "education_level_required", None)
            if edu:
                parts.append(str(edu))
            desc = getattr(job, "raw_description", None) or getattr(job, "job_description_text", None)
            if desc:
                parts.append(str(desc))
            for sk in getattr(job, "skills", []) or []:
                sk_name = getattr(sk, "name", None)
                if not sk_name and hasattr(sk, "skill"):
                    sk_name = getattr(sk.skill, "name", None)
                if sk_name:
                    parts.append(str(sk_name))

        return " ".join(parts)

    def compare_candidate_and_job(self, candidate: Any, job: Any) -> float:
        """Compute semantic similarity directly between candidate profile and job posting objects.

        Args:
            candidate: Candidate profile representation.
            job: Job vacancy representation.

        Returns:
            Cosine similarity score bounded between 0.0 and 1.0.
        """
        cand_text = self.extract_rich_candidate_text(candidate)
        job_text = self.extract_rich_job_text(job)
        return self.compute_similarity(cand_text, job_text)
