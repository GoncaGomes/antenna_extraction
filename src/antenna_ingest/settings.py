from __future__ import annotations

from enum import Enum

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelRole(str, Enum):
    DOCUMENT_EXTRACTOR = "document_extractor"
    ARCHITECTURE_AUTHOR = "architecture_author"


class AntennaIngestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    skynet_base_url: str
    skynet_api_key: SecretStr = Field(exclude=True)
    document_extractor_model: str
    architecture_author_model: str
    document_extractor_timeout_seconds: int = Field(default=180, gt=0)
    document_extractor_max_output_tokens: int = Field(default=24000, gt=0)
    architecture_author_timeout_seconds: int = Field(default=600, gt=0)

    @field_validator(
        "skynet_base_url",
        "document_extractor_model",
        "architecture_author_model",
    )
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

    def model_for_role(self, role: ModelRole) -> str:
        if role == ModelRole.DOCUMENT_EXTRACTOR:
            return self.document_extractor_model
        return self.architecture_author_model

    def timeout_for_role(self, role: ModelRole) -> int:
        if role == ModelRole.DOCUMENT_EXTRACTOR:
            return self.document_extractor_timeout_seconds
        return self.architecture_author_timeout_seconds


def load_settings() -> AntennaIngestSettings:
    return AntennaIngestSettings()
