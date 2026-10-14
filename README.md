# JD Understanding Agent & Candidate Screening System

A production-oriented **JD Understanding Agent** for an AI-powered Candidate Screening and Evaluation System.

The system analyzes Job Descriptions (JDs), enriches requirement interpretation using a local Hybrid RAG pipeline, and produces a canonical **Candidate Evaluation Specification** as:

- `job_specification.md` — concise, human-readable 8-section JD context
- `job_specification.json` — complete machine-readable canonical specification

The current setup uses **Ollama + Qwen3 4B for local/offline LLM inference**, so JD analysis does not require an external LLM API key.

---

## How It Works (Plain English)

> **Important:** The system has **two completely separate pipelines**. One uses the LLM (Ollama / Qwen3 4B). The other is 100% deterministic and **does not need Ollama at all**. This is why you get output even when Ollama is not running.

---

### Why you get output without Ollama

When you click **Analyze**, the worker ([`worker.py`](backend/app/workers/worker.py)) runs **two stages**:

```
Stage 1 — Deterministic Baseline (ALWAYS runs, no Ollama needed)
  ExtractionPipeline → EKG entity matching → rule-based extractor
  → produces: master_context, canonical spec, markdown, JSON
       ↓
Stage 2 — Ollama Enrichment (OPTIONAL, only if Ollama is running)
  GroundedEnrichmentService.check_ollama_available()
    → if True:  call Ollama → enrich the markdown with deeper evidence rules
    → if False: silently skip, use Stage 1 output as-is
```

**Stage 1 always completes and saves a result to the database.** Stage 2 is a best-effort enrichment that improves quality but is not required. If Ollama is off, Stage 2 is skipped with a log warning and the Stage 1 result is returned as the final output.

This means:
- **Without Ollama** → you get a deterministic rule-based extraction (fast, no LLM quality)
- **With Ollama** → you get the same deterministic baseline, enriched by the LLM (slower, higher quality)

---

### Pipeline 1 — Deterministic Baseline (No LLM)

This pipeline runs on every JD analysis regardless of Ollama. It uses **pure Python keyword rules + the Entity Knowledge Graph (EKG)**.

```
Raw JD Text
    │
    ▼
[1] Section Identifier (deterministic)
    Finds sections: Requirements, Responsibilities, etc.
    │
    ▼
[2] Requirement Extractor + EKG entity matching (deterministic)
    Matches skills/tools against a built-in entity knowledge graph
    │
    ▼
[3] Parameter Extractor (deterministic)
    Extracts: work mode, location, travel, salary, education, etc.
    │
    ▼
[4] Disjunction Detector (deterministic)
    Finds "or" conditions: "Python OR Java", "BS OR equivalent experience"
    │
    ▼
[5] Ambiguity Detector (deterministic)
    Flags vague phrases: "strong communication", "fast learner", etc.
    │
    ▼
[6] Responsibility Interpreter (deterministic)
    Classifies responsibilities into 3 tiers
    │
    ▼
ExtractionResult → JDMasterContext (canonical domain model)
    │
    ▼
Clarification Question Generator (deterministic)
    Generates questions TA should answer about missing info
    │
    ▼
Canonical Projector → JobEvaluationSpecification
    │
    ├──▶ job_specification.json
    └──▶ job_specification.md  ← baseline (no LLM)
```

**No Ollama. No API key. Zero external dependencies.** This runs entirely offline.

---

### Pipeline 2 — Ollama Enrichment (Optional, LLM-powered)

If Ollama is running and the model is available, an additional enrichment step runs **on top of the deterministic baseline**:

```
JobEvaluationSpecification (from Pipeline 1)
    │
    ▼
GroundedEnrichmentService.check_ollama_available()
    │
    ├── Ollama NOT running → skip, return baseline as-is
    │
    └── Ollama IS running
            │
            ▼
        Ollama / Qwen3 4B
        (enriches evidence rules, evaluation guidance,
         strong/moderate/weak evidence descriptions
         for each requirement)
            │
            ▼
        job_specification.md  ← enriched version
        (stored separately from baseline; baseline is preserved)
```

The enriched markdown is stored separately. The baseline markdown is **always** preserved. The API returns enriched markdown by default when it exists.

---

### RAG (used in both pipelines)

Before the LLM is called for enrichment or for chat, a **local Hybrid RAG** retrieves relevant knowledge snippets from a built-in knowledge base. This is 100% deterministic — no embedding model, no GPU:

```
Query
  │
  ├──▶ BM25 (keyword search)
  ├──▶ TF-IDF Cosine Similarity (vector-like search, stdlib math only)
  │
  ▼
Reciprocal Rank Fusion (RRF) — merges both ranked lists
  │
  ▼
Top-K snippets → injected into LLM prompt as background guidance only
```

RAG failures never block the pipeline — the system continues without context if retrieval fails.

---

### JD Chat (uses LLM if Ollama is running)

Chat calls Ollama directly. If Ollama is off, the chat endpoint raises a 503 error — unlike analysis, chat has no deterministic fallback because a conversational answer requires the LLM.

---

### Summary: What runs with and without Ollama

| Feature | Without Ollama | With Ollama |
|---|---|---|
| JD Analysis (baseline) | ✅ Works — deterministic EKG extraction | ✅ Works |
| Evidence enrichment | ❌ Skipped (baseline markdown used) | ✅ LLM enriches evidence rules |
| JD Chat | ❌ Returns 503 error | ✅ Works |
| Clarification questions | ✅ Works — deterministic | ✅ Works |
| Finalization / resolve | ✅ Works — deterministic | ✅ Works (+ optional enrichment) |

> **In short:** Ollama makes the output *better*, but the system is designed to work without it. The deterministic pipeline is the foundation; Ollama is an optional upgrade layer.

---

### What is Ollama? What is Qwen3 4B?

- **Ollama** is a free tool that lets you run AI language models locally on your own computer — no internet, no cloud API, no API key needed.
- **Qwen3 4B** is a 4-billion-parameter open-source language model made by Alibaba. It is small enough to run on a laptop CPU (slowly) or a GPU (fast). It understands instructions well and can produce structured JSON reliably.

The two together mean: **this entire system runs 100% offline on your machine.** No data is ever sent to OpenAI, Google, or any cloud service unless you explicitly switch the provider in `.env`.

### Can I use a different LLM?

Yes. The system has four built-in providers you can switch via `LLM_PROVIDER` in `.env`:

| Provider | Model | Requires |
|---|---|---|
| `ollama` | `qwen3:4b` (default) | Ollama installed locally |
| `gemini` | `gemini-2.5-flash` | `GEMINI_API_KEY` |
| `anthropic` | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| `mock` | rule-based extractor | Nothing (dev/CI only) |

The `mock` provider uses **only deterministic keyword rules** and is explicitly not a real LLM — it is only for testing without Ollama installed.

---

## 1. Architecture

```text
JD (Text / TXT / PDF / DOCX)
            |
            v
     JD Understanding Agent
            |
            +----> Local Hybrid RAG
            |      BM25 + TF-IDF + RRF
            |      (Deterministic, no LLM)
            |
            v
     Ollama / Qwen3 4B
       Local Inference
            |
            v
   Pydantic Validation
            |
       +----+----+
       |         |
       v         v
 job_spec.md  job_spec.json
       |
       v
   JD Chat / Downstream Agents
```

The raw JD is the authoritative source. RAG provides supporting interpretation knowledge and must not override explicit JD facts.

Both Markdown and JSON are rendered from the same validated `JobEvaluationSpecification`, so they remain synchronized.

---

## 2. Offline LLM Setup

### Current configuration

```text
Provider:      Ollama
Model:         qwen3:4b
Inference:     Local
API Keys:      Not required
External LLM:  Not required
RAG:           Local
```

Ollama downloads the model once and runs inference locally.

### Install Ollama

Install Ollama from:

https://ollama.com/

Verify:

```bash
ollama --version
```

### Download Qwen3 4B

```bash
ollama pull qwen3:4b
```

Verify:

```bash
ollama list
```

---

## 3. Supported LLM Providers

| Provider | Setting | Model | Notes |
|---|---|---|---|
| Ollama (default) | `LLM_PROVIDER=ollama` | `qwen3:4b` | Local, offline, no API key |
| Gemini | `LLM_PROVIDER=gemini` | `gemini-2.5-flash` | Requires `GEMINI_API_KEY` |
| Anthropic | `LLM_PROVIDER=anthropic` | `claude-sonnet-4-6` | Requires `ANTHROPIC_API_KEY` |
| Mock | `LLM_PROVIDER=mock` | rule-based | Dev / CI only, no real LLM |

Switch providers by changing `LLM_PROVIDER` in `.env`. The model can be overridden separately via `LLM_MODEL`.

---

## 4. JD Understanding Pipeline

```text
Raw JD
  |
  v
[1] Clause Splitter (deterministic)
      Split JD into atomic statements
  |
  v
[2] Requirement Classifier (deterministic, keyword-scored)
      Categories: experience / technical_skills / responsibilities /
                  roles_seniority / domains / job_parameters / compliance
  |
  v
[3] Hybrid RAG Retrieval (deterministic)
      BM25 sparse + TF-IDF dense + RRF fusion
      → domain-knowledge snippets
  |
  v
[4] Prompt Builder
      <jd_content> + <domain_knowledge_context>
  |
  v
[5] LLM Call — Ollama / Qwen3 4B
      JSON schema-constrained output
  |
  v
[6] JSON Parsing + Pydantic Validation
  |
  v
[7] Deterministic Post-processing
      Title override, deduplication, skill surfacing
  |
  v
JobEvaluationSpecification (canonical Python object)
  |
  +----> job_specification.md
  +----> job_specification.json
```

---

## 5. JD Analysis Prompt

The LLM receives a strict system prompt that:

- Designates `<jd_content>` as the only authoritative source of facts
- Designates `<domain_knowledge_context>` as background guidance only
- Prohibits inventing salary, years, skills, education, location, or any absent information
- Distinguishes `"explicit"` (stated in JD) from `"derived"` (reasonable interpretation)
- Defines the exact JSON key skeleton the model must follow
- Caps every string at 25 words and limits list lengths (e.g. responsibilities ≤ 8)
- Instructs the model to output **only** the raw JSON object — no prose, no fences

Ollama enforces the JSON shape with a grammar so the model cannot deviate from the schema.

---

## 6. JD Post-processing (Deterministic)

After the LLM returns its JSON, three deterministic fixups run:

1. **Job title authority** — If the JD starts with `Job Title: ...`, that line always overrides the model's output
2. **Must-have deduplication** — Skills already captured in structured `experience` or `education` fields are removed from the flat `must_have_requirements` list to prevent double-rendering
3. **Skill surfacing** — Technical skills the model extracted into `technical_skills` but omitted from the requirements lists are added back with the correct priority

These fixups exist because a 4B model is unreliable at these mechanical tasks; deterministic code handles them instead.

---

## 7. Pydantic Validation

The LLM output is validated against `JobEvaluationSpecification` (see `backend/app/schemas/canonical.py`):

- All field types and constraints are checked
- Unknown fields are ignored (tolerant parsing)
- If validation fails, a `JDUnderstandingError` is raised — the output is never silently accepted

---

## 8. JD File Parsing

Supported input formats:

- `.txt`
- `.pdf`
- `.docx`

The original JD remains the primary source of truth throughout the pipeline.

---

## 9. Hybrid RAG

The local RAG system provides supporting knowledge for requirement interpretation, evidence rules, and compliance.

### Knowledge categories

1. Experience
2. Technical Skills
3. Evidence & Evaluation
4. Roles & Seniority
5. Domains
6. Job Parameters
7. Compliance

### Retrieval

```text
Query
  |
  +--> BM25
  |
  +--> TF-IDF Cosine
  |
  v
Reciprocal Rank Fusion
  |
  v
Context Selection
  |
  v
Ollama / Qwen3 4B
```

The RAG implementation is lightweight and local. No external embedding model or vector database is required — it uses only Python's standard library math.

---

## 10. Canonical Specification

The canonical schema is:

```text
backend/app/schemas/canonical.py
```

It is the single source of truth for the JD Understanding pipeline.

```text
JobEvaluationSpecification
        |
        +--> Markdown Renderer --> job_specification.md
        |
        +--> JSON Serializer  --> job_specification.json
```

The specification contains role information, responsibilities, conventional requirements, preferred requirements, evidence rules, non-conventional parameters, ambiguities, compliance rules, and candidate-analysis instructions.

---

## 11. Generated Markdown

`job_specification.md` is rendered as 8 sections:

1. Role Overview
2. Requirements
3. Responsibilities
4. Evidence & Evaluation Rules
5. JD-Specific Evaluation Parameters
6. Ambiguities & Missing Information
7. Evaluation Priorities
8. Compliance

It is optimized as context for downstream candidate-analysis agents and the JD chat assistant.

---

## 12. JD Chat

The chat assistant answers questions about the currently active JD.

Examples:

```text
Which company is hiring?

What are the must-have technical skills?

Is the role remote or onsite?

What experience is required?

What are the main responsibilities?

Which skills are preferred?
```

Chat uses:

```text
Active JD Markdown
       +
Supporting RAG knowledge
       |
       v
Ollama / Qwen3 4B
       |
       v
Answer
```

The active JD context must remain authoritative for JD-specific facts.

---

## 13. Multi-JD Support

Each JD maintains its own context:

```text
JD 1
├── Raw JD
├── Analysis
├── job_specification.md
├── job_specification.json
└── Chat context

JD 2
├── Raw JD
├── Analysis
├── job_specification.md
├── job_specification.json
└── Chat context
```

Users can switch between analyzed JDs without mixing their contexts.

---

## 14. API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/jds` | List JDs |
| POST | `/api/jds` | Create/upload JD |
| GET | `/api/jds/{jd_id}` | Get JD metadata |
| POST | `/api/jds/{jd_id}/analyze` | Run JD analysis |
| GET | `/api/jds/{jd_id}/analysis` | Get analysis status/result |
| GET | `/api/jds/{jd_id}/markdown` | Get generated Markdown |
| GET | `/api/jds/{jd_id}/json` | Get canonical JSON |
| POST | `/api/jds/{jd_id}/markdown-to-json` | Parse edited Markdown |
| POST | `/api/jds/{jd_id}/json-to-markdown` | Render Markdown |
| GET | `/api/jds/{jd_id}/versions` | Get specification versions |
| POST | `/api/jds/{jd_id}/chat` | Chat with a specific JD |
| POST | `/api/chat` | Chat with supplied Markdown context |

---

## 15. Repository Structure

```text
ProjectResumeAnalyzer/
├── backend/
│   ├── app/
│   │   ├── schemas/
│   │   │   ├── canonical.py
│   │   │   └── rag_schemas.py
│   │   ├── services/
│   │   │   ├── agent.py
│   │   │   ├── prompt.py
│   │   │   ├── llm_service.py
│   │   │   ├── markdown_renderer.py
│   │   │   ├── json_serializer.py
│   │   │   ├── markdown_to_json.py
│   │   │   ├── validation.py
│   │   │   └── rag/
│   │   ├── models/
│   │   ├── workers/
│   │   ├── api/
│   │   └── main.py
│   └── tests/
├── frontend/
│   ├── src/
│   └── package.json
└── samples/
    ├── job_specification.md
    └── job_specification.json
```

---

## 16. Testing

Run all backend tests:

```bash
cd backend
python -m pytest -v
```

RAG tests:

```bash
python -m pytest tests/test_rag.py -v
```

Pipeline tests:

```bash
python -m pytest tests/test_pipeline.py -v
```

Before committing JD pipeline changes, verify:

- Ollama is running
- `qwen3:4b` is installed
- JD analysis completes
- Pydantic validation succeeds
- Markdown is generated
- JSON is generated
- Markdown and JSON remain consistent
- Chat uses the currently selected JD

---

## 17. Troubleshooting

### Ollama is not running

```bash
ollama list
```

Start Ollama and retry.

### Qwen3 4B is missing

```bash
ollama pull qwen3:4b
```

### Backend uses the wrong provider

Check `.env`:

```ini
LLM_PROVIDER=ollama
LLM_MODEL=qwen3:4b
OLLAMA_BASE_URL=http://localhost:11434
```

Restart Uvicorn after changing `.env`.

### Local inference is slow

Local inference is expected to be slower than cloud inference. GPU acceleration is recommended.

The current development configuration uses:

```text
Context window:           16,384 tokens
Maximum generated output:  8,192 tokens
```

These values can be tuned after measuring quality and latency.

### JSON validation fails

Inspect the Pydantic validation error first. Do not increase the output limit automatically. The canonical schema should remain the source of truth.

---

## 18. Offline Data Flow

```text
             CLIENT MACHINE
                  |
                  v
             Raw JD
                  |
                  v
          Local FastAPI Backend
             /          \
            /            \
      Local RAG         Ollama
    (Deterministic)    Qwen3 4B
            \            /
             \          /
                  v
        Canonical Pydantic Spec
             /          \
            v             v
     Markdown             JSON
            \             /
             \           /
                JD Chat
```

No external LLM API is required in Ollama mode.

---

## 19. Key Design Principles

- **JD is authoritative:** The model must not invent requirements absent from the JD.
- **RAG is supporting knowledge:** Retrieved knowledge cannot override explicit JD facts.
- **Canonical schema is the source of truth:** JSON and Markdown are generated from the same validated object.
- **Offline-first inference:** Ollama + Qwen3 4B keeps LLM inference local.
- **Multi-JD isolation:** Each JD has independent analysis and chat context.
- **Traceability:** Requirements retain source information where supported by the schema.
- **Fail-safe RAG:** RAG failures should not prevent core JD extraction.
- **Validation before output:** LLM output is validated against the canonical Pydantic schema.
- **Rules for the mechanical, LLM for the semantic:** Deterministic code handles deduplication and formatting; the LLM handles understanding and extraction.

---

## 20. Quick Start

```bash
# Install Ollama first, then:
ollama pull qwen3:4b
ollama run qwen3:4b

# Backend
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

Create `.env`:

```ini
LLM_PROVIDER=ollama
LLM_MODEL=qwen3:4b
OLLAMA_BASE_URL=http://localhost:11434
ENABLE_RAG=true
DATABASE_URL=sqlite:///./jd_agent.db
```

Start backend:

```bash
uvicorn app.main:app --reload --port 8000
```

Start frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Then upload a JD, run the analysis, review the generated specification, and use the JD chat.

---

## License

Add the project's applicable license here.
