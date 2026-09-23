from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str  = Field(min_length=1)
    access_token_expire_minutes: int  = Field(default=60, gt=0)
    jwt_secret_key: str  = Field(min_length=32)
    jwt_algorithm: str  = Field(default="HS256")
    rate_limit_global: str  
    rate_limit_login: str | None = Field(default=None)
    rate_limit_register: str | None = Field(default=None)
    cors_allowed_origins: list[str] | None = Field(default=None)
    webhook_secret: str = Field(min_length=8)
    redis_url: str = Field(default="redis://localhost:6379/0")


    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

