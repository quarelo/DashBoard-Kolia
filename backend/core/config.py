from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# One .env for the whole repo, at the root, next to docker-compose.yml.
# Inside a container this path does not exist and Compose supplies the same
# values as real environment variables, which outrank any file regardless.
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    database_url: str
    # Empty/short keys are refused here: PyJWT raises InvalidKeyError per request
    # instead, which surfaces as a 500 on every login rather than a clear boot error.
    # JWT_SECRET is the name the root .env and docker-compose.yml already use.
    secret_key: str = Field(
        min_length=32,
        validation_alias=AliasChoices("SECRET_KEY", "JWT_SECRET"),
    )
    algorithm: str = "HS256"
    access_token_expire_days: int = 7
    ia_service_url: str = "http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(
        env_file=ROOT_ENV, env_file_encoding="utf-8", extra="ignore",
    )


settings = Settings()
