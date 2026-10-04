# Acme Legal Playbook Assistant

A fictional portfolio project for AI-assisted legal operations. The planned first workflow is a vendor-onboarding checklist and risk summary grounded in approved fictional Acme Technologies LLC documents, with mandatory human review.

> **Demo only:** This project is not legal advice. Generated content is a draft for qualified human review and must not be treated as an approved legal determination.

## Current status

Planning and repository scaffolding only. Application services, database migrations, frontend, RAG, and LangGraph workflows have not yet been implemented. See [`plan.md`](plan.md) for staged requirements and acceptance criteria.

## Planned architecture

- `frontend/`: React browser application
- `backend/`: Python FastAPI application and LangGraph workflows
- PostgreSQL + pgvector: application records and approved-source retrieval
- Private file storage: local during development; durable private object storage for deployment

The MVP intentionally uses React + FastAPI without a separate Node.js backend to keep the first implementation manageable.

## Planned first vertical slice

1. Upload a fictional Procurement Policy.
2. Review and approve the source document.
3. Ingest approved text and embeddings into PostgreSQL + pgvector.
4. Create and approve a Vendor Onboarding Playbook.
5. Collect structured vendor intake answers.
6. Generate a cited onboarding checklist and risk summary.
7. Have a human approver approve, request changes, or reject the result.

## Repository layout

See the top-level folders. Placeholder files identify components planned for later stages; they are not runnable services yet.

## Security

- Never commit `.env`, API keys, passwords, or database connection strings.
- Use synthetic fictional Acme data only in the portfolio demo.
- Store LLM credentials on the backend or in the deployment provider's secrets manager; never in browser code.
- Rotate any credential previously shared in chat before using it.
