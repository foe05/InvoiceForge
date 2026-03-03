"""File storage backends (local filesystem, WebDAV)."""

from app.core.storage.local_storage import LocalStorage
from app.core.storage.webdav_storage import FileMetadata, WebDAVStorage

__all__ = ["FileMetadata", "LocalStorage", "WebDAVStorage"]
