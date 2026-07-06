from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from antenna_ingest.nuextract.candidate_schemas import (
    AntennaDesignCandidate,
    EvidenceRef,
    ExtractedProperty,
    ResultCandidate,
)
from antenna_ingest.nuextract.candidate_template import (
    ANTENNA_DESIGN_CANDIDATE_INSTRUCTIONS,
    ANTENNA_DESIGN_CANDIDATE_TEMPLATE,
)
from antenna_ingest.nuextract.client import build_nuextract_client
from antenna_ingest.nuextract.images import image_file_to_data_url
from antenna_ingest.nuextract.pdf_rendering import (
    PAGE_RENDER_REPORT_PATH,
    PAGES_DIR,
    PageRenderReport,
    render_run_pages,
)
from antenna_ingest.nuextract.settings import (
    NuExtractSettings,
    load_nuextract_settings,
)
from antenna_ingest.orchestration.runs import create_run, sha256_file
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    PhaseStatus,
    RunContext,
    RunManifest,
    StrictModel,
)
from antenna_ingest.utils.json_io import read_json, write_json


RAW_EXTRACTION_PHASE = "nuextract_raw_extraction"
ANTENNA_CANDIDATE_PATH = "extraction/nuextract3_antenna_candidate.json"
EXTRACTION_REPORT_PATH = "extraction/nuextract3_extraction_report.json"
RAW_RESPONSE_TRACE_PATH = "extraction/nuextract3_raw_response.txt"
CLEANED_RESPONSE_TRACE_PATH = "extraction/nuextract3_cleaned_response.txt"
PARSE_ERROR_TRACE_PATH = "extraction/nuextract3_parse_error.txt"
REQUEST_METADATA_PATH = "extraction/nuextract3_request_metadata.json"
EXTRACTOR_NAME = "nuextract3_full_document_structured_extraction"


@dataclass(frozen=True)
class PageImagePayload:
    page_number: int
    data_url: str


class NuExtractExtractionReport(StrictModel):
    extractor_name: str = Field(min_length=1)
    model: str = Field(min_length=1)
    source_pages_dir: str = Field(min_length=1)
    source_page_render_report: str = Field(min_length=1)
    output_candidate: str = Field(min_length=1)
    page_count: int = Field(ge=1)
    thinking_enabled: bool
    temperature: float
    candidate_character_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class NuExtractRequestMetadata(StrictModel):
    model: str = Field(min_length=1)
    temperature: float
    max_tokens: int | None = None
    enable_thinking: bool
    page_count: int = Field(ge=1)
    template_version: str = Field(min_length=1)
    timeout_seconds: int = Field(gt=0)


def extract_antenna_candidate_from_run(
    run_dir: Path,
    force: bool = False,
    settings: NuExtractSettings | None = None,
    client: object | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    enable_thinking: bool = True,
) -> tuple[AntennaDesignCandidate, NuExtractExtractionReport]:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    manifest = RunManifest.model_validate(read_json(manifest_path))
    render_report_path = run_dir / PAGE_RENDER_REPORT_PATH
    if not render_report_path.exists():
        render_run_pages(run_dir, force=force)
    page_report = PageRenderReport.model_validate(read_json(render_report_path))

    refuse_existing_extraction_outputs(run_dir, force)
    settings = settings or load_nuextract_settings()
    client = client or build_nuextract_client(settings)

    manifest = RunManifest.model_validate(read_json(manifest_path))
    manifest.phase_status[RAW_EXTRACTION_PHASE] = PhaseStatus.RUNNING
    write_json(manifest_path, manifest.model_dump(mode="json"))

    try:
        page_payloads = [
            PageImagePayload(
                page_number=page.page_number,
                data_url=image_file_to_data_url(run_dir / page.relative_path),
            )
            for page in page_report.pages
        ]
        metadata = NuExtractRequestMetadata(
            model=settings.nuextract_model,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_thinking=enable_thinking,
            page_count=page_report.page_count,
            template_version=ANTENNA_DESIGN_CANDIDATE_TEMPLATE["schema_name"],
            timeout_seconds=settings.nuextract_timeout_seconds,
        )
        write_json(
            run_dir / REQUEST_METADATA_PATH,
            metadata.model_dump(mode="json"),
        )
        response_content = request_antenna_candidate(
            client=client,
            model=settings.nuextract_model,
            page_payloads=page_payloads,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_thinking=enable_thinking,
        )
        try:
            candidate = parse_candidate_response(response_content)
        except Exception as error:
            write_response_parse_traces(run_dir, response_content, error)
            raise
        warnings = validate_candidate_source_pages(
            candidate,
            page_count=page_report.page_count,
        )

        candidate_path = run_dir / ANTENNA_CANDIDATE_PATH
        write_json(candidate_path, candidate.model_dump(mode="json"))
        report = NuExtractExtractionReport(
            extractor_name=EXTRACTOR_NAME,
            model=settings.nuextract_model,
            source_pages_dir=PAGES_DIR,
            source_page_render_report=PAGE_RENDER_REPORT_PATH,
            output_candidate=ANTENNA_CANDIDATE_PATH,
            page_count=page_report.page_count,
            thinking_enabled=enable_thinking,
            temperature=temperature,
            candidate_character_count=len(
                candidate_path.read_text(encoding="utf-8")
            ),
            warnings=warnings,
        )
        write_json(run_dir / EXTRACTION_REPORT_PATH, report.model_dump(mode="json"))

        manifest = RunManifest.model_validate(read_json(manifest_path))
        manifest.phase_status[RAW_EXTRACTION_PHASE] = PhaseStatus.COMPLETED
        replace_raw_extraction_artifacts(manifest, run_dir)
        write_json(manifest_path, manifest.model_dump(mode="json"))
        return candidate, report
    except Exception:
        failed_manifest = RunManifest.model_validate(read_json(manifest_path))
        failed_manifest.phase_status[RAW_EXTRACTION_PHASE] = PhaseStatus.FAILED
        write_json(manifest_path, failed_manifest.model_dump(mode="json"))
        raise


def parse_pdf_to_candidate(
    input_pdf: Path,
    runs_root: Path = Path("runs"),
    paper_id: str | None = None,
    dpi: int = 170,
    force: bool = False,
    settings: NuExtractSettings | None = None,
    client: object | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    enable_thinking: bool = True,
) -> tuple[RunContext, AntennaDesignCandidate, NuExtractExtractionReport]:
    context = create_run(
        input_pdf=input_pdf,
        runs_root=runs_root,
        force=force,
        paper_id=paper_id,
    )
    render_run_pages(context.run_dir, dpi=dpi, force=force)
    candidate, report = extract_antenna_candidate_from_run(
        context.run_dir,
        force=force,
        settings=settings,
        client=client,
        temperature=temperature,
        max_tokens=max_tokens,
        enable_thinking=enable_thinking,
    )
    return context, candidate, report


def request_antenna_candidate(
    client: object,
    model: str,
    page_payloads: list[PageImagePayload],
    temperature: float = 0.0,
    max_tokens: int | None = None,
    enable_thinking: bool = True,
) -> str:
    request = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {
                "role": "user",
                "content": build_page_image_content(page_payloads),
            }
        ],
        "extra_body": {
            "chat_template_kwargs": {
                "template": json.dumps(
                    ANTENNA_DESIGN_CANDIDATE_TEMPLATE,
                    indent=2,
                ),
                "instructions": ANTENNA_DESIGN_CANDIDATE_INSTRUCTIONS,
                "enable_thinking": enable_thinking,
            }
        },
    }
    if max_tokens is not None:
        request["max_tokens"] = max_tokens

    response = client.chat.completions.create(**request)
    return response.choices[0].message.content or ""


def build_page_image_content(page_payloads: list[PageImagePayload]) -> list[dict]:
    content: list[dict] = []
    for payload in page_payloads:
        content.append(
            {
                "type": "text",
                "text": f"PDF_INPUT_PAGE={payload.page_number}",
            }
        )
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": payload.data_url},
            }
        )
    return content


def validate_candidate_source_pages(
    candidate: AntennaDesignCandidate,
    page_count: int,
) -> list[str]:
    warnings: list[str] = []

    def check_evidence(evidence: list[EvidenceRef], location: str) -> None:
        for index, item in enumerate(evidence):
            if item.page is None:
                continue
            if item.page < 1 or item.page > page_count:
                warnings.append(
                    f"Invalid evidence page at {location}[{index}].page: "
                    f"{item.page} is outside PDF input page range 1..{page_count}."
                )

    def check_properties(
        properties: list[ExtractedProperty],
        location: str,
    ) -> None:
        for index, prop in enumerate(properties):
            check_evidence(prop.evidence, f"{location}[{index}].evidence")

    def check_results(results: list[ResultCandidate], location: str) -> None:
        for index, result in enumerate(results):
            check_evidence(result.evidence, f"{location}[{index}].evidence")

    check_evidence(candidate.summary.evidence, "summary.evidence")

    final_design = candidate.final_design
    check_evidence(final_design.evidence, "final_design.evidence")

    for material_index, material in enumerate(final_design.materials):
        material_location = f"final_design.materials[{material_index}]"
        check_evidence(material.evidence, f"{material_location}.evidence")
        check_properties(material.properties, f"{material_location}.properties")

    for component_index, component in enumerate(final_design.components):
        component_location = f"final_design.components[{component_index}]"
        check_evidence(component.evidence, f"{component_location}.evidence")
        check_evidence(
            component.geometry.evidence,
            f"{component_location}.geometry.evidence",
        )
        check_properties(
            component.geometry.properties,
            f"{component_location}.geometry.properties",
        )
        check_properties(component.properties, f"{component_location}.properties")

    for feature_index, feature in enumerate(final_design.features):
        feature_location = f"final_design.features[{feature_index}]"
        check_evidence(feature.evidence, f"{feature_location}.evidence")
        check_properties(feature.properties, f"{feature_location}.properties")

    for feed_index, feed in enumerate(final_design.feeds):
        feed_location = f"final_design.feeds[{feed_index}]"
        check_evidence(feed.evidence, f"{feed_location}.evidence")
        check_properties(feed.properties, f"{feed_location}.properties")

    simulation_setup = final_design.simulation_setup
    check_evidence(
        simulation_setup.evidence,
        "final_design.simulation_setup.evidence",
    )
    check_properties(
        simulation_setup.frequency_sweep,
        "final_design.simulation_setup.frequency_sweep",
    )
    check_properties(
        simulation_setup.properties,
        "final_design.simulation_setup.properties",
    )

    check_results(final_design.results, "final_design.results")

    for variant_index, variant in enumerate(candidate.variants):
        variant_location = f"variants[{variant_index}]"
        check_evidence(variant.evidence, f"{variant_location}.evidence")
        check_properties(variant.properties, f"{variant_location}.properties")
        check_results(variant.results, f"{variant_location}.results")

    for conflict_index, conflict in enumerate(candidate.conflicts):
        check_evidence(
            conflict.evidence,
            f"conflicts[{conflict_index}].evidence",
        )

    for missing_index, missing in enumerate(candidate.missing_information):
        check_evidence(
            missing.evidence,
            f"missing_information[{missing_index}].evidence",
        )

    for note_index, note in enumerate(candidate.notes):
        check_evidence(note.evidence, f"notes[{note_index}].evidence")

    return warnings


def refuse_existing_extraction_outputs(run_dir: Path, force: bool) -> None:
    candidate_path = Path(run_dir) / ANTENNA_CANDIDATE_PATH
    report_path = Path(run_dir) / EXTRACTION_REPORT_PATH
    metadata_path = Path(run_dir) / REQUEST_METADATA_PATH
    if not force:
        if candidate_path.exists():
            raise FileExistsError(f"candidate already exists: {candidate_path}")
        if report_path.exists():
            raise FileExistsError(f"extraction report already exists: {report_path}")
        if metadata_path.exists():
            raise FileExistsError(f"request metadata already exists: {metadata_path}")
        return

    if candidate_path.exists():
        candidate_path.unlink()
    if report_path.exists():
        report_path.unlink()
    if metadata_path.exists():
        metadata_path.unlink()


def replace_raw_extraction_artifacts(
    manifest: RunManifest,
    run_dir: Path,
) -> None:
    artifact_names = {
        "nuextract3_antenna_candidate",
        "nuextract3_extraction_report",
        "nuextract3_request_metadata",
    }
    manifest.artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.name not in artifact_names
    ]
    manifest.add_artifact(
        ArtifactReference(
            name="nuextract3_antenna_candidate",
            relative_path=ANTENNA_CANDIDATE_PATH,
            producing_phase=RAW_EXTRACTION_PHASE,
            checksum=sha256_file(Path(run_dir) / ANTENNA_CANDIDATE_PATH),
        )
    )
    manifest.add_artifact(
        ArtifactReference(
            name="nuextract3_extraction_report",
            relative_path=EXTRACTION_REPORT_PATH,
            producing_phase=RAW_EXTRACTION_PHASE,
            checksum=sha256_file(Path(run_dir) / EXTRACTION_REPORT_PATH),
        )
    )
    manifest.add_artifact(
        ArtifactReference(
            name="nuextract3_request_metadata",
            relative_path=REQUEST_METADATA_PATH,
            producing_phase=RAW_EXTRACTION_PHASE,
            checksum=sha256_file(Path(run_dir) / REQUEST_METADATA_PATH),
        )
    )


def clean_nuextract_json_response(content: str) -> str:
    cleaned = content.rsplit("</think>", maxsplit=1)[-1].strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    return cleaned


def write_response_parse_traces(
    run_dir: Path,
    response_content: str,
    error: Exception,
) -> None:
    run_dir = Path(run_dir)
    cleaned = clean_nuextract_json_response(response_content)
    raw_path = run_dir / RAW_RESPONSE_TRACE_PATH
    cleaned_path = run_dir / CLEANED_RESPONSE_TRACE_PATH
    error_path = run_dir / PARSE_ERROR_TRACE_PATH
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(response_content, encoding="utf-8")
    cleaned_path.write_text(cleaned, encoding="utf-8")
    error_path.write_text(
        format_parse_error_trace(cleaned, error),
        encoding="utf-8",
    )


def format_parse_error_trace(cleaned: str, error: Exception) -> str:
    lines = [
        f"error_type: {type(error).__name__}",
        f"error_message: {error}",
    ]
    if isinstance(error, json.JSONDecodeError):
        start = max(error.pos - 500, 0)
        end = min(error.pos + 500, len(cleaned))
        lines.extend(
            [
                f"line: {error.lineno}",
                f"column: {error.colno}",
                f"char_position: {error.pos}",
                f"context_start: {start}",
                f"context_end: {end}",
                "context:",
                cleaned[start:end],
            ]
        )
    return "\n".join(lines) + "\n"


def parse_candidate_response(content: str) -> AntennaDesignCandidate:
    cleaned = clean_nuextract_json_response(content)
    data = json.loads(cleaned)
    return AntennaDesignCandidate.model_validate(data)
