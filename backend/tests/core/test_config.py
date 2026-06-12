import pytest
from pydantic import ValidationError

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


@pytest.mark.parametrize(
    ("username", "password", "missing_name"),
    [
        (None, None, "BETA_AUTH_USERNAME and BETA_AUTH_PASSWORD"),
        (None, "password", "BETA_AUTH_USERNAME"),
        ("username", None, "BETA_AUTH_PASSWORD"),
        (" ", "password", "BETA_AUTH_USERNAME"),
        ("username", " ", "BETA_AUTH_PASSWORD"),
    ],
)
def test_enabled_beta_auth_requires_non_blank_credentials(
    username: str | None,
    password: str | None,
    missing_name: str,
) -> None:
    with pytest.raises(ValidationError, match=missing_name):
        Settings(
            _env_file=None,
            beta_auth_enabled=True,
            beta_auth_username=username,
            beta_auth_password=password,
        )
