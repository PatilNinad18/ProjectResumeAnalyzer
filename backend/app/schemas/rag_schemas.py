"""
Pydantic models for the RAG subsystem.

These models define the data contracts for:
  - Knowledge Base documents (KBDocument)
  - Classified atomic requirements extracted from a raw JD (ClassifiedRequirement)
  - Search queries generated per classified requirement (RAGQuery)
  - Individual snippets retrieved from the KB (RetrievedSnippet)
  - The final assembled RAG context handed to the Context Creator (RAGContext)
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Requirement category literals (aligned with knowledge-base taxonomy files)
# ---------------------------------------------------------------------------
RequirementCategory = Literal[
    "experience",
    "technical_skills",
    "responsibilities",
    "evidence_evaluation",
    "roles_seniority",
    "domains",
    "job_parameters",
    "compliance",
]


# ---------------------------------------------------------------------------
# Knowledge Base document (mirrors each entry in the 7 JSON taxonomy files)
# ---------------------------------------------------------------------------
class KBDocument(BaseModel):
    """A single knowledge-base document stored in one of the 7 taxonomy files."""

    id: str = Field(..., description="Unique document identifier within the KB.")
    category: RequirementCategory = Field(..., description="Taxonomy category this document belongs to.")
    title: str = Field(..., description="Short human-readable title for the document.")
    content: str = Field(..., description="Full text content used for retrieval and injection.")
    keywords: List[str] = Field(default_factory=list, description="Keyword tokens for BM25 sparse retrieval.")
    applicable_roles: List[str] = Field(
        default_factory=list,
        description="Roles or seniority levels this document is especially relevant for.",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra metadata.")


# ---------------------------------------------------------------------------
# Atomic classified requirement extracted from the raw JD
# ---------------------------------------------------------------------------
class ClassifiedRequirement(BaseModel):
    """One atomic clause extracted from the raw JD and tagged with a category."""

    clause: str = Field(..., description="The atomic JD clause/statement as extracted.")
    category: RequirementCategory = Field(..., description="Classified requirement category.")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Classifier confidence in the category assignment (0-1).",
    )


# ---------------------------------------------------------------------------
# Search query generated for one classified requirement
# ---------------------------------------------------------------------------
class RAGQuery(BaseModel):
    """A search query derived from a ClassifiedRequirement for KB retrieval."""

    query_text: str = Field(..., description="The search query string.")
    category: RequirementCategory = Field(..., description="Category to search within.")
    source_clause: str = Field(..., description="The originating JD clause that generated this query.")


# ---------------------------------------------------------------------------
# A single retrieved snippet from the KB with its retrieval metadata
# ---------------------------------------------------------------------------
class RetrievedSnippet(BaseModel):
    """One KB document snippet selected after RRF rank fusion and deduplication."""

    document_id: str = Field(..., description="ID of the source KBDocument.")
    category: RequirementCategory = Field(..., description="Category of the source document.")
    title: str = Field(..., description="Title of the source document.")
    content: str = Field(..., description="Content of the snippet.")
    rrf_score: float = Field(default=0.0, description="Final RRF score after rank fusion.")
    bm25_rank: Optional[int] = Field(default=None, description="BM25 rank (1-based), if retrieved.")
    dense_rank: Optional[int] = Field(default=None, description="Dense vector rank (1-based), if retrieved.")


# ---------------------------------------------------------------------------
# Final assembled RAG context produced by the RAG pipeline
# ---------------------------------------------------------------------------
class RAGContext(BaseModel):
    """The full RAG output handed to the Context Creator (prompt.py)."""

    classified_requirements: List[ClassifiedRequirement] = Field(
        default_factory=list,
        description="All atomic requirements classified from the raw JD.",
    )
    selected_snippets: List[RetrievedSnippet] = Field(
        default_factory=list,
        description="Top-K deduplicated snippets selected after RRF for prompt injection.",
    )
    total_retrieved: int = Field(default=0, description="Total documents retrieved before deduplication.")
    budget_used: int = Field(default=0, description="Number of snippets injected (≤ max_snippets cap).")
