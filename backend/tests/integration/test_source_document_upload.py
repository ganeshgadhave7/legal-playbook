"""Integration test for DOCX upload, storage, and metadata persistence.

Run from backend with local PostgreSQL configured and migrations applied:
    python -m pytest tests/integration/test_source_document_upload.py -q
"""
import asyncio
import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_DOCX = PROJECT_ROOT / "sample-data" / "source-documents" / "Acme_Procurement_Policy.docx"


def test_upload_sample_docx_persists_metadata_and_private_file():
    settings = get_settings()
    document_code = f"PROC-POL-001-TEST-{uuid4().hex}"
    client = TestClient(app)

    with SAMPLE_DOCX.open("rb") as document:
        response = client.post(
            "/api/v1/source-documents",
            files={
                "file": (
                    SAMPLE_DOCX.name,
                    document,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={
                "title": "Acme Technologies LLC Procurement Policy",
                "department": "Procurement",
                "document_type": "Policy",
                "document_code": document_code,
                "version": "test-1.0",
                "fictional": "true",
            },
        )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "uploaded"
    assert payload["fictional"] is True
    assert payload["original_filename"] == SAMPLE_DOCX.name
    assert "storage_key" not in payload

    storage_path = settings.upload_storage_path
    if not storage_path.is_absolute():
        storage_path = Path(__file__).resolve().parents[2] / storage_path
    stored_file = next(
        candidate
        for candidate in storage_path.glob("*.docx")
        if hashlib.sha256(candidate.read_bytes()).hexdigest() == payload["sha256"]
    )
    assert stored_file.is_file()

    async def verify_record_and_cleanup() -> None:
        try:
            async with engine.begin() as connection:
                result = await connection.execute(
                    text("SELECT status, sha256 FROM source_documents WHERE id = :id"),
                    {"id": payload["id"]},
                )
                row = result.one()
                assert row.status == "uploaded"
                assert row.sha256 == payload["sha256"]
        finally:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM source_documents WHERE id = :id"),
                    {"id": payload["id"]},
                )
            stored_file.unlink(missing_ok=True)
            await engine.dispose()

    asyncio.run(verify_record_and_cleanup())
