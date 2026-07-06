from __future__ import annotations

from antenna_ingest.nuextract.client import build_nuextract_client
from antenna_ingest.nuextract.settings import (
    NuExtractSettings,
    load_nuextract_settings,
)
from antenna_ingest.orchestration.schemas import StrictModel


class NuExtractDoctorResult(StrictModel):
    ok: bool
    base_url: str
    model: str
    response_text: str | None = None
    error: str | None = None


def run_nuextract_doctor(
    settings: NuExtractSettings | None = None,
    client: object | None = None,
) -> NuExtractDoctorResult:
    if settings is None:
        settings = load_nuextract_settings()
    if client is None:
        client = build_nuextract_client(settings)

    try:
        response = client.chat.completions.create(
            model=settings.nuextract_model,
            messages=[{"role": "user", "content": "Reply exactly: NUEXTRACT3-OK"}],
            temperature=0,
        )
        response_text = response.choices[0].message.content
        return NuExtractDoctorResult(
            ok=True,
            base_url=settings.skynet_base_url,
            model=settings.nuextract_model,
            response_text=response_text,
        )
    except Exception as exc:
        return NuExtractDoctorResult(
            ok=False,
            base_url=settings.skynet_base_url,
            model=settings.nuextract_model,
            error=str(exc),
        )
