"""Bilingual taxonomy of technical and behavioral skills for talent matching."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import unicodedata


def _strip_accents(text: str) -> str:
    """Normalize text by removing diacritics and converting to lowercase."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower().strip()


@dataclass(frozen=True)
class SkillTaxonomyItem:
    """Descriptor for a canonical skill in the talent taxonomy."""

    key: str
    name: str
    category: str  # 'hard_skill' or 'soft_skill'
    subcategory: str
    aliases: List[str] = field(default_factory=list)


# Curated catalog of technical hard skills
_HARD_SKILLS: List[SkillTaxonomyItem] = [
    # Programming Languages
    SkillTaxonomyItem(
        key="python",
        name="Python",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["python", "python3", "py", "pyspark"],
    ),
    SkillTaxonomyItem(
        key="sql",
        name="SQL",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["sql", "t-sql", "tsql"],
    ),
    SkillTaxonomyItem(
        key="cpp",
        name="C++",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["c++", "cpp"],
    ),
    SkillTaxonomyItem(
        key="csharp",
        name="C#",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["c#", "csharp", "c sharp"],
    ),
    SkillTaxonomyItem(
        key="java",
        name="Java",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["java", "java8", "java11", "java17"],
    ),
    SkillTaxonomyItem(
        key="javascript",
        name="JavaScript",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["javascript", "js", "ecmascript"],
    ),
    SkillTaxonomyItem(
        key="typescript",
        name="TypeScript",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["typescript", "ts"],
    ),
    SkillTaxonomyItem(
        key="golang",
        name="Go",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["golang", "go"],
    ),
    SkillTaxonomyItem(
        key="rust",
        name="Rust",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["rust", "rustlang"],
    ),
    SkillTaxonomyItem(
        key="r",
        name="R",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["r", "rlang", "r-lang"],
    ),
    SkillTaxonomyItem(
        key="scala",
        name="Scala",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["scala"],
    ),
    SkillTaxonomyItem(
        key="php",
        name="PHP",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["php", "php7", "php8"],
    ),
    SkillTaxonomyItem(
        key="ruby",
        name="Ruby",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["ruby", "ruby on rails", "rails"],
    ),
    SkillTaxonomyItem(
        key="bash",
        name="Bash",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["bash", "shell", "powershell", "sh"],
    ),
    SkillTaxonomyItem(
        key="html_css",
        name="HTML/CSS",
        category="hard_skill",
        subcategory="programming_languages",
        aliases=["html", "css", "html5", "css3", "html/css"],
    ),

    # Frameworks and Web
    SkillTaxonomyItem(
        key="react",
        name="React",
        category="hard_skill",
        subcategory="frameworks",
        aliases=["react", "reactjs", "react.js", "react native"],
    ),
    SkillTaxonomyItem(
        key="angular",
        name="Angular",
        category="hard_skill",
        subcategory="frameworks",
        aliases=["angular", "angularjs", "angular.js"],
    ),
    SkillTaxonomyItem(
        key="vue_js",
        name="Vue.js",
        category="hard_skill",
        subcategory="frameworks",
        aliases=["vue", "vuejs", "vue.js"],
    ),
    SkillTaxonomyItem(
        key="node_js",
        name="Node.js",
        category="hard_skill",
        subcategory="frameworks",
        aliases=["node.js", "nodejs", "node"],
    ),
    SkillTaxonomyItem(
        key="django",
        name="Django",
        category="hard_skill",
        subcategory="frameworks",
        aliases=["django", "django rest framework", "drf"],
    ),
    SkillTaxonomyItem(
        key="fastapi",
        name="FastAPI",
        category="hard_skill",
        subcategory="frameworks",
        aliases=["fastapi", "fast-api"],
    ),
    SkillTaxonomyItem(
        key="flask",
        name="Flask",
        category="hard_skill",
        subcategory="frameworks",
        aliases=["flask"],
    ),
    SkillTaxonomyItem(
        key="spring_boot",
        name="Spring Boot",
        category="hard_skill",
        subcategory="frameworks",
        aliases=["spring boot", "spring-boot", "spring framework", "spring"],
    ),
    SkillTaxonomyItem(
        key="dotnet",
        name=".NET",
        category="hard_skill",
        subcategory="frameworks",
        aliases=[".net", "dotnet", ".net core", "asp.net"],
    ),
    SkillTaxonomyItem(
        key="next_js",
        name="Next.js",
        category="hard_skill",
        subcategory="frameworks",
        aliases=["next.js", "nextjs", "next"],
    ),

    # Databases and Data Engineering
    SkillTaxonomyItem(
        key="postgresql",
        name="PostgreSQL",
        category="hard_skill",
        subcategory="databases",
        aliases=["postgresql", "postgres", "pgsql"],
    ),
    SkillTaxonomyItem(
        key="mysql",
        name="MySQL",
        category="hard_skill",
        subcategory="databases",
        aliases=["mysql", "mariadb"],
    ),
    SkillTaxonomyItem(
        key="sqlite",
        name="SQLite",
        category="hard_skill",
        subcategory="databases",
        aliases=["sqlite", "sqlite3"],
    ),
    SkillTaxonomyItem(
        key="mongodb",
        name="MongoDB",
        category="hard_skill",
        subcategory="databases",
        aliases=["mongodb", "mongo"],
    ),
    SkillTaxonomyItem(
        key="redis",
        name="Redis",
        category="hard_skill",
        subcategory="databases",
        aliases=["redis"],
    ),
    SkillTaxonomyItem(
        key="elasticsearch",
        name="Elasticsearch",
        category="hard_skill",
        subcategory="databases",
        aliases=["elasticsearch", "elastic search", "opensearch"],
    ),
    SkillTaxonomyItem(
        key="oracle",
        name="Oracle",
        category="hard_skill",
        subcategory="databases",
        aliases=["oracle", "pl/sql", "plsql"],
    ),
    SkillTaxonomyItem(
        key="apache_spark",
        name="Apache Spark",
        category="hard_skill",
        subcategory="data_engineering",
        aliases=["apache spark", "spark", "pyspark", "spark sql", "spark streaming"],
    ),
    SkillTaxonomyItem(
        key="apache_kafka",
        name="Apache Kafka",
        category="hard_skill",
        subcategory="data_engineering",
        aliases=["apache kafka", "kafka"],
    ),
    SkillTaxonomyItem(
        key="apache_airflow",
        name="Apache Airflow",
        category="hard_skill",
        subcategory="data_engineering",
        aliases=["apache airflow", "airflow"],
    ),
    SkillTaxonomyItem(
        key="snowflake",
        name="Snowflake",
        category="hard_skill",
        subcategory="data_engineering",
        aliases=["snowflake"],
    ),
    SkillTaxonomyItem(
        key="bigquery",
        name="BigQuery",
        category="hard_skill",
        subcategory="data_engineering",
        aliases=["bigquery", "google bigquery"],
    ),
    SkillTaxonomyItem(
        key="dbt",
        name="dbt",
        category="hard_skill",
        subcategory="data_engineering",
        aliases=["dbt", "data build tool"],
    ),
    SkillTaxonomyItem(
        key="databricks",
        name="Databricks",
        category="hard_skill",
        subcategory="data_engineering",
        aliases=["databricks"],
    ),

    # Cloud and DevOps
    SkillTaxonomyItem(
        key="docker",
        name="Docker",
        category="hard_skill",
        subcategory="cloud_devops",
        aliases=["docker", "container", "containers", "containerization", "conteneurs"],
    ),
    SkillTaxonomyItem(
        key="kubernetes",
        name="Kubernetes",
        category="hard_skill",
        subcategory="cloud_devops",
        aliases=["kubernetes", "k8s"],
    ),
    SkillTaxonomyItem(
        key="aws",
        name="AWS",
        category="hard_skill",
        subcategory="cloud_devops",
        aliases=["aws", "amazon web services", "amazon aws"],
    ),
    SkillTaxonomyItem(
        key="azure",
        name="Azure",
        category="hard_skill",
        subcategory="cloud_devops",
        aliases=["azure", "microsoft azure"],
    ),
    SkillTaxonomyItem(
        key="gcp",
        name="GCP",
        category="hard_skill",
        subcategory="cloud_devops",
        aliases=["gcp", "google cloud", "google cloud platform"],
    ),
    SkillTaxonomyItem(
        key="ci_cd",
        name="CI/CD",
        category="hard_skill",
        subcategory="cloud_devops",
        aliases=[
            "ci/cd",
            "ci-cd",
            "cicd",
            "integration continue",
            "continuous integration",
            "deploiement continu",
            "continuous deployment",
        ],
    ),
    SkillTaxonomyItem(
        key="terraform",
        name="Terraform",
        category="hard_skill",
        subcategory="cloud_devops",
        aliases=["terraform"],
    ),
    SkillTaxonomyItem(
        key="ansible",
        name="Ansible",
        category="hard_skill",
        subcategory="cloud_devops",
        aliases=["ansible"],
    ),
    SkillTaxonomyItem(
        key="linux",
        name="Linux",
        category="hard_skill",
        subcategory="cloud_devops",
        aliases=["linux", "unix", "debian", "ubuntu", "redhat", "centos"],
    ),
    SkillTaxonomyItem(
        key="git",
        name="Git",
        category="hard_skill",
        subcategory="cloud_devops",
        aliases=["git", "github", "gitlab", "bitbucket"],
    ),
    SkillTaxonomyItem(
        key="jenkins",
        name="Jenkins",
        category="hard_skill",
        subcategory="cloud_devops",
        aliases=["jenkins"],
    ),

    # Data Science and Machine Learning
    SkillTaxonomyItem(
        key="scikit_learn",
        name="Scikit-Learn",
        category="hard_skill",
        subcategory="data_science",
        aliases=["scikit-learn", "scikit learn", "sklearn"],
    ),
    SkillTaxonomyItem(
        key="pandas",
        name="Pandas",
        category="hard_skill",
        subcategory="data_science",
        aliases=["pandas"],
    ),
    SkillTaxonomyItem(
        key="numpy",
        name="NumPy",
        category="hard_skill",
        subcategory="data_science",
        aliases=["numpy"],
    ),
    SkillTaxonomyItem(
        key="pytorch",
        name="PyTorch",
        category="hard_skill",
        subcategory="data_science",
        aliases=["pytorch", "torch"],
    ),
    SkillTaxonomyItem(
        key="tensorflow",
        name="TensorFlow",
        category="hard_skill",
        subcategory="data_science",
        aliases=["tensorflow", "tf"],
    ),
    SkillTaxonomyItem(
        key="keras",
        name="Keras",
        category="hard_skill",
        subcategory="data_science",
        aliases=["keras"],
    ),
    SkillTaxonomyItem(
        key="mlflow",
        name="MLflow",
        category="hard_skill",
        subcategory="data_science",
        aliases=["mlflow"],
    ),
    SkillTaxonomyItem(
        key="mlops",
        name="MLOps",
        category="hard_skill",
        subcategory="data_science",
        aliases=["mlops", "machine learning operations"],
    ),
    SkillTaxonomyItem(
        key="machine_learning",
        name="Machine Learning",
        category="hard_skill",
        subcategory="data_science",
        aliases=[
            "machine learning",
            "apprentissage automatique",
            "apprentissage supervise",
            "apprentissage non supervise",
        ],
    ),
    SkillTaxonomyItem(
        key="deep_learning",
        name="Deep Learning",
        category="hard_skill",
        subcategory="data_science",
        aliases=["deep learning", "apprentissage profond", "reseaux de neurones", "neural networks"],
    ),
    SkillTaxonomyItem(
        key="nlp",
        name="NLP",
        category="hard_skill",
        subcategory="data_science",
        aliases=[
            "nlp",
            "natural language processing",
            "traitement du langage naturel",
            "taln",
            "text mining",
        ],
    ),
    SkillTaxonomyItem(
        key="computer_vision",
        name="Computer Vision",
        category="hard_skill",
        subcategory="data_science",
        aliases=["computer vision", "vision par ordinateur", "opencv"],
    ),
    SkillTaxonomyItem(
        key="statistics",
        name="Statistics",
        category="hard_skill",
        subcategory="data_science",
        aliases=[
            "statistics",
            "statistical analysis",
            "statistiques",
            "analyse statistique",
            "probabilites",
            "biostatistique",
        ],
    ),

    # Business Intelligence and Visualization
    SkillTaxonomyItem(
        key="tableau",
        name="Tableau",
        category="hard_skill",
        subcategory="bi_analytics",
        aliases=["tableau", "tableau software", "tableau desktop", "tableau server"],
    ),
    SkillTaxonomyItem(
        key="power_bi",
        name="Power BI",
        category="hard_skill",
        subcategory="bi_analytics",
        aliases=["power bi", "powerbi", "power-bi", "dax"],
    ),
    SkillTaxonomyItem(
        key="microsoft_excel",
        name="Microsoft Excel",
        category="hard_skill",
        subcategory="bi_analytics",
        aliases=["microsoft excel", "excel", "ms excel", "vba"],
    ),
    SkillTaxonomyItem(
        key="looker",
        name="Looker",
        category="hard_skill",
        subcategory="bi_analytics",
        aliases=["looker", "lookml"],
    ),
    SkillTaxonomyItem(
        key="metabase",
        name="Metabase",
        category="hard_skill",
        subcategory="bi_analytics",
        aliases=["metabase"],
    ),
    SkillTaxonomyItem(
        key="matplotlib",
        name="Matplotlib",
        category="hard_skill",
        subcategory="bi_analytics",
        aliases=["matplotlib"],
    ),
    SkillTaxonomyItem(
        key="seaborn",
        name="Seaborn",
        category="hard_skill",
        subcategory="bi_analytics",
        aliases=["seaborn"],
    ),
    SkillTaxonomyItem(
        key="qlik",
        name="Qlik",
        category="hard_skill",
        subcategory="bi_analytics",
        aliases=["qlik", "qlikview", "qlik sense"],
    ),
    SkillTaxonomyItem(
        key="business_intelligence",
        name="Business Intelligence",
        category="hard_skill",
        subcategory="bi_analytics",
        aliases=["business intelligence", "bi", "reporting", "decisionnel", "tableaux de bord"],
    ),
]

# Curated catalog of behavioral soft skills and methodologies
_SOFT_SKILLS: List[SkillTaxonomyItem] = [
    SkillTaxonomyItem(
        key="communication",
        name="Communication",
        category="soft_skill",
        subcategory="communication",
        aliases=[
            "communication",
            "communicant",
            "communicante",
            "aisance relationnelle",
            "expression ecrite",
            "expression orale",
            "communication interpersonnelle",
            "presentation",
            "vulgarisation",
            "oral communication",
            "written communication",
            "capacite de redaction",
        ],
    ),
    SkillTaxonomyItem(
        key="esprit_dequipe",
        name="Esprit d'équipe",
        category="soft_skill",
        subcategory="teamwork",
        aliases=[
            "esprit d'equipe",
            "esprit dequipe",
            "travail d'equipe",
            "travail dequipe",
            "teamwork",
            "collaboration",
            "entraide",
            "team player",
            "collaboratif",
            "collaborative",
            "transversalite",
            "esprit collaboratif",
        ],
    ),
    SkillTaxonomyItem(
        key="leadership",
        name="Leadership",
        category="soft_skill",
        subcategory="leadership",
        aliases=[
            "leadership",
            "management",
            "gestion d'equipe",
            "animation d'equipe",
            "mentorat",
            "mentoring",
            "coaching",
            "meneur",
            "prise de decision",
            "sens du leadership",
            "encadrement",
        ],
    ),
    SkillTaxonomyItem(
        key="resolution_de_problemes",
        name="Résolution de problèmes",
        category="soft_skill",
        subcategory="problem_solving",
        aliases=[
            "resolution de problemes",
            "problem solving",
            "analyse de donnees",
            "esprit d'analyse",
            "esprit critique",
            "pensee critique",
            "curiosite intellectuelle",
            "diagnostic",
            "sens de l'analyse",
            "capacite d'analyse",
            "capacite a resoudre",
        ],
    ),
    SkillTaxonomyItem(
        key="adaptabilite",
        name="Adaptabilité",
        category="soft_skill",
        subcategory="adaptability",
        aliases=[
            "adaptabilite",
            "agilite",
            "flexibilite",
            "adaptability",
            "adaptable",
            "gestion du changement",
            "polyvalence",
            "polyvalent",
            "polyvalente",
            "reactivite",
        ],
    ),
    SkillTaxonomyItem(
        key="autonomie",
        name="Autonomie",
        category="soft_skill",
        subcategory="autonomy",
        aliases=[
            "autonomie",
            "autonome",
            "autonomous",
            "autonomy",
            "proactivite",
            "proactif",
            "proactive",
            "initiative",
            "prise d'initiative",
            "sens de l'initiative",
            "independance",
        ],
    ),
    SkillTaxonomyItem(
        key="rigueur",
        name="Rigueur",
        category="soft_skill",
        subcategory="rigor",
        aliases=[
            "rigueur",
            "rigoureux",
            "rigoureuse",
            "rigorous",
            "rigor",
            "organisation",
            "sens de l'organisation",
            "precision",
            "souci du detail",
            "methode",
            "methodique",
            "fiabilite",
            "structure",
        ],
    ),
    SkillTaxonomyItem(
        key="gestion_de_projet",
        name="Gestion de projet",
        category="soft_skill",
        subcategory="methodology",
        aliases=[
            "gestion de projet",
            "project management",
            "gestion de projets",
            "agile",
            "scrum",
            "kanban",
            "planification",
            "pilotage de projet",
            "suivi de projet",
            "gestion des priorites",
        ],
    ),
]

_ALL_ITEMS: List[SkillTaxonomyItem] = _HARD_SKILLS + _SOFT_SKILLS
_TAXONOMY_REGISTRY: Dict[str, SkillTaxonomyItem] = {item.key: item for item in _ALL_ITEMS}

# Reverse index: normalized alias -> canonical key
_ALIAS_TO_KEY: Dict[str, str] = {}
for item in _ALL_ITEMS:
    # Always include normalized item key and name
    _ALIAS_TO_KEY[_strip_accents(item.key)] = item.key
    _ALIAS_TO_KEY[_strip_accents(item.name)] = item.key
    for alias in item.aliases:
        _ALIAS_TO_KEY[_strip_accents(alias)] = item.key


def get_all_taxonomy_items() -> List[SkillTaxonomyItem]:
    """Return complete list of all taxonomy skill items."""
    return list(_ALL_ITEMS)


def get_taxonomy_registry() -> Dict[str, SkillTaxonomyItem]:
    """Return dictionary of all canonical skills keyed by their unique identifier."""
    return dict(_TAXONOMY_REGISTRY)


def get_hard_skills() -> Dict[str, SkillTaxonomyItem]:
    """Return technical hard skills dictionary keyed by identifier."""
    return {item.key: item for item in _HARD_SKILLS}


def get_soft_skills() -> Dict[str, SkillTaxonomyItem]:
    """Return behavioral and methodology soft skills dictionary keyed by identifier."""
    return {item.key: item for item in _SOFT_SKILLS}


def lookup_canonical_skill(name_or_alias: str) -> Optional[SkillTaxonomyItem]:
    """Resolve a raw skill string or alias into its canonical taxonomy descriptor.

    Args:
        name_or_alias: Raw skill name, abbreviation, or synonym.

    Returns:
        Canonical SkillTaxonomyItem if identified, else None.
    """
    cleaned = _strip_accents(name_or_alias)
    if not cleaned:
        return None

    # Exact normalized alias match
    canonical_key = _ALIAS_TO_KEY.get(cleaned)
    if canonical_key:
        return _TAXONOMY_REGISTRY[canonical_key]

    # Check without punctuation
    condensed = "".join(c for c in cleaned if c.isalnum())
    for alias, key in _ALIAS_TO_KEY.items():
        if "".join(c for c in alias if c.isalnum()) == condensed and len(condensed) >= 3:
            return _TAXONOMY_REGISTRY[key]

    return None
