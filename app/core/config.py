from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(min_length=1)
    access_token_expire_minutes: int = Field(default=60, gt=0)
    jwt_secret_key: str | None = Field(min_length=32)
    jwt_algorithm: str | None = Field(default="HS256")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

