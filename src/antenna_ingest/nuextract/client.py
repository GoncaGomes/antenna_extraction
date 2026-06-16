from __future__ import annotations

from openai import OpenAI

from antenna_ingest.nuextract.settings import NuExtractSettings


def build_nuextract_client(settings: NuExtractSettings) -> OpenAI:
    return OpenAI(
        base_url=settings.openai_base_url,
        api_key=settings.skynet_api_key.get_secret_value(),
        timeout=120,
    )
