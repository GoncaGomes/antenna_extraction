from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from antenna_ingest.orchestration.schemas import StrictModel


RECONSTRUCTION_STATUSES = (
    "buildable",
    "partially_buildable",
    "not_buildable_from_paper",
    "unknown",
)


class SourceEvidence(StrictModel):
    source_page: int | None = Field(default=None, ge=1)
    source_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class ExtractedValue(StrictModel):
    name: str | None = None
    value: str | None = None
    numeric_value: float | None = None
    unit: str | None = None
    source_page: int | None = Field(default=None, ge=1)
    source_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)

    def is_empty(self) -> bool:
        return (
            self.name is None
            and self.value is None
            and self.numeric_value is None
            and self.unit is None
            and self.source_page is None
            and self.source_text is None
            and self.confidence is None
        )


class DocumentMetadata(StrictModel):
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    venue: str | None = None


class CandidateSummary(StrictModel):
    antenna_name: str | None = None
    antenna_class: str | None = None
    application: str | None = None
    operating_band: str | None = None
    final_design_claim: str | None = None
    reconstruction_status: str | None = None
    source_page: int | None = Field(default=None, ge=1)
    source_text: str | None = None


class MaterialCandidate(StrictModel):
    material_id: str
    name: str | None = None
    role: str | None = None
    properties: list[ExtractedValue] = Field(default_factory=list)


class GeometryCandidate(StrictModel):
    representation: str | None = None
    primitive_type: str | None = None
    shape_family: str | None = None
    description: str | None = None
    dimensions: list[ExtractedValue] = Field(default_factory=list)
    parameters: list[ExtractedValue] = Field(default_factory=list)
    location_description: str | None = None
    reconstruction_status: str | None = None


class ComponentCandidate(StrictModel):
    component_id: str
    label: str | None = None
    role: str | None = None
    material_id: str | None = None
    geometry: GeometryCandidate = Field(default_factory=GeometryCandidate)
    source_pages: list[int] = Field(default_factory=list)
    source_texts: list[str] = Field(default_factory=list)


class GeometryFeatureCandidate(StrictModel):
    feature_id: str
    label: str | None = None
    feature_type: str | None = None
    associated_component_id: str | None = None
    description: str | None = None
    parameters: list[ExtractedValue] = Field(default_factory=list)
    location_description: str | None = None
    source_page: int | None = Field(default=None, ge=1)
    source_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class FeedCandidate(StrictModel):
    feed_id: str
    feed_type: str | None = None
    associated_component_id: str | None = None
    description: str | None = None
    parameters: list[ExtractedValue] = Field(default_factory=list)
    source_page: int | None = Field(default=None, ge=1)
    source_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class SimulationSetupCandidate(StrictModel):
    software: ExtractedValue | None = None
    frequency_range: list[ExtractedValue] = Field(default_factory=list)
    solver: ExtractedValue | None = None
    boundary_conditions: ExtractedValue | None = None
    notes: list[str] = Field(default_factory=list)


class ResultCandidate(StrictModel):
    metric: str
    value: str | None = None
    numeric_value: float | None = None
    unit: str | None = None
    condition: str | None = None
    source_page: int | None = Field(default=None, ge=1)
    source_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class FinalDesignCandidate(StrictModel):
    design_label: str | None = None
    is_explicitly_final_or_proposed: bool | None = None
    final_design_evidence: list[SourceEvidence] = Field(default_factory=list)
    materials: list[MaterialCandidate] = Field(default_factory=list)
    components: list[ComponentCandidate] = Field(default_factory=list)
    geometry_features: list[GeometryFeatureCandidate] = Field(default_factory=list)
    feeds: list[FeedCandidate] = Field(default_factory=list)
    simulation_setup: SimulationSetupCandidate = Field(
        default_factory=SimulationSetupCandidate
    )
    results: list[ResultCandidate] = Field(default_factory=list)


class DesignVariantCandidate(StrictModel):
    variant_label: str | None = None
    variant_role: str | None = None
    relationship_to_final: str | None = None
    description: str | None = None
    key_parameters: list[ExtractedValue] = Field(default_factory=list)
    reported_results: list[ResultCandidate] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    source_texts: list[str] = Field(default_factory=list)


class MissingInformation(StrictModel):
    missing_field: str
    severity: str | None = None
    reason: str | None = None


class ConflictCandidate(StrictModel):
    field: str
    values: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    notes: str | None = None


class ExtractionNote(StrictModel):
    note: str
    source_page: int | None = Field(default=None, ge=1)


class AntennaDesignCandidate(StrictModel):
    schema_name: str = "antenna_design_candidate_v1"
    document: DocumentMetadata = Field(default_factory=DocumentMetadata)
    candidate_summary: CandidateSummary = Field(default_factory=CandidateSummary)
    final_design_candidate: FinalDesignCandidate = Field(
        default_factory=FinalDesignCandidate
    )
    design_variants: list[DesignVariantCandidate] = Field(default_factory=list)
    missing_information: list[MissingInformation] = Field(default_factory=list)
    conflicts: list[ConflictCandidate] = Field(default_factory=list)
    extraction_notes: list[ExtractionNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> Self:
        final_design = self.final_design_candidate
        _ensure_unique(
            [component.component_id for component in final_design.components],
            "component_id",
        )
        _ensure_unique(
            [material.material_id for material in final_design.materials],
            "material_id",
        )
        _ensure_unique(
            [feed.feed_id for feed in final_design.feeds],
            "feed_id",
        )
        _ensure_unique(
            [feature.feature_id for feature in final_design.geometry_features],
            "feature_id",
        )
        return self


def _ensure_unique(values: list[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {field_name} values are not allowed")
