# Initial Data Model — Vendor Onboarding MVP

> **Status:** Approved for initial implementation. See [Decision 0001](decisions/0001-initial-source-document-schema.md).  
> **Scope:** Source document upload, review, and approved-source RAG ingestion.  
> This file documents the initial database design; it does not itself create database objects.

## Scope

The first vertical slice handles fictional Acme Technologies LLC source policies, their approval, and RAG ingestion. It does not yet model users, playbooks, cases, generated drafts, or a full audit log.

## Decisions

1. **One row per source version.** Each uploaded version is a separate `source_documents` row. Historical metadata and chunks remain associated with the exact version used.
2. **Approval history is append-only.** Decisions are stored in `approval_decisions`; changing current status does not erase earlier decisions.
3. **Ingest after approval.** Extract and validate text while the source is pending review, but create embeddings and make chunks retrievable only after human approval. An approved source is not RAG-ready until indexing succeeds.
4. **Embedding model selected:** Voyage `voyage-4`; the test request returned a 1,024-dimensional vector. Use `vector(1024)` and validate dimension at runtime. Reconfirm current model documentation and account quota before bulk ingestion.
5. **Reviewer identity is provisional.** Store a non-secret reviewer identifier until authentication and users are implemented; later migrate to a user foreign key.
6. **Files are private and external to PostgreSQL.** `storage_key` identifies a generated file path/key in private local storage during development. Never trust the original filename as a path.
7. **Only approved and successfully indexed versions are retrievable.** Retrieval must enforce `status = 'ready'`.

## Entity relationship

```text
source_documents 1 ─────── * document_chunks
        │
        └─────────────── * approval_decisions
```

Chunks and approval decisions refer to one exact uploaded version.

## `source_documents`

One row represents one uploaded version of a source document.

| Column | Proposed type | Rules / purpose |
|---|---|---|
| `id` | UUID | Primary key |
| `title` | text | Required; e.g. `Procurement Policy` |
| `department` | text | Required for MVP; e.g. `Procurement` |
| `document_type` | text | Required; e.g. `Policy` |
| `document_code` | text | Optional stable fictional identifier, e.g. `PROC-POL-001` |
| `version` | text | Required version label, e.g. `1.0` |
| `status` | text or enum | Required; values below |
| `storage_key` | text | Required private path/key to original file |
| `original_filename` | text | Required display/audit metadata; never use as a trusted filesystem path |
| `mime_type` | text | Required allow-listed content type |
| `file_size_bytes` | bigint | Required positive size; application applies an upload limit |
| `sha256` | text | Required checksum for integrity/deduplication checks |
| `fictional` | boolean | Required; true for Acme demo material |
| `processing_error` | text | Optional safe error summary, without secrets or unnecessary extracted content |
| `created_at` | timestamptz | Required creation timestamp |
| `updated_at` | timestamptz | Required update timestamp |

### Status values

- `uploaded` — file and metadata saved; not processed
- `processing` — validation and text extraction in progress
- `pending_review` — extraction/validation completed; awaiting approval
- `approved` — human-approved; eligible to start embedding/indexing
- `indexing` — embedding/index operation in progress
- `ready` — approved and successfully indexed; eligible for retrieval
- `rejected` — rejected; never eligible for retrieval
- `archived` — inactive; excluded from retrieval
- `failed` — processing or indexing failed; excluded from retrieval

Allowed transitions:

```text
uploaded → processing
processing → pending_review | failed
pending_review → approved | rejected
approved → indexing | archived
indexing → ready | failed
ready → archived
failed → processing | indexing (explicit retry, depending on failure stage)
rejected → archived
```

A correction to an approved source normally creates a new version row. Do not silently replace an approved file in place.

## `document_chunks`

A row represents an extracted passage from one exact source-document version.

| Column | Proposed type | Rules / purpose |
|---|---|---|
| `id` | UUID | Primary key |
| `source_document_id` | UUID | Required foreign key to `source_documents.id` |
| `chunk_index` | integer | Required, zero-based ordering within the source version |
| `content` | text | Required extracted text; do not log unnecessarily |
| `section` | text | Optional heading or section label |
| `page_number` | integer | Optional positive page number when extraction supports it |
| `embedding` | `vector(1024)` | Voyage `voyage-4`; verify dimension before insertion |
| `created_at` | timestamptz | Required creation timestamp |

Constraints/indexes:

- Unique `(source_document_id, chunk_index)`.
- Foreign key to the source version; define intentional cascade/re-index behavior.
- Index `source_document_id` for joins and re-indexing.
- Retrieval joins to the document and requires `status = 'ready'`.
- Add a vector index only after selecting a distance metric and evaluating retrieval quality at expected corpus size.

## `approval_decisions`

Append-only record of each review outcome on one source-document version.

| Column | Proposed type | Rules / purpose |
|---|---|---|
| `id` | UUID | Primary key |
| `source_document_id` | UUID | Required foreign key to `source_documents.id` |
| `decision` | text or enum | Required; `approved`, `changes_requested`, or `rejected` |
| `reviewer` | text | Required provisional reviewer identifier; replace with user foreign key later |
| `reason` | text | Optional explanation or requested changes |
| `created_at` | timestamptz | Required decision timestamp |

Approval decision and indexing are distinct. If indexing fails after approval, retain the approval record, set status to `failed`, and exclude the source from retrieval until indexing succeeds.

## Ingestion behavior

1. Validate the allow-listed file type and size; compute SHA-256.
2. Save the original under a generated key in private local storage.
3. Insert source metadata with status `uploaded`.
4. Transition to `processing`; extract/validate text but do not embed yet.
5. Save extracted chunks and transition to `pending_review`.
6. On rejection, append a decision and set status `rejected`; do not create embeddings.
7. On approval, append a decision and set status `approved`.
8. Generate embeddings and transition to `indexing`.
9. On success, transition to `ready`; retrieval is now allowed.
10. On error, save a safe error summary and set status `failed`; retry explicitly.

Transactions and retries must leave the document in a recoverable state. Application startup must not create or mutate the schema; use Alembic migrations.

## Deferred decisions

- Database enum versus constrained text status columns.
- Authentication provider and reviewer foreign key.
- Extraction library and initial supported file format.
- Vector distance metric and vector-index type.
- Durable object storage for deployment.
- Retention/deletion rules and general-purpose audit events.
- Playbook, case, answer, draft, citation, and their approval tables.
