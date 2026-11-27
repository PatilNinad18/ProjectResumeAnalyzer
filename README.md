# 🎯 ProjectResumeAnalyzer
### Intelligent Job Description Understanding & Candidate Screening Agent

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Next.js 15](https://img.shields.io/badge/Frontend-Next.js%2015-black.svg?logo=next.js)](https://nextjs.org/)
[![Inference](https://img.shields.io/badge/Inference-Local%20%2F%20Ollama-purple.svg)](https://ollama.com/)
[![Architecture](https://img.shields.io/badge/Pipeline-Deterministic%20%2B%20Hybrid%20RAG-orange.svg)]()
[![Privacy](https://img.shields.io/badge/Privacy-100%25%20Offline%20First-success.svg)]()

---

## 📌 Executive Overview

**ProjectResumeAnalyzer** is an intelligent, privacy-first recruiting intelligence platform. It provides a complete, end-to-end evaluation pipeline across two tightly integrated stages:

1. **Stage 1 — Job Description Understanding Agent:** Ingests complex, unstructured JDs (PDF, DOCX, TXT) and transforms them into strict, canonical **Job Evaluation Specifications (Spec v2)** through deterministic extraction, local Hybrid RAG, and optional Ollama LLM enrichment.
2. **Stage 2 — Resume Screening Agent:** Ingests batches of candidate resumes and conducts **grounded, evidence-backed evaluation** against the finalized Job Specification—extracting verbatim quotes, calculating verified job/internship tenure, ranking candidates by match tier, and synthesizing tailored interview questions.

Unlike conventional AI tools that blindly feed raw text to cloud APIs or hallucinate qualifications, ProjectResumeAnalyzer employs a **dual-pipeline, evidence-grounded architecture**:
- **Zero Hallucination Risk:** Critical constraints (salary, location, must-have skills, tenure) and evaluation verdicts are strictly grounded in explicit source text with verbatim quotes.
- **Privacy & Offline Independence:** Operates completely on your local machine using local RAG and optional Ollama inference—zero hiring data ever leaves your workstation.
- **Evidence-based scoring.** Dynamic weight normalization and explicit evidence statuses (`MET`, `PARTIALLY_MET`, `NOT_EVIDENCED`).

---

## ⚡ How It Works (At a Glance)

```text
 STAGE 1: JD UNDERSTANDING AGENT              STAGE 2: RESUME SCREENING AGENT
 
 Raw Job Description                         Candidate Resumes (Batch)
 (PDF, DOCX, TXT)                            (PDF, DOCX, TXT)
        │                                           │
        ▼                                           ▼
 ┌───────────────────────────────┐           ┌───────────────────────────────┐
 │ • Deterministic EKG Parser    │           │ • Deterministic Profiler      │
 │ • Local Hybrid RAG (BM25+TF)  │           │   (Contact, Skills, Education)│
 │ • Offline LLM Enrichment      │           │ • Verified Tenure Calculation │
 └──────────────┬────────────────┘           │   (Jobs/Internships Only)     │
                │                            └──────────────┬────────────────┘
                ▼                                           │
  Canonical Specification v2                                │
  (JSON Schema + Structured Markdown)                       │
                │                                           │
                └───────────────────┬───────────────────────┘
                                    │
                                    ▼
                      ┌───────────────────────────────┐
                      │ Grounded Screening Evaluator  │
                      │ • Verbatim Quote Extraction   │
                      │ • Dynamic Weighted Scoring    │
                      │ • Strict Must-Have Guardrails │
                      │ • Interview Questions & Gaps  │
                      └──────────────┬────────────────┘
                                     │
                                     ▼
                      ┌───────────────────────────────┐
                      │ Ranked Leaderboard & Drawer   │
                      │ 🟢 Strong  🟡 Potential  🔴 No │
                      └───────────────────────────────┘
```

| Phase | What Happens | Key Benefit |
|---|---|---|
| **1. Parse & Match (JD)** | Cleans text, segments sections, and matches domain terms against an Entity Knowledge Graph (EKG). | High-speed, 100% deterministic baseline requiring zero GPU or cloud API. |
| **2. Contextualize (JD)** | Injects domain-specific evaluation standards via built-in BM25 + TF-IDF Reciprocal Rank Fusion (RRF). | Grounded interpretation without semantic drift or invented requirements. |
| **3. Enrich & Standardize (JD)** | *(Optional)* Uses local Qwen3 4B to generate 3-tier evidence rules (Strong / Moderate / Weak). | Produces synchronized Spec v2 JSON schema and structured Markdown. |
| **4. Profile & Extract (Resumes)** | Extracts candidate contact info, technical skills, education, and verified job/internship tenure. | Prevents academic degrees from inflating career experience (freshers evaluate to 0.0y). |
| **5. Grounded Evaluation (Screening)** | Evaluates candidate text against Spec v2 criteria; extracts verbatim quotes for every verdict. | 100% grounded scoring (`MET`, `PARTIALLY_MET`, `NOT_EVIDENCED`) with zero hallucination. |
| **6. Rank & Synthesize** | Computes weighted match score, assigns match tier, flags anomalies, and generates interview questions. | Recruiter-ready leaderboard with deep-dive evidence drawer. |

---

## Windows Quick Start (Recommended)

ProjectResumeAnalyzer includes ready-to-run Windows launcher scripts so you can set up and start the entire stack (FastAPI backend + Next.js frontend) with a single command or double-click.

### Prerequisites for Windows
Before running the scripts, make sure you have:
1. **Python 3.10+** (Download from [python.org](https://www.python.org/))  
   > ⚠️ **Important:** During Python setup, make sure to check the box **"Add Python to PATH"**.
2. **Node.js 18+ & npm** (Download LTS from [nodejs.org](https://nodejs.org/))
3. *(Optional)* **Ollama + Qwen3 4B** (Download from [ollama.com](https://ollama.com/))  
   > 💡 The system runs a **100% deterministic baseline** without Ollama! Ollama is only required for optional local AI evidence enrichment and interactive JD chat.

---

### Step 1: First-Time Setup (`setup.bat`)

Run `setup.bat` once after cloning or pulling repository updates. You can double-click it in Windows Explorer or run it in your terminal:

```cmd
setup.bat
```

**What `setup.bat` does automatically:**
- **Checks prerequisites:** Verifies `python`, `node`, and `npm` in your PATH, and notes if `ollama` is present.
- **Prepares `.env`:** Copies `backend\.env.example` to `backend\.env` if not present. It **preserves your existing `.env`** without overwriting.
- **Creates Virtual Environment:** Creates an isolated Python virtual environment at `backend\.venv`.
- **Installs Backend Dependencies:** Upgrades `pip` and installs all packages from `backend\requirements.txt`.
- **Initializes Database:** Prepares the SQLite database schema at `backend\jd_agent.db`.
- **Installs Frontend Dependencies:** Runs `npm install` inside `frontend`.

---

### Step 2: Daily Launch (`run.bat`)

To start both the FastAPI backend and Next.js frontend, double-click `run.bat` or run:

```cmd
run.bat
```

**What `run.bat` does automatically:**
- Verifies that `backend\.venv` and `frontend\node_modules` exist (prompting you to run `setup.bat` first if not).
- Checks whether the local Ollama service is reachable on port 11434 (informs you if offline, but proceeds safely).
- Checks for port conflicts on port 8000 (backend) and port 3000 (frontend).
- Spawns two dedicated, labeled Command Prompt windows:
  1. `ProjectResumeAnalyzer-Backend` running FastAPI (`http://localhost:8000`)
  2. `ProjectResumeAnalyzer-Frontend` running Next.js (`http://localhost:3000`)
- Displays all relevant application and documentation URLs.

#### Application URLs:
- **Frontend Web UI:** [http://localhost:3000](http://localhost:3000)
- **Backend API:** [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Step 3: Safely Stopping Services (`stop.bat`)

To stop the running application without leaving lingering background processes, double-click `stop.bat` or run:

```cmd
stop.bat
```

**Safety guarantee:**
`stop.bat` specifically targets only ProjectResumeAnalyzer services:
1. Closes the dedicated terminal windows labeled `ProjectResumeAnalyzer-Backend` and `ProjectResumeAnalyzer-Frontend`.
2. Checks ports 8000 and 3000 and terminates *only* listening processes belonging to `python`/`uvicorn` and `node`.
3. Leaves all unrelated applications, editor terminals, and system background processes intact.
4. Cleans up `.run_state`.

---

### Manual Startup Alternatives (Cross-Platform)

If you prefer running manual commands or are running on macOS or Linux:

#### Backend (Terminal 1)
```bash
# 1. Navigate to backend
cd backend

# 2. Create and activate a virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On macOS / Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment variables (if .env doesn't exist)
# On Windows:
copy .env.example .env
# On macOS / Linux:
cp .env.example .env

# 5. Start the FastAPI server
python -m uvicorn app.main:app --reload --port 8000
```

#### Frontend (Terminal 2)
```bash
# 1. Navigate to frontend
cd frontend

# 2. Install dependencies
npm install

# 3. Start the Next.js dev server
npm run dev
```

#### Optional: Local Ollama LLM (Terminal 3)
```bash
# Start Ollama service (if not already running as a Windows service)
ollama serve

# In another terminal, pull the recommended offline model (one-time)
ollama pull qwen3:4b
```

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

## 14. Resume Screening Agent (Grounded Candidate Evaluation)

The **Resume Screening Agent** executes Stage 2 of the recruiting intelligence pipeline. Once a Job Description has been finalized into a **Job Evaluation Specification (Spec v2)**, candidate resumes can be uploaded in bulk to undergo automated, evidence-grounded evaluation.

```text
Candidate Resumes (PDF / DOCX / TXT)
                │
                ▼
┌──────────────────────────────────────────────┐
│ 1. Deterministic Resume Profiler             │
│    • Contact details (email, phone, links)   │
│    • Skills & education parsing              │
│    • Work history filtering (jobs/interns)   │
│    • Strict tenure calculation (0.0y freshers│
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ 2. Grounded Screening Evaluator              │
│    • Evaluates against Spec v2 canonical JSON│
│    • Verbatim quote extraction from resume   │
│    • Standardized verdicts:                  │
│      MET | PARTIALLY_MET | NOT_EVIDENCED     │
│    • Dynamic score weights (70/20/10)         │
│    • Hard must-have guardrails               │
│    • Tailored interview question synthesis   │
│    • Screening run and override history      │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ 3. Asynchronous Worker & DB State Recovery   │
│    • Background worker with SQLite isolation │
│    • Auto-recovery of queued tasks on reboot │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ 4. Interactive Screening Dashboard           │
│    • Ranked candidate leaderboard            │
│    • Tier filters (Strong, Potential, Not Fit│
│    • Verbatim evidence deep-dive drawer      │
│    • One-click candidate deletion & retry    │
└──────────────────────────────────────────────┘
```

### Key Screening Capabilities

1. **Ollama resume profiles**
   - The worker extracts resume text and uses the local Ollama model to create a structured profile with resume excerpts. The candidate detail drawer offers JSON and Markdown downloads.
   - Start Ollama with `qwen3:4b` installed, or set `OLLAMA_RESUME_MODEL` to another installed model. An unreadable file or incomplete model response stays unranked for review.
   - Overall experience uses dated employment and internships and counts overlapping periods once.

2. **Resume evidence**
   - Ollama compares the profile with the finalized JD and returns one judgment per criterion. Positive grades cite excerpts verified against the extracted resume text.
   - A batch run that shares resume files across JDs can reuse the resume profile. Each JD gets its own grades and leaderboard.

3. **Evidence grades**
   - Full evidence earns 100% of the requirement's points, partial evidence earns 50%, a mention earns 25%, and missing evidence earns zero.

4. **Dynamic weighted scoring**
   - The baseline weights are 70 for must-haves, 20 for preferred criteria, and 10 for an explicit overall experience minimum. The evaluator normalizes the active weights. Overall experience earns proportional credit up to the stated minimum.
   - The candidate drawer shows the points earned and available for each requirement. Earlier runs remain in history and can be rerun with the current evaluator.
   - A specification with no usable criteria routes candidates to review without a rank.

5. **Advisory match tiers**
   - **Strong match** requires a score of at least 75%, evidence for every must-have, and a fully met grade for every requirement marked critical by a recruiter.
   - **Potential match** applies at 50% or above when the strong-match conditions need further verification.
   - **Limited evidence** applies below 50%. The recruiter decides how to proceed.
   - Each rerun records its specification and evaluator. Outdated runs stay in history and leave the current ranking. Recruiter overrides preserve the automated result and record the reviewer, time, and reason.

6. **Automated Interview Question Synthesis:**
   - Dynamically crafts technical and behavioral interview questions targeted specifically at the candidate's `PARTIALLY_MET` and `NOT_EVIDENCED` criteria.

7. **Asynchronous Background Processing:**
   - Resumes process in the background without blocking the UI.
   - The worker recovers queued runs from the database after a restart.

### Recruiter validation

Use 30–50 approved, de-identified resumes across the target JDs. Include different file formats, layouts, and experience levels. Give two recruiters separate copies of the same offline reviewer form and have them grade the evidence independently before discussing disagreements. Use an approved transcript for scanned files when available so human reviewers can label them even if the app cannot extract text.

From `backend/`, prepare a packet and compare the two returned review exports.

```powershell
python scripts/validate_screening.py prepare --manifest <manifest.json> --output-dir ../outputs/screening-validation/recruiter
python scripts/validate_screening.py report ../outputs/screening-validation/recruiter/predictions.private.json <review-a.json> <review-b.json> --top-k 10
```

Replace the bracketed paths with your files. The manifest paths are relative to the manifest directory.

```json
{
  "cases": [
    {
      "id": "R001",
      "resume": "approved/R001.pdf",
      "specification": "finalized/backend-spec.json",
      "review_transcript": "approved/R001-transcript.txt",
      "validation_group": "optional-approved-group"
    }
  ]
}
```

The transcript and validation group are optional. The tool keeps scores and validation groups in `predictions.private.json`. Give reviewers `reviewer.html` and keep the predictions with the validation owner. The report shows exact agreement and Cohen's kappa for criterion grades, parsing outcomes by format, and cases both reviewers would advance that fell below the automated shortlist. The shortlist uses the current potential-match score threshold and, if supplied, a per-JD top-k limit that includes ties. Group results require at least five cases, and the tool uses only the groups supplied in the manifest.

Use `prepare --synthetic` in place of `prepare --manifest <manifest.json>` to practice with the offline baseline. Add `--evaluator ollama` to test the synthetic cases with the installed model. The [performance baseline](PERFORMANCE_BASELINE.md#9-screening-batch-benchmark) records the earlier 200-file test of the deterministic evaluator.

### Candidate data handling

- **Access.** Default development and startup commands bind to loopback. The API allows the local frontend origins and an optional exact `FRONTEND_ORIGIN`. The current pilot relies on access to the local machine. Shared deployments need recruiter authentication and project-level authorization before accepting candidate data.
- **Retention.** The data owner chooses the retention period for each JD. From `backend/`, run `python scripts/candidate_retention.py --jd-id <jd-id> --older-than-days <approved-days>` to preview the number of matches. Add `--apply` only when removing those records is approved. The same policy should cover retained copies, exports, and backups.
- **Deletion.** Deleting a candidate removes the stored file, parsed profile, evaluation history, and candidate-specific audit entries for that JD. A failed file deletion leaves the database record available for retry. Active screening runs must finish before deletion.
- **Duplicates and JD reuse.** Uploads reject identical file bytes within the same JD, even after a rename. Different documents for the same person can coexist. Upload the resume to each applicable JD to keep those records and decisions independent.
- **Upload checks.** The app enforces supported formats, PDF and DOCX file signatures, a 10 MB upload limit, and a bound on decompressed DOCX text. Shared deployments should apply malware scanning before the app receives candidate files.

---

## 15. API

### Job Description Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/jds` | List all JDs |
| POST | `/api/jds` | Create/upload a new JD |
| GET | `/api/jds/{jd_id}` | Get JD metadata |
| POST | `/api/jds/{jd_id}/analyze` | Run JD analysis pipeline |
| GET | `/api/jds/{jd_id}/analysis` | Get JD analysis status and results |
| GET | `/api/jds/{jd_id}/markdown` | Get generated Job Specification Markdown |
| GET | `/api/jds/{jd_id}/json` | Get canonical Spec v2 JSON |
| POST | `/api/jds/{jd_id}/markdown-to-json` | Parse edited Markdown back to canonical schema |
| POST | `/api/jds/{jd_id}/json-to-markdown` | Render canonical schema to Markdown |
| GET | `/api/jds/{jd_id}/versions` | Get specification audit versions |
| POST | `/api/jds/{jd_id}/chat` | Chat with a specific JD using RAG + LLM |
| POST | `/api/chat` | Chat with supplied Markdown context |

### Resume Screening Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/jds/{jd_id}/resumes` | Upload candidate resume files (PDF, DOCX, TXT) |
| POST | `/api/jds/{jd_id}/resumes/screen` | Queue screening against the current finalized specification |
| GET | `/api/jds/{jd_id}/resumes` | List candidates with scores, tiers, and statuses |
| GET | `/api/jds/{jd_id}/resumes/{resume_id}` | View the latest run or select a historical run with `evaluation_id` |
| PUT | `/api/jds/{jd_id}/resumes/policy` | Publish a specification revision with updated critical requirements |
| POST | `/api/jds/{jd_id}/resumes/{resume_id}/override` | Record a recruiter override and audit entry |
| POST | `/api/jds/{jd_id}/resumes/{resume_id}/re-screen` | Queue a new run and preserve previous results |
| DELETE | `/api/jds/{jd_id}/resumes/{resume_id}` | Delete a candidate resume and its evaluation records |

---

## 16. Repository Structure

```text
ProjectResumeAnalyzer/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes.py                 # Core JD REST routes
│   │   │   └── screening_routes.py       # Candidate resume screening REST routes
│   │   ├── models/
│   │   │   ├── db_models.py              # JD database tables
│   │   │   └── screening_models.py       # Candidate resume & evaluation tables
│   │   ├── schemas/
│   │   │   ├── canonical.py              # Spec v2 canonical schemas
│   │   │   ├── rag_schemas.py            # RAG domain schemas
│   │   │   └── screening.py              # Candidate screening Pydantic models
│   │   ├── services/
│   │   │   ├── agent.py                  # JD understanding coordinator
│   │   │   ├── llm_service.py            # Provider abstraction (Ollama/Gemini/Claude)
│   │   │   ├── markdown_renderer.py      # Spec v2 Markdown generation
│   │   │   ├── rag/                      # BM25 + TF-IDF Hybrid RAG
│   │   │   └── resume/                   # Resume Screening Services
│   │   │       ├── profiler.py           # Deterministic contact & tenure parser
│   │   │       └── evaluator.py          # Grounded candidate evaluation engine
│   │   ├── workers/
│   │   │   ├── worker.py                 # JD analysis background worker
│   │   │   └── screening_worker.py       # Resume screening queue & worker
│   │   ├── db.py                         # SQLAlchemy database initialization
│   │   └── main.py                       # FastAPI application entrypoint
│   └── tests/
│       ├── test_pipeline.py              # Deterministic JD extraction tests
│       ├── test_rag.py                   # Hybrid RAG retrieval tests
│       ├── test_clarification_lifecycle.py
│       └── test_resume_screening.py      # Grounded screening & profiler tests
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── workflow/                 # JD upload, clarification, & spec review
│   │   │   ├── screening/                # Candidate screening UI
│   │   │   │   ├── ScreeningPage.tsx     # Screening coordinator
│   │   │   │   ├── ResumeUploadZone.tsx  # Multi-file drag & drop upload
│   │   │   │   ├── CandidateLeaderboard.tsx # Ranked candidate table
│   │   │   │   └── CandidateDetailDrawer.tsx # Verbatim quote deep-dive drawer
│   │   │   ├── chat/                     # Interactive JD chat assistant
│   │   │   └── layout/                   # Top navigation tabs & headers
│   │   ├── hooks/
│   │   │   ├── useAgents.ts              # JD analysis workflow state
│   │   │   └── useCandidateScreening.ts  # Screening state, polling & filters
│   │   ├── lib/
│   │   │   ├── api.ts                    # JD API client
│   │   │   └── screening_api.ts          # Screening API client
│   │   └── pages/                        # Next.js pages
│   └── package.json
└── samples/
    ├── job_specification.md
    └── job_specification.json
```

---

## 17. Testing

Run all backend tests:

```bash
cd backend
python -m pytest -v
```

Resume screening tests:

```bash
python -m pytest tests/test_resume_screening.py -v
```

RAG tests:

```bash
python -m pytest tests/test_rag.py -v
```

Pipeline tests:

```bash
python -m pytest tests/test_pipeline.py -v
```

Clarification lifecycle tests:

```bash
python -m pytest tests/test_clarification_lifecycle.py tests/test_batch_clarifications.py -v
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

## 18. Troubleshooting

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

### Port 8000 or 3000 Already in Use
If `run.bat` shows `[WARN] Port 8000 is already in use` or `[WARN] Port 3000 is already in use`:
1. Run `stop.bat` to gracefully terminate any previously opened ProjectResumeAnalyzer instances.
2. If another application is holding the port, inspect which process ID is using it:
   ```cmd
   netstat -ano | findstr /R /C:":8000 .*LISTENING"
   netstat -ano | findstr /R /C:":3000 .*LISTENING"
   ```
3. Terminate the blocking PID (replace `<PID>` with the number from the last column):
   ```cmd
   taskkill /PID <PID> /F
   ```

### Python or Node is Not Recognized on Windows
If `setup.bat` reports that `python` or `node` is missing:
- **Python:** Reinstall Python 3.10+ from [python.org](https://www.python.org/) and make sure to check the box **"Add Python to PATH"** on the first installer screen.
- **Node.js:** Install Node.js LTS from [nodejs.org](https://nodejs.org/).
- Close and reopen your terminal or command prompt window for PATH changes to take effect.

### Frontend Dependency Errors
If `npm install` fails during `setup.bat`:
1. Clear the local npm cache:
   ```cmd
   cd frontend
   npm cache clean --force
   ```
2. Re-run `npm install`:
   ```cmd
   npm install
   ```

### Ollama 404 or 503 Chat / Enrichment Warnings
If you see a warning in backend logs:
```text
WARNING [jd_agent.enrichment] Enrichment batch failed: Ollama chat error: Client error '404 Not Found' for url 'http://localhost:11434/api/chat'
```
- **Cause:** Ollama service is stopped, or the model `qwen3:4b` has not been downloaded yet.
- **Resolution:**
  1. Open a terminal and run `ollama list` to check installed models.
  2. If `qwen3:4b` is not listed, download it: `ollama pull qwen3:4b`
  3. Start the Ollama server: `ollama serve`
- **Fallback behavior:** ProjectResumeAnalyzer is designed to be **resilient**; if Ollama is unavailable, the pipeline automatically falls back to deterministic extraction and returns a complete evaluation specification.

### JSON validation fails

Inspect the Pydantic validation error first. Do not increase the output limit automatically. The canonical schema should remain the source of truth.

---

## 19. Offline Data Flow

```text
                     LOCAL MACHINE (100% PRIVATE)
                     
       Job Description (PDF/DOCX/TXT)      Candidate Resumes (PDF/DOCX/TXT)
                     │                                    │
                     ▼                                    ▼
           Deterministic EKG + RAG               Resume Profiler Engine
           (Optional Ollama Enrich)              (Verified Tenure & Skills)
                     │                                    │
                     ▼                                    │
           Canonical Spec v2 ─────────────────────────────┘
          (JSON + Structured MD)
                     │
                     ▼
           Grounded Screening Evaluator
           • Verbatim Quote Extraction
           • 70/30 Weighted Scoring & Guardrails
           • Tailored Interview Question Synthesis
                     │
                     ▼
           Interactive Next.js Web UI
           • JD Editor & Spec Inspector
           • Candidate Leaderboard & Deep Dive Drawer
           • Real-time Screening Polling
```

No external LLM API or cloud service is required. All hiring data and resume texts remain on your local machine.

---

## 20. Key Design Principles

- **JD & Resumes are authoritative:** The system never invents facts absent from the raw documents.
- **Verbatim Grounding:** Every candidate criterion match must cite an exact quote directly from the candidate's resume.
- **Fair & Standardized Statuses:** `MET`, `PARTIALLY_MET`, and `NOT_EVIDENCED` are applied consistently. Missing skills are treated as unevidenced rather than assumed failures.
- **Fresher Protection:** Work history parsing distinguishes degrees and courses from actual job and internship tenures.
- **Canonical schema is the source of truth:** Downstream screening strictly compares against the validated Spec v2 canonical schema.
- **Offline-first & Privacy-first:** Complete core evaluation runs locally without internet connectivity or data leakage.
- **Multi-JD isolation:** Each JD maintains its own independent analysis, specifications, and candidate pools.
- **Fail-safe resilience:** Division-by-zero protection for zero-criteria JDs and automatic database recovery for queued screening tasks upon restart.

---

## 21. Quick Reference

### Summary of Commands

| Task | Automated (Windows Recommended) | Manual Alternative (Cross-Platform) |
|---|---|---|
| **First-Time Setup** | `setup.bat` | `python -m venv backend/.venv`<br>`backend\.venv\Scripts\activate`<br>`pip install -r backend/requirements.txt`<br>`cd frontend && npm install` |
| **Start Application** | `run.bat` | Terminal 1: `cd backend && python -m uvicorn app.main:app --reload --port 8000`<br>Terminal 2: `cd frontend && npm run dev` |
| **Stop Application** | `stop.bat` | Press `Ctrl+C` in both terminal windows |
| **Optional LLM Setup** | `ollama run qwen3:4b` | `ollama serve` & `ollama pull qwen3:4b` |
| **Run All Tests** | `pytest` | `cd backend && python -m pytest -v` |
| **Run Screening Tests** | `pytest screening` | `cd backend && python -m pytest tests/test_resume_screening.py -v` |

### Key URLs

- **Web Application:** [http://localhost:3000](http://localhost:3000)
- **FastAPI Backend:** [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)


---

## License

Add the project's applicable license here.
