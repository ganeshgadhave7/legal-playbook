"""FastAPI entry point for the Acme Legal Playbook demo."""
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.api.v1 import auth_router, playbooks_router, retrieval_router, source_documents_router
from app.db.session import SessionFactory
from app.services.auth import create_default_admin

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Seed default admin if no users exist, then release the pool on shutdown."""
    async with SessionFactory() as db:
        await create_default_admin(db)
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

app.include_router(auth_router, prefix="/api/v1")
app.include_router(source_documents_router, prefix="/api/v1")
app.include_router(retrieval_router, prefix="/api/v1")
app.include_router(playbooks_router, prefix="/api/v1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.exception_handler(Exception)
async def debug_exception_handler(_request: Request, exc: Exception):
    """Return traceback details for unexpected errors (demo debugging only)."""
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": traceback.format_exception(type(exc), exc, exc.__traceback__)},
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
