# Backend

Initial backend skeleton for the fictional Acme Legal Playbook Assistant.

## Local setup

From the repository root, in PowerShell:

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Edit `backend/.env` with your local PostgreSQL credentials and a **rotated** Voyage key. Do not put secrets in `.env.example`, source code, React, or Git. The `.env` file is ignored by Git.

Set `DATABASE_URL` in SQLAlchemy async format, for example:

```text
postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/legal_playbook
```

If the password contains URL-reserved characters, percent-encode them in the URL. Do not share the resulting URL.

## Run the API

```powershell
python -m uvicorn app.main:app --reload
```

Then open:

- Health check: <http://127.0.0.1:8000/health>
- Interactive API docs: <http://127.0.0.1:8000/docs>

The health endpoint checks PostgreSQL with `SELECT 1` and does not return credentials. No schema or tables are created by this endpoint.

## Database migration

The initial migration creates `source_documents`, `document_chunks` (`vector(1024)`), and append-only `approval_decisions`, and enables the pgvector extension if needed. Review the migration before applying it. From `backend/`, run:

```powershell
.venv\\Scripts\\alembic upgrade head
```

This changes the configured `legal_playbook` database. It is a schema change, so back up any valuable data first. Do not run a downgrade against data you need; the initial downgrade drops these tables.

## Current scope

Implemented: configuration loading, async SQLAlchemy engine/session factory, FastAPI app, and a database health check.

Implemented: initial Alembic migration, local DOCX text extraction with section metadata, and a DOCX upload API that validates files, stores them privately, and writes source metadata with status `uploaded`.

Not implemented yet: document review/approval endpoints, extraction persistence into chunks, Voyage API calls, RAG retrieval, playbooks, LangGraph workflow, authentication, and React UI.

## Test DOCX extraction

From `backend/` with the virtual environment active:

```powershell
python -m pip install -r requirements.txt
python -m pytest tests/unit tests/integration -q
```

The extractor reads the fictional sample at `sample-data/source-documents/Acme_Procurement_Policy.docx` and returns ordered heading, paragraph, and table-row blocks. It does not infer page numbers or create embeddings. Regenerate the sample with `python ../scripts/create_sample_policy.py` from `backend/`.

## Upload a source document

Run the API, open <http://127.0.0.1:8000/docs>, and use `POST /api/v1/source-documents`. Provide the DOCX file and metadata fields. Uploads are limited to 10 MB by default, validated as DOCX containers, saved under the configured private `UPLOAD_STORAGE_PATH` (default `backend/storage/uploads`), and recorded with status `uploaded`. The API records metadata and stores the original file but does not persist extracted blocks or create embeddings. `GET /api/v1/source-documents` lists public metadata with pagination (`limit`, `offset`) and optional exact filters (`status`, `department`). The configured 10 MB limit is a development default.

Upload responses and listing results intentionally omit the private storage key and extracted document contents.
