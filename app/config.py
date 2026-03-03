"""Application configuration via environment variables."""

from enum import Enum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(str, Enum):
    NONE = "none"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_env: Environment = Environment.DEVELOPMENT
    app_debug: bool = False
    app_secret_key: str = "change-me-in-production"

    # Database
    database_url: str = (
        "postgresql+asyncpg://invoiceforge:invoiceforge@localhost:5432/invoiceforge"
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # KoSIT Validator
    kosit_validator_url: str = "http://localhost:8080"

    # File storage
    storage_base_path: Path = Path("./data/storage")
    upload_max_size_mb: int = 50

    # Validation schemas
    schema_dir: Path = Path("./data/schemas")

    # WebDAV / Nextcloud
    webdav_enabled: bool = False
    webdav_url: str = ""
    webdav_username: str = ""
    webdav_password: str = ""
    nextcloud_url: str = ""
    nextcloud_username: str = ""
    nextcloud_password: str = ""
    nextcloud_root_path: str = "/InvoiceForge"

    # LLM
    llm_provider: LLMProvider = LLMProvider.NONE
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # OCR
    tesseract_cmd: str = "tesseract"

    # Default tenant settings
    default_output_format: str = "zugferd_pdf"
    default_zugferd_profile: str = "EN 16931"

    @property
    def is_development(self) -> bool:
        return self.app_env == Environment.DEVELOPMENT

    @property
    def database_url_sync(self) -> str:
        """Synchronous database URL for Alembic migrations."""
        return self.database_url.replace("+asyncpg", "+psycopg2")

    @property
    def upload_max_size_bytes(self) -> int:
        return self.upload_max_size_mb * 1024 * 1024

    @property
    def effective_webdav_url(self) -> str:
        """Return the Nextcloud/WebDAV URL (prefer NEXTCLOUD_URL)."""
        return self.nextcloud_url or self.webdav_url

    @property
    def effective_webdav_username(self) -> str:
        """Return the Nextcloud/WebDAV username."""
        return self.nextcloud_username or self.webdav_username

    @property
    def effective_webdav_password(self) -> str:
        """Return the Nextcloud/WebDAV password."""
        return self.nextcloud_password or self.webdav_password


settings = Settings()
