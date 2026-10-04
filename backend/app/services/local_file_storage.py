"""Private local file storage for development uploads."""
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings


class LocalFileStorage:
    """Stores upload bytes under a generated name outside public web assets."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_settings().upload_storage_path

    def save_docx(self, content: bytes, original_filename: str | None = None) -> tuple[str, Path]:
        """Save DOCX bytes and return a relative storage key and absolute path."""
        self.root.mkdir(parents=True, exist_ok=True)
        suffix = Path(original_filename or "").suffix.lower()
        key = f"{uuid4().hex}{suffix if suffix == '.docx' else '.docx'}"
        path = self.root / key
        path.write_bytes(content)
        return key, path

    def path_for(self, key: str) -> Path:
        """Resolve an opaque storage key while preventing path traversal."""
        if Path(key).name != key or not key.endswith(".docx"):
            raise ValueError("Invalid storage key")
        return self.root / key

    def delete(self, key: str) -> None:
        """Remove an upload by generated key; reject path traversal attempts."""
        if Path(key).name != key:
            raise ValueError("Invalid storage key")
        path = self.path_for(key)
        if path.exists():
            path.unlink()
