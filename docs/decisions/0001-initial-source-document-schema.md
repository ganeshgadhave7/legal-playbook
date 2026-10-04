# Decision 0001: Initial source-document schema

- **Status:** Accepted
- **Scope:** First source document upload, review, and RAG-indexing milestone
- **Date:** 2026-09-26

## Context

The project has a local PostgreSQL 18.6 database named `legal_playbook` with pgvector 0.8.6. The FastAPI health endpoint can connect to it. The fictional DOCX sample `sample-data/source-documents/Acme_Procurement_Policy.docx` exists. Voyage `voyage-4` returned a 1,024-dimensional embedding during a single-sentence test.

The first workflow needs to store source metadata, maintain approval history, and eventually store extracted text chunks and vectors. Embeddings must not be generated for or retrieved from unapproved documents.

## Decision

Use three initial tables:

1. `source_documents` — one row per uploaded source version; metadata, processing/approval/indexing status, private storage key, checksum, and fictional marker.
2. `document_chunks` — extracted passages associated with a specific source version, including section/page metadata and `vector(1024)` embedding.
3. `approval_decisions` — append-only decisions for a source version, with a provisional reviewer identifier until user/auth tables are introduced.

Create embeddings only after approval. Transition approved sources through `indexing` to `ready`. Retrieval is permitted only when the source status is `ready`.

## Initial status values

```text
uploaded → processing
processing → pending_review | failed
pending_review → approved | rejected
approved → indexing | archived
indexing → ready | failed
ready → archived
failed → processing | indexing (explicit retry)
rejected → archived
```

Transitions are enforced in application services; the database should also constrain status and decision values. A new upload/revision is a new `source_documents` row, not an in-place overwrite.

## Consequences

- Embedding storage uses pgvector `vector(1024)` for the tested Voyage model. Validate the returned vector length before inserting. Changing models/dimensions later requires a planned migration and re-embedding strategy.
- Unapproved and failed versions cannot be retrieved.
- Approval is recorded separately from current status so review history is preserved.
- Reviewer identity is provisional and will be migrated to a user foreign key when authentication is added.
- The initial schema does not model playbooks, cases, generated drafts, or full audit events; those are separate later stages.

## Initial constraints and indexes

- Primary keys are UUIDs.
- Required text and metadata columns are non-null where specified in `docs/data-model.md`.
- `file_size_bytes > 0`.
- `page_number > 0` when present; `chunk_index >= 0`.
- Unique `(source_document_id, chunk_index)`.
- Foreign keys from chunks and decisions to source documents.
- Check constraints for source status and approval decision values.
- Index source status and document foreign keys for filtering/joins. Add vector index only after retrieval tests and corpus-size needs justify it.

## Migration implementation notes

- Enable the pgvector extension using `CREATE EXTENSION IF NOT EXISTS vector` in the migration or confirm it is provisioned before migration.
- Apply migrations using Alembic; do not create schema as an application-startup side effect.
- Store timestamps as timezone-aware `timestamptz`.
- Make revision/rollback behavior explicit and test against a development database.
- Never include credentials in migration files or logs.
