"""
Unit tests for the RAG subsystem.

Tests cover:
  1. Knowledge Base loading (all 7 taxonomy files)
  2. Atomic clause splitting
  3. Requirement classification (heuristic keyword signals)
  4. BM25 and TF-IDF search correctness
  5. RRF rank fusion score computation
  6. Context selector deduplication and budget capping
  7. Full run_rag_pipeline() end-to-end
  8. Prompt assembly with RAG context (build_user_prompt)
  9. JD source-of-truth preservation (RAG must not override JD facts in prompt)
"""
import math
import sys
import os

import pytest

# Ensure the backend app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas.rag_schemas import (
    ClassifiedRequirement,
    KBDocument,
    RAGContext,
    RAGQuery,
    RetrievedSnippet,
)
from app.services.rag.knowledge_base import KnowledgeBase, get_knowledge_base
from app.services.rag.query_generator import (
    classify_clause,
    extract_and_classify,
    generate_queries,
    split_into_clauses,
)
from app.services.rag.retrieval import (
    BM25Index,
    HybridRetriever,
    TFIDFIndex,
    rrf_fuse,
)
from app.services.rag.context_selector import format_snippets_for_prompt, select_context
from app.services.rag import run_rag_pipeline
from app.services.prompt import build_user_prompt


# ─────────────────────────────────────────────────────────────────────────────
# 1. Knowledge Base Loading
# ─────────────────────────────────────────────────────────────────────────────

class TestKnowledgeBaseLoading:
    def test_kb_loads_all_categories(self):
        kb = get_knowledge_base()
        expected = {"experience", "technical_skills", "evidence_evaluation",
                    "roles_seniority", "domains", "job_parameters", "compliance"}
        assert expected.issubset(set(kb.categories())), f"Missing categories: {expected - set(kb.categories())}"

    def test_kb_has_documents_in_each_category(self):
        kb = get_knowledge_base()
        for category in kb.categories():
            docs = kb.get_by_category(category)
            assert len(docs) > 0, f"Category '{category}' has no documents."

    def test_kb_documents_have_required_fields(self):
        kb = get_knowledge_base()
        for doc in kb.get_all():
            assert doc.id, f"Document missing id: {doc}"
            assert doc.category, f"Document missing category: {doc.id}"
            assert doc.title, f"Document missing title: {doc.id}"
            assert doc.content, f"Document missing content: {doc.id}"

    def test_kb_total_document_count(self):
        kb = get_knowledge_base()
        # We have at minimum 5+6+6+6+5+5+6 = 39 documents across 7 taxonomies
        assert len(kb) >= 30, f"Expected ≥30 total documents, got {len(kb)}"

    def test_kb_unknown_category_returns_empty(self):
        kb = get_knowledge_base()
        assert kb.get_by_category("nonexistent_category") == []

    def test_kb_singleton_is_same_object(self):
        kb1 = get_knowledge_base()
        kb2 = get_knowledge_base()
        assert kb1 is kb2, "get_knowledge_base() must return the same singleton."


# ─────────────────────────────────────────────────────────────────────────────
# 2. Clause Splitting
# ─────────────────────────────────────────────────────────────────────────────

class TestClauseSplitting:
    def test_basic_bullet_splitting(self):
        jd = "- 5+ years of Python experience\n- Proficiency in FastAPI\n- Experience with PostgreSQL"
        clauses = split_into_clauses(jd)
        assert len(clauses) == 3
        assert "5+ years of Python experience" in clauses

    def test_numbered_list_splitting(self):
        jd = "1. Design scalable APIs\n2. Collaborate with product team\n3. Write unit tests"
        clauses = split_into_clauses(jd)
        assert len(clauses) == 3

    def test_empty_lines_filtered(self):
        jd = "\n\n5+ years of Python experience\n\n\nProficiency in React\n\n"
        clauses = split_into_clauses(jd)
        assert len(clauses) == 2

    def test_short_lines_filtered(self):
        jd = "ok\nYes\n5+ years of Python experience in production environments"
        clauses = split_into_clauses(jd)
        # 'ok' and 'Yes' should be filtered (< 10 chars)
        assert len(clauses) == 1

    def test_deduplication(self):
        jd = "5+ years of Python experience\n5+ years of Python experience\nProficiency in FastAPI"
        clauses = split_into_clauses(jd)
        assert len(clauses) == 2  # duplicate removed


# ─────────────────────────────────────────────────────────────────────────────
# 3. Requirement Classification
# ─────────────────────────────────────────────────────────────────────────────

class TestRequirementClassification:
    def test_experience_clause_classified(self):
        clause = "5+ years of hands-on experience with Python and backend development"
        req = classify_clause(clause)
        assert req.category == "experience"
        assert req.confidence > 0.5

    def test_technical_skill_classified(self):
        clause = "Proficiency in Python, FastAPI, and PostgreSQL required"
        req = classify_clause(clause)
        assert req.category == "technical_skills"

    def test_compliance_clause_classified(self):
        clause = "Equal opportunity employer, recent graduates welcome, digital native preferred"
        req = classify_clause(clause)
        assert req.category == "compliance"

    def test_seniority_clause_classified(self):
        clause = "Senior Engineer level role with staff-level architectural influence"
        req = classify_clause(clause)
        assert req.category == "roles_seniority"

    def test_job_parameters_classified(self):
        clause = "This is a hybrid role with onsite lab bench work required 3 days per week"
        req = classify_clause(clause)
        assert req.category == "job_parameters"

    def test_domains_classified(self):
        clause = "Experience in fintech or payment processing systems is strongly preferred"
        req = classify_clause(clause)
        assert req.category == "domains"

    def test_unknown_clause_defaults_gracefully(self):
        clause = "This is a general statement with no specific category signals anywhere"
        req = classify_clause(clause)
        assert req.category in {"responsibilities", "experience", "technical_skills",
                                 "roles_seniority", "domains", "job_parameters", "compliance"}
        assert 0.0 <= req.confidence <= 1.0

    def test_extract_and_classify_full_jd(self):
        jd = """
        Senior Software Engineer - FinTech Platform
        5+ years of Python experience required.
        Proficiency in FastAPI, PostgreSQL, and Redis.
        Design and implement scalable payment processing APIs.
        Experience in fintech or banking domain preferred.
        Hybrid role with 3 days onsite per week.
        Equal Opportunity Employer.
        """
        requirements = extract_and_classify(jd)
        assert len(requirements) >= 5
        categories_found = {r.category for r in requirements}
        # Should have classified at least experience, technical_skills, and domains
        assert len(categories_found) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# 4. BM25 and TF-IDF Search
# ─────────────────────────────────────────────────────────────────────────────

_SAMPLE_DOCS = [
    KBDocument(
        id="test-001",
        category="experience",
        title="Years of Experience Standard",
        content="Five years of relevant Python experience means sustained professional usage.",
        keywords=["years", "experience", "python", "relevant", "professional"],
        applicable_roles=["all"],
        metadata={},
    ),
    KBDocument(
        id="test-002",
        category="technical_skills",
        title="Framework Inference Prohibition",
        content="Django experience does not imply Python proficiency and vice versa.",
        keywords=["django", "python", "inference", "framework", "prohibited"],
        applicable_roles=["all"],
        metadata={},
    ),
    KBDocument(
        id="test-003",
        category="compliance",
        title="Age Proxy Detection",
        content="Digital native and recent graduate language may constitute age discrimination.",
        keywords=["digital native", "age", "discrimination", "recent graduate", "eeoc"],
        applicable_roles=["all"],
        metadata={},
    ),
]


class TestBM25Index:
    def test_returns_results_for_matching_query(self):
        idx = BM25Index(_SAMPLE_DOCS)
        results = idx.search("python experience years", top_k=3)
        assert len(results) > 0
        # test-001 should score highest for python+experience+years
        top_idx = results[0][0]
        assert _SAMPLE_DOCS[top_idx].id == "test-001"

    def test_returns_empty_for_unrelated_query(self):
        idx = BM25Index(_SAMPLE_DOCS)
        results = idx.search("zzz xyzxyz nonexistent", top_k=3)
        # Should return nothing (all scores 0)
        assert results == []

    def test_scores_are_positive(self):
        idx = BM25Index(_SAMPLE_DOCS)
        results = idx.search("python framework", top_k=3)
        for _, score in results:
            assert score > 0.0


class TestTFIDFIndex:
    def test_returns_results_for_matching_query(self):
        idx = TFIDFIndex(_SAMPLE_DOCS)
        results = idx.search("age discrimination digital native", top_k=3)
        assert len(results) > 0
        top_idx = results[0][0]
        assert _SAMPLE_DOCS[top_idx].id == "test-003"

    def test_cosine_scores_between_0_and_1(self):
        idx = TFIDFIndex(_SAMPLE_DOCS)
        results = idx.search("python experience", top_k=3)
        for _, score in results:
            assert 0.0 <= score <= 1.0 + 1e-9  # small float tolerance


# ─────────────────────────────────────────────────────────────────────────────
# 5. RRF Rank Fusion
# ─────────────────────────────────────────────────────────────────────────────

class TestRRFFusion:
    def test_rrf_single_list(self):
        ranked = [(0, 1.0), (1, 0.8), (2, 0.5)]
        fused = rrf_fuse([ranked])
        # Score for rank 1 = 1/(60+1)
        assert abs(fused[0][1] - 1 / 61) < 1e-9
        assert fused[0][0] == 0

    def test_rrf_two_lists_agreement_boosts(self):
        list1 = [(0, 1.0), (1, 0.5)]
        list2 = [(0, 0.9), (1, 0.3)]
        fused = rrf_fuse([list1, list2])
        # doc 0 is rank 1 in both lists → highest RRF
        assert fused[0][0] == 0
        expected_score = 1 / (60 + 1) + 1 / (60 + 1)
        assert abs(fused[0][1] - expected_score) < 1e-9

    def test_rrf_two_lists_disagreement(self):
        # Doc 0 is #1 in list1 but #2 in list2
        # Doc 1 is #2 in list1 but #1 in list2
        list1 = [(0, 1.0), (1, 0.5)]
        list2 = [(1, 0.9), (0, 0.3)]
        fused = rrf_fuse([list1, list2])
        assert fused[0][0] in {0, 1}  # one of them wins

    def test_rrf_empty_lists(self):
        assert rrf_fuse([]) == []
        assert rrf_fuse([[]]) == []


# ─────────────────────────────────────────────────────────────────────────────
# 6. Context Selector
# ─────────────────────────────────────────────────────────────────────────────

def _make_snippet(doc_id: str, category: str, rrf_score: float) -> RetrievedSnippet:
    return RetrievedSnippet(
        document_id=doc_id,
        category=category,  # type: ignore[arg-type]
        title=f"Title {doc_id}",
        content=f"Content for {doc_id}",
        rrf_score=rrf_score,
    )


def _make_classified(clause: str) -> ClassifiedRequirement:
    return ClassifiedRequirement(clause=clause, category="experience", confidence=0.8)


class TestContextSelector:
    def test_deduplication(self):
        snippets = [
            (_make_snippet("doc-A", "experience", 0.05), "clause 1"),
            (_make_snippet("doc-A", "experience", 0.03), "clause 2"),  # duplicate
            (_make_snippet("doc-B", "compliance", 0.04), "clause 3"),
        ]
        classified = [_make_classified("test")]
        ctx = select_context(snippets, classified, max_snippets=8)
        ids = [s.document_id for s in ctx.selected_snippets]
        assert ids.count("doc-A") == 1  # deduplicated
        assert ids.count("doc-B") == 1

    def test_budget_capping(self):
        snippets = [
            (_make_snippet(f"doc-{i}", "experience", 0.1 - i * 0.005), f"clause {i}")
            for i in range(20)
        ]
        classified = [_make_classified("test")]
        ctx = select_context(snippets, classified, max_snippets=5)
        assert ctx.budget_used <= 5
        assert len(ctx.selected_snippets) <= 5

    def test_aggregation_boosts_duplicate_docs(self):
        snippets = [
            (_make_snippet("doc-A", "experience", 0.05), "clause 1"),
            (_make_snippet("doc-A", "experience", 0.04), "clause 2"),  # same doc, different query
            (_make_snippet("doc-B", "compliance", 0.06), "clause 3"),
        ]
        classified = [_make_classified("test")]
        ctx = select_context(snippets, classified, max_snippets=8)
        a_snippet = next(s for s in ctx.selected_snippets if s.document_id == "doc-A")
        # Aggregated score = 0.05 + 0.04 = 0.09 > doc-B score 0.06
        assert a_snippet.rrf_score > 0.06

    def test_format_snippets_for_prompt(self):
        snippets = [
            _make_snippet("doc-A", "experience", 0.1),
            _make_snippet("doc-B", "compliance", 0.08),
        ]
        formatted = format_snippets_for_prompt(snippets)
        assert "[Experience]" in formatted
        assert "[Compliance]" in formatted
        assert "Content for doc-A" in formatted

    def test_empty_snippets_returns_empty_string(self):
        assert format_snippets_for_prompt([]) == ""


# ─────────────────────────────────────────────────────────────────────────────
# 7. Full Pipeline End-to-End
# ─────────────────────────────────────────────────────────────────────────────

class TestFullPipeline:
    def test_run_rag_pipeline_technical_jd(self):
        jd = """
        Senior Backend Engineer
        5+ years of Python development experience required.
        Proficiency in FastAPI, PostgreSQL, and Redis.
        Experience with AWS (ECS, S3, SQS) and Kubernetes.
        Design and maintain scalable microservices in a SaaS environment.
        Hybrid role with 2 days onsite per week.
        """
        ctx = run_rag_pipeline(jd, max_snippets=8)
        assert isinstance(ctx, RAGContext)
        assert len(ctx.classified_requirements) >= 3
        assert ctx.total_retrieved >= 0
        assert ctx.budget_used == len(ctx.selected_snippets)
        assert ctx.budget_used <= 8

    def test_run_rag_pipeline_compliance_jd(self):
        jd = """
        Junior Developer — Energetic team, digital natives preferred.
        Recent graduates welcome.
        Fast-paced startup environment with lots of ambiguity.
        """
        ctx = run_rag_pipeline(jd, max_snippets=8)
        # Should retrieve compliance + experience + startup-fit snippets
        assert len(ctx.classified_requirements) >= 2

    def test_run_rag_pipeline_hardware_jd(self):
        jd = """
        Embedded Systems Engineer
        5+ years of C/C++ firmware development on ARM microcontrollers.
        Hands-on experience with oscilloscopes, JTAG debuggers, and PCB bring-up.
        Lab-based role, on-site 5 days per week.
        """
        ctx = run_rag_pipeline(jd, max_snippets=8)
        assert isinstance(ctx, RAGContext)
        # Should classify hardware/lab/embedded signals
        categories = {r.category for r in ctx.classified_requirements}
        assert len(categories) >= 2

    def test_run_rag_pipeline_empty_jd_returns_empty_context(self):
        ctx = run_rag_pipeline("   ", max_snippets=8)
        assert len(ctx.classified_requirements) == 0
        assert len(ctx.selected_snippets) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 8 & 9. Prompt Assembly and Source-of-Truth Preservation
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptAssembly:
    def test_prompt_without_rag(self):
        prompt = build_user_prompt("Engineer with Python skills needed.")
        assert "<jd_content>" in prompt
        assert "Engineer with Python skills needed." in prompt
        assert "domain_knowledge_context" not in prompt

    def test_prompt_with_rag_context(self):
        rag_context = "[Experience] Relevant Experience\nMust have 5 years relevant Python."
        prompt = build_user_prompt("5+ years Python required.", rag_context=rag_context)
        assert "<jd_content>" in prompt
        assert "<domain_knowledge_context>" in prompt
        assert "SUPPORTING INTERPRETATION GUIDANCE ONLY" in prompt
        assert "NEVER override" in prompt
        assert rag_context in prompt

    def test_jd_content_appears_before_domain_context(self):
        """Raw JD must come before domain knowledge context in the prompt."""
        jd = "Senior Python Engineer needed."
        rag = "Some domain context."
        prompt = build_user_prompt(jd, rag_context=rag)
        jd_pos = prompt.find("<jd_content>")
        rag_pos = prompt.find("<domain_knowledge_context>")
        assert jd_pos < rag_pos, "JD content must appear before domain knowledge context."

    def test_empty_rag_context_not_injected(self):
        prompt = build_user_prompt("Some JD text.", rag_context="")
        assert "domain_knowledge_context" not in prompt

    def test_whitespace_only_rag_context_not_injected(self):
        prompt = build_user_prompt("Some JD text.", rag_context="   \n  ")
        assert "domain_knowledge_context" not in prompt

    def test_rag_context_does_not_duplicate_jd_content(self):
        """
        Source-of-truth preservation: the JD content section must not be
        duplicated inside domain_knowledge_context.
        """
        jd = "5+ years Python required. On-site in New York."
        rag = "Framework inference is prohibited."
        prompt = build_user_prompt(jd, rag_context=rag)
        # JD text should appear exactly once (inside <jd_content>)
        assert prompt.count("5+ years Python required") == 1


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
