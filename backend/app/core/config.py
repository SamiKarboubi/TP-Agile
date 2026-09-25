import json
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    anthropic_timeout_seconds: float = Field(default=25, gt=0)
    anthropic_max_retries: int = Field(default=1, ge=0, le=5)

    tmdb_api_token: str = ""
    omdb_api_key: str = ""
    tmdb_language: str = "fr-FR"
    tmdb_region: str = "FR"
    tmdb_mcp_command: str = "npx"
    tmdb_mcp_args: str = '["-y","tmdb-mcp@0.11.0"]'
    mcp_call_timeout_seconds: float = Field(default=30, gt=0)

    max_user_message_length: int = Field(default=200, ge=50, le=1000)
    max_recommendations: int = Field(default=7, ge=1, le=7)
    movie_candidate_limit: int = Field(default=20, ge=5, le=20)
    default_min_votes: int = Field(default=200, ge=0)
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    log_level: str = "INFO"

    @field_validator("tmdb_region")
    @classmethod
    def validate_region(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 2 or not normalized.isalpha():
            raise ValueError("TMDB_REGION must be a two-letter country code")
        return normalized

    @property
    def mcp_args(self) -> list[str]:
        try:
            value = json.loads(self.tmdb_mcp_args)
        except json.JSONDecodeError as exc:
            raise ValueError("TMDB_MCP_ARGS must be a JSON array of strings") from exc
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError("TMDB_MCP_ARGS must be a JSON array of strings")
        return value

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def mcp_environment(self) -> dict[str, str]:
        values = {
            "TMDB_API_TOKEN": self.tmdb_api_token,
            "OMDB_API_KEY": self.omdb_api_key,
            "TMDB_LANGUAGE": self.tmdb_language,
            "TMDB_REGION": self.tmdb_region,
            "LOG_LEVEL": self.log_level.lower(),
        }
        return {key: value for key, value in values.items() if value}


@lru_cache
def get_settings() -> Settings:
    return Settings()
