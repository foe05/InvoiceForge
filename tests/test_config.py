"""Tests for application configuration."""

from app.config import Environment, Settings


class TestSettings:
    """Tests for Settings model."""

    def test_default_values(self) -> None:
        s = Settings(
            _env_file=None,  # don't read .env file in tests
        )
        assert s.app_env == Environment.DEVELOPMENT
        assert s.app_debug is False
        assert s.upload_max_size_mb == 50

    def test_upload_max_size_bytes(self) -> None:
        s = Settings(upload_max_size_mb=10, _env_file=None)
        assert s.upload_max_size_bytes == 10 * 1024 * 1024

    def test_database_url_sync(self) -> None:
        s = Settings(
            database_url="postgresql+asyncpg://user:pass@host:5432/db",
            _env_file=None,
        )
        assert s.database_url_sync == "postgresql+psycopg2://user:pass@host:5432/db"

    def test_is_development(self) -> None:
        s = Settings(app_env=Environment.DEVELOPMENT, _env_file=None)
        assert s.is_development is True

        s2 = Settings(app_env=Environment.PRODUCTION, _env_file=None)
        assert s2.is_development is False
