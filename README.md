# JD Understanding Agent & Candidate Screening System

A production-oriented **JD Understanding Agent** for an AI-powered Candidate Screening and Evaluation System.

The system analyzes Job Descriptions (JDs), enriches requirement interpretation using a local Hybrid RAG pipeline, and produces a canonical **Candidate Evaluation Specification** as:

- `job_specification.md` — concise, human-readable 8-section JD context
- `job_specification.json` — complete machine-readable canonical specification

The current setup uses **Ollama + Qwen3 4B for local/offline LLM inference**, so JD analysis does not require an external LLM API key.

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

Test the model:

```bash
ollama run qwen3:4b
```

If Qwen responds, the local LLM is ready.

---

## 3. Backend Setup

```bash
cd backend
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
```

### Linux/macOS

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
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

No OpenAI, Gemini, Anthropic, or other external API key is required for Ollama mode.

---

## 4. Optional: Custom Ollama Model Directory

If the Ollama models should be stored on another drive, configure `OLLAMA_MODELS`.

Example on Windows:

```powershell
$env:OLLAMA_MODELS="D:\OllamaModels"
```

For a permanent configuration, add it through Windows Environment Variables.

Do not commit local model files or machine-specific paths to Git.

---

## 5. Run the Backend

From `backend/`:

```bash
uvicorn app.main:app --reload --port 8000
```

Backend:

```text
http://127.0.0.1:8000
```

FastAPI docs:

```text
http://127.0.0.1:8000/docs
```

---

## 6. Run the Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the URL provided by Vite.

---

## 7. End-to-End Workflow

```text
1. Create/select JD
2. Paste JD or upload TXT/PDF/DOCX
3. Run analysis
4. Retrieve local RAG context
5. Generate structured output with Qwen3 4B
6. Validate with Pydantic
7. Generate Markdown + JSON
8. Review JD specification
9. Chat with the active JD
10. Use the specification for downstream candidate evaluation
```

The application supports multiple JDs with independent analysis and chat contexts.

---

## 8. Supported JD Input

The system supports:

- Raw text
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

The RAG implementation is lightweight and local.

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
Context window:          16,384 tokens
Maximum generated output: 8,192 tokens
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
             /                      /                   Local RAG      Ollama
                       Qwen3 4B
            \            /
             \          /
                  v
        Canonical Pydantic Spec
             /                       v             v
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
