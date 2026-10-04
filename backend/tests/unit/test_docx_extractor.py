"""Unit tests for DOCX text extraction."""
from pathlib import Path

import pytest
from docx import Document

from app.services.docx_extractor import extract_docx


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_DOCX = PROJECT_ROOT / "sample-data" / "source-documents" / "Acme_Procurement_Policy.docx"


def test_extracts_sample_policy_headings_and_paragraphs():
    blocks = extract_docx(SAMPLE_DOCX)

    assert blocks[0].kind == "heading"
    assert blocks[0].text == "Acme Technologies LLC — Procurement Policy"
    assert any("Fictional document" in block.text for block in blocks)
    assert any(block.text == "3. Vendor Review" for block in blocks)
    assert any("sanctions screening" in block.text for block in blocks)
    assert any("$10,000" in block.text for block in blocks)
    assert any("7 years" in block.text for block in blocks)

    vendor_rule = next(block for block in blocks if "sanctions screening" in block.text)
    assert vendor_rule.section == "3. Vendor Review"


def test_missing_file_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        extract_docx(SAMPLE_DOCX.parent / "missing.docx")


def test_non_docx_file_is_rejected(tmp_path: Path):
    wrong_type = tmp_path / "notes.txt"
    wrong_type.write_text("not a Word document", encoding="utf-8")

    with pytest.raises(ValueError, match="Only .docx"):
        extract_docx(wrong_type)


def test_empty_docx_is_rejected(tmp_path: Path):
    empty_path = tmp_path / "empty.docx"
    Document().save(empty_path)

    with pytest.raises(ValueError, match="no extractable text"):
        extract_docx(empty_path)
