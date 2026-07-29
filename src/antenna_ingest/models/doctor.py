from __future__ import annotations

from antenna_ingest.models.client import build_model_client
from antenna_ingest.orchestration.schemas import StrictModel
from antenna_ingest.settings import (
    AntennaIngestSettings,
    ModelRole,
    load_settings,
)


class EndpointDoctorResult(StrictModel):
    ok: bool
    base_url: str
    model_role: ModelRole
    model: str
    response_text: str | None = None
    error: str | None = None


def run_endpoint_doctor(
    model_role: ModelRole,
    settings: AntennaIngestSettings | None = None,
    client: object | None = None,
) -> EndpointDoctorResult:
    settings = settings or load_settings()
    model = settings.model_for_role(model_role)
    client = client or build_model_client(settings, model_role)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply exactly: ENDPOINT-OK"}],
            temperature=0,
        )
        return EndpointDoctorResult(
            ok=True,
            base_url=settings.skynet_base_url,
            model_role=model_role,
            model=model,
            response_text=response.choices[0].message.content,
        )
    except Exception as exc:
        return EndpointDoctorResult(
            ok=False,
            base_url=settings.skynet_base_url,
            model_role=model_role,
            model=model,
            error=str(exc),
        )
