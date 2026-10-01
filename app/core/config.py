from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_db_url(url: str) -> str:
    """Coerce bare postgres URLs to the psycopg3 driver.

    Managed providers (Render, Supabase, Neon) hand out driverless
    ``postgresql://`` URLs, which SQLAlchemy maps to psycopg2. The image
    only ships psycopg3, so rewrite the scheme explicitly. URLs that
    already name a driver pass through untouched.
    """
    scheme, sep, rest = url.partition("://")
    if sep and scheme in {"postgres", "postgresql"}:
        return f"postgresql+psycopg://{rest}"
    return url


class Settings(BaseSettings):
    database_url: str  = Field(min_length=1)
    access_token_expire_minutes: int  = Field(default=60, gt=0)
    jwt_secret_key: str  = Field(min_length=32)
    jwt_algorithm: str  = Field(default="HS256")
    rate_limit_global: str  
    rate_limit_login: str | None = Field(default=None)
    rate_limit_register: str | None = Field(default=None)
    cors_allowed_origins: list[str] | None = Field(default=None)
    redis_url: str = Field(default="redis://localhost:6379/0")
    webhook_secret: str = Field(min_length=8)


    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

