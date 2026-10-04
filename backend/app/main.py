"""FastAPI entry point for the Acme Legal Playbook demo."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.api.v1 import playbooks_router, retrieval_router, source_documents_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Release the database connection pool during application shutdown."""
    yield
    await engine.dispose()


app = FastAPI(
    title="Acme Legal Playbook Assistant",
    description=(
        "Fictional portfolio demo for AI-assisted legal operations. "
        "Generated content is a draft for qualified human review, not legal advice."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(source_documents_router, prefix="/api/v1")
app.include_router(retrieval_router, prefix="/api/v1")
app.include_router(playbooks_router, prefix="/api/v1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Report service and database health without returning sensitive details."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        # Do not include exception text: database errors can expose connection details.
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    return {"status": "ok", "database": "connected", "environment": settings.app_env}
