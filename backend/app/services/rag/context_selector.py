"""
Context selector: deduplication, cross-query aggregation, and budget capping.

After HybridRetriever produces (snippet, source_clause) pairs for all queries,
this module:
  1. Deduplicates: keeps the highest-scoring occurrence of each document_id.
  2. Aggregates RRF scores across queries that retrieved the same document.
  3. Caps selection to max_snippets (default 8 per prompt budget).
  4. Returns an ordered list of RetrievedSnippet ready for prompt injection.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from app.schemas.rag_schemas import RAGContext, RAGQuery, RetrievedSnippet, ClassifiedRequirement

_DEFAULT_MAX_SNIPPETS: int = 8
_DEFAULT_TOP_K_PER_QUERY: int = 3
_MIN_RRF_THRESHOLD: float = 0.005  # filter out noise-level retrievals


def select_context(
    retrieval_results: List[Tuple[RetrievedSnippet, str]],
    classified_requirements: List[ClassifiedRequirement],
    max_snippets: int = _DEFAULT_MAX_SNIPPETS,
    min_rrf_threshold: float = _MIN_RRF_THRESHOLD,
) -> RAGContext:
    """
    Deduplicate, aggregate, threshold, and cap retrieval results.

    Args:
        retrieval_results: All (RetrievedSnippet, source_clause) pairs from retriever.
        classified_requirements: Original classified requirements (for RAGContext).
        max_snippets: Maximum snippets to inject into the prompt (budget cap).
        min_rrf_threshold: Minimum RRF score; snippets below this are discarded.

    Returns:
        RAGContext with selected_snippets ordered by descending aggregated RRF score.
    """
    total_retrieved = len(retrieval_results)

    # Aggregate: sum RRF scores across all queries that returned the same document
    aggregated: Dict[str, RetrievedSnippet] = {}
    for snippet, _ in retrieval_results:
        doc_id = snippet.document_id
        if doc_id in aggregated:
            # Accumulate RRF score (document was retrieved by multiple queries)
            existing = aggregated[doc_id]
            aggregated[doc_id] = existing.model_copy(
                update={"rrf_score": existing.rrf_score + snippet.rrf_score}
            )
        else:
            aggregated[doc_id] = snippet

    # Apply minimum RRF threshold
    above_threshold = [
        s for s in aggregated.values() if s.rrf_score >= min_rrf_threshold
    ]

    # Sort by aggregated RRF score descending
    sorted_snippets = sorted(above_threshold, key=lambda s: s.rrf_score, reverse=True)

    # Cap to budget
    selected = sorted_snippets[:max_snippets]

    return RAGContext(
        classified_requirements=classified_requirements,
        selected_snippets=selected,
        total_retrieved=total_retrieved,
        budget_used=len(selected),
    )


def format_snippets_for_prompt(snippets: List[RetrievedSnippet]) -> str:
    """
    Format selected snippets as a clean domain_knowledge_context block
    for injection into the LLM prompt.

    Each snippet is rendered as:
        [Category: <category>] <title>
        <content>
    Separated by blank lines.
    """
    if not snippets:
        return ""

    parts: List[str] = []
    for snippet in snippets:
        category_label = snippet.category.replace("_", " ").title()
        parts.append(
            f"[{category_label}] {snippet.title}\n{snippet.content}"
        )

    return "\n\n".join(parts)
