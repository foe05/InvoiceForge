"""WebDAV storage backend for Nextcloud / ownCloud integration.

Stores and retrieves invoice files via WebDAV (RFC 4918).
Falls back to local storage if WebDAV is unavailable.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path, PurePosixPath

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class WebDAVStorage:
    """Store and retrieve files via a WebDAV-compatible server (e.g. Nextcloud).

    Files are organized by tenant:
        {base_path}/{tenant_id}/input/{filename}
        {base_path}/{tenant_id}/output/{filename}
    """

    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.base_url = (url or settings.webdav_url).rstrip("/")
        self.username = username or settings.webdav_username
        self.password = password or settings.webdav_password
        self._auth = (self.username, self.password) if self.username else None

    def _url(self, *parts: str) -> str:
        """Build a full WebDAV URL from path segments."""
        path = PurePosixPath(self.base_url)
        for p in parts:
            path = path / p
        return str(path)

    async def _ensure_collection(self, *parts: str) -> None:
        """Create nested WebDAV collections (directories) if they don't exist."""
        async with httpx.AsyncClient(auth=self._auth, timeout=15.0) as client:
            current = self.base_url
            for part in parts:
                current = f"{current}/{part}"
                try:
                    await client.request("MKCOL", current)
                except httpx.HTTPError:
                    pass  # Collection may already exist

    async def save_input(self, tenant_id: str, filename: str, data: bytes) -> str:
        """Upload an input file to WebDAV. Returns the remote path."""
        safe_name = f"{uuid.uuid4().hex}_{filename}"
        remote_path = f"{tenant_id}/input/{safe_name}"

        await self._ensure_collection(tenant_id, "input")
        url = f"{self.base_url}/{remote_path}"

        async with httpx.AsyncClient(auth=self._auth, timeout=30.0) as client:
            resp = await client.put(url, content=data)
            resp.raise_for_status()

        logger.info("WebDAV: saved input %s", remote_path)
        return remote_path

    async def save_output(self, tenant_id: str, filename: str, data: bytes) -> str:
        """Upload an output file to WebDAV. Returns the remote path."""
        safe_name = f"{uuid.uuid4().hex}_{filename}"
        remote_path = f"{tenant_id}/output/{safe_name}"

        await self._ensure_collection(tenant_id, "output")
        url = f"{self.base_url}/{remote_path}"

        async with httpx.AsyncClient(auth=self._auth, timeout=30.0) as client:
            resp = await client.put(url, content=data)
            resp.raise_for_status()

        logger.info("WebDAV: saved output %s", remote_path)
        return remote_path

    async def read_file(self, remote_path: str) -> bytes:
        """Download a file from WebDAV."""
        url = f"{self.base_url}/{remote_path}"
        async with httpx.AsyncClient(auth=self._auth, timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    async def delete_file(self, remote_path: str) -> None:
        """Delete a file from WebDAV."""
        url = f"{self.base_url}/{remote_path}"
        async with httpx.AsyncClient(auth=self._auth, timeout=15.0) as client:
            resp = await client.delete(url)
            if resp.status_code not in (200, 204, 404):
                resp.raise_for_status()

    async def is_available(self) -> bool:
        """Check if the WebDAV server is reachable."""
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient(auth=self._auth, timeout=5.0) as client:
                resp = await client.request("PROPFIND", self.base_url, headers={"Depth": "0"})
                return resp.status_code in (200, 207)
        except httpx.HTTPError:
            return False
