from pydantic_settings import BaseSettings, SettingsConfigDict

# CURRENT_PATH = pathlib.Path(__file__).parent
# PATH_ENV = CURRENT_PATH / ".env"

class Settings(BaseSettings):
    database_url: str | None = None
    access_token_expire_minutes: int
    jwt_secret_key: str
    jwt_algorithm: str
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
