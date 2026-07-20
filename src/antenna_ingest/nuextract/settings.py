from __future__ import annotations

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class NuExtractSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    skynet_base_url: str = Field(
        validation_alias=AliasChoices("SKYNET_BASE_URL", "OPENAI_BASE_URL")
    )
    skynet_api_key: SecretStr = Field(validation_alias="SKYNET_API_KEY")
    nuextract_model: str = Field(
        validation_alias=AliasChoices("NUEXTRACT_MODEL", "OLLAMA_MODEL")
    )
    canonicalizer_model: str = Field(
        validation_alias="CANONICALIZER_MODEL",
    )
    verifier_model: str | None = Field(
        default=None,
        validation_alias="VERIFIER_MODEL",
    )
    nuextract_timeout_seconds: int = Field(
        default=180,
        gt=0,
        validation_alias="NUEXTRACT_TIMEOUT_SECONDS",
    )
    canonicalizer_timeout_seconds: int = Field(
        default=600,
        gt=0,
        validation_alias="CANONICALIZER_TIMEOUT_SECONDS",
    )

    @field_validator(
        "skynet_base_url",
        "nuextract_model",
        "canonicalizer_model",
    )
    @classmethod
    def validate_non_empty_string(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned

    @field_validator("verifier_model")
    @classmethod
    def validate_optional_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
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
