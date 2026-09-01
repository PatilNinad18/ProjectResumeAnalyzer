# JD Understanding Agent

A reference implementation of the "JD Understanding Agent" for an AI-powered
Candidate Screening and Evaluation System. It converts a raw Job Description
into a **canonical Candidate Evaluation Specification**, rendered as both
`job_specification.md` (context for downstream Candidate-Analysis LLMs) and
`job_specification.json` (machine-readable, backend/API-consumable).

```
RAW JD
  │
  ▼
JD Understanding Agent  (LLM + structured output, Pydantic-validated)
  │
  ▼
Canonical JobEvaluationSpecification   <-- SINGLE SOURCE OF TRUTH
  ├── Markdown Renderer  ──▶ job_specification.md
  └── JSON Serializer    ──▶ job_specification.json
  │
  ▼
Candidate Analysis LLMs (out of scope here; consumes MD as context, JSON as schema)
```

Markdown and JSON never drift because both are deterministic functions of the
same in-memory Pydantic object (`app/schemas/canonical.py`). A schema-aware
`Markdown → JSON` converter (`app/services/markdown_to_json.py`) also exists so
a TA can hand-edit the rendered Markdown and have those edits validated back
into the canonical object.

## 1. Repository layout

```
backend/
  app/
    schemas/canonical.py          Canonical Pydantic schema (source of truth)
    services/
      prompt.py                   JD Understanding Agent system prompt
      agent.py                    Orchestration: JD -> LLM -> validated canonical object
      llm_service.py              Model-agnostic LLMService -> ProviderAdapter abstraction
      mock_extractor.py           Deterministic offline stand-in for the LLM (dev/CI only)
      markdown_renderer.py        Canonical object -> Markdown (deterministic)
      json_serializer.py          Canonical object -> JSON
      markdown_to_json.py         Markdown -> Canonical object (schema-aware parser)
      validation.py               Pydantic + cross-field validation, structured issues
      storage.py                  Private S3 helper (put/get/presign)
    models/db_models.py           SQLAlchemy models (Postgres/RDS)
    workers/worker.py             SQS-polling background worker (PARSING..READY pipeline)
    api/routes.py                 FastAPI endpoints
    main.py                       FastAPI app entrypoint
    config.py, db.py              Settings & DB session
  tests/
    sample_jds/                   5 required test JDs (technical, senior, sales,
                                   ambiguous, bias-flagged)
    test_pipeline.py              End-to-end tests against the mock LLM provider
frontend/
  src/pages/index.tsx             Upload -> status polling -> MD/JSON preview -> download
  src/lib/api.ts                  Typed API client
samples/
  sample_jd.txt
  job_specification.md            Generated sample output (mock provider)
  job_specification.json          Generated sample output (mock provider)
```

## 2. Running it

### Backend (API + pipeline)

```bash
cd backend
pip install -r requirements.txt --break-system-packages
cp .env.example .env          # set LLM_PROVIDER=mock for local dev without an API key
uvicorn app.main:app --reload
```

With `LLM_PROVIDER=mock` (the default), the whole pipeline runs end-to-end
without any external API key or network access, using a small deterministic
rule-based extractor (`mock_extractor.py`) that stands in for the real LLM.

For real LLM output during testing without a paid key, set
`LLM_PROVIDER=gemini` and `GEMINI_API_KEY` (free key from
https://aistudio.google.com/apikey — Flash / Flash-Lite models currently
have a no-cost quota; Pro-series models are paid-only). E.g.:

```bash
export LLM_PROVIDER=gemini
export LLM_MODEL=gemini-2.5-flash        # or gemini-2.5-flash-lite for higher rate limits
export GEMINI_API_KEY=your-free-api-key
uvicorn app.main:app --reload
```

Switch to `LLM_PROVIDER=anthropic` (and set `ANTHROPIC_API_KEY` via your
secrets manager / environment) for production. No other code changes are
required in any case, because the Agent only talks to `LLMService` —
`app/services/llm_service.py` holds a `ProviderAdapter` per provider
(`AnthropicAdapter`, `GeminiAdapter`, `MockAdapter`), so adding yet another
provider (OpenAI, Bedrock, Groq, a local Ollama endpoint, etc.) only means
adding one more adapter class there.

### Tests

```bash
cd backend
LLM_PROVIDER=mock PYTHONPATH=. python -m pytest tests/ -v
```

This exercises all 5 required test-JD categories through the full pipeline:
conventional extraction, must-have/preferred classification, semantic
interpretation, responsibility mapping, non-conventional parameters, evidence
requirements, UNCORED rules, ambiguity detection, compliance flags, Markdown
generation, JSON generation, Markdown→JSON, and Markdown/JSON consistency. It
also has a dedicated test asserting prompt-injection content embedded in a JD
is never echoed into the output, and that no numeric probabilities/weights
are invented.

### Background worker

```bash
cd backend
python -m app.workers.worker   # polls SQS_QUEUE_URL; processes PARSING..READY
```

The API's `/analyze` endpoint enqueues work; in this reference build it also
provides an inline fallback (`_queue_processing` in `api/routes.py`) so the
same code path works without standing up SQS locally.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_BASE` if the API isn't on `http://localhost:8000/api`.

## 3. API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/jds` | Upload a JD (file or raw text) |
| GET  | `/api/jds/{jd_id}` | JD metadata |
| POST | `/api/jds/{jd_id}/analyze` | Enqueue JD Understanding |
| GET  | `/api/jds/{jd_id}/analysis` | Processing status |
| GET  | `/api/jds/{jd_id}/markdown` | Latest rendered Markdown |
| GET  | `/api/jds/{jd_id}/json` | Latest canonical JSON |
| POST | `/api/jds/{jd_id}/markdown-to-json` | Convert (TA-edited) Markdown back to validated JSON |
| POST | `/api/jds/{jd_id}/json-to-markdown` | Deterministically re-render Markdown from JSON |
| GET  | `/api/jds/{jd_id}/versions` | Specification version history |

## 4. Key design decisions

- **Canonical object, not Markdown, is the source of truth.** Both artifacts
  are pure functions of `JobEvaluationSpecification`.
- **Structured output first.** The Agent prompt (`services/prompt.py`)
  requires the LLM to return a single JSON object; free-form Markdown is
  never the primary output.
- **Explicit vs. derived is tracked everywhere** (`explicit_or_derived` on
  requirements, interpretations, and non-conventional parameters) so
  downstream Candidate-Analysis LLMs never mistake an inference for a stated
  requirement.
- **No fabricated evidence, no invented weights.** The schema has no numeric
  score/weight field; `evaluation_rules` and `unscored_rules` explicitly
  forbid the LLM from inventing them. Priority is qualitative
  (MUST_HAVE/PREFERRED/CONTEXTUAL/INFORMATIONAL/AMBIGUOUS) so the
  deterministic backend scoring engine (out of scope here) assigns weights.
- **Bias/compliance is flag-only.** `ComplianceFlag` entries are never folded
  into `evidence_requirements` or scoring guidance; they only route to TA
  review.
- **Prompt-injection resistance.** The JD is wrapped in `<jd_content>` tags
  and the system prompt explicitly instructs the model to treat its contents
  as data, never instructions. A regression test enforces this for the mock
  provider; the same instruction applies to the real LLM prompt.
- **Model-agnostic LLM layer.** `LLMService -> ProviderAdapter` means adding
  a second provider (OpenAI, Bedrock, etc.) touches only `llm_service.py`.
- **Versioning & traceability.** Every specification carries
  `jd_id/jd_version/specification_version/prompt_version/model_version`, and
  important requirements carry a `source` (verbatim snippet + section) back
  to the JD text.

## 5. Known limitations

- `mock_extractor.py` is a **development/CI stand-in**, not a real JD
  understanding model. It uses a small keyword/regex heuristic and is
  intentionally conservative (it omits rather than guesses), but it is far
  less capable than a real LLM run through `prompt.py`. Swap
  `LLM_PROVIDER=anthropic` (or another real adapter) before relying on
  output quality.
- `markdown_to_json.py` round-trips the Markdown produced by
  `markdown_renderer.py` reliably, but a heavily hand-edited or
  restructured Markdown document (headers renamed, sections reordered
  beyond recognition) may not parse cleanly — it returns `warnings` rather
  than silently guessing, but very free-form edits may need a
  re-run through the LLM instead of the deterministic parser.
- Authentication, RBAC enforcement, and Secrets Manager wiring are stubbed
  (`config.py`/`db_models.py` model the shape; no concrete Cognito/Auth0/
  Supabase client is wired up) — this is called out per the "do not
  over-engineer" instruction to prioritize the JD Understanding Agent core.
- CloudWatch/monitoring integration is represented by structured
  fields (tokens, latency, cost, status) persisted on `JobSpecificationVersion`
  / `ProcessingJob`; actual CloudWatch metric emission is not wired up.
- The background worker's SQS polling loop is minimal (no dead-letter queue
  handling, no exponential backoff/jitter beyond the LLMService retry count).
- The frontend is a single-page minimal implementation covering the core
  workflow (upload → status → MD/JSON preview → download); it does not yet
  implement multi-project navigation, auth screens, or version diffing.

## 6. Recommended next steps

1. Wire a real `ProviderAdapter` (Anthropic/Bedrock) into production and
   evaluate the Agent prompt against a larger, more diverse JD corpus.
2. Add Alembic migrations in place of `Base.metadata.create_all`.
3. Wire actual AWS Cognito/Auth0/Supabase auth + role-based route guards.
4. Emit CloudWatch custom metrics (latency, token usage, cost, failure
   counts, queue depth) from the worker and API.
5. Add version-diff UI (compare `specification_version` N vs N-1).
6. Expand the frontend to show non-conventional parameters, ambiguities, and
   compliance flags as distinct, visually separated panels (not just inside
   the Markdown preview), matching section 28 of the original brief.
7. Add per-requirement TA override/approval workflow that writes an
   `AuditEvent` and produces a new `specification_version`.
"# ProjectResumeAnalyzer" 
