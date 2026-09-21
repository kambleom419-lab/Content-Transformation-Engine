# Content Transformation Engine

**Gen AI Platform for Automated Content Transformation**
Smart India Hackathon 2026 · Problem Statement **26154** · Sponsored by **NTRO** · Theme: Blockchain & Cybersecurity

One source in. Every deliverable out — consistently, with citations, human review, and an audit trail.

---

## What it does

An operator submits source material — an advisory, incident report, policy document, article, prompt, image, scan, or recording — selects one or more output types on the dashboard, and the platform produces **all of them from a single reading of that source**.

| Output selected | Deliverable |
|---|---|
| **Advisory** | Structured security advisory (PDF) |
| **Executive Summary** | Concise executive briefing (PDF) |
| **Presentation** | Slides with speaker notes (PPTX) |
| **LinkedIn Post** | Publication-ready post (TXT) |
| **Twitter/X Post** | Platform-optimised post or thread (TXT) |
| **Video Package** | Script, storyboard, scene descriptions, narration, subtitles (SRT) and visual recommendations |
| **Infographic** | Rendered poster (PNG) with content, layout recommendations and key messaging |

Generation parameters per run: **target audience, tone, language, communication objective** — with **language selectable per artefact**, so one deck can be in English while the post is in Hindi.

---

## Architecture

```
                    ┌─────────────────────────────────────────┐
   SOURCES          │              UNDERSTAND                 │       DELIVERABLES
  PDF · DOCX  ──────┤    one reading → one content model      ├─────►  Advisory
  Scans · Images    │   (the only stage that decides facts)   │        Executive summary
  Audio · Video     │                                         │        Presentation
  URLs · Text       └─────────────────────────────────────────┘        LinkedIn post
  Hindi · English                     ▲                                X thread
                                      │                                Video package
                           ┌──────────┴──────────┐                     Infographic
                           │    HUMAN REVIEW     │
                           │   pause · refine    │
                           └─────────────────────┘
```

The pipeline is a **LangGraph state machine**:

```
ingest_source → clean_parse → understand → ┬→ generate_and_check[advisory]      ┐
                                           ├→ generate_and_check[presentation]  ├ run in parallel
                                           └→ generate_and_check[linkedin_post] ┘
                                                     ↓
                                              human_review  (interrupt)
                                                     ↓
                           accept → guardrails_render → real files + sha256 manifest
                           refine → apply_feedback → back to the fan-out
```

**The central design decision:** the model reads the source **once** and freezes its meaning into a single *content model*. Every artefact is a projection of that object rather than a fresh reading — which is why outputs cannot disagree with each other, and why adding an eighth artefact costs one small call instead of another full read.

A separate 2-page architecture document accompanies this repository.

---

## Setup

### Prerequisites

| | Version used | Notes |
|---|---|---|
| Python | 3.11+ | tested on 3.11 |
| Node.js | 20+ | tested on 24.15 |
| Disk | ~4 GB free | Docling pulls PyTorch (~2.5 GB) |
| RAM | 16 GB | **CPU only — no GPU required** |

> **The first `pip install` is slow.** PyTorch is ~2.5 GB and downloads into pip's cache, so the virtual-environment size does not move for several minutes. This is expected — do not interrupt it.

### 1. Backend

```bash
git clone https://github.com/kambleom419-lab/Content-Transformation-Engine.git
cd Content-Transformation-Engine

python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
```

### 2. Configure providers

```bash
copy .env.example .env            # Windows
# cp .env.example .env            # macOS / Linux
```

Open `.env` and set **at least one** provider key:

```bash
GEMINI_API_KEY=...        # vision, audio transcription, strongest structured output
GROQ_API_KEY=...          # text, JSON, Whisper audio — fast
OPENROUTER_API_KEY=...    # text and vision backup
```

You do **not** need all three. The configured chain is `groq,openrouter,gemini`, and any provider without a key is skipped automatically — the system runs on whatever you have.

**No API key at all?** Set `USE_STUB=1` to run the entire pipeline — ingestion, graph, review, rendering — with deterministic offline responses.

**Fully offline / air-gapped?** Start [Ollama](https://ollama.com), pull a model, then set:

```bash
LLM_FALLBACK_CHAIN=ollama
OLLAMA_MODEL=qwen2.5:7b
DOCLING_OCR=1             # local OCR instead of a cloud vision model
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The UI expects the API at `http://127.0.0.1:8000`. To change it, create `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

### 4. Run

Two terminals:

```bash
# Terminal 1 — engine
.venv\Scripts\python.exe -m uvicorn engine.api:app --host 127.0.0.1 --port 8000

# Terminal 2 — user interface
cd frontend && npm run dev
```

Open **http://localhost:3000/dashboard**.

Confirm the engine is healthy:

```bash
curl http://127.0.0.1:8000/health
```

> **Start the engine before demonstrating it.** The first request loads Docling's document-layout model (10–20 seconds). A cold first run looks like a hang.

---

## Using it

1. **Upload** a source document, paste text, or supply a URL.
2. **Select outputs** — one or more of the seven types. A language selector appears under each selection.
3. **Set parameters** — audience, tone, language, objective.
4. **Choose a template** for the deck and poster (Classic / Midnight / Bold), previewed as real renders.
5. **Generate.** The run pauses at **human review**.
6. **Inspect** the artefacts and the per-claim verification panel on the results page.
7. **Refine** specific artefacts with an instruction, or **Accept & export**.
8. **Download** the export pack — every file carries a sha256 hash.

### API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Provider chain, cooldowns, tracing status |
| `GET` | `/usage` | Token, latency and error accounting per provider |
| `POST` | `/run` | Start a run (JSON sources) |
| `POST` | `/run/upload` | Start a run (multipart file upload) |
| `GET` | `/run/{id}` | Current snapshot — status, artefacts, verdicts |
| `POST` | `/run/{id}/resume` | `{"action": "accept"}` or `{"action": "refine", ...}` |
| `GET` | `/run/{id}/preview/{type}` | Render an artefact on demand, before approval |
| `GET` | `/run/{id}/artefacts/{type}/download` | Download a rendered file |
| `GET` | `/runs` | Run list |
| `GET` | `/templates` | Design templates with preview URLs |
| `GET` | `/languages` | Supported languages per artefact |

---

## Tests

```bash
.venv\Scripts\python.exe -m pytest tests/ -q
```

**82 offline tests** — no network and no API key required. They cover chunking, document parsing (real PDF and DOCX generated at test time), OCR page selection, vision-call batching, URL extraction, language detection, multi-source dedupe and partial failure, content-model repair, the fact-check (including a regression test for changed numbers) and graph wiring.

---

## What makes it different

1. **One reading, one content model.** Artefacts are projections of a single structured object, so they cannot drift apart. This is the architectural reason multi-output works.
2. **Claims are verified, not merely generated.** Every sentence in an artefact is checked against the source with its citation shown. Changed numbers, dates and versions are caught explicitly; fabricated indicators are flagged by pattern.
3. **The model produces blueprints; libraries produce files.** Rendering is deterministic, so a given draft always yields byte-identical output — which is what makes the sha256 manifest meaningful.
4. **Human review is structural.** The graph genuinely pauses (`interrupt()`) and resumes on a decision. It is not a UI overlay.
5. **Multi-source and multimodal.** Several sources in one run, with partial failures tolerated and reported, including scanned pages, handwriting, embedded figures, audio, and multiple languages.
6. **Provider-agnostic by design.** Groq, OpenRouter, Gemini and Ollama behind one adapter, rotated per call with per-provider cooldowns. This is the answer to *"can it run inside our network?"* — one configuration line, no code change.

---

## Known limitations

Stated plainly, because an intelligence platform should not overstate itself:

| Limitation | Detail |
|---|---|
| **Fact-checking is lexical, not semantic** | Word-overlap grounding plus explicit number and indicator checks. It will not catch a well-paraphrased fabrication; semantic entailment is the next step. |
| **PDF and poster renderers are Latin-script only** | Pillow and reportlab do not shape complex scripts. Non-Latin languages work in `.txt` and `.pptx`; for PDF and poster artefacts the option is disabled and the run warns, rather than emitting empty boxes. |
| **Run history is in-memory** | The checkpointer is `MemorySaver`, so runs do not survive an engine restart. `SqliteSaver` is the production path. |
| **Free-tier rate limits** | Parallel branches are capped (`MAX_CONCURRENT_BRANCHES`) because each selected output is one provider request. Runs can take 60–180 seconds under throttling. |
| **Docling's first run is slow** | A model download followed by a 10–20 second cold start. |

---

## Tech stack

| Concern | Choice |
|---|---|
| Orchestration | LangGraph — state machine, `Send` fan-out, `interrupt`, checkpointer |
| Document parsing | Docling (PDF, DOCX, PPTX, XLSX, HTML) with a PyMuPDF fast path |
| Vision OCR / transcription | Provider vision; Groq Whisper or Gemini Files API for audio |
| Language detection | `langdetect`; translation via the provider |
| Model providers | Groq, OpenRouter, Gemini, Ollama behind one adapter |
| API | FastAPI + Uvicorn |
| Rendering | `python-pptx`, ReportLab, Pillow |
| Frontend | Next.js (App Router) + TypeScript |
| Observability | Optional LangSmith tracing + a local token/latency ledger |

---

## Repository layout

```
engine/
├── graph.py           LangGraph state machine
├── state.py           EngineState contract
├── ingestion/         Multi-source ingestion, Docling, OCR, language
├── understand.py      Corpus → content model (map-reduce for large documents)
├── generate.py        Artefact generation and verification
├── render.py          PDF, PPTX, PNG, Markdown, SRT, TXT renderers and templates
├── recipes.py         Schemas, prompts, artefact profiles, languages
├── llm.py             Provider interface (Gemini, Stub)
├── providers.py       OpenAI-compatible providers with per-call rotation
├── api.py             FastAPI application
├── jobs.py            Run registry
├── usage.py           Local token and latency ledger
└── tracing.py         Optional LangSmith tracing

frontend/              Next.js operator dashboard
tests/                 Offline test suite
```
