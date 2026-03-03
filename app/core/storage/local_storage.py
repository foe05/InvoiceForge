"""Local filesystem storage backend."""

from __future__ import annotations

import uuid
from pathlib import Path

from app.config import settings


class LocalStorage:
    """Store and retrieve files on the local filesystem.

    Files are organized by tenant and type:
        {base_path}/{tenant_id}/input/{filename}
        {base_path}/{tenant_id}/output/{filename}
    """

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or settings.storage_base_path

    def _tenant_path(self, tenant_id: str, subdir: str) -> Path:
        path = self.base_path / tenant_id / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_input(self, tenant_id: str, filename: str, data: bytes) -> Path:
        """Save an uploaded input file."""
        safe_name = f"{uuid.uuid4().hex}_{filename}"
        path = self._tenant_path(tenant_id, "input") / safe_name
        path.write_bytes(data)
        return path

    def save_output(self, tenant_id: str, filename: str, data: bytes) -> Path:
        """Save a generated output file."""
        safe_name = f"{uuid.uuid4().hex}_{filename}"
        path = self._tenant_path(tenant_id, "output") / safe_name
        path.write_bytes(data)
        return path

    def read_file(self, file_path: Path) -> bytes:
        """Read a file from storage."""
        return file_path.read_bytes()

    def delete_file(self, file_path: Path) -> None:
        """Delete a file from storage."""
        if file_path.exists():
            file_path.unlink()
