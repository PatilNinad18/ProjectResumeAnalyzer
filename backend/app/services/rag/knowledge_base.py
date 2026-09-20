"""
Knowledge Base loader and in-memory registry.

Loads all 7 taxonomy JSON files from the knowledge_base/ directory on first
access and caches them in memory. Provides lookup by category and full
flat document list for retrieval indexing.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from app.schemas.rag_schemas import KBDocument, RequirementCategory

logger = logging.getLogger("jd_agent.rag.knowledge_base")

_KB_DIR = Path(__file__).parent / "knowledge_base"

_TAXONOMY_FILES: Dict[str, str] = {
    "experience": "1_experience.json",
    "technical_skills": "2_skills.json",
    "evidence_evaluation": "3_evidence_evaluation.json",
    "roles_seniority": "4_roles_seniority.json",
    "domains": "5_domains.json",
    "job_parameters": "6_job_parameters.json",
    "compliance": "7_compliance.json",
}


class KnowledgeBase:
    """In-memory Knowledge Base with by-category lookup."""

    def __init__(self) -> None:
        self._by_category: Dict[str, List[KBDocument]] = {}
        self._all_documents: List[KBDocument] = []
        self._load()

    def _load(self) -> None:
        for category, filename in _TAXONOMY_FILES.items():
            filepath = _KB_DIR / filename
            if not filepath.exists():
                logger.warning("KB taxonomy file not found: %s — skipping.", filepath)
                continue
            try:
                raw = json.loads(filepath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("Failed to load KB file %s: %s", filepath, exc)
                continue
            docs: List[KBDocument] = []
            for entry in raw:
                try:
                    doc = KBDocument.model_validate(entry)
                    docs.append(doc)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Skipping malformed KB entry in %s: %s", filename, exc)
            self._by_category[category] = docs
            self._all_documents.extend(docs)
            logger.debug("Loaded %d documents from %s (category=%s)", len(docs), filename, category)

        logger.info(
            "KnowledgeBase loaded: %d total documents across %d categories.",
            len(self._all_documents),
            len(self._by_category),
        )

    def get_by_category(self, category: str) -> List[KBDocument]:
        """Return all documents for a given category. Returns [] if unknown."""
        return self._by_category.get(category, [])

    def get_all(self) -> List[KBDocument]:
        """Return all documents across all categories."""
        return list(self._all_documents)

    def categories(self) -> List[str]:
        """Return list of loaded categories."""
        return list(self._by_category.keys())

    def __len__(self) -> int:
        return len(self._all_documents)


@lru_cache(maxsize=1)
def get_knowledge_base() -> KnowledgeBase:
    """Return the singleton KnowledgeBase instance (loaded once, cached forever)."""
    return KnowledgeBase()
