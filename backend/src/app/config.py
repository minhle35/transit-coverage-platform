import secrets
from functools import cache
from typing import Literal

from pydantic import BaseModel, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    drivername: str = "postgresql+psycopg"
    host: str = "localhost"
    port: int = 5432
    user: str = "transit_user"
    password: str = "postgres"
    name: str = "transit"
    poolclass: Literal["_default_", "static_pool", "queue_pool"] = "_default_"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return (
            f"{self.drivername}://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class Settings(BaseSettings):
    """Configuration for the pipeline and the API.

    Values come from the environment first, then from the repo-root .env.
    Inside Docker, set TRANSIT_DB_HOST=db; on the host it defaults to localhost.
    """

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",  # double-underscore: DB__HOST, DB__PORT etc.
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "TransitCov"
    dev_reload: bool = False

    server_host: str = "0.0.0.0"
    server_port: int = 8000
    server_version: str = "0.1.0"

    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32))

    db: DatabaseSettings = DatabaseSettings()


@cache
def get_settings() -> Settings:
    """One Settings instance per process, so the secret_key stays stable."""
    return Settings()
