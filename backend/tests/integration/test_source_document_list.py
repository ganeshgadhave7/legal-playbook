"""Integration tests for listing source-document metadata."""
import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.main import app


def test_list_source_documents_paginates_filters_and_hides_storage():
    code_a = f"LIST-A-{uuid4().hex}"
    code_b = f"LIST-B-{uuid4().hex}"
    ids = [uuid4(), uuid4()]

    async def seed_rows() -> None:
        async with engine.begin() as connection:
            for doc_id, code, title, dept in [
                (ids[0], code_a, "Synthetic Procurement Policy A", "Procurement"),
                (ids[1], code_b, "Synthetic IT Policy B", "IT"),
            ]:
                await connection.execute(
                    text(
                        """
                        INSERT INTO source_documents (
                            id,title,department,document_type,document_code,version,status,
                            storage_key,original_filename,mime_type,file_size_bytes,sha256,fictional
                        ) VALUES (
                            :id,:title,:department,'Policy',:code,'test-1','uploaded',
                            :storage_key,'synthetic.docx',
                            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                            10,:sha256,true
                        )
                        """
                    ),
                    {
                        "id": doc_id,
                        "title": title,
                        "department": dept,
                        "code": code,
                        "storage_key": f"test-{doc_id}.docx",
                        "sha256": ("a" if dept == "Procurement" else "b") * 64,
                    },
                )

    asyncio.run(seed_rows())
    client = TestClient(app)
    try:
        all_response = client.get("/api/v1/source-documents?limit=1&offset=0")
        assert all_response.status_code == 200
        page = all_response.json()
        assert page["limit"] == 1
        assert page["offset"] == 0
        assert page["total"] >= 2
        assert len(page["items"]) == 1
        assert "storage_key" not in page["items"][0]
        assert "content" not in page["items"][0]

        filtered_response = client.get(
            "/api/v1/source-documents", params={"department": "Procurement", "status": "uploaded"}
        )
        assert filtered_response.status_code == 200
        filtered = filtered_response.json()
        assert all(item["department"] == "Procurement" for item in filtered["items"])
        assert all(item["status"] == "uploaded" for item in filtered["items"])
        assert any(item["document_code"] == code_a for item in filtered["items"])
    finally:
        async def cleanup() -> None:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM source_documents WHERE id = ANY(:ids)"),
                    {"ids": ids},
                )
            await engine.dispose()

        asyncio.run(cleanup())


def test_list_rejects_unknown_status():
    response = TestClient(app).get("/api/v1/source-documents?status=not-a-real-status")
    assert response.status_code == 422
