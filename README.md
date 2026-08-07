# UAE VAT Compliance Platform

An AI-powered platform for reviewing invoices and documents against **UAE Federal
Tax Authority (FTA)** VAT legislation. It combines a **deterministic VAT rule
engine** (reproducible, auditable verdicts) with **AI-assisted extraction** and a
**RAG assistant** grounded in official FTA source material.

> **Design principle — trust before cleverness.** Compliance verdicts (mandatory
> fields, TRN format, VAT math, reverse-charge triggers) are produced by an
> explicit rule engine, not by a language model. The AI handles OCR, data
> extraction, natural-language explanation, and citation retrieval. This keeps the
> tool's conclusions **defensible in an FTA audit**.

---

## Architecture

```
vat-platform/
├─ apps/
│  ├─ web/        Next.js 14 (App Router) · TypeScript · Tailwind · shadcn/ui
│  ├─ api/        FastAPI (Python 3.11) · REST · Pydantic v2
│  └─ worker/     Background jobs: OCR, extraction, embedding (Celery + Redis)
├─ packages/
│  └─ shared/     Shared type/schema definitions
├─ infra/
│  └─ docker-compose.yml   Postgres (+pgvector) · MinIO (S3-compatible) · Redis
└─ docs/          Architecture notes, VAT rule references
```

**Data services**

| Service    | Role                                             | Local           | Production          |
|------------|--------------------------------------------------|-----------------|---------------------|
| PostgreSQL | Relational data **and** vector search (pgvector) | Docker          | Managed Postgres    |
| MinIO      | Document object storage (S3 API)                 | Docker          | AWS S3 / compatible |
| Redis      | Job queue + sessions                             | Docker          | Managed Redis       |

The API also supports a **zero-dependency dev mode** (SQLite + local-folder
storage) so you can boot it without Docker while developing.

---

## Legal knowledge hierarchy

All VAT conclusions cite the applicable source, prioritised in this order:

1. **Federal Decree-Law No. 8 of 2017** (VAT) and amendments
2. **Executive Regulation** — Cabinet Decision No. 52 of 2017 (as amended, incl. No. 46 of 2020, No. 99 of 2022)
3. **Cabinet Decisions**
4. **Ministerial Decisions**
5. **FTA Public Clarifications** (VATPxxx)
6. **Official FTA Guides**
7. Other FTA publications

> **Knowledge-base honesty note.** The platform does **not** scrape or mirror the
> entire tax.gov.ae website. Official FTA PDFs/guides are **ingested, versioned,
> and cited** through a controlled pipeline with a manual *refresh & approve* step.
> The AI answers from **retrieved official text**, never from unattributed model
> memory.

---

## Roadmap

| Phase | Deliverable                                                                 | Status |
|-------|-----------------------------------------------------------------------------|--------|
| 0     | Repo scaffold, docker-compose, DB schema, app skeleton                       | ✅ done |
| 1     | Invoice Review slice: upload → OCR → AI extraction → rule engine → report (backend) | ✅ done (unverified until Python installed) |
| 2     | Next.js dashboard UI + VAT AI Assistant + RAG knowledge base with citations  | ⏳ next |
| 3     | Document repository, global search, compliance history, approval workflow    | ⏳ |
| 4     | Reports (Excel/Word), admin panel, RBAC, audit logs                          | ⏳ |
| 5     | Security hardening, backups, deployment prep                                 | 🔨 configs ready — see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |

## Deploying

Frontend → **Vercel** (`apps/web`), backend → **Render** (`apps/api`, Docker) with
managed Postgres + a persistent disk. Everything is pre-configured
([`render.yaml`](render.yaml), [`apps/api/Dockerfile`](apps/api/Dockerfile),
[`apps/web/vercel.json`](apps/web/vercel.json)). Step-by-step:
**[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

## API (Phase 1)

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/health` | Liveness |
| POST | `/api/review` | Run the rule engine on a structured invoice (JSON) |
| POST | `/api/documents/upload` | Upload a file (PDF/image/Excel/CSV/Word/ZIP) → extract → review → persist |
| GET  | `/api/reviews` | List reviews (filter by `risk`, `status`) |
| GET  | `/api/reviews/{id}` | Full review detail (invoice + findings + advisory) |
| PATCH| `/api/reviews/{id}/status` | Approval workflow: draft/pending/approved/rejected/archived |
| GET  | `/api/reviews/{id}/report?format=pdf\|html` | Download compliance report |
| GET  | `/api/dashboard` | Risk/status aggregates for the Home dashboard |
| GET  | `/api/ai/status` | Current AI configuration (configured/ready/provider/model) |
| POST | `/api/ai/verify` | Live check that the API key + model actually work |
| POST | `/api/ai/reviews/{id}/reanalyze` | Regenerate the AI advisory for a review with the current provider |
| POST | `/api/ai/analyze/combined` | Cross-document AI analysis over several reviews |
| POST | `/api/chat` | VAT assistant — RAG-grounded, returns `citations` |
| POST | `/api/knowledge/seed` | Load the bundled seed corpus (idempotent) |
| POST | `/api/knowledge/ingest` | Ingest an official FTA document (PDF/Word/text) into the KB |
| GET  | `/api/knowledge/search?q=` | Semantic search over indexed provisions |
| GET  | `/api/knowledge/documents` | List indexed knowledge documents |

**RAG:** retrieval uses an offline lexical embedder by default (no key) and OpenAI
embeddings when `OPENAI_API_KEY` is set; answer generation uses the chat provider
(Claude). Vectors are stored in the DB and ranked in Python — portable across SQLite
and Postgres (pgvector-ready). The seed corpus is concise cited summaries, not
verbatim law; ingest official FTA PDFs for authoritative text.

**AI provider:** Extraction and advisory run through a provider-agnostic layer
(`app/ai/`). The provider is **auto-detected from whichever API key is present** —
just add `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) to `apps/api/.env` and restart.
With no key, the app still produces a **deterministic, data-grounded advisory**
(referencing the actual extracted values) — never a dead-end message. Adding a key
upgrades this to full Claude/GPT consultant-style analysis that reads the raw
extracted text and structured data. Check status at `GET /api/ai/status`; confirm a
key works with `POST /api/ai/verify`.

**Activate AI (one step):** edit `apps/api/.env`, paste your key after
`ANTHROPIC_API_KEY=`, restart the API. `GET /api/ai/status` should then show
`"ready": true`.

Install everything for the full pipeline: `pip install -e ".[all,dev]"`.

---

## Getting started (Windows)

### 1. Install the toolchain

You currently have only Git installed. Install these (all free):

| Tool            | Version | Download                                             |
|-----------------|---------|------------------------------------------------------|
| **Python**      | 3.11+   | https://www.python.org/downloads/ (tick *Add to PATH*) |
| **Node.js**     | 20 LTS  | https://nodejs.org/en/download                       |
| **Docker Desktop** *(optional for dev)* | latest | https://www.docker.com/products/docker-desktop/ |

Verify in a **new** terminal:

```bash
python --version   # 3.11+
node --version     # v20+
docker --version   # optional
```

### 2. Run the backend (SQLite dev mode — no Docker needed)

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy ..\..\.env.example .env
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs · Health: http://localhost:8000/health

### 3. Run with full data services (Docker)

```bash
docker compose -f infra/docker-compose.yml up -d
# then run the API pointing at Postgres (set DATABASE_URL in .env)
```

### 4. Run the tests

```bash
cd apps/api
pytest
```

### 5. Run the frontend (Next.js dashboard)

```bash
cd apps/web
npm install
npm run dev
```

Dashboard: http://localhost:3000 — it talks to the API at `NEXT_PUBLIC_API_BASE`
(default `http://localhost:8000`, set in `apps/web/.env.local`). Run the backend
(step 2) at the same time.

> **Note (this machine):** Node was installed per-user (portable) at
> `%LOCALAPPDATA%\nodejs-portable\node-v20.18.1-win-x64`. Either add that folder to
> your PATH, or prefix `npm`/`node` with that path.

---

## Status

This repository is under active, incremental construction. Nothing is deployed.
See `docs/` for architecture decisions and the VAT rule catalogue.
