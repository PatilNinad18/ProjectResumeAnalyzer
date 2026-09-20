"""
Atomic clause extractor, requirement classifier, and RAG query generator.

Pipeline:
  raw_jd_text
    ├── split_into_clauses()       → List[str]  (atomic JD statements)
    ├── classify_clause()          → ClassifiedRequirement (category + confidence)
    └── generate_queries()         → List[RAGQuery]  (targeted KB search queries)

Design goals:
  - Zero external dependencies (pure Python, stdlib only).
  - Heuristic classifier uses keyword signals per category — no LLM call needed
    for classification so there is no added latency or cost.
  - Deterministic and testable: same JD → same classified requirements always.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from app.schemas.rag_schemas import ClassifiedRequirement, RAGQuery, RequirementCategory

# ---------------------------------------------------------------------------
# Keyword signal tables: category → (keywords list, base_score_per_hit)
# ---------------------------------------------------------------------------

_CATEGORY_SIGNALS: Dict[str, List[str]] = {
    "experience": [
        "years of experience", "years experience", "years of", "yrs", "minimum experience",
        "prior experience", "background in", "proven experience", "track record",
        "demonstrated experience", "hands-on experience", "work experience",
    ],
    "technical_skills": [
        "python", "java", "javascript", "typescript", "c++", "c#", "go", "golang", "rust",
        "react", "angular", "vue", "node", "django", "flask", "fastapi", "spring",
        "sql", "postgresql", "mysql", "mongodb", "redis", "kafka", "rabbitmq",
        "aws", "gcp", "azure", "kubernetes", "docker", "terraform", "ansible",
        "git", "ci/cd", "jenkins", "github actions", "linux", "bash",
        "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy",
        "oscilloscope", "fpga", "embedded", "firmware", "pcb", "jtag",
        "proficiency in", "experience with", "skilled in", "knowledge of",
        "technical skills", "tech stack", "tools:", "technologies:",
    ],
    "responsibilities": [
        "design", "develop", "build", "implement", "maintain", "deploy", "manage",
        "lead", "collaborate", "work with", "responsible for", "own", "ownership",
        "drive", "deliver", "support", "review", "architect", "optimize", "scale",
        "integrate", "test", "debug", "monitor", "operate", "contribute",
        "duties", "responsibilities", "accountable", "ensure",
    ],
    "roles_seniority": [
        "senior", "staff", "principal", "lead", "junior", "mid-level", "entry-level",
        "director", "manager", "architect", "head of", "vp", "associate",
        "individual contributor", "ic", "tech lead", "engineering manager",
        "new grad", "graduate", "intern", "seniority",
    ],
    "domains": [
        "fintech", "finance", "banking", "payment", "healthcare", "medical", "hipaa",
        "e-commerce", "retail", "logistics", "supply chain", "manufacturing",
        "embedded systems", "hardware", "iot", "robotics", "autonomous",
        "saas", "platform", "enterprise", "b2b", "b2c", "marketplace",
        "cybersecurity", "security", "defense", "aerospace", "edtech", "education",
        "ai", "machine learning", "data science", "analytics", "big data",
        "industry", "sector", "domain",
    ],
    "job_parameters": [
        "onsite", "on-site", "remote", "hybrid", "work from home", "wfh",
        "travel", "travel required", "client site", "office days", "in-office",
        "startup", "fast-paced", "ambiguity", "wear many hats", "high ownership",
        "on-call", "shift", "24/7", "after hours", "availability",
        "lab", "bench work", "physical", "equipment", "in-person",
        "contract", "part-time", "full-time", "freelance",
    ],
    "compliance": [
        "equal opportunity", "eeo", "eeoc", "ada", "disability", "accommodation",
        "visa", "work authorization", "authorized to work", "sponsorship",
        "no sponsorship", "citizenship", "security clearance", "clearance required",
        "background check", "drug test",
        "recent graduate", "fresh graduate", "new grad", "digital native",
        "young", "energetic team", "class of", "graduation year",
        "diverse", "inclusion", "deia", "affirmative action",
    ],
}


def _score_clause(clause: str) -> List[Tuple[str, float]]:
    """
    Score a clause against each category's keyword signals.
    Returns list of (category, score) tuples, sorted descending.
    """
    lower = clause.lower()
    scores: Dict[str, float] = {cat: 0.0 for cat in _CATEGORY_SIGNALS}
    for category, keywords in _CATEGORY_SIGNALS.items():
        for kw in keywords:
            if kw in lower:
                # longer keywords are more specific → higher weight
                scores[category] += 1.0 + len(kw.split()) * 0.2
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def classify_clause(clause: str) -> ClassifiedRequirement:
    """
    Classify an atomic JD clause into one of the 7 requirement categories.

    Fallback: if no signal fires strongly, defaults to "responsibilities"
    (the most general category).
    """
    ranked = _score_clause(clause)
    best_cat, best_score = ranked[0]
    second_cat, second_score = ranked[1] if len(ranked) > 1 else ("", 0.0)

    if best_score == 0.0:
        # No signals matched → default to responsibilities
        return ClassifiedRequirement(clause=clause, category="responsibilities", confidence=0.3)

    # Confidence = how much better the top category is vs the runner-up
    total = best_score + second_score + 1e-9
    confidence = min(0.95, best_score / total + 0.1)

    return ClassifiedRequirement(
        clause=clause,
        category=best_cat,  # type: ignore[arg-type]
        confidence=round(confidence, 3),
    )


def split_into_clauses(jd_text: str) -> List[str]:
    """
    Split raw JD text into atomic requirement clauses.

    Strategy:
      1. Split on newlines first (each line is a candidate clause).
      2. Within long lines, split on bullet/list punctuation.
      3. Filter out empty/boilerplate fragments.
    """
    # Normalise line endings
    text = jd_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    clauses: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Strip common bullet characters
        stripped = re.sub(r"^[\-\*\•\·\◦\–\—\▪\►\✓\✔\✗\+]\s+", "", stripped)
        stripped = re.sub(r"^\d+[\.\)]\s+", "", stripped)  # "1. " or "1) "
        if len(stripped) < 10:
            continue  # too short to be a meaningful clause
        # Split on semicolons or long compound sentences if > 200 chars
        if len(stripped) > 200 and (";" in stripped or " and " in stripped.lower()):
            sub_parts = re.split(r";\s*| and | & ", stripped, flags=re.IGNORECASE)
            for part in sub_parts:
                part = part.strip()
                if len(part) >= 10:
                    clauses.append(part)
        else:
            clauses.append(stripped)

    # Deduplicate while preserving order
    seen = set()
    unique: List[str] = []
    for c in clauses:
        key = c.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def generate_queries(requirements: List[ClassifiedRequirement]) -> List[RAGQuery]:
    """
    Generate targeted KB search queries from classified requirements.

    One query per ClassifiedRequirement. The query text is the clause itself
    (the KB retrieval will match it against document content + keywords).
    Higher-confidence classifications produce more targeted queries.
    """
    queries: List[RAGQuery] = []
    for req in requirements:
        queries.append(
            RAGQuery(
                query_text=req.clause,
                category=req.category,
                source_clause=req.clause,
            )
        )
    return queries


def extract_and_classify(jd_text: str) -> List[ClassifiedRequirement]:
    """
    Full extraction + classification pipeline for a raw JD.

    Returns a list of ClassifiedRequirements, one per atomic clause.
    """
    clauses = split_into_clauses(jd_text)
    return [classify_clause(clause) for clause in clauses]
