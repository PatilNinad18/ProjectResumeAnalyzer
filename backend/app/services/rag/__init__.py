"""
RAG subsystem public interface.

Import from here rather than from internal submodules directly.
"""
from app.schemas.rag_schemas import (
    ClassifiedRequirement,
    KBDocument,
    RAGContext,
    RAGQuery,
    RetrievedSnippet,
)
from app.services.rag.context_selector import format_snippets_for_prompt, select_context
from app.services.rag.knowledge_base import KnowledgeBase, get_knowledge_base
from app.services.rag.query_generator import (
    classify_clause,
    extract_and_classify,
    generate_queries,
    split_into_clauses,
)
from app.services.rag.retrieval import HybridRetriever

__all__ = [
    # Schemas
    "KBDocument",
    "ClassifiedRequirement",
    "RAGQuery",
    "RetrievedSnippet",
    "RAGContext",
    # Knowledge Base
    "KnowledgeBase",
    "get_knowledge_base",
    # Query generation
    "split_into_clauses",
    "classify_clause",
    "extract_and_classify",
    "generate_queries",
    # Retrieval
    "HybridRetriever",
    # Context selection
    "select_context",
    "format_snippets_for_prompt",
]


def run_rag_pipeline(jd_text: str, max_snippets: int = 8) -> RAGContext:
    """
    Convenience function: full RAG pipeline from raw JD text → RAGContext.

    Stages:
      1. Atomic extraction & classification
      2. Query generation
      3. Hybrid retrieval (BM25 + TF-IDF + RRF) per query
      4. Context selection (dedup, threshold, budget cap)

    Returns RAGContext with selected_snippets ready for prompt injection.
    """
    # Stage 1 & 2
    classified = extract_and_classify(jd_text)
    queries = generate_queries(classified)

    # Stage 3
    retriever = HybridRetriever()
    all_results = retriever.search_all(queries, top_k_per_query=3)

    # Stage 4
    context = select_context(
        retrieval_results=all_results,
        classified_requirements=classified,
        max_snippets=max_snippets,
    )
    return context
