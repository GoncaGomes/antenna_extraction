from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Literal

from pydantic import Field

from antenna_ingest.contracts.common import DocumentReference, PageRecord
from antenna_ingest.contracts.paper_extraction import PaperExtraction
from antenna_ingest.extraction.nuextract_contract import (
    NuExtractPaperExtraction,
    normalize_nuextract_extraction,
)
from antenna_ingest.models.client import build_model_client
from antenna_ingest.orchestration.failures import (
    sanitize_failure_message,
    write_failure_record,
)
from antenna_ingest.orchestration.phases import (
    complete_phase,
    fail_phase,
    start_phase,
)
from antenna_ingest.orchestration.runs import load_run_manifest, sha256_file
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    PhaseStatus,
    RunManifest,
    StrictModel,
)
from antenna_ingest.rendering import PAGE_RENDER_REPORT_PATH, PageRenderReport
from antenna_ingest.settings import (
    AntennaIngestSettings,
    ModelRole,
    load_settings,
)
from antenna_ingest.utils.images import image_file_to_data_url
from antenna_ingest.utils.json_io import read_json, write_json


PAPER_EXTRACTION_PHASE = "paper_extraction"
REQUEST_METADATA_PATH = "extraction/nuextract3_request_metadata.json"
RAW_RESPONSE_PATH = "extraction/nuextract3_raw_response.txt"
PAPER_EXTRACTION_PATH = "extraction/paper_extraction.json"
EXTRACTION_REPORT_PATH = "extraction/extraction_report.json"
EXTRACTION_VALIDATION_PATH = "reports/extraction_validation.json"
EXTRACTION_ARTIFACT_PATHS = {
    "nuextract3_request_metadata": REQUEST_METADATA_PATH,
    "nuextract3_raw_response": RAW_RESPONSE_PATH,
    "paper_extraction": PAPER_EXTRACTION_PATH,
    "extraction_report": EXTRACTION_REPORT_PATH,
    "extraction_validation": EXTRACTION_VALIDATION_PATH,
}

EXTRACTION_PROMPT = """You are a source-faithful extractor of antenna-engineering scientific papers.

The ordered page images that follow are all pages of one scientific paper. Treat them as a single complete document, not as independent page-level documents. Each image is preceded by its globally one-based PDF_INPUT_PAGE number.

Return exactly one JSON object matching the supplied NuExtractPaperExtraction JSON Schema. Return no commentary, Markdown, or text outside that object.

Extract distinct scientifically relevant information about antenna designs that the paper itself proposes, analyses, simulates, fabricates, or measures.

Do not extract paper-organisation statements, bibliographic background, conflict-of-interest declarations, or antenna designs mentioned only as related work into the engineering collections.

Identify every distinct antenna design, intermediate design, variant, final design, fabricated design, and measured prototype studied by the paper. Set parent_design_id or predecessor_design_id only when the exact referenced design_id is declared by another record in the same designs array. Otherwise the relationship field must be null.

The document object contains only source-derived title and DOI metadata. Use null when either value is not reported.

Populate each collection only with information matching its scientific meaning:

- observations contains all source-supported engineering observations. Each observation must use exactly one best matching kind: material, parameter, geometry, feed, port, or excitation.
  - material: a material used by a studied design, fabrication, simulation or measurement, including explicitly reported material properties.
  - parameter: a named or symbolized engineering, simulation or measurement parameter that is not primarily a material, geometry, feed, port or excitation description.
  - geometry: physical shape, topology, dimension, placement, layer, slot, cut, connection or structural relationship.
  - feed: the physical or conceptual feeding arrangement.
  - port: a reported port definition, type, location or impedance.
  - excitation: a reported excitation method, mode, polarization or source.
- setups: explicitly reported simulation, measurement, or analytical configurations used for the extracted designs or results. Do not include configurations belonging only to cited related work.
- results: source-supported antenna performance values or qualitative findings. Distinguish simulated, measured, analytical, and unspecified origins.
- derivations: equations, formulas, or calculation procedures explicitly reported by the source. A reported dimension or value alone is not a derivation.
- conflicts: incompatible scientific values, claims, design descriptions, or reported findings. Do not record conflict-of-interest declarations.
- missing_information: technically relevant information that is absent, unavailable, or required to interpret an emitted record. Its description must state what is missing. Do not place reported conclusions or positive findings in this collection.

Leave a collection empty when the paper contains no information matching that collection.

Emit each distinct scientific fact exactly once. Choose the single best matching observation kind. Do not repeat the same fact under multiple observation kinds. Do not emit general antenna definitions, explanations of common terminology, paper organisation, related work, or repeated conclusion summaries as engineering observations.

Associate each observation, setup, and result with the correct design whenever that association is explicitly supported. Preserve ambiguity when the paper does not support an unambiguous association.

Every emitted factual record except missing_information must contain its supporting evidence inline.

- Inline evidence is a list of only the source items directly required to support the record.
- The same source item may support different distinct records, but duplicate scientific records must not be emitted.
- Do not include evidence merely because it concerns the same antenna.
- Each inline evidence object must contain the correct page number, source kind, and concise source-faithful excerpt or visual description. Include a source label, bounding region, or legibility note only when available.
- Do not create evidence objects for individual words, table cells, numeric values, curve samples, or repeated claims from the same source item.
- Omit any claim that does not have direct source evidence.

Choose the result representation that matches the source evidence.

- Use scalar for one explicitly reported value, magnitude, width, or span. A reported width or span without explicit endpoints is a scalar, not an interval.
- Use interval only when the source explicitly reports both lower and upper endpoints.
- Use point_collection, sampled_series, matrix, or angular_pattern only for source-supported numeric data.
- Use spatial_map for spatially distributed quantities.
- Use image_only when visual evidence exists but trustworthy numeric samples cannot be preserved.
- Use qualitative for source-supported non-numeric findings.
- Use unavailable only when an identified result cannot be represented because its value is not reported, illegible, or ambiguous.
- Never invent, derive, estimate, interpolate, or digitise values.

Preserve exact source symbols, numeric lexemes, units, qualifiers, and wording. Do not silently normalise or rewrite source values.

Do not invent dimensions, materials, values, relationships, design choices, result points, or engineering assumptions. Do not infer typical antenna properties that are not stated or visibly supported. Do not select or construct the final solver architecture. Do not emit CST commands, solver commands, simulation instructions, optimisation steps, or construction plans.

When information is ambiguous, uncertain, or illegible, represent that honestly using the fields provided by the schema.

Before returning the JSON, verify all of the following:

- every emitted factual record except missing_information contains direct supporting evidence inline
- no inline evidence is included merely because it concerns the same antenna
- no engineering collection contains paper organisation, unrelated work, or administrative declarations
- each distinct scientific fact appears exactly once under the single best observation kind
- interval representations contain two explicit source-reported endpoints
"""


class PageImageMetadata(StrictModel):
    page_number: int = Field(ge=1)
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)


class EndpointMetadata(StrictModel):
    base_url: str = Field(min_length=1)
    timeout_seconds: int = Field(gt=0)


class TokenUsage(StrictModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class NuExtractRequestMetadata(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    model_role: Literal["document_extractor"] = "document_extractor"
    model: str = Field(min_length=1)
    thinking_enabled: bool
    temperature: float
    page_count: int = Field(ge=1)
    pages: list[PageImageMetadata] = Field(min_length=1)
    prompt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_started_at: datetime
    metadata_written_at: datetime
    request_completed_at: datetime | None = None
    endpoint: EndpointMetadata
    response_id: str | None = None
    finish_reason: str | None = None
    usage: TokenUsage | None = None


class ExtractionValidationReport(StrictModel):
    status: Literal["valid"] = "valid"
    validated_at: datetime
    deterministic_context_source: Literal["manifest_and_render_report"] = (
        "manifest_and_render_report"
    )
    deterministic_document_fields: list[
        Literal[
            "document_id",
            "page_count",
            "source_filename",
            "sha256",
            "pages",
        ]
    ]
    document_id: str
    source_filename: str
    input_sha256: str
    page_count: int = Field(ge=1)
    ordered_page_numbers: list[int] = Field(min_length=1)
    evidence_count: int = Field(ge=0)
    design_count: int = Field(ge=0)
    setup_count: int = Field(ge=0)
    result_count: int = Field(ge=0)
    contract_references_valid: Literal[True] = True
    manifest_and_render_references_valid: Literal[True] = True
    extraction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExtractionReport(StrictModel):
    status: Literal["completed"] = "completed"
    model: str
    thinking_enabled: bool
    call_count: Literal[1] = 1
    started_at: datetime
    completed_at: datetime
    duration_seconds: float = Field(ge=0)
    page_count: int = Field(ge=1)
    response_id: str | None = None
    finish_reason: str | None = None
    usage: TokenUsage | None = None
    request_metadata_path: Literal[REQUEST_METADATA_PATH] = REQUEST_METADATA_PATH
    raw_response_path: Literal[RAW_RESPONSE_PATH] = RAW_RESPONSE_PATH
    extraction_path: Literal[PAPER_EXTRACTION_PATH] = PAPER_EXTRACTION_PATH
    validation_report_path: Literal[EXTRACTION_VALIDATION_PATH] = (
        EXTRACTION_VALIDATION_PATH
    )


def extract_paper_from_run(
    run_dir: Path,
    *,
    enable_thinking: bool,
    force: bool = False,
    settings: AntennaIngestSettings | None = None,
    client: object | None = None,
) -> PaperExtraction:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    manifest, render_report, page_metadata = _load_validated_inputs(run_dir)
    _refuse_existing_outputs(run_dir, manifest, force)

    settings = settings or load_settings()
    client = client or build_model_client(settings, ModelRole.DOCUMENT_EXTRACTOR)
    model = settings.model_for_role(ModelRole.DOCUMENT_EXTRACTOR)
    temperature = 0.6 if enable_thinking else 0.2
    schema = NuExtractPaperExtraction.model_json_schema(mode="validation")
    effective_prompt = EXTRACTION_PROMPT
    prompt_hash = _sha256_text(effective_prompt)
    schema_hash = _sha256_json(schema)

    start_phase(
        manifest,
        PAPER_EXTRACTION_PHASE,
        allow_completed_restart=force,
        model_role=ModelRole.DOCUMENT_EXTRACTOR.value,
        input_artifact_names=["source_pdf", "rendered_pages", "render_report"],
        prompt_hash=prompt_hash,
        schema_hash=schema_hash,
    )
    if force:
        _clear_extraction_outputs(run_dir, manifest)
    write_json(manifest_path, manifest.model_dump(mode="json"))

    substage = "request_preparation"
    invocation_id: str | None = None
    request_started_at = datetime.now(timezone.utc)
    monotonic_started_at = monotonic()
    metadata = NuExtractRequestMetadata(
        model=model,
        thinking_enabled=enable_thinking,
        temperature=temperature,
        page_count=render_report.page_count,
        pages=page_metadata,
        prompt_hash=prompt_hash,
        schema_hash=schema_hash,
        request_started_at=request_started_at,
        metadata_written_at=datetime.now(timezone.utc),
        endpoint=EndpointMetadata(
            base_url=sanitize_failure_message(settings.skynet_base_url),
            timeout_seconds=settings.timeout_for_role(ModelRole.DOCUMENT_EXTRACTOR),
        ),
    )

    try:
        write_json(
            run_dir / REQUEST_METADATA_PATH,
            metadata.model_dump(mode="json"),
        )
        content = _build_multimodal_content(run_dir, effective_prompt, page_metadata)
        substage = "model_request"
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            temperature=temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "nuextract_paper_extraction",
                    "strict": True,
                    "schema": schema,
                },
            },
            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": enable_thinking,
                }
            },
        )
        request_completed_at = datetime.now(timezone.utc)
        choice = response.choices[0]
        raw_response = choice.message.content
        if not isinstance(raw_response, str):
            raw_response = ""
        _write_text_atomic(run_dir / RAW_RESPONSE_PATH, raw_response)
        invocation_id = _optional_string(getattr(response, "id", None))
        finish_reason = _optional_string(getattr(choice, "finish_reason", None))
        usage = _extract_usage(getattr(response, "usage", None))

        metadata.request_completed_at = request_completed_at
        metadata.response_id = invocation_id
        metadata.finish_reason = finish_reason
        metadata.usage = usage
        write_json(
            run_dir / REQUEST_METADATA_PATH,
            metadata.model_dump(mode="json"),
        )

        if finish_reason == "length":
            substage = "response_truncation"
            raise RuntimeError(
                "NuExtract response reached the output-token limit and is incomplete"
            )

        substage = "response_parsing"
        response_data = json.loads(raw_response)
        substage = "model_response_validation"
        model_extraction = NuExtractPaperExtraction.model_validate(response_data)
        document = DocumentReference(
            document_id=manifest.document_id,
            page_count=render_report.page_count,
            source_filename=Path(manifest.input_file).name,
            sha256=manifest.input_sha256,
            title=model_extraction.document.title,
            doi=model_extraction.document.doi,
        )
        pages = [
            PageRecord(page_number=page.page_number, visible_label=None)
            for page in render_report.pages
        ]
        substage = "deterministic_normalization"
        extraction = normalize_nuextract_extraction(
            model_extraction,
            document=document,
            pages=pages,
        )
        substage = "final_validation"
        _validate_extraction_context(extraction, manifest, render_report)

        substage = "artifact_persistence"
        write_json(
            run_dir / PAPER_EXTRACTION_PATH,
            extraction.model_dump(mode="json"),
        )
        extraction_checksum = sha256_file(run_dir / PAPER_EXTRACTION_PATH)
        validation_report = ExtractionValidationReport(
            validated_at=datetime.now(timezone.utc),
            deterministic_document_fields=[
                "document_id",
                "page_count",
                "source_filename",
                "sha256",
                "pages",
            ],
            document_id=manifest.document_id,
            source_filename=Path(manifest.input_file).name,
            input_sha256=manifest.input_sha256,
            page_count=render_report.page_count,
            ordered_page_numbers=[page.page_number for page in render_report.pages],
            evidence_count=len(extraction.evidence_catalog),
            design_count=len(extraction.designs),
            setup_count=len(extraction.setups),
            result_count=len(extraction.results),
            extraction_sha256=extraction_checksum,
        )
        write_json(
            run_dir / EXTRACTION_VALIDATION_PATH,
            validation_report.model_dump(mode="json"),
        )
        extraction_report = ExtractionReport(
            model=model,
            thinking_enabled=enable_thinking,
            started_at=request_started_at,
            completed_at=request_completed_at,
            duration_seconds=max(monotonic() - monotonic_started_at, 0.0),
            page_count=render_report.page_count,
            response_id=invocation_id,
            finish_reason=finish_reason,
            usage=usage,
        )
        write_json(
            run_dir / EXTRACTION_REPORT_PATH,
            extraction_report.model_dump(mode="json"),
        )

        completed_manifest = load_run_manifest(manifest_path)
        _replace_extraction_artifacts(completed_manifest, run_dir)
        complete_phase(
            completed_manifest,
            PAPER_EXTRACTION_PHASE,
            output_artifact_names=list(EXTRACTION_ARTIFACT_PATHS),
        )
        write_json(manifest_path, completed_manifest.model_dump(mode="json"))
        return extraction
    except Exception as error:
        failed_manifest = load_run_manifest(manifest_path)
        phase = failed_manifest.phases[PAPER_EXTRACTION_PHASE]
        available_artifacts = _available_extraction_paths(run_dir)
        raw_response_artifact = (
            RAW_RESPONSE_PATH if RAW_RESPONSE_PATH in available_artifacts else None
        )
        failure_reference = write_failure_record(
            run_dir,
            phase=PAPER_EXTRACTION_PHASE,
            attempt=phase.attempt,
            substage=substage,
            error=error,
            invocation_id=invocation_id,
            response_artifact=raw_response_artifact,
            partial_artifacts=available_artifacts,
        )
        _replace_extraction_artifacts(failed_manifest, run_dir)
        fail_phase(failed_manifest, PAPER_EXTRACTION_PHASE, failure_reference)
        write_json(manifest_path, failed_manifest.model_dump(mode="json"))
        raise


def _load_validated_inputs(
    run_dir: Path,
) -> tuple[RunManifest, PageRenderReport, list[PageImageMetadata]]:
    manifest_path = run_dir / "manifest.json"
    manifest = load_run_manifest(manifest_path)
    if manifest.phases["page_rendering"].status != PhaseStatus.COMPLETED:
        raise ValueError("page_rendering phase must be completed before extraction")

    input_pdf = _resolve_run_path(run_dir, manifest.input_file)
    if not input_pdf.is_file():
        raise FileNotFoundError(f"manifest input file does not exist: {input_pdf}")
    if sha256_file(input_pdf) != manifest.input_sha256:
        raise ValueError("input PDF checksum contradicts the run manifest")

    render_report_path = run_dir / PAGE_RENDER_REPORT_PATH
    render_report = PageRenderReport.model_validate(read_json(render_report_path))
    if render_report.source_document != manifest.input_file:
        raise ValueError("render report source document contradicts the manifest")
    expected_numbers = list(range(1, render_report.page_count + 1))
    actual_numbers = [page.page_number for page in render_report.pages]
    if actual_numbers != expected_numbers:
        raise ValueError("rendered pages must be complete, one-based, and ordered")
    if len(render_report.pages) != render_report.page_count:
        raise ValueError("render report page count does not match its page list")

    render_artifact = next(
        (item for item in manifest.artifacts if item.name == "render_report"),
        None,
    )
    if render_artifact is None or render_artifact.checksum is None:
        raise ValueError("manifest does not contain a checksummed render report")
    if sha256_file(render_report_path) != render_artifact.checksum:
        raise ValueError("render report checksum contradicts the manifest")

    relative_paths = [page.relative_path for page in render_report.pages]
    if len(relative_paths) != len(set(relative_paths)):
        raise ValueError("render report contains duplicate page image paths")
    page_metadata: list[PageImageMetadata] = []
    for page in render_report.pages:
        image_path = _resolve_run_path(run_dir, page.relative_path)
        if not image_path.is_file():
            raise FileNotFoundError(f"rendered page does not exist: {image_path}")
        page_metadata.append(
            PageImageMetadata(
                page_number=page.page_number,
                relative_path=page.relative_path,
                sha256=sha256_file(image_path),
                width_px=page.width_px,
                height_px=page.height_px,
            )
        )
    return manifest, render_report, page_metadata


def _build_multimodal_content(
    run_dir: Path,
    effective_prompt: str,
    pages: list[PageImageMetadata],
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": effective_prompt}]
    for page in pages:
        content.append({"type": "text", "text": f"PDF_INPUT_PAGE={page.page_number}"})
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": image_file_to_data_url(
                        _resolve_run_path(run_dir, page.relative_path)
                    )
                },
            }
        )
    return content


def _validate_extraction_context(
    extraction: PaperExtraction,
    manifest: RunManifest,
    render_report: PageRenderReport,
) -> None:
    expected_filename = Path(manifest.input_file).name
    expected_pages = [page.page_number for page in render_report.pages]
    actual_pages = [page.page_number for page in extraction.pages]
    mismatches: list[str] = []
    if extraction.document.document_id != manifest.document_id:
        mismatches.append("document_id")
    if extraction.document.page_count != render_report.page_count:
        mismatches.append("page_count")
    if extraction.document.source_filename != expected_filename:
        mismatches.append("source_filename")
    if extraction.document.sha256 != manifest.input_sha256:
        mismatches.append("sha256")
    if actual_pages != expected_pages:
        mismatches.append("ordered pages")
    if mismatches:
        raise ValueError(
            "extraction contradicts manifest or render report: " + ", ".join(mismatches)
        )


def _refuse_existing_outputs(
    run_dir: Path,
    manifest: RunManifest,
    force: bool,
) -> None:
    existing = _available_extraction_paths(run_dir)
    phase_completed = (
        manifest.phases[PAPER_EXTRACTION_PHASE].status == PhaseStatus.COMPLETED
    )
    if not force and (existing or phase_completed):
        raise FileExistsError(
            "extraction outputs already exist; use --force to replace them"
        )


def _clear_extraction_outputs(run_dir: Path, manifest: RunManifest) -> None:
    for relative_path in EXTRACTION_ARTIFACT_PATHS.values():
        (run_dir / relative_path).unlink(missing_ok=True)
    artifact_names = set(EXTRACTION_ARTIFACT_PATHS)
    manifest.artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.name not in artifact_names
    ]


def _replace_extraction_artifacts(manifest: RunManifest, run_dir: Path) -> None:
    artifact_names = set(EXTRACTION_ARTIFACT_PATHS)
    manifest.artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.name not in artifact_names
    ]
    for name, relative_path in EXTRACTION_ARTIFACT_PATHS.items():
        path = run_dir / relative_path
        if path.is_file():
            manifest.add_artifact(
                ArtifactReference(
                    name=name,
                    relative_path=relative_path,
                    producing_phase=PAPER_EXTRACTION_PHASE,
                    checksum=sha256_file(path),
                )
            )


def _available_extraction_paths(run_dir: Path) -> list[str]:
    return [
        relative_path
        for relative_path in EXTRACTION_ARTIFACT_PATHS.values()
        if (run_dir / relative_path).is_file()
    ]


def _resolve_run_path(run_dir: Path, relative_path: str) -> Path:
    candidate = (run_dir / relative_path).resolve()
    if not candidate.is_relative_to(run_dir):
        raise ValueError(f"path leaves run directory: {relative_path}")
    return candidate


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: dict[str, Any]) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_text(rendered)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
            newline="",
        ) as file:
            temporary_path = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _extract_usage(usage: object | None) -> TokenUsage | None:
    if usage is None:
        return None
    return TokenUsage(
        prompt_tokens=_optional_int(getattr(usage, "prompt_tokens", None)),
        completion_tokens=_optional_int(getattr(usage, "completion_tokens", None)),
        total_tokens=_optional_int(getattr(usage, "total_tokens", None)),
    )


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
