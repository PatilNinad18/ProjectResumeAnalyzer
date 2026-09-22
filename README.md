# JD Understanding Agent & Candidate Screening System

A production-grade reference implementation of the **JD Understanding Agent** with integrated **Hybrid RAG (Retrieval-Augmented Generation)** for an AI-powered Candidate Screening and Evaluation System. 

It analyzes raw Job Descriptions (JDs), enriches requirement interpretation with domain-specific evaluation standards via hybrid RAG, and produces a **canonical Candidate Evaluation Specification** rendered as both:
1. `job_specification.md` — A crisp, scannable context document for downstream Candidate-Analysis LLMs.
2. `job_specification.json` — The complete machine-readable source of truth for backend API consumers, storage, and database persistence.

---

## 1. System Architecture

```
                                  ┌──────────────────────────────┐
                                  │   Curated Knowledge Base     │
                                  │   (7 Taxonomy Categories)    │
                                  └──────────────┬───────────────┘
                                                 │
RAW JD (Text or File)                            ▼
   │                             ┌───────────────────────────────┐
   ├───▶ Preserve Original JD ──▶│ Atomic Query & Classification │
   │                             └──────────────┬────────────────┘
   │                                            │
   │                                            ▼
   │                             ┌───────────────────────────────┐
   │                             │  Hybrid Retrieval & RRF:      │
   │                             │  - Okapi BM25                 │
   │                             │  - TF-IDF Cosine Similarity   │
   │                             │  - Reciprocal Rank Fusion     │
   │                             └──────────────┬────────────────┘
   │                                            │
   │                                            ▼
   │                             ┌───────────────────────────────┐
   │                             │  Context Selector & Budgeting │
   │                             └──────────────┬────────────────┘
   │                                            │
   ▼                                            ▼
┌────────────────────────────────────────────────────────────────┐
│                   JD Understanding Agent                       │
│    (Structured LLM prompt with <domain_knowledge_context>)     │
└───────────────────────────────┬────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────┐
│   Canonical JobEvaluationSpecification (Pydantic Validated)    │
├───────────────────────────────┬────────────────────────────────┤
│       Markdown Renderer       │         JSON Serializer        │
│               │               │                │               │
│               ▼               │                ▼               │
│      job_specification.md     │      job_specification.json    │
│    (Crisp 8-Section View)     │     (Full Persistent Spec)     │
└───────────────┬───────────────┴────────────────┬───────────────┘
                │                                │
                ▼                                ▼
┌───────────────────────────────┐ ┌──────────────────────────────┐
│  Dedicated JD Chat Interface  │ │  Downstream Candidate LLMs   │
│   (Dual-Context RAG Chat)     │ │  (Resume Evaluator / Agents) │
└───────────────────────────────┘ └──────────────────────────────┘
```

Markdown and JSON never drift because both are deterministic representations of the same in-memory Pydantic object (`app/schemas/canonical.py`). A schema-aware `Markdown → JSON` converter (`app/services/markdown_to_json.py`) allows Talent Acquisition (TA) users to edit the rendered Markdown and parse those changes back into the canonical object.

---

## 2. Repository Layout

```
ProjectResumeAnalyzer/
├── backend/
│   ├── app/
│   │   ├── schemas/
│   │   │   ├── canonical.py              Canonical Pydantic schema (single source of truth)
│   │   │   └── rag_schemas.py            RAG schemas (KBDocument, ClassifiedRequirement, etc.)
│   │   ├── services/
│   │   │   ├── agent.py                  Orchestration: JD -> RAG -> LLM -> validated canonical spec
│   │   │   ├── prompt.py                 System & user prompts with RAG context injection
│   │   │   ├── llm_service.py            Model-agnostic LLMService -> ProviderAdapter (Gemini/Mock/Anthropic)
│   │   │   ├── mock_extractor.py         Deterministic offline stand-in for LLM (dev/CI testing)
│   │   │   ├── markdown_renderer.py      Canonical spec -> Crisp 8-Section Markdown (deterministic)
│   │   │   ├── json_serializer.py        Canonical spec -> JSON serializer
│   │   │   ├── markdown_to_json.py       Markdown -> Canonical spec (schema-aware parser)
│   │   │   ├── validation.py             Pydantic + cross-field validation rules
│   │   │   ├── storage.py                File/S3 storage abstraction
│   │   │   └── rag/
│   │   │       ├── __init__.py           Public RAG interface & pipeline runner
│   │   │       ├── knowledge_base.py     Thread-safe singleton KnowledgeBase loader
│   │   │       ├── query_generator.py    Atomic clause extractor & heuristic requirement classifier
│   │   │       ├── retrieval.py          Pure stdlib BM25, TF-IDF Cosine, & RRF Rank Fusion
│   │   │       ├── context_selector.py   Deduplication, relevance thresholding & prompt formatter
│   │   │       └── knowledge_base/       Curated domain knowledge JSON documents:
│   │   │           ├── 1_experience.json
│   │   │           ├── 2_skills.json
│   │   │           ├── 3_evidence_evaluation.json
│   │   │           ├── 4_roles_seniority.json
│   │   │           ├── 5_domains.json
│   │   │           ├── 6_job_parameters.json
│   │   │           └── 7_compliance.json
│   │   ├── models/db_models.py           SQLAlchemy models (SQLite / PostgreSQL)
│   │   ├── workers/worker.py             Background worker for asynchronous pipeline execution
│   │   ├── api/routes.py                 FastAPI endpoints (JD management, analysis, chat)
│   │   └── main.py                       FastAPI application entrypoint
│   └── tests/
│       ├── sample_jds/                   6 realistic test JDs across various domains
│       ├── test_pipeline.py              Pipeline validation, round-tripping & Markdown tests (16 tests)
│       └── test_rag.py                   Knowledge base, BM25, TF-IDF, RRF & prompt tests (44 tests)
├── frontend/
│   ├── src/
│   │   ├── pages/index.tsx               Linear workflow, dedicated chat, settings, & spec viewer
│   │   └── lib/api.ts                    Typed API client for backend communication
│   └── package.json
└── samples/
    ├── job_specification.md              Sample rendered Markdown output
    └── job_specification.json            Sample canonical JSON output
```

---

## 3. Integrated RAG Engine

The RAG subsystem enriches the LLM prompt with domain knowledge for standardizing ambiguous requirements, evaluation rules, and compliance standards.

### Key Features
- **7 Taxonomy Knowledge Categories:** Experience, Technical Skills, Evidence & Evaluation, Roles & Seniority, Domains, Job Parameters, and Compliance.
- **Hybrid Retrieval:** Combines lexical search (**Okapi BM25**) and semantic term vector search (**Sublinear TF-IDF Cosine Similarity**).
- **Reciprocal Rank Fusion (RRF):** Fuses rankings ($k=60$) to balance exact term hits and semantic keyword overlap.
- **Zero Heavy Dependencies:** Implemented using pure Python standard library (`math`, `re`, `collections`, `dataclasses`) without bulky vector database dependencies.
- **Strict Source of Truth Preservation:** The raw JD is strictly isolated in `<jd_content>`, while retrieved knowledge is injected in `<domain_knowledge_context>` marked as *supporting interpretation guidance only*. RAG never overrides explicit JD facts.
- **Dual-Context Chat Assistant:** The `/api/jds/{jd_id}/chat` and `/api/chat` endpoints perform dual-context retrieval, combining the JD Markdown context with supporting evaluation knowledge to answer recruiter queries accurately.

---

## 4. Frontend & User Experience

The web interface (`frontend/`) provides an intuitive workflow:

1. **Linear JD Workflow:**
   - Step 1: **Company Details** (Company name, department, hiring manager).
   - Step 2: **Enter / Upload JD** (File upload or paste raw text).
   - Step 3: **Analyse** (Triggers asynchronous LLM parsing & RAG enrichment).
   - Step 4: **View / Download JD Context** (Tabbed preview of crisp 8-Section Markdown and full JSON with copy/download options).
   - Step 5: **Create Agent** (Deploys a configured agent for downstream screening).
2. **Dedicated JD Chat:**
   - Full conversational interface separate from configuration setup.
   - Interactive dropdown to switch between analyzed JDs.
   - Dual-context conversational assistant for answering role, requirement, and evaluation questions.
3. **Agent Settings & Context Regeneration:**
   - Per-agent customizable settings (evaluation strictness, weighting, role level).
   - One-click context regeneration when JD requirements change.

---

## 5. Target 8-Section Markdown Structure

The rendered `job_specification.md` is optimized for downstream candidate screening, strictly outputting **8 scannable sections**:

1. **Role Overview** — Title, seniority, location/work mode, environment, department, and team context.
2. **Requirements** — `### Must-Have` (including merged experience) and `### Preferred` qualifications.
3. **Responsibilities** — Core operational duties and primary expectations.
4. **Evidence & Evaluation Rules** — Per-requirement evidence expectations, process evaluation rules, UNSCORED conditions, and prohibited inferences.
5. **JD-Specific Evaluation Parameters** — Non-conventional parameters presented with title, purpose, and expected evidence.
6. **Ambiguities & Missing Information** — Ambiguous statements (with TA confirmation flags) and missing parameters (with recommended actions).
7. **Evaluation Priorities** — Priority matrix for downstream candidate evaluation.
8. **Compliance** — Bias and compliance flags with concerns and recommended actions.

---

## 6. Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+ and npm

### Backend Setup

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

#### Environment Variables (`.env`)

```ini
# Mock provider for offline testing / development (no API key needed):
LLM_PROVIDER=mock

# Or configure Gemini:
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.6-flash
GEMINI_API_KEY=your_gemini_api_key_here

# Optional:
ENABLE_RAG=true
DATABASE_URL=sqlite:///./jd_agent.db
```

#### Running the Backend Server

```bash
uvicorn app.main:app --reload --port 8000
```

#### Running the Asynchronous Worker (Optional in Dev)

```bash
python -m app.workers.worker
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000` to access the application.

---

## 7. Running Tests

The test suite contains **60 automated tests** across RAG components and end-to-end pipeline execution:

```bash
cd backend

# Run the complete test suite (60 tests)
python -m pytest tests/test_rag.py tests/test_pipeline.py -v

# Run only RAG unit tests (44 tests)
python -m pytest tests/test_rag.py -v

# Run only Pipeline integration tests (16 tests)
python -m pytest tests/test_pipeline.py -v
```

---

## 8. API Surface

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/jds` | Upload a JD (multipart file or raw text) |
| `GET`  | `/api/jds/{jd_id}` | Retrieve JD metadata and version info |
| `POST` | `/api/jds/{jd_id}/analyze` | Enqueue JD Understanding & RAG pipeline |
| `GET`  | `/api/jds/{jd_id}/analysis` | Poll processing status (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`) |
| `GET`  | `/api/jds/{jd_id}/markdown` | Get rendered 8-section `job_specification.md` |
| `GET`  | `/api/jds/{jd_id}/json` | Get canonical `job_specification.json` |
| `POST` | `/api/jds/{jd_id}/markdown-to-json` | Parse edited Markdown back into validated canonical JSON |
| `POST` | `/api/jds/{jd_id}/json-to-markdown` | Deterministically re-render Markdown from JSON payload |
| `GET`  | `/api/jds/{jd_id}/versions` | View specification version history |
| `POST` | `/api/jds/{jd_id}/chat` | Ask questions about a specific JD with dual-context RAG |
| `POST` | `/api/chat` | Direct chat endpoint with custom Markdown context |

---

## 9. Key Design Principles

- **Canonical Specification as Source of Truth:** `JobEvaluationSpecification` (Pydantic) guarantees synchronization between JSON and Markdown formats.
- **Fail-Safe RAG Execution:** RAG errors are caught and logged; the extraction pipeline seamlessly falls back to core LLM parsing if retrieval fails.
- **No Uncontrolled Hallucination:** Anti-fabrication guardrails prevent the LLM from inventing numeric scoring weights or unstated requirements.
- **Preserved Source Citations:** Verbatim source citations from the original JD are retained in the JSON schema for auditing and traceability.
- **Prompt Injection Defense:** Raw JD content is quarantined in `<jd_content>` tags to prevent adversarial instruction overrides.
