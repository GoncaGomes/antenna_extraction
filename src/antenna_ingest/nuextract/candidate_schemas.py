from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from antenna_ingest.orchestration.schemas import StrictModel


SCHEMA_NAME = "antenna_design_candidate_v2"

RECONSTRUCTION_STATUSES = (
    "buildable",
    "partially_buildable",
    "not_buildable_from_paper",
    "unknown",
)


class EvidenceRef(StrictModel):
    page: int | None = Field(default=None, ge=1)
    quote: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class ExtractedProperty(StrictModel):
    name: str | None = None
    raw_value: str | None = None
    value: float | str | bool | None = None
    unit: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return (
            self.name is None
            and self.raw_value is None
            and self.value is None
            and self.unit is None
            and not self.evidence
            and not self.notes
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
    reconstruction_status: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)

    @field_validator("reconstruction_status")
    @classmethod
    def validate_reconstruction_status(cls, value: str | None) -> str | None:
        return _validate_reconstruction_status(value)


class MaterialCandidate(StrictModel):
    material_id: str
    name: str | None = None
    role: str | None = None
    properties: list[ExtractedProperty] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class GeometryDescription(StrictModel):
    representation: str | None = None
    primitive_type: str | None = None
    shape_family: str | None = None
    description: str | None = None
    properties: list[ExtractedProperty] = Field(default_factory=list)
    location: str | None = None
    reconstruction_status: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)

    @field_validator("reconstruction_status")
    @classmethod
    def validate_reconstruction_status(cls, value: str | None) -> str | None:
        return _validate_reconstruction_status(value)


class ComponentCandidate(StrictModel):
    component_id: str
    label: str | None = None
    role: str | None = None
    material_id: str | None = None
    geometry: GeometryDescription = Field(default_factory=GeometryDescription)
    properties: list[ExtractedProperty] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class FeatureCandidate(StrictModel):
    feature_id: str
    label: str | None = None
    feature_type: str | None = None
    associated_component_id: str | None = None
    description: str | None = None
    properties: list[ExtractedProperty] = Field(default_factory=list)
    location: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)


class FeedCandidate(StrictModel):
    feed_id: str
    feed_type: str | None = None
    associated_component_id: str | None = None
    description: str | None = None
    properties: list[ExtractedProperty] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class SimulationSetupCandidate(StrictModel):
    software: str | None = None
    solver: str | None = None
    boundary_conditions: str | None = None
    frequency_sweep: list[ExtractedProperty] = Field(default_factory=list)
    properties: list[ExtractedProperty] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ResultCandidate(StrictModel):
    metric: str
    raw_value: str | None = None
    value: float | str | bool | None = None
    unit: str | None = None
    condition: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FinalDesignCandidate(StrictModel):
    design_label: str | None = None
    is_explicitly_final_or_proposed: bool | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    materials: list[MaterialCandidate] = Field(default_factory=list)
    components: list[ComponentCandidate] = Field(default_factory=list)
    features: list[FeatureCandidate] = Field(default_factory=list)
    feeds: list[FeedCandidate] = Field(default_factory=list)
    simulation_setup: SimulationSetupCandidate = Field(
        default_factory=SimulationSetupCandidate
    )
    results: list[ResultCandidate] = Field(default_factory=list)


class VariantCandidate(StrictModel):
    variant_id: str | None = None
    label: str | None = None
    role: str | None = None
    relationship_to_final: str | None = None
    description: str | None = None
    properties: list[ExtractedProperty] = Field(default_factory=list)
    results: list[ResultCandidate] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class MissingInformation(StrictModel):
    field: str
    severity: str | None = None
    reason: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ConflictCandidate(StrictModel):
    field: str
    values: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    notes: str | None = None


class ExtractionNote(StrictModel):
    note: str
    evidence: list[EvidenceRef] = Field(default_factory=list)


class AntennaDesignCandidate(StrictModel):
    schema_name: Literal["antenna_design_candidate_v2"] = (
        "antenna_design_candidate_v2"
    )
    document: DocumentMetadata = Field(default_factory=DocumentMetadata)
    summary: CandidateSummary = Field(default_factory=CandidateSummary)
    final_design: FinalDesignCandidate = Field(default_factory=FinalDesignCandidate)
    variants: list[VariantCandidate] = Field(default_factory=list)
    conflicts: list[ConflictCandidate] = Field(default_factory=list)
    missing_information: list[MissingInformation] = Field(default_factory=list)
    notes: list[ExtractionNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> Self:
        final_design = self.final_design
        _ensure_unique(
            [material.material_id for material in final_design.materials],
            "material_id",
        )
        _ensure_unique(
            [component.component_id for component in final_design.components],
            "component_id",
        )
        _ensure_unique(
            [feature.feature_id for feature in final_design.features],
            "feature_id",
        )
        _ensure_unique(
            [feed.feed_id for feed in final_design.feeds],
            "feed_id",
        )
        return self


def _ensure_unique(values: list[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {field_name} values are not allowed")


def _validate_reconstruction_status(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in RECONSTRUCTION_STATUSES:
        allowed_values = ", ".join(RECONSTRUCTION_STATUSES)
        raise ValueError(
            f"reconstruction_status must be one of: {allowed_values}"
        )
    return value
