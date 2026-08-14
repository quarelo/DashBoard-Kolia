from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://kolia:kolia@postgres:5432/kolia"
    
    secret_key: str = "c0a67d30a708eefde66979ce4393ab41628e080592e23744a074040ddb89d649"
    algorithm: str = "HS256"
    access_token_expire_days: int = 7

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()