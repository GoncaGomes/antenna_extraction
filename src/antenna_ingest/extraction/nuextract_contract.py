from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import Field

from antenna_ingest.contracts.base import ContractModel
from antenna_ingest.contracts.common import (
    AngularPatternRepresentation,
    AxisDescriptor,
    BoundingRegion,
    DesignRole,
    DocumentReference,
    EvidenceRecord,
    EvidenceSourceKind,
    Identifier,
    IntervalRepresentation,
    LegibilityState,
    MatrixRepresentation,
    NonEmptyString,
    PageRecord,
    PointCollectionRepresentation,
    QualitativeRepresentation,
    ReportedCondition,
    ReportedPoint,
    ResultOrigin,
    SampledSeriesRepresentation,
    SampledSpatialMapContent,
    ScalarRepresentation,
    SourceValue,
    UnavailableRepresentation,
)
from antenna_ingest.contracts.paper_extraction import PaperExtraction


class InlineEvidence(ContractModel):
    page_number: int = Field(ge=1)
    source_kind: EvidenceSourceKind
    excerpt_or_description: NonEmptyString
    source_label: NonEmptyString | None = None
    bounding_region: BoundingRegion | None = None
    legibility_note: NonEmptyString | None = None


class NuExtractDesignRecord(ContractModel):
    design_id: Identifier
    name: NonEmptyString
    role: DesignRole
    description: NonEmptyString | None = None
    parent_design_id: Identifier | None = Field(
        default=None,
        description=(
            "May be non-null only when the exact referenced ID is declared by "
            "another record in the same designs array; otherwise it must be null."
        ),
    )
    predecessor_design_id: Identifier | None = Field(
        default=None,
        description=(
            "May be non-null only when the exact referenced ID is declared by "
            "another record in the same designs array; otherwise it must be null."
        ),
    )
    evidence: list[InlineEvidence] = Field(
        min_length=1,
        description=(
            "Inline source evidence directly supporting this design's identity, "
            "name, role, or description."
        ),
    )


class NuExtractSetupBase(ContractModel):
    setup_id: Identifier
    description: NonEmptyString
    evidence: list[InlineEvidence] = Field(min_length=1)
    legibility: LegibilityState = "clear"
    uncertainty_note: NonEmptyString | None = None


class NuExtractSimulationSetup(NuExtractSetupBase):
    kind: Literal["simulation"]
    software: NonEmptyString | None = None
    solver_or_method: NonEmptyString | None = None
    model: NonEmptyString | None = None
    conditions: list[ReportedCondition] = Field(default_factory=list)


class NuExtractMeasurementSetup(NuExtractSetupBase):
    kind: Literal["measurement"]
    equipment: list[NonEmptyString] = Field(default_factory=list)
    calibration: NonEmptyString | None = None
    fixture: NonEmptyString | None = None
    environment: NonEmptyString | None = None


class NuExtractAnalyticalSetup(NuExtractSetupBase):
    kind: Literal["analytical"]
    method: NonEmptyString | None = None
    assumptions: list[NonEmptyString] = Field(default_factory=list)


NuExtractSetup = Annotated[
    NuExtractSimulationSetup | NuExtractMeasurementSetup | NuExtractAnalyticalSetup,
    Field(discriminator="kind"),
]


class NuExtractObservationBase(ContractModel):
    observation_id: Identifier
    design_id: Identifier | None = None
    description: NonEmptyString
    evidence: list[InlineEvidence] = Field(min_length=1)
    legibility: LegibilityState = "clear"
    uncertainty_note: NonEmptyString | None = None


class NuExtractMaterialObservation(NuExtractObservationBase):
    material_name: NonEmptyString | None = None
    reported_properties: list[ReportedCondition] = Field(default_factory=list)


class NuExtractParameterObservation(NuExtractObservationBase):
    symbol: NonEmptyString | None = None
    reported_value: SourceValue | None = None


class NuExtractGeometryObservation(NuExtractObservationBase):
    source_feature_label: NonEmptyString | None = None


class NuExtractFeedPortExcitationObservation(NuExtractObservationBase):
    observation_kind: Literal["feed", "port", "excitation"]
    reported_impedance: SourceValue | None = None


class NuExtractReportedDerivation(ContractModel):
    derivation_id: Identifier
    description: NonEmptyString
    expression_text: NonEmptyString | None = None
    symbols: list[NonEmptyString] = Field(default_factory=list)
    evidence: list[InlineEvidence] = Field(min_length=1)


NuExtractReferenceKind = Literal[
    "design",
    "setup",
    "result",
    "material_observation",
    "parameter_observation",
    "geometry_observation",
    "feed_port_excitation_observation",
    "derivation",
    "conflict",
    "missing_information",
]


class NuExtractEntityReference(ContractModel):
    kind: NuExtractReferenceKind
    id: Identifier


class NuExtractConflictRecord(ContractModel):
    conflict_id: Identifier
    description: NonEmptyString
    related_refs: list[NuExtractEntityReference] = Field(min_length=2)
    evidence: list[InlineEvidence] = Field(min_length=1)


class NuExtractMissingInformationRecord(ContractModel):
    missing_information_id: Identifier
    description: NonEmptyString
    related_refs: list[NuExtractEntityReference] = Field(default_factory=list)
    evidence: list[InlineEvidence] = Field(min_length=1)


class NuExtractImageOnlySpatialMapContent(ContractModel):
    kind: Literal["image_only"]
    map_type_or_component: NonEmptyString | None = None
    plane_or_cut: NonEmptyString | None = None
    legend_or_scale_label: NonEmptyString | None = None
    annotated_points: list[ReportedPoint] = Field(default_factory=list)
    evidence: list[InlineEvidence] = Field(min_length=1)


NuExtractSpatialMapContent = Annotated[
    SampledSpatialMapContent | NuExtractImageOnlySpatialMapContent,
    Field(discriminator="kind"),
]


class NuExtractSpatialMapRepresentation(ContractModel):
    kind: Literal["spatial_map"]
    quantity: NonEmptyString
    content: NuExtractSpatialMapContent


class NuExtractImageOnlyGraphRepresentation(ContractModel):
    kind: Literal["image_only"]
    axes: list[AxisDescriptor] = Field(default_factory=list)
    trace_labels: list[NonEmptyString] = Field(default_factory=list)
    annotated_points: list[ReportedPoint] = Field(default_factory=list)
    evidence: list[InlineEvidence] = Field(min_length=1)


NuExtractResultRepresentation = Annotated[
    ScalarRepresentation
    | IntervalRepresentation
    | PointCollectionRepresentation
    | SampledSeriesRepresentation
    | MatrixRepresentation
    | AngularPatternRepresentation
    | NuExtractSpatialMapRepresentation
    | NuExtractImageOnlyGraphRepresentation
    | QualitativeRepresentation
    | UnavailableRepresentation,
    Field(discriminator="kind"),
]


class NuExtractResultRecord(ContractModel):
    result_id: Identifier
    design_id: Identifier
    setup_id: Identifier | None = None
    origin: ResultOrigin
    metric: NonEmptyString
    conditions: list[ReportedCondition] = Field(default_factory=list)
    representation: NuExtractResultRepresentation
    evidence: list[InlineEvidence] = Field(min_length=1)
    uncertainty_note: NonEmptyString | None = None


class NuExtractPaperExtraction(ContractModel):
    schema_name: Literal["paper_extraction"]
    schema_version: Literal["1.0.0"]
    document: DocumentReference
    pages: list[PageRecord] = Field(min_length=1)
    designs: list[NuExtractDesignRecord]
    material_observations: list[NuExtractMaterialObservation]
    parameter_observations: list[NuExtractParameterObservation]
    geometry_observations: list[NuExtractGeometryObservation]
    feed_port_excitation_observations: list[NuExtractFeedPortExcitationObservation]
    setups: list[NuExtractSetup]
    results: list[NuExtractResultRecord]
    derivations: list[NuExtractReportedDerivation]
    conflicts: list[NuExtractConflictRecord]
    missing_information: list[NuExtractMissingInformationRecord]
    architecture_page_refs: list[int]


class _EvidenceCatalogBuilder:
    def __init__(self) -> None:
        self.records: list[EvidenceRecord] = []
        self._ids_by_content: dict[str, str] = {}

    def ids_for(self, evidence: list[InlineEvidence]) -> list[str]:
        evidence_ids: list[str] = []
        for item in evidence:
            content = item.model_dump(mode="json")
            key = json.dumps(
                content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            evidence_id = self._ids_by_content.get(key)
            if evidence_id is None:
                evidence_id = f"evidence_{len(self.records) + 1}"
                self._ids_by_content[key] = evidence_id
                self.records.append(
                    EvidenceRecord.model_validate(
                        {"evidence_id": evidence_id, **content}
                    )
                )
            evidence_ids.append(evidence_id)
        return evidence_ids


def normalize_nuextract_extraction(
    extraction: NuExtractPaperExtraction,
) -> PaperExtraction:
    """Normalize inline evidence in deterministic top-level collection order.

    Evidence is visited through designs, material_observations,
    parameter_observations, geometry_observations,
    feed_port_excitation_observations, setups, results, derivations, conflicts,
    then missing_information. For each result, direct evidence precedes any
    image-only representation evidence.
    """
    catalog = _EvidenceCatalogBuilder()

    designs = [
        _record_with_evidence(record, record.evidence, catalog)
        for record in extraction.designs
    ]
    material_observations = [
        _record_with_evidence(record, record.evidence, catalog)
        for record in extraction.material_observations
    ]
    parameter_observations = [
        _record_with_evidence(record, record.evidence, catalog)
        for record in extraction.parameter_observations
    ]
    geometry_observations = [
        _record_with_evidence(record, record.evidence, catalog)
        for record in extraction.geometry_observations
    ]
    feed_observations = [
        _record_with_evidence(record, record.evidence, catalog)
        for record in extraction.feed_port_excitation_observations
    ]
    setups = [
        _record_with_evidence(record, record.evidence, catalog)
        for record in extraction.setups
    ]
    results = [_normalize_result(record, catalog) for record in extraction.results]
    derivations = [
        _record_with_evidence(record, record.evidence, catalog)
        for record in extraction.derivations
    ]
    conflicts = [
        _record_with_evidence(record, record.evidence, catalog)
        for record in extraction.conflicts
    ]
    missing_information = [
        _record_with_evidence(record, record.evidence, catalog)
        for record in extraction.missing_information
    ]

    return PaperExtraction.model_validate(
        {
            "schema_name": extraction.schema_name,
            "schema_version": extraction.schema_version,
            "document": extraction.document.model_dump(mode="json"),
            "pages": [page.model_dump(mode="json") for page in extraction.pages],
            "evidence_catalog": [
                record.model_dump(mode="json") for record in catalog.records
            ],
            "designs": designs,
            "material_observations": material_observations,
            "parameter_observations": parameter_observations,
            "geometry_observations": geometry_observations,
            "feed_port_excitation_observations": feed_observations,
            "setups": setups,
            "results": results,
            "derivations": derivations,
            "conflicts": conflicts,
            "missing_information": missing_information,
            "architecture_page_refs": extraction.architecture_page_refs,
        }
    )


def _record_with_evidence(
    record: ContractModel,
    evidence: list[InlineEvidence],
    catalog: _EvidenceCatalogBuilder,
) -> dict:
    data = record.model_dump(mode="json")
    data.pop("evidence")
    data["evidence_ids"] = catalog.ids_for(evidence)
    return data


def _normalize_result(
    result: NuExtractResultRecord,
    catalog: _EvidenceCatalogBuilder,
) -> dict:
    data = _record_with_evidence(result, result.evidence, catalog)
    representation = result.representation
    representation_data = representation.model_dump(mode="json")

    if isinstance(representation, NuExtractImageOnlyGraphRepresentation):
        representation_data.pop("evidence")
        representation_data["evidence_ids"] = catalog.ids_for(representation.evidence)
    elif isinstance(representation, NuExtractSpatialMapRepresentation) and isinstance(
        representation.content,
        NuExtractImageOnlySpatialMapContent,
    ):
        content_data = representation.content.model_dump(mode="json")
        content_data.pop("evidence")
        content_data["evidence_ids"] = catalog.ids_for(representation.content.evidence)
        representation_data["content"] = content_data

    data["representation"] = representation_data
    return data
