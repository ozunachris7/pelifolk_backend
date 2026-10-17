from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: SecretStr
    jwt_secret: SecretStr
    jwt_issuer: str = "pelifolk-api"
    access_token_minutes: int = Field(default=30, ge=1, le=1440)
    cors_origins: list[str] = ["http://localhost:4200"]
    environment: Literal["development", "production"] = "development"
    profile_photos_dir: Path = Path(__file__).resolve().parents[3] / "upload" / "photos_profile"

    @model_validator(mode="after")
    def production_configuration(self):
        if self.environment == "production":
            for origin in self.cors_origins:
                parsed = urlsplit(origin)
                if (parsed.scheme != "https" or not parsed.hostname or
                        parsed.username or parsed.password or parsed.path or
                        parsed.query or parsed.fragment):
                    raise ValueError("Production CORS origins must be exact HTTPS origins")
            if not self.database_url.get_secret_value().startswith("mysql+pymysql://"):
                raise ValueError("Production requires a mysql+pymysql database URL")
        return self

    @field_validator("jwt_secret")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32 or value.get_secret_value().startswith("REPLACE_"):
            raise ValueError("JWT_SECRET must be a random secret of at least 32 characters")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
