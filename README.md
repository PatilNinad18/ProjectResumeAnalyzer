# JD Understanding Agent & Candidate Screening System

A production-oriented **JD Understanding Agent** for an AI-powered Candidate Screening and Evaluation System.

The system analyzes Job Descriptions (JDs), enriches requirement interpretation using a local Hybrid RAG pipeline, and produces a canonical **Candidate Evaluation Specification** as:

- `job_specification.md` — concise, human-readable 8-section JD context
- `job_specification.json` — complete machine-readable canonical specification

The current setup uses **Ollama + Qwen3 4B for local/offline LLM inference**, so JD analysis does not require an external LLM API key.

---

## How It Works (Plain English)

> **Short answer:** This project uses a real LLM (Qwen3 4B running locally via Ollama) — NOT a deterministic rule-based system. Rules are only used in two small, well-defined support roles.

Here is exactly what happens when you upload a Job Description (JD):

### Step 1 — Rule-Based Pre-processing (Deterministic)

Before the LLM sees anything, a **pure Python, zero-dependency classifier** reads the raw JD text and splits it into atomic clauses (bullet points, sentences). Each clause is scored against keyword signal tables (e.g. "python", "years of experience", "remote") and assigned to one of 7 categories:

| Category | Example keywords |
|---|---|
| `experience` | "years of experience", "prior experience" |
| `technical_skills` | "python", "aws", "docker", "react" |
| `responsibilities` | "design", "build", "deploy", "lead" |
| `roles_seniority` | "senior", "junior", "principal", "intern" |
| `domains` | "fintech", "healthcare", "saas", "AI/ML" |
| `job_parameters` | "remote", "hybrid", "on-call", "contract" |
| `compliance` | "visa sponsorship", "security clearance", "EEO" |

This step is **100% deterministic** — same JD always gives the same classification. No LLM is called here. Its only job is to figure out *what kind* of knowledge to look up next.

### Step 2 — Hybrid RAG Retrieval (Deterministic)

The classified clauses are used as search queries against a **local knowledge base** of hiring evaluation standards. The retrieval uses two complementary algorithms fused together:

- **BM25** (keyword matching): finds documents with exact or near-exact term matches
- **TF-IDF Cosine Similarity** (vector matching): finds documents that are *conceptually similar*
- **Reciprocal Rank Fusion (RRF)**: merges both result lists into one ranked list

**No external search engine, no embeddings model, no GPU required** — this is plain Python math using only the standard library. The retrieved "knowledge snippets" tell the LLM things like *"when a JD says 3 years of Python, it means 3 years of relevant Python, not total employment"*.

### Step 3 — LLM Call (Ollama / Qwen3 4B)

Now the LLM is called. The LLM receives:

```
[System Prompt: strict extraction rules + required JSON shape]
[User Prompt:
  <jd_content> ... raw JD text ... </jd_content>
  <domain_knowledge_context> ... RAG snippets ... </domain_knowledge_context>
  "Generate the Candidate Evaluation Specification now."
]
```

The LLM's job is to **read the JD and fill in a pre-defined JSON schema** — it extracts job title, skills, experience requirements, responsibilities, evidence rules, ambiguities, etc. It is explicitly told:

- The JD is the only source of facts
- RAG snippets are background guidance only and must not override JD facts
- Never invent salary, years, skills, or any detail not in the JD
- Output **only** the JSON object — no prose, no markdown, no reasoning

Ollama constrains the LLM's output to match the exact JSON schema using a grammar, so the model cannot produce malformed JSON.

**This is the only step where a language model is used.**

### Step 4 — Deterministic Post-processing (Rule-Based)

After the LLM responds, a small Python function runs three deterministic fixes:

1. **Job title override** — if the JD starts with `"Job Title: ..."`, that exact string always wins over whatever the model guessed
2. **Deduplication** — skills that appear in both the structured fields and the free-text must-have list are deduplicated using token matching
3. **Skill surfacing** — any technical skill the LLM extracted but forgot to include in the requirements lists is added back

### Step 5 — Pydantic Validation

The LLM's JSON is validated against the `JobEvaluationSpecification` Pydantic schema. If it fails, the error is logged and the analysis is rejected — the LLM output is never silently accepted.

### Step 6 — Output: Markdown + JSON

The validated Python object is rendered into:
- `job_specification.md` — 8 human-readable sections for TA teams
- `job_specification.json` — machine-readable spec for downstream agents

Both files are generated from the **same validated object**, so they are always in sync.

### Step 7 — JD Chat

Users can ask questions about the uploaded JD (e.g. *"Is the role remote?"*, *"What Python experience is required?"*). Chat calls the LLM again with:
- The raw JD text (authoritative)
- The generated `job_specification.md` (supporting)
- Relevant RAG snippets (background only)
- Conversation history (last 6 turns)

The LLM answers in ≤150 words using only the provided context. It cannot invent facts.

---

### Summary: Which parts use the LLM vs rules?

| Step | Approach |
|---|---|
| Clause splitting & classification | ✅ Deterministic rules (keyword scoring) |
| Knowledge retrieval (RAG) | ✅ Deterministic math (BM25 + TF-IDF + RRF) |
| JD understanding & extraction | 🤖 **LLM — Ollama / Qwen3 4B** |
| Post-processing (dedup, title fix) | ✅ Deterministic rules |
| Pydantic validation | ✅ Deterministic (schema check) |
| Markdown + JSON rendering | ✅ Deterministic (template renderer) |
| JD Chat answers | 🤖 **LLM — Ollama / Qwen3 4B** |

The LLM (Qwen3 4B) is the brain. The rules are the guardrails that make its output reliable and consistent.

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
