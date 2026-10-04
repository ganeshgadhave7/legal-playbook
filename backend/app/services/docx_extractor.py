"""Extract structured paragraphs and headings from DOCX files.

This service performs local parsing only. It does not upload files, write to
PostgreSQL, call an embedding API, or make legal judgments.
"""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.document import Document as DocumentType
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.table import Table
from docx.text.paragraph import Paragraph


@dataclass(frozen=True)
class ExtractedBlock:
    """A text block with lightweight structural metadata."""

    index: int
    kind: str
    text: str
    section: str | None
    page_number: int | None = None


def _extract_document(document: DocumentType) -> list[ExtractedBlock]:
    blocks: list[ExtractedBlock] = []
    current_section: str | None = None

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph = Paragraph(child, document)
            text = " ".join(paragraph.text.split())
            if not text:
                continue

            style_name = paragraph.style.name.lower() if paragraph.style else ""
            is_heading = style_name.startswith("heading") or style_name == "title"
            if is_heading:
                current_section = text
            blocks.append(
                ExtractedBlock(
                    index=len(blocks),
                    kind="heading" if is_heading else "paragraph",
                    text=text,
                    section=current_section,
                )
            )
        elif isinstance(child, CT_Tbl):
            table = Table(child, document)
            for row in table.rows:
                cells = [" ".join(cell.text.split()) for cell in row.cells]
                row_text = "\t".join(cell for cell in cells if cell)
                if row_text:
                    blocks.append(
                        ExtractedBlock(
                            index=len(blocks),
                            kind="table_row",
                            text=row_text,
                            section=current_section,
                        )
                    )

    if not blocks:
        raise ValueError("The DOCX contains no extractable text")
    return blocks


def extract_docx_bytes(content: bytes) -> list[ExtractedBlock]:
    """Extract text from DOCX bytes in memory."""
    try:
        return _extract_document(Document(BytesIO(content)))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("DOCX file could not be parsed") from exc


def extract_docx(path: str | Path) -> list[ExtractedBlock]:
    """Extract non-empty paragraphs and table rows from a DOCX file path."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"DOCX file not found: {file_path}")
    if file_path.suffix.lower() != ".docx":
        raise ValueError("Only .docx files are supported by this extractor")
    return extract_docx_bytes(file_path.read_bytes())
