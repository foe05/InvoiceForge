"""WebDAV storage backend for Nextcloud / ownCloud integration.

Stores and retrieves invoice files via WebDAV (RFC 4918).
Supports per-tenant configuration overrides.

Konfiguration per .env (pro Mandant überschreibbar):
    NEXTCLOUD_URL=https://cloud.example.com
    NEXTCLOUD_USERNAME=user
    NEXTCLOUD_PASSWORD=app-password
    NEXTCLOUD_ROOT_PATH=/InvoiceForge
"""

from __future__ import annotations

import fnmatch
import logging
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# WebDAV XML namespaces
DAV_NS = "DAV:"


@dataclass
class FileMetadata:
    """Metadaten einer WebDAV-Datei."""

    path: str
    name: str
    size: int = 0
    content_type: str = ""
    last_modified: str = ""
    etag: str = ""
    is_directory: bool = False


class WebDAVStorage:
    """Store and retrieve files via a WebDAV-compatible server (e.g. Nextcloud).

    Unterstützt:
      - list_files: Dateien in einem Verzeichnis auflisten (mit Muster)
      - download_file: Datei herunterladen
      - upload_file: Datei hochladen
      - ensure_directory: Verzeichnis anlegen (rekursiv)
      - get_file_metadata: Datei-Metadaten abrufen

    Output-Pfad-Logik:
      Wenn Input-Datei aus Nextcloud stammt, wird der Output-Standardpfad
      auf den Input-Ordner gesetzt.
      Beispiel: Input /Rechnungen/Eingang/rechnung.pdf
              → Output /Rechnungen/Eingang/rechnung_zugferd.pdf
    """

    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        root_path: str = "/InvoiceForge",
    ) -> None:
        self.base_url = (url or settings.webdav_url).rstrip("/")
        self.username = username or settings.webdav_username
        self.password = password or settings.webdav_password
        self.root_path = root_path
        self._auth = (self.username, self.password) if self.username else None

    def _full_url(self, remote_path: str) -> str:
        """Build a full WebDAV URL from a remote path."""
        clean_path = remote_path.lstrip("/")
        return f"{self.base_url}/{clean_path}"

    @staticmethod
    def derive_output_path(input_path: str, suffix: str = "_zugferd") -> str:
        """Leite den Output-Pfad aus dem Input-Pfad ab.

        Input:  /Rechnungen/Eingang/rechnung.pdf
        Output: /Rechnungen/Eingang/rechnung_zugferd.pdf

        Args:
            input_path: Pfad der Eingabedatei.
            suffix: Suffix vor der Dateiendung (Standard: '_zugferd').

        Returns:
            Abgeleiteter Ausgabepfad.
        """
        p = PurePosixPath(input_path)
        new_name = f"{p.stem}{suffix}{p.suffix}"
        return str(p.parent / new_name)

    async def list_files(
        self, path: str = "/", pattern: str = "*.pdf"
    ) -> list[FileMetadata]:
        """Dateien in einem Verzeichnis auflisten.

        Args:
            path: WebDAV-Verzeichnispfad.
            pattern: Glob-Muster zum Filtern (z.B. '*.pdf', '*.xml').

        Returns:
            Liste von FileMetadata-Objekten.
        """
        url = self._full_url(path)
        propfind_body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<d:propfind xmlns:d="DAV:">'
            "<d:prop>"
            "<d:getlastmodified/>"
            "<d:getcontentlength/>"
            "<d:getcontenttype/>"
            "<d:getetag/>"
            "<d:resourcetype/>"
            "</d:prop>"
            "</d:propfind>"
        )

        async with httpx.AsyncClient(auth=self._auth, timeout=30.0) as client:
            resp = await client.request(
                "PROPFIND",
                url,
                content=propfind_body.encode("utf-8"),
                headers={
                    "Content-Type": "application/xml",
                    "Depth": "1",
                },
            )
            resp.raise_for_status()

        files = self._parse_propfind(resp.text, path)

        # Filter by pattern
        if pattern != "*":
            files = [
                f
                for f in files
                if f.is_directory or fnmatch.fnmatch(f.name, pattern)
            ]

        return files

    async def download_file(self, remote_path: str) -> bytes:
        """Datei von WebDAV herunterladen.

        Args:
            remote_path: Pfad der Datei auf dem Server.

        Returns:
            Dateiinhalt als Bytes.
        """
        url = self._full_url(remote_path)
        async with httpx.AsyncClient(auth=self._auth, timeout=60.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    async def upload_file(
        self,
        data: bytes,
        remote_path: str,
        content_type: str = "application/octet-stream",
    ) -> bool:
        """Datei auf WebDAV hochladen.

        Args:
            data: Dateiinhalt als Bytes.
            remote_path: Zielpfad auf dem Server.
            content_type: MIME-Typ der Datei.

        Returns:
            True bei Erfolg.
        """
        # Ensure parent directory exists
        parent = str(PurePosixPath(remote_path).parent)
        await self.ensure_directory(parent)

        url = self._full_url(remote_path)
        async with httpx.AsyncClient(auth=self._auth, timeout=60.0) as client:
            resp = await client.put(
                url,
                content=data,
                headers={"Content-Type": content_type},
            )
            resp.raise_for_status()

        logger.info("WebDAV: Datei hochgeladen nach %s", remote_path)
        return True

    async def ensure_directory(self, path: str) -> bool:
        """Verzeichnis rekursiv anlegen (MKCOL).

        Args:
            path: Zu erstellender Verzeichnispfad.

        Returns:
            True wenn das Verzeichnis existiert oder erstellt wurde.
        """
        parts = PurePosixPath(path).parts
        async with httpx.AsyncClient(auth=self._auth, timeout=15.0) as client:
            current = self.base_url
            for part in parts:
                if part == "/":
                    continue
                current = f"{current}/{part}"
                try:
                    resp = await client.request("MKCOL", current)
                    # 201 Created, 405 Already exists
                    if resp.status_code not in (201, 405, 301):
                        check = await client.request(
                            "PROPFIND", current, headers={"Depth": "0"}
                        )
                        if check.status_code not in (200, 207):
                            logger.warning(
                                "WebDAV MKCOL fehlgeschlagen für %s: %d",
                                current,
                                resp.status_code,
                            )
                            return False
                except httpx.HTTPError as e:
                    logger.warning("WebDAV MKCOL Fehler für %s: %s", current, e)
                    return False
        return True

    async def get_file_metadata(self, path: str) -> FileMetadata | None:
        """Metadaten einer einzelnen Datei abrufen.

        Args:
            path: Pfad der Datei.

        Returns:
            FileMetadata oder None wenn nicht gefunden.
        """
        url = self._full_url(path)
        propfind_body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<d:propfind xmlns:d="DAV:">'
            "<d:prop>"
            "<d:getlastmodified/>"
            "<d:getcontentlength/>"
            "<d:getcontenttype/>"
            "<d:getetag/>"
            "<d:resourcetype/>"
            "</d:prop>"
            "</d:propfind>"
        )

        try:
            async with httpx.AsyncClient(auth=self._auth, timeout=15.0) as client:
                resp = await client.request(
                    "PROPFIND",
                    url,
                    content=propfind_body.encode("utf-8"),
                    headers={
                        "Content-Type": "application/xml",
                        "Depth": "0",
                    },
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
        except httpx.HTTPError:
            return None

        files = self._parse_propfind_single(resp.text, path)
        return files

    async def delete_file(self, remote_path: str) -> None:
        """Datei von WebDAV löschen."""
        url = self._full_url(remote_path)
        async with httpx.AsyncClient(auth=self._auth, timeout=15.0) as client:
            resp = await client.delete(url)
            if resp.status_code not in (200, 204, 404):
                resp.raise_for_status()

    async def is_available(self) -> bool:
        """Prüfe ob der WebDAV-Server erreichbar ist."""
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient(auth=self._auth, timeout=5.0) as client:
                resp = await client.request(
                    "PROPFIND", self.base_url, headers={"Depth": "0"}
                )
                return resp.status_code in (200, 207)
        except httpx.HTTPError:
            return False

    # --- Legacy API (backward-compatible) ---

    async def save_input(self, tenant_id: str, filename: str, data: bytes) -> str:
        """Upload an input file to WebDAV. Returns the remote path."""
        safe_name = f"{uuid.uuid4().hex}_{filename}"
        remote_path = f"{self.root_path}/{tenant_id}/input/{safe_name}"
        await self.upload_file(data, remote_path)
        return remote_path

    async def save_output(self, tenant_id: str, filename: str, data: bytes) -> str:
        """Upload an output file to WebDAV. Returns the remote path."""
        safe_name = f"{uuid.uuid4().hex}_{filename}"
        remote_path = f"{self.root_path}/{tenant_id}/output/{safe_name}"
        await self.upload_file(data, remote_path)
        return remote_path

    async def read_file(self, remote_path: str) -> bytes:
        """Download a file from WebDAV (legacy alias)."""
        return await self.download_file(remote_path)

    # --- Internal helpers ---

    def _parse_propfind(self, xml_text: str, base_path: str) -> list[FileMetadata]:
        """Parse a WebDAV PROPFIND XML response into FileMetadata objects."""
        files: list[FileMetadata] = []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            logger.warning("WebDAV PROPFIND-Antwort konnte nicht geparst werden")
            return files

        for response in root.iter(f"{{{DAV_NS}}}response"):
            href_el = response.find(f"{{{DAV_NS}}}href")
            if href_el is None or href_el.text is None:
                continue

            href = href_el.text
            name = PurePosixPath(href.rstrip("/")).name

            # Skip the directory itself
            if not name or href.rstrip("/").endswith(base_path.rstrip("/")):
                continue

            meta = self._extract_metadata(response, name, base_path)
            if meta:
                files.append(meta)

        return files

    def _parse_propfind_single(self, xml_text: str, path: str) -> FileMetadata | None:
        """Parse a PROPFIND Depth:0 response for a single resource."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return None

        for response in root.iter(f"{{{DAV_NS}}}response"):
            href_el = response.find(f"{{{DAV_NS}}}href")
            if href_el is None:
                continue

            name = PurePosixPath(path).name
            return self._extract_metadata(response, name, str(PurePosixPath(path).parent))

        return None

    def _extract_metadata(
        self, response: ET.Element, name: str, base_path: str
    ) -> FileMetadata | None:
        """Extract FileMetadata from a single DAV:response element."""
        props = response.find(f".//{{{DAV_NS}}}prop")
        if props is None:
            return None

        is_dir = props.find(f".//{{{DAV_NS}}}collection") is not None

        size_el = props.find(f"{{{DAV_NS}}}getcontentlength")
        size = int(size_el.text) if size_el is not None and size_el.text else 0

        ct_el = props.find(f"{{{DAV_NS}}}getcontenttype")
        content_type = ct_el.text if ct_el is not None and ct_el.text else ""

        mod_el = props.find(f"{{{DAV_NS}}}getlastmodified")
        last_modified = mod_el.text if mod_el is not None and mod_el.text else ""

        etag_el = props.find(f"{{{DAV_NS}}}getetag")
        etag = etag_el.text.strip('"') if etag_el is not None and etag_el.text else ""

        file_path = f"{base_path.rstrip('/')}/{name}"

        return FileMetadata(
            path=file_path,
            name=name,
            size=size,
            content_type=content_type,
            last_modified=last_modified,
            etag=etag,
            is_directory=is_dir,
        )
