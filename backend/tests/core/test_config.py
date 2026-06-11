from backend.core.config import Settings, normalize_async_database_url


def test_normalize_render_postgresql_url_for_asyncpg() -> None:
    assert (
        normalize_async_database_url("postgresql://user:password@host:5432/capilearn")
        == "postgresql+asyncpg://user:password@host:5432/capilearn"
    )


def test_normalize_legacy_postgres_url_for_asyncpg() -> None:
    assert (
        normalize_async_database_url("postgres://user:password@host:5432/capilearn")
        == "postgresql+asyncpg://user:password@host:5432/capilearn"
    )


def test_preserve_existing_asyncpg_url() -> None:
    database_url = "postgresql+asyncpg://user:password@host:5432/capilearn"
    assert normalize_async_database_url(database_url) == database_url


def test_settings_normalize_database_url() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql://user:password@host:5432/capilearn",
    )

    assert settings.database_url == ("postgresql+asyncpg://user:password@host:5432/capilearn")
