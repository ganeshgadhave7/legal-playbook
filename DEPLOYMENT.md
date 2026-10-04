# Deployment Guide — Vercel + Railway

## Architecture

```
Vercel
  └── Frontend (React + Vite + TypeScript SPA)

Railway
  ├── FastAPI (Docker)
  ├── LangGraph + Agentic Workflow (inside FastAPI)
  ├── PostgreSQL + pgvector
  └── (Optional: Redis for LangGraph persistence)

External
  ├── LLM API (OpenAI-compatible, e.g., OpenCode, OpenAI, etc.)
  └── Embedding API (Voyage AI)
```

---

## Prerequisites

- [Railway](https://railway.app) account
- [Vercel](https://vercel.com) account
- API keys for:
  - **LLM**: `LLM_API_KEY` (OpenAI-compatible)
  - **Embeddings**: `VOYAGE_API_KEY`
- Git repo pushed to GitHub/GitLab (Railway and Vercel both connect to Git)

---

## 1. Railway — PostgreSQL + pgvector

1. In Railway, create a new project.
2. Add a **PostgreSQL** service.
3. Railway's Postgres images support `pgvector` — enable the extension by connecting once and running:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
   (Or add an Alembic migration that runs this automatically.)
4. Copy the **Database URL** (private) and **Database Public URL** (optional, for external tools).

---

## 2. Railway — FastAPI Backend

### Option A: Deploy from Git (Recommended)

1. In your Railway project, add a new service → **GitHub Repo** → select this repo.
2. Set the **Root Directory** to `backend` (or leave as root if the repo is backend-only).
3. Railway will detect `railway.json` and use the Dockerfile automatically.

### Option B: Deploy from Dockerfile directly

1. Add a new service → **Empty Service**.
2. Under **Settings → Source**, connect your repo.
3. Set the builder to **Dockerfile**.

### Required Environment Variables

Add these in Railway under **Variables**:

| Variable | Example / Source | Notes |
|---|---|---|
| `DATABASE_URL` | Railway Postgres private URL | Auto-injected if you link the Postgres service |
| `DATABASE_PUBLIC_URL` | Railway Postgres public URL | Optional; fallback reference |
| `VOYAGE_API_KEY` | `pa-...` | Voyage AI API key |
| `VOYAGE_EMBEDDING_MODEL` | `voyage-4` | Optional; defaults to voyage-4 |
| `VOYAGE_EMBEDDING_DIMENSIONS` | `1024` | Optional; defaults to 1024 |
| `LLM_API_KEY` | `sk-...` | Your LLM provider key |
| `LLM_BASE_URL` | `https://opencode.ai/zen/go/v1` | OpenAI-compatible base URL |
| `LLM_MODEL` | `kimi-k2.6` | Model name |
| `APP_ENV` | `production` | Sets environment context |
| `CORS_ORIGINS` | `https://your-frontend.vercel.app` | Your Vercel frontend domain |
| `MAX_UPLOAD_BYTES` | `10485760` | 10 MB default |
| `VOYAGE_TOKEN_BUDGET` | `180000000` | Optional usage cap |

> **Tip:** If you link the Postgres service to your FastAPI service in Railway, `DATABASE_URL` is automatically injected.

### URL Handling

Railway Postgres URLs start with `postgres://` or `postgresql://`. The backend automatically converts them to `postgresql+asyncpg://` for SQLAlchemy async compatibility via `Settings.async_database_url`.

---

## 3. Vercel — Frontend

1. In Vercel, import your Git repo.
2. Set the **Root Directory** to `frontend`.
3. Framework preset: **Vite** (or "Other" if not auto-detected).
4. Add the environment variable:
   - `VITE_API_BASE_URL` = `https://your-backend.up.railway.app` (your Railway backend domain)
5. Deploy.

### SPA Routing

`frontend/vercel.json` is already configured to rewrite all routes to `index.html` so React Router (if added later) works correctly.

---

## 4. CORS Configuration

After your Vercel deployment gets a domain, update Railway:

```
CORS_ORIGINS=https://acme-legal-playbook.vercel.app
```

For multiple preview domains, comma-separate them:

```
CORS_ORIGINS=https://acme-legal-playbook.vercel.app,https://acme-legal-playbook-git-dev.vercel.app
```

**Do not** set `CORS_ALLOW_ALL=true` in production unless this is a public demo with no auth.

---

## 5. First Deploy & Migrations

On first Railway deploy, the `entrypoint.sh` automatically runs:

```bash
alembic upgrade head
```

This executes all migrations, including creating tables and enabling `pgvector` if your migration includes it.

### Verify deployment

- Health check: `GET https://<railway-domain>/health`
- Should return: `{"status":"ok","database":"connected","environment":"production"}`

---

## 6. File Uploads & Storage Warning

Railway containers have an **ephemeral filesystem**. Files saved to `storage/uploads/` will be lost on redeploy or restart.

**Options for production file storage:**
- **Railway Volumes** (persistent disk): Mount a volume to `storage/uploads`
- **AWS S3 / Cloudflare R2 / Backblaze B2**: Store files externally (update `upload_storage_path` logic to use an object storage SDK)
- For a demo, ephemeral storage may be acceptable if you re-upload after deploys.

---

## 7. External API Notes

### LLM
- Ensure your LLM provider's base URL is OpenAI-compatible (the app uses `langchain-openai` / `openai` SDK).
- If using OpenAI directly, set `LLM_BASE_URL=https://api.openai.com/v1` and `LLM_MODEL=gpt-4o`.

### Embeddings
- Voyage AI requires a valid API key with access to the chosen model.
- The token budget is tracked in the `embedding_usage` table.

---

## 8. Railway Service Diagram

In Railway, link services like this:

```
┌─────────────┐         ┌──────────────┐
│  PostgreSQL │◄────────│   FastAPI    │
│  + pgvector │  env var│   (Docker)   │
└─────────────┘         └──────────────┘
                               │
                               │ HTTPS
                               ▼
                        ┌──────────────┐
                        │    Vercel    │
                        │   Frontend   │
                        └──────────────┘
```

---

## 9. Troubleshooting

| Issue | Fix |
|---|---|
| `ModuleNotFoundError` on deploy | Ensure `backend/requirements.txt` is committed and Docker build runs `pip install` |
| Database connection fails | Check `DATABASE_URL` is injected; verify `async_database_url` conversion in logs |
| CORS errors in browser | Update `CORS_ORIGINS` in Railway to match exact Vercel domain (no trailing slash) |
| 502 on `/health` | Check `entrypoint.sh` logs — migrations may be failing or port mismatch |
| pgvector not found | Run `CREATE EXTENSION vector;` manually, or add it to the first Alembic migration |

---

## 10. Optional: GitHub Actions CI

Add `.github/workflows/deploy.yml` to run backend tests before deploy:

```yaml
name: CI
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - run: pip install -r backend/requirements.txt
      - run: pytest backend/tests
```
