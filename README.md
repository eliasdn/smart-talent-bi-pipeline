# Smart Talent BI Pipeline

A local, offline-first talent analytics and business intelligence pipeline implemented in Python. Combines automated ETL data ingestion, relational 3NF SQLite modeling, boundary-aware n-gram skill extraction, offline TF-IDF profile matching, multi-factor weighted scoring, and automated reporting across multi-tab Excel workbooks and structured PDF summaries. Designed as a privacy-friendly (GDPR-compliant) proof-of-concept for automated candidate screening and HR process analytics without sending personal data to external cloud APIs.

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [Business Problem & Recruitment Context](#business-problem--recruitment-context)
- [System Architecture](#system-architecture)
- [Core Functional Modules](#core-functional-modules)
  - [1. ETL Ingestion & Schema Validation](#1-etl-ingestion--schema-validation)
  - [2. Relational 3NF Data Warehouse](#2-relational-3nf-data-warehouse)
  - [3. Semantic Matching & Multi-Factor Scoring](#3-semantic-matching--multi-factor-scoring)
  - [4. Automated BI Reporting & Deliverables](#4-automated-bi-reporting--deliverables)
  - [5. CLI & Orchestration Engine](#5-cli--orchestration-engine)
- [Relational Data Model Specification](#relational-data-model-specification)
- [Scoring Methodology & Mathematical Weights](#scoring-methodology--mathematical-weights)
- [Business Intelligence & ROI Metrics](#business-intelligence--roi-metrics)
- [Project Directory Layout](#project-directory-layout)
- [Installation & Setup](#installation--setup)
- [Usage & CLI Reference](#usage--cli-reference)
- [Automated Verification](#automated-verification)
- [Test Suite & Quality Assurance](#test-suite--quality-assurance)
- [Compliance & Engineering Standards](#compliance--engineering-standards)
- [Author & License](#author--license)

---

## Executive Summary

The **Smart Talent BI Pipeline** provides recruitment workflows with an automated, objective, and reproducible talent screening pipeline. Rather than transmitting sensitive resume data to external cloud APIs or relying purely on manual keyword matching, the pipeline executes 100% locally and deterministically.

Key technical characteristics:
- **Privacy & GDPR Friendly**: Fully offline NLP execution using scikit-learn TF-IDF vectorization and custom bilingual taxonomy matching, ensuring zero candidate data leaves the local environment.
- **Relational Integrity**: 10 SQLite tables modeled in Third Normal Form (3NF) with strict foreign key constraints, cascading deletions, and savepoint-protected error quarantining.
- **Fast Execution**: Evaluates candidate profiles against open requisitions in seconds, producing structured match scores and gap breakdowns.
- **Automated Deliverables**: Generates an interactive 4-tab OpenPyXL Excel dashboard and a 3-page structured ReportLab PDF summary complete with KPI summaries, ranking tables, and tailored French synthesis narratives.

---

## Business Problem & Recruitment Context

Modern talent acquisition organizations face severe operational bottlenecks:

1. **Screening Latency**: Recruiters spend an average of 15 to 20 minutes manually reviewing each resume, leading to multi-week time-to-hire cycles and talent loss.
2. **Keyword Mismatches**: Naive keyword search tools miss qualified applicants who express technical skills in different phrasing, while overlooking critical contextual experience.
3. **Qualification Inconsistency**: Human evaluators introduce subjective bias when weighting education, hard skills, seniority, and soft competencies.
4. **Audit and Compliance Gaps**: Traditional processes lack systematic tracking of screening decisions, ingestion errors, and operational funnel conversion metrics.

The Smart Talent BI Pipeline solves these issues by automating the end-to-end flow from raw data ingestion to executive reporting with quantitative scoring, transparent gap analyses, and recruitment ROI tracking.

---

## System Architecture

The pipeline follows a modular, decoupled architecture where each package encapsulates a distinct domain boundary:

```
+-----------------------------------------------------------------------------------+
|                                 CLI Interface                                     |
|               (Typer / Rich: ingest, match, report, run-all, verify)              |
+-----------------------------------------------------------------------------------+
                                         |
     +-----------------------------------+-----------------------------------+
     |                                   |                                   |
     v                                   v                                   v
+-----------------------+   +-------------------------+   +-------------------------+
|     ETL Ingestion     |   |   Semantic Matching     |   |      BI Reporting       |
|  - Raw JSON/CSV read  |   |  - N-gram skill extract |   |  - KPI & ROI synthesis  |
|  - Pydantic valid.    |   |  - TF-IDF & Cosine Sim  |   |  - OpenPyXL (4 tabs)    |
|  - Quarantine errors  |   |  - Weighted multi-score |   |  - ReportLab PDF dossier|
|  - SQLite 3NF upsert  |   |  - Strengths & gaps     |   |                         |
+-----------------------+   +-------------------------+   +-------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                         Relational Database (SQLite)                              |
|   candidates, skills, candidate_skills, candidate_experiences,                   |
|   job_descriptions, job_skills, matching_evaluations, operational_metrics,        |
|   ingestion_batches, ingestion_errors                                             |
+-----------------------------------------------------------------------------------+
```

### Data Flow Overview

```
[Raw Data Sources]
   ├── candidates.json
   ├── job_descriptions.json
   └── operational_metrics.csv
           │
           ▼
[ETL Ingestion Pipeline]
   ├── Pydantic v2 Schema Validation
   ├── Normalization & Data Cleansing
   └── Savepoint-Guarded Upsert / Error Quarantine
           │
           ▼
[Relational 3NF SQLite Warehouse] (talent_bi.db)
   ├── 10 Tables with Strict Foreign Keys (PRAGMA foreign_keys = ON)
   └── Composite Indexes for Query Optimization
           │
           ▼
[Semantic Matching Engine]
   ├── Boundary-Aware N-Gram Extraction (Technical & Soft Skills)
   ├── Scikit-Learn TF-IDF Vectorization & Cosine Similarity
   ├── Multi-Factor Composite Scoring (45% Skills, 25% Exp, 15% Edu, 15% Soft)
   └── French Narrative Synthesis (Strengths, Gaps, Recommendations)
           │
           ▼
[BI Metrics & Document Generation Service]
   ├── Recruitment KPI & Financial ROI Synthesis
   ├── 4-Tab OpenPyXL Excel Workbook (talent_bi_report.xlsx)
   └── Executive ReportLab PDF Dossier (executive_evaluation_summary.pdf)
```

---

## Core Functional Modules

### 1. ETL Ingestion & Schema Validation
- **Path**: `src/etl/`
- **Schemas**: Validates incoming payloads via Pydantic v2 models (`RawCandidateSchema`, `RawJobDescriptionSchema`, `RawOperationalMetricSchema`).
- **Resilience & Defensive Quarantine**: Operates with SQLAlchemy transaction savepoints (`begin_nested()`). Unlike basic ETL scripts that abort on the first malformed entry, corrupt records (e.g. invalid emails, inverted employment dates, malformed dates) are automatically trapped and logged into the `ingestion_errors` quarantine table, allowing valid records in the batch to commit cleanly.
- **Tested with Unstructured / Dirty Data**: Includes production-like messy samples (`data/raw/candidates_unstructured_sample.json`, `data/raw/operational_metrics_messy_sample.csv`) verifying robust parsing of French diacritics, extra whitespaces, and quarantine isolation.
- **Batch Auditing**: Logs every execution batch with timestamp, record counts, and status (`completed`, `partial`, `failed`) in `ingestion_batches`.

### 2. Relational 3NF Data Warehouse
- **Path**: `src/models/`
- **Database Engine**: SQLite with SQLAlchemy 2.0 ORM and connection event hooks enforcing `PRAGMA foreign_keys = ON`.
- **Normalization**: Structured in Third Normal Form (3NF) across 10 tables to eliminate data redundancy and preserve referential integrity.
- **Cascade Rules**: Configured with `ON DELETE CASCADE` across foreign keys, ensuring child records (skills, experiences, evaluations) are pruned upon parent deletion.

### 3. Text Matching & Multi-Factor Scoring Engine
- **Path**: `src/engine/`
- **Skill Extraction**: Word-boundary pattern matching using curated bilingual (French/English) dictionaries extracting single and multi-word competencies (e.g., "Machine Learning", "Power BI", "Scrum").
- **Vector Matching**: Offline Scikit-Learn TF-IDF vectorizer equipped with a bilingual stop-word corpus (French + English) and sublinear term frequency scaling, paired with Cosine Similarity calculation.
- **Why TF-IDF instead of LLMs?**: Designed for 100% data privacy (no resume text sent to cloud APIs), sub-millisecond execution, and total scoring explainability without non-deterministic hallucinations.
- **Multi-Factor Scoring**: Evaluates candidates across 4 distinct dimensions:
  1. Technical Skills & Vector Match (45%)
  2. Experience Alignment (25%)
  3. Education Level (15%)
  4. Soft Skills Match (15%)
- **Narrative Synthesis**: Generates structured French executive evaluation summaries detailing candidate strengths, identified gaps, and targeted training recommendations.

### 4. Automated BI Reporting & Deliverables
- **Path**: `src/reporting/`
- **Excel Workbook**: Generates `talent_bi_report.xlsx` containing 4 styled worksheets:
  - `Executive Dashboard`: High-level metrics, funnel conversion rates, time-to-hire by department.
  - `Candidates Ranking`: Ranked candidate-job pairings with overall scores and dimension sub-scores.
  - `Gap Analysis`: Missing mandatory skills and targeted training curricula per candidate.
  - `Operational Metrics`: Recruitment funnel logs, channel performance, and cost distributions.
- **Executive PDF Dossier**: Generates `executive_evaluation_summary.pdf` via ReportLab:
  - Custom `NumberedCanvas` producing running footers with "Page X / Y" and generation timestamp.
  - KPI summary scorecards, candidate ranking tables, and detailed profile evaluation cards.

### 5. CLI & Orchestration Engine
- **Path**: `src/cli/`
- **Interface**: Built with Typer and Rich, delivering colored status panels, progress tables, and clean terminal outputs.
- **Subcommands**: Individual commands for `ingest`, `match`, `report`, `run-all`, and `verify`.

---

## Relational Data Model Specification

The database consists of 10 tables designed in strict Third Normal Form (3NF):

| Table Name | Purpose | Primary Key | Key Foreign Constraints |
|---|---|---|---|
| `candidates` | Core candidate profile master table | `id` (VARCHAR) | None |
| `skills` | Canonical skill taxonomy dictionary | `id` (INTEGER) | Unique constraint on `(name, category)` |
| `candidate_skills` | Association between candidates and skills | Composite `(candidate_id, skill_id)` | FK to `candidates.id` (CASCADE), FK to `skills.id` |
| `candidate_experiences`| Candidate employment history | `id` (INTEGER) | FK to `candidates.id` (CASCADE) |
| `job_descriptions` | Requisition master table | `id` (VARCHAR) | Unique constraint on `job_code` |
| `job_skills` | Required skills per requisition | Composite `(job_id, skill_id)` | FK to `job_descriptions.id` (CASCADE), FK to `skills.id` |
| `matching_evaluations` | Persisted matching scores and synthesis | `id` (INTEGER) | FK to `candidates.id` (CASCADE), FK to `job_descriptions.id` (CASCADE) |
| `operational_metrics` | Operational recruitment process events | `id` (INTEGER) | Optional FK to `job_descriptions.id`, `candidates.id` |
| `ingestion_batches` | ETL batch run auditing | `id` (INTEGER) | Unique constraint on `batch_id` |
| `ingestion_errors` | Quarantined malformed records | `id` (INTEGER) | FK to `ingestion_batches.id` (CASCADE) |

---

## Scoring Methodology & Mathematical Weights

The candidate match score is calculated as a composite weighted average bounded between `0.00` and `100.00`:

$$\text{Overall Score} = 0.45 \times S_{\text{tech}} + 0.25 \times S_{\text{exp}} + 0.15 \times S_{\text{edu}} + 0.15 \times S_{\text{soft}}$$

### 1. Technical Skills & Semantic Relevance ($S_{\text{tech}}$) — 45%
- Weighted coverage of mandatory (weight: 1.0), preferred (weight: 0.6), and nice-to-have (weight: 0.3) skills.
- Blended with TF-IDF cosine similarity between the candidate's raw CV text and the job description:
  $$S_{\text{tech}} = 0.70 \times \text{SkillRequirementCoverage} + 0.30 \times (\text{CosineSimilarity} \times 100)$$

### 2. Experience Alignment ($S_{\text{exp}}$) — 25%
- Evaluates total years of verified professional experience against the job's minimum required years:
  - If $\text{Years} \ge \text{MinYears}$: $100.00$
  - If $\text{Years} < \text{MinYears}$: $\max\left(0, \frac{\text{Years}}{\text{MinYears}} \times 100 - \text{Penalty}\right)$

### 3. Education Level ($S_{\text{edu}}$) — 15%
- Normalized scoring based on French national academic degree equivalencies:
  - Doctorate / PhD (Bac+8): 100.00
  - Master / Diplome d'Ingenieur (Bac+5): 90.00
  - Licence / Bachelor (Bac+3): 75.00
  - BTS / DUT (Bac+2): 60.00
  - Baccalaureat / High School: 40.00

### 4. Soft Skills Compatibility ($S_{\text{soft}}$) — 15%
- Percentage coverage of behavioral and interpersonal skills identified in the requisition (e.g., Communication, Leadership, Agile Methodology, Problem Solving).

### Match Tiers
- **Strong Match** ($\ge 70.00\%$): Recommended for immediate interview.
- **Moderate Match** ($50.00\% - 69.99\%$): Partial qualification, training gap identified.
- **Low Match** ($< 50.00\%$): Insufficient qualification alignment.

---

## Business Intelligence & ROI Metrics

The pipeline calculates operational recruitment metrics to measure process velocity and financial return on investment (ROI):

### Funnel Conversion Tracking
- Aggregates progression rates across hiring stages: `applied` -> `screened` -> `interviewed` -> `offered` -> `hired`.
- Identifies recruitment stage drop-offs and channel yield (LinkedIn, Referrals, Direct Applications, Job Boards).

### Time-to-Hire Analytics
- Computes mean duration (days) from application to final decision across departments (Data, Engineering, Product, Operations).

### Operational Time & Cost Simulation
To assess the productivity impact compared to manual resume screening, the pipeline includes a simple operational simulation model:

$$\text{Estimated Time Saved} = \frac{\text{Candidates Evaluated} \times 15 \text{ minutes}}{60 \text{ min/hour}}$$

$$\text{Estimated Cost Equivalent} = \text{Estimated Time Saved} \times \text{Hourly Rate (EUR)}$$

**Sample Benchmark (on provided 10-candidate test set):**
- **Pairs Evaluated**: 40 candidate-requisition pairs
- **Execution Latency**: ~0.8 seconds
- **Theoretical Manual Screening Time**: ~10 hours
- **Purpose**: Provides HR teams with an operational estimate of screening time reduced before human interviews.

---

## Project Directory Layout

```
smart-talent-bi-pipeline/
├── .env.example                       # Environment configuration template
├── .gitignore                         # Git exclusion rules
├── app.py                             # Interactive Streamlit Web Application
├── pyproject.toml                     # Project packaging and metadata
├── requirements.txt                   # Production and testing dependencies
├── README.md                          # Technical architecture and documentation
├── data/
│   ├── raw/                           # Input benchmark datasets
│   │   ├── candidates.json            # Structured candidate profiles and CVs
│   │   ├── job_descriptions.json      # Requisitions with weighted skill criteria
│   │   └── operational_metrics.csv    # Historical recruitment process events
│   └── output/                        # Generated deliverables (git-ignored)
│       ├── reports/
│       │   ├── talent_bi_report.xlsx  # Multi-tab Excel workbook
│       │   └── executive_evaluation_summary.pdf  # Executive PDF dossier
│       └── talent_bi.db               # Populated 3NF SQLite database
├── src/
│   ├── __init__.py
│   ├── config.py                      # Pydantic Settings configuration loader
│   ├── models/
│   │   ├── __init__.py
│   │   ├── entities.py                # SQLAlchemy 2.0 ORM models (10 tables)
│   │   └── schemas.py                 # Pydantic v2 validation DTOs
│   ├── etl/
│   │   ├── __init__.py
│   │   ├── extractors.py              # JSON and CSV data loaders
│   │   ├── transformers.py            # Cleansing, typing, and normalization
│   │   ├── loaders.py                 # Database upsert and error quarantine
│   │   └── pipeline.py                # Orchestrated ETL pipeline
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── taxonomies.py              # Bilingual skill dictionaries
│   │   ├── extractor.py               # Boundary-aware n-gram extraction
│   │   ├── semantic.py                # Offline TF-IDF vectorizer and cosine sim
│   │   ├── scorer.py                  # Multi-factor weighted scoring
│   │   ├── synthesizer.py             # French narrative synthesis generator
│   │   └── service.py                 # Matching engine high-level service
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── metrics.py                 # BI KPIs and financial ROI calculator
│   │   ├── excel_generator.py         # OpenPyXL 4-tab workbook generator
│   │   ├── pdf_generator.py           # ReportLab executive PDF generator
│   │   └── service.py                 # BI query and reporting service
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py                    # Typer and Rich command-line application
│   └── utils/
│       ├── __init__.py
│       └── logger.py                  # Formatted logging setup
├── scripts/
│   ├── generate_synthetic_data.py    # Synthetic dataset generator for volume testing
│   └── verify_pipeline.py            # 14-point standalone empirical verification
└── tests/
    ├── __init__.py
    ├── conftest.py                    # Pytest fixtures and test database factories
    ├── unit/                          # Unit & edge-case tests (models, etl, engine, cli, reporting)
    ├── integration/                   # Cross-module tests (persistence, cascade, flow)
    └── e2e/                           # End-to-end pipeline execution tests
```

---

## Installation & Setup

### Prerequisites
- Python 3.11 or higher
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/eliasdn/smart-talent-bi-pipeline.git
cd smart-talent-bi-pipeline
```

### 2. Create and Activate a Virtual Environment
On Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the sample environment file:
```bash
cp .env.example .env
```

Default settings in `.env`:
```ini
DATABASE_URL=sqlite:///data/output/talent_bi.db
RAW_DATA_DIR=data/raw
OUTPUT_REPORTS_DIR=data/output/reports
LOG_LEVEL=INFO
RECRUITER_HOURLY_RATE=45.0
```

---

## Usage & CLI Reference

### 1. Interactive Streamlit Web Dashboard
Launch the local web dashboard for real-time candidate evaluation, KPI visualization, and direct report downloads:
```bash
streamlit run app.py
```

### 2. Execute Full End-to-End Pipeline (CLI)
Runs ingestion, semantic matching, evaluation persistence, and report generation in a single automated pass:
```bash
python -m src.cli.main run-all
```
Optional custom paths:
```bash
python -m src.cli.main run-all --data-dir data/raw --db-path data/output/talent_bi.db --output-dir data/output/reports
```

### 3. Step-by-Step Execution

#### Step A: Ingest Raw Datasets
Parses raw JSON and CSV files, validates schemas via Pydantic, and loads into SQLite:
```bash
python -m src.cli.main ingest --data-dir data/raw --db-path data/output/talent_bi.db
```

#### Step B: Execute Semantic Matching
Calculates TF-IDF similarity, extracts n-gram skills, computes composite scores, and writes evaluations:
```bash
python -m src.cli.main match --db-path data/output/talent_bi.db
```

#### Step C: Generate BI Reports
Produces the 4-tab Excel workbook and the executive PDF evaluation dossier:
```bash
python -m src.cli.main report --db-path data/output/talent_bi.db --output-dir data/output/reports
```

### 3. In-CLI Pipeline Verification
Inspects database tables, integrity constraints, and deliverables directly from the CLI:
```bash
python -m src.cli.main verify
```

---

## Automated Verification

The project provides a standalone verification script (`scripts/verify_pipeline.py`) implementing 14 automated empirical checks across data integrity, schema compliance, and output deliverable validity:

```bash
python scripts/verify_pipeline.py
```

### Verification Checks Summary

| Check ID | Category | Target | Acceptance Criteria | Status |
|---|---|---|---|:---:|
| `DB-01` | Database | `talent_bi.db` | File exists and non-zero size | PASS |
| `DB-02` | Database | Schema | All 10 3NF tables present in SQLite master | PASS |
| `DB-03` | Volume | `candidates` | Count $\ge 10$ candidate records | PASS |
| `DB-04` | Volume | `job_descriptions` | Count $\ge 4$ job vacancies | PASS |
| `DB-05` | Volume | `operational_metrics` | Count $\ge 35$ operational metric rows | PASS |
| `DB-06` | Volume | `matching_evaluations`| Count $\ge 40$ matching evaluation records | PASS |
| `DB-07` | Integrity | Relational | 0 foreign key constraint violations | PASS |
| `DB-08` | Integrity | Scores | All scores within $[0.00, 100.00]$, similarity in $[0.00, 1.00]$ | PASS |
| `REP-01` | Deliverables | `talent_bi_report.xlsx` | File exists and readable by openpyxl | PASS |
| `REP-02` | Deliverables | `talent_bi_report.xlsx` | All 4 worksheets present | PASS |
| `REP-03` | Deliverables | `talent_bi_report.xlsx` | All sheets contain valid structured data rows | PASS |
| `REP-04` | Deliverables | `executive_evaluation_summary.pdf` | File exists with size $> 5$ KB | PASS |
| `REP-05` | Deliverables | `executive_evaluation_summary.pdf` | Valid `%PDF-` magic header signature | PASS |
| `REP-06` | Deliverables | `executive_evaluation_summary.pdf` | Valid page count ($\ge 3$) and extracted text | PASS |

---

## Test Suite & Quality Assurance

The system maintains a comprehensive, opaque-box, multi-tier test suite executed via pytest:

```bash
pytest -v tests/
```

### Test Breakdown

- **Unit & Edge-Case Tests** (`tests/unit/`):
  - `test_models.py`: 3NF schema, relationships, cascade deletes, Pydantic DTO validations.
  - `test_etl.py`, `test_etl_edge_cases.py` & `test_etl_quarantine.py`: Extractors, transformers, transaction savepoints, error quarantine.
  - `test_engine.py` & `test_engine_boundaries.py`: N-gram skill extractor, TF-IDF vectorizer, composite scoring weights, boundary token inputs.
  - `test_reporting.py` & `test_reporting_generation.py`: KPI calculations, Excel worksheet structure, PDF canvas styling, empty DB handling.
  - `test_cli.py` & `test_cli_validation.py`: Typer CLI subcommands, input argument handling, corrupted inputs validation.
  - `test_pipeline_integrity.py`: Resilience against corrupted inputs, dropped tables, foreign key violations, and missing assets.
- **Integration Tests** (`tests/integration/`):
  - `test_db_persistence.py`: Scale tests (500+ candidates, 2,000+ metrics), foreign key pragma integrity, indexed query plans.
  - `test_matching_flow.py`: End-to-end data transfer from ingested models to persisted evaluations.
- **End-to-End Tests** (`tests/e2e/test_full_pipeline.py`):
  - Full pipeline runs via CLI runner and Python API.
  - Verification script execution under normal and degraded conditions.
  - Automated code compliance verification (zero emojis, clean terminology).

**Test Results Summary**:
- Total Tests: **228**
- Passing: **228 (100%)**
- Failures: **0**
- Execution Duration: ~2 minutes (including full-scale database stress workloads)

---

## Compliance & Engineering Standards

The project strictly follows institutional engineering guidelines:

1. **Deterministic & Offline**: Zero reliance on external cloud language models or hosted APIs. All computations use reproducible mathematical algorithms (TF-IDF, Cosine Similarity, linear weighting).
2. **Type Safety & Data Contracts**: Fully typed with Python type hints and Pydantic v2 validation models.
3. **Transactional Integrity**: Every ETL operation executes under transactional boundaries with savepoints. Malformed data is recorded in `ingestion_errors` without aborting batch execution.
4. **Data Privacy First**: Zero third-party network requests. Sensitive CV personal details remain strictly local to the runtime environment.

---

## Author & License

- **Author**: Elias DANI
- **Email**: 79227843+eliasdn@users.noreply.github.com
- **License**: MIT License
