from __future__ import annotations

from openai import OpenAI

from antenna_ingest.settings import AntennaIngestSettings, ModelRole


def build_openai_compatible_client(
    base_url: str,
    api_key: str,
    timeout_seconds: int,
) -> OpenAI:
    return OpenAI(
    base_url=base_url,
    api_key=api_key,
    timeout=timeout_seconds,
    max_retries=0,
)


def build_model_client(
    settings: AntennaIngestSettings,
    model_role: ModelRole,
) -> OpenAI:
    return build_openai_compatible_client(
        base_url=settings.skynet_base_url,
        api_key=settings.skynet_api_key.get_secret_value(),
        timeout_seconds=settings.timeout_for_role(model_role),
    )
