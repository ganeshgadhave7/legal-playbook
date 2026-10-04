"""Create embedding-sized passages while preserving source section metadata."""
from dataclasses import dataclass

from app.services.docx_extractor import ExtractedBlock


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str
    section: str | None
    page_number: int | None = None


def chunk_blocks(blocks: list[ExtractedBlock], max_chars: int = 1800) -> list[TextChunk]:
    """Pack adjacent extracted blocks up to max_chars, keeping section labels.

    This character-based initial chunker is intentionally deterministic and
    conservative. It does not estimate tokens; Voyage request limits will be
    checked separately before embedding.
    """
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")

    chunks: list[TextChunk] = []
    parts: list[str] = []
    current_section: str | None = None
    current_size = 0

    def flush() -> None:
        nonlocal parts, current_size
        if parts:
            chunks.append(
                TextChunk(
                    index=len(chunks),
                    content="\n".join(parts),
                    section=current_section,
                )
            )
            parts = []
            current_size = 0

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue

        # Headings mark section boundaries but should not be repeated as chunk text.
        if block.kind == "heading":
            current_section = text
            continue

        section = block.section
        piece = f"[{section}]\n{text}" if section else text
        if len(piece) > max_chars:
            flush()
            start = 0
            while start < len(piece):
                part = piece[start : start + max_chars]
                chunks.append(TextChunk(len(chunks), part, section))
                start += max_chars
            current_section = section
            continue

        if parts and (section != current_section or current_size + len(piece) + 1 > max_chars):
            flush()
        current_section = section
        parts.append(piece)
        current_size += len(piece) + 1

    flush()
    return chunks
