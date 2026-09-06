# JD Understanding Agent

A reference implementation of the **JD Understanding Agent** for an AI-powered Candidate Screening and Evaluation System. It converts raw Job Descriptions (JDs) into a **canonical Candidate Evaluation Specification**, rendered as both:
1. `job_specification.md` — A crisp, scannable context document for downstream Candidate-Analysis LLMs.
2. `job_specification.json` — The complete machine-readable source of truth for backend API consumers, storage, and database persistence.

```
RAW JD
  │
  ▼
JD Understanding Agent  (LLM + structured output, Pydantic-validated)
  │
  ▼
Canonical JobEvaluationSpecification   <-- SINGLE SOURCE OF TRUTH (Pydantic / JSON)
  ├── Markdown Renderer  ──▶ job_specification.md   (Crisp 8-Section LLM Context View)
  └── JSON Serializer    ──▶ job_specification.json (Full Internal Source of Truth)
  │
  ▼
Candidate Analysis LLMs (consumes MD as context, JSON as schema)
```

Markdown and JSON never drift because both are deterministic representations of the same in-memory Pydantic object (`app/schemas/canonical.py`). A schema-aware `Markdown → JSON` converter (`app/services/markdown_to_json.py`) also exists so a TA can edit the rendered Markdown and have those edits parsed back into the canonical object.

---

## 1. Repository Layout

```
ProjectResumeAnalyzer/
├── backend/
│   ├── app/
│   │   ├── schemas/canonical.py          Canonical Pydantic schema (source of truth)
│   │   ├── services/
│   │   │   ├── prompt.py                 JD Understanding Agent system prompt
│   │   │   ├── agent.py                  Orchestration: JD -> LLM -> validated canonical object
│   │   │   ├── llm_service.py            Model-agnostic LLMService -> ProviderAdapter abstraction
│   │   │   ├── mock_extractor.py         Deterministic offline stand-in for LLM (dev/CI testing)
│   │   │   ├── markdown_renderer.py      Canonical object -> Crisp 8-Section Markdown (deterministic)
│   │   │   ├── json_serializer.py        Canonical object -> JSON serializer
│   │   │   ├── markdown_to_json.py       Markdown -> Canonical object (schema-aware parser)
│   │   │   ├── validation.py             Pydantic + cross-field validation rules
│   │   │   └── storage.py                File/S3 storage helpers
│   │   ├── models/db_models.py           SQLAlchemy models (Postgres/SQLite)
│   │   ├── workers/worker.py             Background worker for asynchronous pipeline jobs
│   │   ├── api/routes.py                 FastAPI endpoints
│   │   └── main.py                       FastAPI app entrypoint
│   └── tests/
│       ├── sample_jds/                   6 Test JDs (technical, senior, sales, ambiguous,
│       │                                  bias-flagged, hardware engineering)
│       └── test_pipeline.py              Full pipeline unit & round-trip tests (16 tests)
├── frontend/
│   ├── src/pages/index.tsx               Upload -> status polling -> MD/JSON preview -> download
│   └── src/lib/api.ts                    Typed API client
└── samples/
    ├── job_specification.md              Generated sample output (mock provider)
    └── job_specification.json            Generated sample output (mock provider)
```

---

## 2. Target 8-Section Markdown Structure

The Markdown view is optimized specifically for downstream candidate evaluation, removing repetitive text, internal metadata, and LLM reasoning clutter. It emits strictly **8 scannable sections**:

1. **Role Overview** — Title, seniority, location/work mode, environment, department, and team context.
2. **Requirements** — `### Must-Have` (including merged experience requirements) and `### Preferred` qualifications.
3. **Responsibilities** — Core operational duties and primary expectations.
4. **Evidence & Evaluation Rules** — Per-requirement evidence expectations, process evaluation rules, UNCORED conditions, and concise prohibited inferences.
5. **JD-Specific Evaluation Parameters** — Derived non-conventional parameters presented concisely with title, purpose, and expected evidence.
6. **Ambiguities & Missing Information** — Consolidated ambiguous statements (with TA confirmation flags) and missing JD parameters (with why it matters and recommended actions).
7. **Evaluation Priorities** — Downstream candidate evaluation instructions.
8. **Compliance** — Bias and compliance flags with concerns and recommended actions.

> [!NOTE]
> **Internal Metadata Separation:** Metadata such as `JD ID`, `Prompt Version`, `Model Version`, `Specification Version`, and `Generated At`—along with detailed schema fields (`explicit/derived` status, verbatim source citations, rationale, responsibility mappings, and requirement interpretations)—are **omitted from Markdown** to keep it concise, but remain **100% available in the canonical JSON file and API payloads**.

---

## 3. Running the Project

### Backend (API & Pipeline)

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # Default sets LLM_PROVIDER=mock for offline development
uvicorn app.main:app --reload
```

With `LLM_PROVIDER=mock` (default), the pipeline runs end-to-end without an API key using `mock_extractor.py`.

For real LLM execution via Gemini API, set `LLM_PROVIDER=gemini` and your API key:

```bash
export LLM_PROVIDER=gemini
export LLM_MODEL=gemini-3.6-flash
export GEMINI_API_KEY=your-gemini-api-key
uvicorn app.main:app --reload
```

You can also use Anthropic by setting `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`. The provider abstraction (`LLMService` / `ProviderAdapter` in `app/services/llm_service.py`) handles model integration seamlessly.

### Running Tests

```bash
cd backend
python -m pytest tests/test_pipeline.py -v
```

The test suite runs **16 automated tests** covering:
- End-to-end pipeline execution across all 6 sample JDs (technical, senior, sales, ambiguous, bias-flagged, hardware).
- Verification of the new **8-section Markdown structure**.
- Exclusion of metadata from Markdown while confirming metadata presence in JSON.
- Absence of redundant sections in Markdown.
- Preservation of JD-specific evaluation parameters, evidence rules, ambiguities, and missing information.
- Markdown to JSON round-trip parsing (`Markdown -> Canonical Spec -> JSON`).
- Injection safety and anti-fabrication rules (no invented numeric weights).

### Background Worker

```bash
cd backend
python -m app.workers.worker
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## 4. API Surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/jds` | Upload a JD (file or raw text) |
| GET  | `/api/jds/{jd_id}` | Retrieve JD metadata |
| POST | `/api/jds/{jd_id}/analyze` | Enqueue JD Understanding pipeline |
| GET  | `/api/jds/{jd_id}/analysis` | Check processing status |
| GET  | `/api/jds/{jd_id}/markdown` | Get crisp rendered Markdown (`job_specification.md`) |
| GET  | `/api/jds/{jd_id}/json` | Get canonical JSON payload (`job_specification.json`) |
| POST | `/api/jds/{jd_id}/markdown-to-json` | Parse edited Markdown back to validated canonical JSON |
| POST | `/api/jds/{jd_id}/json-to-markdown` | Deterministically re-render Markdown from JSON |
| GET  | `/api/jds/{jd_id}/versions` | View specification version history |

---

## 5. Key Design Decisions

- **Canonical Object is the Source of Truth:** Both JSON and Markdown are derived deterministically from `JobEvaluationSpecification`.
- **Crisp Markdown View:** The Markdown document is streamlined into 8 scannable sections without metadata bloat or repeated text.
- **No Invented Weights or Scores:** Priority is qualitative (`MUST_HAVE`, `PREFERRED`, etc.). Downstream engines assign scoring weights deterministically.
- **Explicit vs. Derived Tracking:** Preserved internally so downstream agents distinguish explicitly stated requirements from derived interpretations.
- **Bias & Compliance Flagging:** Compliance issues are flagged for TA review without affecting automated candidate scoring.
- **Prompt Injection Defense:** Input JDs are isolated inside `<jd_content>` tags, treating input text strictly as data.
