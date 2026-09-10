"""CLI script to generate realistic synthetic benchmark datasets for scale testing."""

import argparse
import json
import random
import sys
from pathlib import Path

ROLES = [
    ("Data Analyst", "Analytics", ["SQL", "PowerBI", "Tableau", "Python", "Excel"]),
    ("Data Engineer", "Data", ["Python", "SQL", "Apache Spark", "Airflow", "Docker", "AWS", "PostgreSQL"]),
    ("Machine Learning Engineer", "AI", ["Python", "PyTorch", "Scikit-Learn", "Docker", "MLflow", "Kubernetes"]),
    ("Analytics Engineer", "Analytics", ["dbt", "Snowflake", "SQL", "Python", "Airflow"]),
    ("Business Intelligence Specialist", "BI", ["PowerBI", "SQL", "DAX", "Data Modeling", "Excel"]),
]

CITIES = ["Paris, France", "Lyon, France", "Nantes, France", "Toulouse, France", "Bordeaux, France", "Remote, France"]
DEGREES = [
    "Master of Science in Data Science",
    "Master en Informatique",
    "Diplome d Ingenieur",
    "Bachelor in Business Analytics",
    "Licence Informatique",
]
FIRST_NAMES = ["Lucas", "Emma", "Thomas", "Chloe", "Maxime", "Lea", "Alexandre", "Sarah", "Julien", "Manon", "Nicolas", "Camille"]
LAST_NAMES = ["Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand", "Leroy", "Moreau", "Simon", "Laurent"]

def generate_candidates(count: int) -> list:
    candidates = []
    for i in range(1, count + 1):
        role_title, dept, key_skills = random.choice(ROLES)
        fn = random.choice(FIRST_NAMES)
        ln = random.choice(LAST_NAMES)
        exp = round(random.uniform(1.0, 10.0), 1)
        cand_id = f"cand-gen-{i:04d}"
        
        cand_skills = []
        for s in key_skills:
            cand_skills.append({
                "name": s,
                "category": "technical",
                "proficiency_level": random.choice(["intermediate", "advanced", "expert"]),
                "years_experience": round(min(exp, random.uniform(1.0, exp)), 1),
                "is_primary": True,
            })
        
        candidates.append({
            "candidate_id": cand_id,
            "full_name": f"{fn} {ln}",
            "email": f"{fn.lower()}.{ln.lower()}.{i}@example.com",
            "phone": f"+33 6 {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)}",
            "location": random.choice(CITIES),
            "current_title": role_title,
            "years_of_experience": exp,
            "education_level": random.choice(DEGREES),
            "raw_cv_text": f"{role_title} with {exp} years of experience in {dept}. Proficient in {', '.join(key_skills)}. Worked on high-impact data analytics and operational tooling.",
            "linkedin_url": f"https://linkedin.com/in/{fn.lower()}-{ln.lower()}-{i}",
            "github_url": f"https://github.com/{fn.lower()}{ln.lower()}{i}",
            "skills": cand_skills,
            "experiences": [
                {
                    "company": f"TechCorp {random.randint(1, 20)}",
                    "role_title": role_title,
                    "start_date": "2021-01-01",
                    "end_date": None,
                    "is_current": True,
                    "description": f"Led data operations and development of analytics pipelines using {', '.join(key_skills[:3])}.",
                    "technologies": ", ".join(key_skills),
                }
            ],
        })
    return candidates

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic candidates for volume testing.")
    parser.add_argument("--count", type=int, default=50, help="Number of candidate records to generate")
    parser.add_argument("--output", type=str, default="data/raw/candidates_generated.json", help="Output file path")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = generate_candidates(args.count)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generated {args.count} synthetic candidate profiles in: {out_path}")

if __name__ == "__main__":
    main()
