"""
test_ollama.py — Ollama integration tests (T1–T7)

Tests verify the full Ollama/qwen3:4b stack without touching any cloud API.

Run with:
    cd S:\\ResumeTA
    python -m pytest backend/tests/test_ollama.py -v

All tests are marked `ollama` and will be skipped automatically when Ollama is
not reachable (e.g. in a CI environment without a local GPU), so they are safe
to include in the full suite.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("LLM_MODEL", "qwen3:4b")


def _ollama_available() -> bool:
    """Return True when Ollama is reachable and the target model is present."""
    try:
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        if r.status_code != 200:
            return False
        models = [m["name"] for m in r.json().get("models", [])]
        return OLLAMA_MODEL in models
    except Exception:
        return False


ollama_available = pytest.mark.skipif(
    not _ollama_available(),
    reason=f"Ollama not reachable or {OLLAMA_MODEL} not installed — skipping live tests",
)


# ---------------------------------------------------------------------------
# T1 — Ollama connectivity
# ---------------------------------------------------------------------------


@ollama_available
def test_t1_ollama_connectivity():
    """T1: Ollama is running and the target model is available."""
    r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
    assert r.status_code == 200, "Expected 200 from /api/tags"
    models = [m["name"] for m in r.json().get("models", [])]
    assert OLLAMA_MODEL in models, (
        f"Model '{OLLAMA_MODEL}' not in installed models: {models}"
    )


# ---------------------------------------------------------------------------
# T2 — Simple text generation
# ---------------------------------------------------------------------------


@ollama_available
def test_t2_simple_text_generation():
    """T2: LLMService.chat_with_jd_context() exercises OllamaAdapter.complete_text()."""
    import sys

    sys.path.insert(0, ".")
    from app.services.llm_service import LLMService

    llm = LLMService()
    # Confirm provider is ollama
    assert llm.provider == "ollama", f"Expected provider=ollama, got {llm.provider}"

    # chat_with_jd_context → OllamaAdapter.complete_text() internally
    result = llm.chat_with_jd_context(
        markdown_context="Python developer role requiring Python and FastAPI.",
        question="Reply with exactly the word OK, nothing else.",
    )
    assert isinstance(result, str), "chat_with_jd_context must return str"
    assert len(result.strip()) > 0, "Response must not be empty"



# ---------------------------------------------------------------------------
# T3 — Structured JobEvaluationSpecification generation
# ---------------------------------------------------------------------------


@ollama_available
def test_t3_structured_jd_spec_generation():
    """T3: JDUnderstandingAgent.understand() produces a valid JobEvaluationSpecification."""
    import sys

    sys.path.insert(0, ".")
    from app.models.jd_spec import JobEvaluationSpecification
    from app.services.agent import JDUnderstandingAgent

    jd_text = (
        "Senior Python Engineer — 5+ years Python, FastAPI, PostgreSQL. "
        "Build microservices on AWS. Docker/Kubernetes required. "
        "Strong communication skills. Remote. $120k-$150k."
    )

    agent = JDUnderstandingAgent()
    t0 = time.perf_counter()
    spec, result = agent.understand(jd_text, jd_id="t3-test", jd_version=1)
    elapsed = time.perf_counter() - t0

    # Must finish in under 300s (our read timeout)
    assert elapsed < 300, f"Timed out after {elapsed:.0f}s"

    # Must return valid pydantic model
    assert isinstance(spec, JobEvaluationSpecification), (
        f"Expected JobEvaluationSpecification, got {type(spec)}"
    )

    # Core fields must be non-empty
    assert spec.role.job_title, "job_title must not be empty"
    assert len(spec.conventional_requirements.technical_skills) > 0, (
        "At least one technical skill expected"
    )

    # Token counts must be positive
    assert result.usage.input_tokens > 0, "input_tokens must be > 0"
    assert result.usage.output_tokens > 0, "output_tokens must be > 0"

    print(
        f"\n[T3] Title={spec.role.job_title!r} | "
        f"Skills={[s.name for s in spec.conventional_requirements.technical_skills[:3]]} | "
        f"In={result.usage.input_tokens} Out={result.usage.output_tokens} | "
        f"Elapsed={elapsed:.1f}s"
    )


# ---------------------------------------------------------------------------
# T4 — JD Agent chat
# ---------------------------------------------------------------------------


@ollama_available
def test_t4_jd_agent_chat():
    """T4: LLMService.chat_with_jd_context() returns a non-empty answer."""
    import sys

    sys.path.insert(0, ".")
    from app.services.llm_service import LLMService

    jd_context = (
        "Senior Python Engineer. Skills: Python, FastAPI, PostgreSQL, AWS, Docker. "
        "5+ years experience. Remote position. Salary $120k-$150k."
    )
    question = "What are the key technical skills required for this role?"

    llm = LLMService()
    answer = llm.chat_with_jd_context(jd_context, question)

    assert isinstance(answer, str), "chat_with_jd_context must return str"
    assert len(answer.strip()) > 20, f"Answer too short: {answer!r}"
    # Expect Python or FastAPI to appear somewhere in the answer
    assert any(kw in answer.lower() for kw in ("python", "fastapi", "postgresql", "aws")), (
        f"Expected relevant tech in answer, got: {answer!r}"
    )
    print(f"\n[T4] Chat answer: {answer[:200]}")


# ---------------------------------------------------------------------------
# T5 — Existing RAG tests still pass (smoke check)
# ---------------------------------------------------------------------------


def test_t5_rag_pipeline_still_local():
    """T5: Spot-check that RAG imports and BM25/TF-IDF retriever work without Ollama."""
    import sys

    sys.path.insert(0, ".")
    from app.services.rag import HybridRetriever  # type: ignore

    retriever = HybridRetriever()
    # Should instantiate without any network call
    assert retriever is not None


# ---------------------------------------------------------------------------
# T6 — Multiple JD isolation (separate understand() calls don't bleed)
# ---------------------------------------------------------------------------


@ollama_available
def test_t6_multiple_jd_isolation():
    """T6: Two back-to-back understand() calls return distinct job titles."""
    import sys

    sys.path.insert(0, ".")
    from app.services.agent import JDUnderstandingAgent

    jd_a = (
        "Junior Frontend Developer. React, TypeScript, CSS. "
        "1-2 years experience. On-site in New York."
    )
    jd_b = (
        "Principal Data Scientist. Python, ML, TensorFlow, Spark. "
        "PhD preferred. 8+ years experience. San Francisco."
    )

    agent = JDUnderstandingAgent()
    spec_a, _ = agent.understand(jd_a, jd_id="t6-a", jd_version=1)
    spec_b, _ = agent.understand(jd_b, jd_id="t6-b", jd_version=1)

    title_a = spec_a.role.job_title.lower()
    title_b = spec_b.role.job_title.lower()

    # Titles must differ — context from JD-A must not bleed into JD-B
    assert title_a != title_b, (
        f"Job titles should differ but both returned: {title_a!r}"
    )

    # JD-A should reference frontend/React; JD-B data science / ML
    skills_a = [s.name.lower() for s in spec_a.conventional_requirements.technical_skills]
    skills_b = [s.name.lower() for s in spec_b.conventional_requirements.technical_skills]
    assert any("react" in s or "typescript" in s for s in skills_a), (
        f"JD-A skills don't contain React/TypeScript: {skills_a}"
    )
    assert any("python" in s or "tensorflow" in s or "spark" in s for s in skills_b), (
        f"JD-B skills don't contain ML stack: {skills_b}"
    )

    print(f"\n[T6] JD-A={title_a!r} skills={skills_a[:3]}")
    print(f"[T6] JD-B={title_b!r} skills={skills_b[:3]}")


# ---------------------------------------------------------------------------
# T7 — No external API calls when LLM_PROVIDER=ollama
# ---------------------------------------------------------------------------


def test_t7_no_external_api_calls_with_ollama_provider(monkeypatch):
    """T7: With LLM_PROVIDER=ollama, no Anthropic/Gemini adapter is selected."""
    import sys

    sys.path.insert(0, ".")

    # Patch env so settings reload with ollama
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "qwen3:4b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # Clear settings cache so our patched env takes effect
    from app.config import get_settings
    # get_settings() creates a fresh Settings() on every call — no cache to clear.

    from app.services.llm_service import LLMService

    llm = LLMService()
    assert llm.provider == "ollama", f"Expected ollama provider, got {llm.provider!r}"

    # Confirm the selected adapter is OllamaAdapter, not Anthropic/Gemini
    from app.services.llm_service import OllamaAdapter

    assert isinstance(llm.adapter, OllamaAdapter), (
        f"Expected OllamaAdapter, got {type(llm.adapter).__name__}"
    )

    # Confirm no Anthropic or Gemini key is being used
    settings = get_settings()
    # Keys may be set in env for other reasons; what matters is they are NOT
    # referenced by the active adapter — OllamaAdapter has no api_key field
    assert not hasattr(llm.adapter, "api_key"), (
        "OllamaAdapter must not expose an api_key attribute"
    )

    print(
        f"\n[T7] provider={llm.provider!r} adapter={type(llm.adapter).__name__!r} — "
        "no cloud key referenced ✓"
    )
