"""Tests for DOCX upload validation helpers."""
import pytest
from fastapi import HTTPException

from fastapi.testclient import TestClient

from app.api.v1.source_documents import _validate_docx_container
from app.main import app


def test_rejects_non_zip_content():
    with pytest.raises(HTTPException) as error:
        _validate_docx_container(b"plain text pretending to be DOCX")
    assert error.value.status_code == 415


def test_rejects_invalid_zip_container():
    with pytest.raises(HTTPException) as error:
        _validate_docx_container(b"PK\x03\x04not-a-real-docx")
    assert error.value.status_code == 415


def test_upload_and_list_endpoints_are_registered():
    client = TestClient(app)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/source-documents" in paths
    assert "get" in paths["/api/v1/source-documents"]
    assert "post" in paths["/api/v1/source-documents"]
