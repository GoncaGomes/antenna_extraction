from __future__ import annotations

from openai import OpenAI

from antenna_ingest.nuextract.settings import NuExtractSettings


def build_openai_compatible_client(
    base_url: str,
    api_key: str,
    timeout_seconds: int,
) -> OpenAI:
    return OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout_seconds,
    )


def build_nuextract_client(settings: NuExtractSettings) -> OpenAI:
    return build_openai_compatible_client(
        base_url=settings.skynet_base_url,
        api_key=settings.skynet_api_key.get_secret_value(),
        timeout_seconds=settings.nuextract_timeout_seconds,
    )
