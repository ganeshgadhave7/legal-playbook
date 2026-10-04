# Project Handover — Acme Legal Playbook Assistant

## Project Objective
A fictional portfolio/demo application for **AI-assisted legal operations** at Acme Technologies LLC. The first vertical slice is a **Vendor Onboarding Playbook**: upload an approved fictional Procurement Policy, answer structured intake questions, and generate a cited onboarding checklist and risk summary that a human approver must review before it is considered valid.

> Demo-only: outputs are AI-generated drafts for qualified human review, not legal advice or approved determinations.

## Architecture
- **Frontend:** React + Vite + TypeScript SPA
- **Backend:** Python FastAPI with async SQLAlchemy
- **AI workflow:** LangGraph state graph for retrieval, assessment, and draft assembly
- **Database:** PostgreSQL + pgvector for relational data and semantic retrieval
- **File storage:** Local private storage during development; planned migration to durable private object storage for deployment
- **Embeddings:** Voyage AI (`voyage-4`, 1024-dim vectors)

## Technology Stack
- Python 3.13, FastAPI, Uvicorn
- SQLAlchemy 2 (async), asyncpg, Alembic
- pgvector, python-docx, python-multipart
- LangGraph, LangChain Core
- Voyage AI client
- React 19, React-DOM, Vite 6, TypeScript 5.8

## Folder Structure
```
legal-playbook/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── core/config.py          # Pydantic settings
│   │   ├── db/session.py           # Async engine + session factory
│   │   ├── models/                 # SQLAlchemy models
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── api/v1/                 # API routers
│   │   ├── services/               # DOCX extraction, chunking, embeddings, storage, usage budget
│   │   └── workflows/              # LangGraph workflows
│   ├── migrations/                 # Alembic migrations
│   ├── tests/                      # Unit + integration tests
│   └── storage/uploads/            # Local upload directory (ignored)
├── frontend/
│   ├── src/app/App.tsx             # Main UI
│   ├── src/lib/api.ts              # API client
│   └── src/styles/global.css
├── docs/                           # Design docs (planned)
├── infra/local/                    # Local infrastructure config (planned)
├── sample-data/                    # Fictional Acme documents
└── scripts/                        # Development helper scripts
```

## Database / Schema
Managed by Alembic migrations:

| Table | Purpose |
|---|---|
| `source_documents` | Uploaded policy versions with status, metadata, storage key, SHA-256 |
| `document_chunks` | Extracted passages with `vector(1024)` embeddings |
| `approval_decisions` | Append-only human review decisions on source documents |
| `embedding_usage` | Singleton token-usage ledger against a local Voyage budget |
| `playbooks` | Reusable playbook definitions (intake questions, prompt template, status) |
| `cases` | Vendor onboarding cases and intake answers (JSONB), linked to a playbook |
| `drafts` | Generated draft versions with content, disclaimer, status |
| `draft_citations` | Links from drafts to retrieved `document_chunks` |
| `draft_reviews` | Human approver decisions on drafts |

Key status flows:
- Source: `uploaded → processing → pending_review → approved → indexing → ready`
- Case: `submitted → processing → draft_pending_review → approved / changes_requested / rejected`
- Draft: `pending_review → approved / changes_requested / rejected / superseded`

## Implemented Features
- FastAPI app with CORS, lifespan management, and `/health` check
- Environment-based configuration with `.env` support
- Async SQLAlchemy session factory and Alembic migrations
- DOCX upload endpoint with MIME/size validation, SHA-256 checksum, and private local storage
- Source-document listing with pagination and status/department filters
- Approval endpoint that records decisions and, on approval, triggers extraction → chunking → Voyage embedding → chunk persistence, moving the source to `ready`
- Semantic retrieval endpoint over `ready` fictional sources with department filter and token-budget tracking
- Database model, schemas, and Alembic migration for generic `playbooks`
- Seeded the existing **Vendor Onboarding Playbook** into `playbooks`
- Generic LangGraph workflow engine (`app/workflows/playbook_draft.py`) that loads any published playbook, validates dynamic intake answers, retrieves sources, and generates drafts using the playbook's prompt template
- Legacy `/api/v1/playbooks/vendor-onboarding/draft` now runs through the generic engine
- New `/api/v1/playbooks/draft` endpoint for any playbook
- Playbook definition CRUD API:
  - `GET /api/v1/playbooks` — list with status/department filters
  - `POST /api/v1/playbooks` — create a draft playbook
  - `GET /api/v1/playbooks/{key}` — get latest version
  - `PUT /api/v1/playbooks/{key}` — update draft version
  - `POST /api/v1/playbooks/{key}/publish` — publish draft
- React frontend:
  - **Source library** tab: upload and approve source documents
  - **Playbooks** tab: create/edit/publish playbooks with a question builder
  - **Run playbook** tab: select a published playbook, render dynamic intake form, generate and display draft with citations
- Playbook API: create draft, list cases, get case, review draft, submit revision
- React UI: source library upload/approval, vendor intake form, draft display with citations, reviewer actions
- Unit and integration tests for DOCX extraction and upload persistence

## APIs
| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Service + database health |
| GET | `/api/v1/source-documents` | List source documents |
| POST | `/api/v1/source-documents` | Upload a DOCX source document |
| POST | `/api/v1/source-documents/{id}/decision` | Approve/reject/request changes; approval triggers indexing |
| POST | `/api/v1/retrieval` | Embed a query and retrieve relevant passages |
| POST | `/api/v1/playbooks/vendor-onboarding/draft` | Create a new vendor onboarding draft |
| GET | `/api/v1/playbooks/vendor-onboarding/cases` | List cases |
| GET | `/api/v1/playbooks/vendor-onboarding/cases/{id}` | Get case + latest draft |
| POST | `/api/v1/playbooks/vendor-onboarding/cases/{id}/revisions` | Submit a revised draft after changes requested |
| POST | `/api/v1/playbooks/vendor-onboarding/cases/{id}/review` | Approve/request changes/reject a draft |

## Configuration Requirements
Create `backend/.env` from `.env.example`:
- `DATABASE_URL` — asyncpg URL, e.g. `postgresql+asyncpg://postgres:PASSWORD@localhost:5432/legal_playbook`
- `VOYAGE_API_KEY` — required for embeddings
- `VOYAGE_EMBEDDING_MODEL` — default `voyage-4`
- `VOYAGE_EMBEDDING_DIMENSIONS` — default `1024`
- `APP_ENV`, `CORS_ORIGINS`, `UPLOAD_STORAGE_PATH`, `MAX_UPLOAD_BYTES`

Frontend uses `VITE_API_BASE_URL` (defaults to `http://localhost:8000`).

## Current Incomplete Work
- No authentication or user/role model; reviewer fields are provisional strings
- Only one playbook (`vendor_onboarding`) is hard-coded; no playbook authoring UI or generic playbook engine
- LLM-based draft generation is implemented but requires an OpenCode API key to produce richer outputs
- No human-in-the-loop interrupt inside LangGraph; workflow runs to completion and then awaits external review
- No vector index beyond the raw `embedding` column; no distance-metric evaluation
- No durable object storage or deployment infrastructure
- No general audit-events table beyond `approval_decisions` and `draft_reviews`
- No automatic retry scheduler for failed indexing
- Frontend is a single-page demo; routing, feature modules, and tests are minimal

## Likely Next Steps
1. Add user/role authentication and replace provisional reviewer strings with foreign keys.
2. Build a generic playbook authoring UI and backend model so new playbooks can be created without code changes.
3. Integrate an LLM into the draft-generation node with strict grounding/citation guardrails.
4. Add LangGraph human-in-the-loop checkpoints for clarification or escalations.
5. Evaluate and add a pgvector index (e.g., IVFFlat/HNSW) and tune retrieval quality.
6. Expand test coverage: workflow integration, retrieval filters, status transitions, and concurrent approvals.
7. Provide Docker Compose local setup and migrate file storage to a private object-store for staging/production.
8. Add an audit-events table and retention/deletion policies.
