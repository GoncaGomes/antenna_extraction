from __future__ import annotations

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class NuExtractSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_base_url: str = Field(validation_alias="OPENAI_BASE_URL")
    ollama_model: str = Field(validation_alias="OLLAMA_MODEL")
    skynet_api_key: SecretStr = Field(validation_alias="SKYNET_API_KEY")

    @field_validator("openai_base_url", "ollama_model")
    @classmethod
    def validate_non_empty_string(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned

    @field_validator("skynet_api_key")
    @classmethod
    def validate_non_empty_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("SKYNET_API_KEY must not be empty")
        return value


def load_nuextract_settings() -> NuExtractSettings:
    return NuExtractSettings()
