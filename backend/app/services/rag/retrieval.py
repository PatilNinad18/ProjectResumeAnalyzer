"""
Hybrid retrieval engine: Sparse (BM25) + Dense (TF-IDF cosine) + RRF Rank Fusion.

Architecture:
  HybridRetriever
    ├── BM25Index          — sparse keyword retrieval (pure Python, no external deps)
    ├── TFIDFIndex         — dense vector retrieval (stdlib math, cosine similarity)
    └── rrf_fuse()         — Reciprocal Rank Fusion (k=60) merges both ranked lists

Design:
  - Zero external dependencies (no rank-bm25, no faiss, no sentence-transformers).
  - BM25 is implemented with standard TF-IDF variant using log-normalised IDF.
  - Dense search uses pre-computed TF-IDF vectors with cosine similarity.
  - Both indexes are built lazily on first query, keyed by category for targeted search.
  - When the KB is loaded once via get_knowledge_base(), indexes are built once per
    process (no repeated I/O).

RRF Formula (Cormack et al., 2009):
  RRF_Score(d) = Σ_m  1 / (k + r_m(d))
  where k=60, r_m(d) = 1-based rank of document d in ranking list m.
"""
from __future__ import annotations

import math
import re
import string
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from app.schemas.rag_schemas import KBDocument, RAGQuery, RetrievedSnippet
from app.services.rag.knowledge_base import get_knowledge_base

# RRF smoothing constant (standard value from the original paper)
_RRF_K: int = 60


# ---------------------------------------------------------------------------
# Tokenisation helpers
# ---------------------------------------------------------------------------

def _tokenise(text: str) -> List[str]:
    """Lowercase, remove punctuation, split into tokens."""
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return [t for t in text.split() if len(t) > 1]


_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "this", "that", "these", "those",
    "and", "or", "but", "not", "no", "as", "if", "it", "its", "they",
    "their", "them", "we", "our", "you", "your", "he", "she", "his", "her",
    "who", "which", "what", "when", "where", "how", "all", "any", "both",
    "each", "more", "most", "other", "some", "such", "than", "then", "so",
})


def _filter_tokens(tokens: List[str]) -> List[str]:
    return [t for t in tokens if t not in _STOP_WORDS]


# ---------------------------------------------------------------------------
# BM25 Index (Okapi BM25 with k1=1.5, b=0.75)
# ---------------------------------------------------------------------------

class BM25Index:
    """
    Okapi BM25 sparse retrieval index over a list of KBDocuments.

    Indexes the combined content of: title + content + keywords.
    """

    _k1: float = 1.5
    _b: float = 0.75

    def __init__(self, documents: List[KBDocument]) -> None:
        self._documents = documents
        self._doc_tokens: List[List[str]] = []
        self._doc_freqs: List[Dict[str, int]] = []
        self._idf: Dict[str, float] = {}
        self._avg_dl: float = 0.0
        self._n: int = len(documents)
        self._build()

    def _doc_text(self, doc: KBDocument) -> str:
        parts = [doc.title, doc.content] + doc.keywords
        return " ".join(parts)

    def _build(self) -> None:
        # Tokenise each document
        for doc in self._documents:
            tokens = _filter_tokens(_tokenise(self._doc_text(doc)))
            self._doc_tokens.append(tokens)
            freq: Dict[str, int] = defaultdict(int)
            for t in tokens:
                freq[t] += 1
            self._doc_freqs.append(dict(freq))

        if not self._doc_tokens:
            return

        self._avg_dl = sum(len(t) for t in self._doc_tokens) / max(len(self._doc_tokens), 1)

        # IDF: log( (N - df + 0.5) / (df + 0.5) + 1 )
        df: Dict[str, int] = defaultdict(int)
        for freq in self._doc_freqs:
            for term in freq:
                df[term] += 1
        for term, count in df.items():
            self._idf[term] = math.log((self._n - count + 0.5) / (count + 0.5) + 1)

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """
        Return (doc_index, bm25_score) sorted descending, up to top_k results.
        """
        query_tokens = _filter_tokens(_tokenise(query))
        scores: List[float] = []
        for i, freq in enumerate(self._doc_freqs):
            dl = len(self._doc_tokens[i])
            score = 0.0
            for qt in query_tokens:
                if qt not in self._idf:
                    continue
                tf = freq.get(qt, 0)
                numerator = tf * (self._k1 + 1)
                denominator = tf + self._k1 * (1 - self._b + self._b * dl / max(self._avg_dl, 1))
                score += self._idf[qt] * numerator / max(denominator, 1e-9)
            scores.append(score)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(idx, sc) for idx, sc in ranked[:top_k] if sc > 0.0]


# ---------------------------------------------------------------------------
# TF-IDF + Cosine Similarity Dense Index
# ---------------------------------------------------------------------------

class TFIDFIndex:
    """
    TF-IDF vector index for dense (cosine similarity) retrieval.

    Uses log-normalised TF and smooth IDF. Each document is represented as a
    sparse TF-IDF vector; query-document cosine similarity is computed at
    search time.
    """

    def __init__(self, documents: List[KBDocument]) -> None:
        self._documents = documents
        self._n = len(documents)
        self._idf: Dict[str, float] = {}
        self._doc_vectors: List[Dict[str, float]] = []
        self._build()

    def _doc_text(self, doc: KBDocument) -> str:
        parts = [doc.title, doc.content] + doc.keywords
        return " ".join(parts)

    def _build(self) -> None:
        if not self._documents:
            return
        tokenised = [_filter_tokens(_tokenise(self._doc_text(d))) for d in self._documents]

        # IDF: log( N / df ) + 1  (smooth IDF)
        df: Dict[str, int] = defaultdict(int)
        for tokens in tokenised:
            for t in set(tokens):
                df[t] += 1
        for term, count in df.items():
            self._idf[term] = math.log(self._n / max(count, 1)) + 1.0

        # TF-IDF vectors (log-normalised TF: 1 + log(tf) if tf > 0 else 0)
        for tokens in tokenised:
            tf_raw: Dict[str, int] = defaultdict(int)
            for t in tokens:
                tf_raw[t] += 1
            vec: Dict[str, float] = {}
            for term, count in tf_raw.items():
                tf = 1.0 + math.log(count) if count > 0 else 0.0
                vec[term] = tf * self._idf.get(term, 1.0)
            self._doc_vectors.append(vec)

    @staticmethod
    def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
        dot = sum(a.get(t, 0.0) * v for t, v in b.items())
        norm_a = math.sqrt(sum(v * v for v in a.values())) or 1e-9
        norm_b = math.sqrt(sum(v * v for v in b.values())) or 1e-9
        return dot / (norm_a * norm_b)

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """Return (doc_index, cosine_similarity) sorted descending, up to top_k."""
        query_tokens = _filter_tokens(_tokenise(query))
        if not query_tokens:
            return []

        tf_raw: Dict[str, int] = defaultdict(int)
        for t in query_tokens:
            tf_raw[t] += 1
        qvec: Dict[str, float] = {}
        for term, count in tf_raw.items():
            tf = 1.0 + math.log(count) if count > 0 else 0.0
            qvec[term] = tf * self._idf.get(term, 1.0)

        sims: List[Tuple[int, float]] = []
        for i, dvec in enumerate(self._doc_vectors):
            sim = self._cosine(qvec, dvec)
            sims.append((i, sim))
        return sorted(sims, key=lambda x: x[1], reverse=True)[:top_k]


# ---------------------------------------------------------------------------
# RRF Rank Fusion
# ---------------------------------------------------------------------------

def rrf_fuse(
    ranked_lists: List[List[Tuple[int, float]]],
    k: int = _RRF_K,
) -> List[Tuple[int, float]]:
    """
    Reciprocal Rank Fusion over multiple ranked lists.

    Each ranked list is a sequence of (doc_index, score) tuples ordered by
    descending relevance. The final RRF score for document d is:
        RRF(d) = Σ_m  1 / (k + r_m(d))
    where r_m(d) is the 1-based rank of d in list m.

    Returns (doc_index, rrf_score) sorted descending.
    """
    rrf_scores: Dict[int, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank_idx, (doc_idx, _) in enumerate(ranked):
            rrf_scores[doc_idx] += 1.0 / (k + rank_idx + 1)  # rank is 1-based → +1
    return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)


# ---------------------------------------------------------------------------
# Hybrid Retriever
# ---------------------------------------------------------------------------

class HybridRetriever:
    """
    Hybrid retriever that combines BM25 sparse + TF-IDF dense retrieval via RRF.

    Indexes are built lazily per category and cached in-process.
    """

    def __init__(self) -> None:
        self._kb = get_knowledge_base()
        # Cache per category: { category: (BM25Index, TFIDFIndex, docs) }
        self._indexes: Dict[str, Tuple[BM25Index, TFIDFIndex, List[KBDocument]]] = {}

    def _get_indexes(self, category: str) -> Tuple[BM25Index, TFIDFIndex, List[KBDocument]]:
        if category not in self._indexes:
            docs = self._kb.get_by_category(category)
            if not docs:
                # Fall back to all documents if category is unknown
                docs = self._kb.get_all()
            bm25 = BM25Index(docs)
            tfidf = TFIDFIndex(docs)
            self._indexes[category] = (bm25, tfidf, docs)
        return self._indexes[category]

    def search(
        self,
        query: RAGQuery,
        top_k: int = 5,
        include_cross_category: bool = False,
    ) -> List[RetrievedSnippet]:
        """
        Run hybrid search for a single RAGQuery.

        Args:
            query: The RAGQuery containing query_text and category.
            top_k: Number of top results to return after RRF fusion.
            include_cross_category: If True, also searches across all categories.

        Returns:
            List of RetrievedSnippet ordered by descending RRF score.
        """
        bm25_idx, tfidf_idx, docs = self._get_indexes(query.category)

        bm25_results = bm25_idx.search(query.query_text, top_k=top_k * 2)
        tfidf_results = tfidf_idx.search(query.query_text, top_k=top_k * 2)

        fused = rrf_fuse([bm25_results, tfidf_results])

        snippets: List[RetrievedSnippet] = []
        bm25_rank_map = {idx: rank + 1 for rank, (idx, _) in enumerate(bm25_results)}
        tfidf_rank_map = {idx: rank + 1 for rank, (idx, _) in enumerate(tfidf_results)}

        for doc_idx, rrf_score in fused[:top_k]:
            if doc_idx >= len(docs):
                continue
            doc = docs[doc_idx]
            snippets.append(
                RetrievedSnippet(
                    document_id=doc.id,
                    category=doc.category,
                    title=doc.title,
                    content=doc.content,
                    rrf_score=round(rrf_score, 6),
                    bm25_rank=bm25_rank_map.get(doc_idx),
                    dense_rank=tfidf_rank_map.get(doc_idx),
                )
            )
        return snippets

    def search_all(
        self,
        queries: List[RAGQuery],
        top_k_per_query: int = 3,
    ) -> List[Tuple[RetrievedSnippet, str]]:
        """
        Run search for all queries, collecting (snippet, source_clause) pairs.
        Used by context_selector to aggregate across all classified requirements.
        """
        results: List[Tuple[RetrievedSnippet, str]] = []
        for query in queries:
            snippets = self.search(query, top_k=top_k_per_query)
            for snippet in snippets:
                results.append((snippet, query.source_clause))
        return results
