from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from antenna_ingest.contracts.base import ContractModel


def _reject_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be blank")
    return value


NonEmptyString = Annotated[
    str,
    StringConstraints(strict=True, min_length=1),
    AfterValidator(_reject_blank),
]
Identifier = NonEmptyString

LegibilityState = Literal["clear", "uncertain", "illegible", "missing"]
ResultOrigin = Literal["simulated", "measured", "analytical", "unspecified"]
EvidenceSourceKind = Literal[
    "text",
    "caption",
    "figure",
    "table",
    "equation",
    "graph",
    "other",
]


class SourceValue(ContractModel):
    value: NonEmptyString = Field(
        description="Exact non-empty value lexeme preserved from the source."
    )
    unit: NonEmptyString | None = None
    qualifier: NonEmptyString | None = None
    legibility: Literal["clear", "uncertain"] = Field(
        description="Explicit legibility of the preserved source value."
    )


class DocumentReference(ContractModel):
    document_id: Identifier
    page_count: int = Field(ge=1)
    source_filename: NonEmptyString | None = None
    title: NonEmptyString | None = None
    doi: NonEmptyString | None = None
    sha256: NonEmptyString | None = None


class PageRecord(ContractModel):
    page_number: int = Field(ge=1)
    visible_label: NonEmptyString | None = None


class BoundingRegion(ContractModel):
    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def validate_bounds(self) -> BoundingRegion:
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("bounding region must have positive width and height")
        return self


class EvidenceRecord(ContractModel):
    evidence_id: Identifier
    page_number: int = Field(ge=1)
    source_kind: EvidenceSourceKind
    excerpt_or_description: NonEmptyString
    source_label: NonEmptyString | None = None
    bounding_region: BoundingRegion | None = None
    legibility_note: NonEmptyString | None = None


DesignRole = Literal[
    "candidate",
    "final",
    "fabricated",
    "measured_prototype",
    "variant",
    "other",
]


class DesignRecord(ContractModel):
    design_id: Identifier
    name: NonEmptyString
    role: DesignRole
    description: NonEmptyString | None = None
    parent_design_id: Identifier | None = None
    predecessor_design_id: Identifier | None = None
    evidence_ids: list[Identifier] = Field(
        default_factory=list,
        description=(
            "IDs declared in the top-level evidence_catalog that directly support "
            "this design's identity, name, role, or description. This is not the "
            "complete set of evidence associated with the design."
        ),
    )


class ReportedCondition(ContractModel):
    name: NonEmptyString
    value: SourceValue | None = None
    description: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_content(self) -> ReportedCondition:
        if self.value is None and self.description is None:
            raise ValueError("a condition requires a value or description")
        return self


class SetupBase(ContractModel):
    setup_id: Identifier
    description: NonEmptyString
    evidence_ids: list[Identifier] = Field(default_factory=list)
    legibility: LegibilityState = "clear"
    uncertainty_note: NonEmptyString | None = None


class SimulationSetup(SetupBase):
    kind: Literal["simulation"]
    software: NonEmptyString | None = None
    solver_or_method: NonEmptyString | None = None
    model: NonEmptyString | None = None
    conditions: list[ReportedCondition] = Field(default_factory=list)


class MeasurementSetup(SetupBase):
    kind: Literal["measurement"]
    equipment: list[NonEmptyString] = Field(default_factory=list)
    calibration: NonEmptyString | None = None
    fixture: NonEmptyString | None = None
    environment: NonEmptyString | None = None


class AnalyticalSetup(SetupBase):
    kind: Literal["analytical"]
    method: NonEmptyString | None = None
    assumptions: list[NonEmptyString] = Field(default_factory=list)


Setup = Annotated[
    SimulationSetup | MeasurementSetup | AnalyticalSetup,
    Field(discriminator="kind"),
]


class AxisDescriptor(ContractModel):
    name: NonEmptyString
    unit: NonEmptyString | None = None


class NamedValue(ContractModel):
    name: NonEmptyString
    value: SourceValue


class ReportedPoint(ContractModel):
    values: list[NamedValue] = Field(min_length=1)
    label: NonEmptyString | None = None


class SeriesPoint(ContractModel):
    x: SourceValue
    y: SourceValue


class AngularPoint(ContractModel):
    angle: SourceValue
    value: SourceValue


class ScalarRepresentation(ContractModel):
    """A single source-reported quantity."""

    kind: Literal["scalar"]
    value: SourceValue = Field(
        description=(
            "One exact source-reported value. This includes a magnitude, "
            "width, or span reported without explicit range endpoints."
        )
    )


class IntervalRepresentation(ContractModel):
    """A source-reported range with two explicit endpoints."""

    kind: Literal["interval"]
    lower: SourceValue = Field(
        description=(
            "Exact lower endpoint explicitly reported by the source. "
            "Do not derive it from a center value and range width."
        )
    )
    upper: SourceValue = Field(
        description=(
            "Exact upper endpoint explicitly reported by the source. "
            "Do not derive it from a center value and range width."
        )
    )


class PointCollectionRepresentation(ContractModel):
    kind: Literal["point_collection"]
    points: list[ReportedPoint] = Field(min_length=1)


class SampledSeriesRepresentation(ContractModel):
    kind: Literal["sampled_series"]
    x_axis: AxisDescriptor
    y_axis: AxisDescriptor
    trace_label: NonEmptyString | None = None
    points: list[SeriesPoint] = Field(min_length=1)


class MatrixRepresentation(ContractModel):
    kind: Literal["matrix"]
    rows: list[list[SourceValue]] = Field(min_length=1)
    row_labels: list[NonEmptyString] = Field(default_factory=list)
    column_labels: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_matrix_shape(self) -> MatrixRepresentation:
        column_count = len(self.rows[0])
        if column_count == 0 or any(len(row) != column_count for row in self.rows):
            raise ValueError("matrix rows must be non-empty and rectangular")
        if self.row_labels and len(self.row_labels) != len(self.rows):
            raise ValueError("row label count must match matrix row count")
        if self.column_labels and len(self.column_labels) != column_count:
            raise ValueError("column label count must match matrix column count")
        return self


class AngularPatternRepresentation(ContractModel):
    kind: Literal["angular_pattern"]
    angular_coordinate: NonEmptyString
    angular_unit: NonEmptyString | None = None
    plane_or_cut: NonEmptyString | None = None
    fixed_angle: SourceValue | None = None
    component_or_polarization: NonEmptyString | None = None
    radial_quantity: NonEmptyString
    points: list[AngularPoint] = Field(min_length=1)


class SampledSpatialMapContent(ContractModel):
    kind: Literal["sampled"]
    coordinate_description: NonEmptyString
    samples: list[ReportedPoint] = Field(min_length=1)


class ImageOnlySpatialMapContent(ContractModel):
    kind: Literal["image_only"]
    map_type_or_component: NonEmptyString | None = None
    plane_or_cut: NonEmptyString | None = None
    legend_or_scale_label: NonEmptyString | None = None
    annotated_points: list[ReportedPoint] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(min_length=1)


SpatialMapContent = Annotated[
    SampledSpatialMapContent | ImageOnlySpatialMapContent,
    Field(discriminator="kind"),
]


class SpatialMapRepresentation(ContractModel):
    kind: Literal["spatial_map"]
    quantity: NonEmptyString
    content: SpatialMapContent


class ImageOnlyGraphRepresentation(ContractModel):
    kind: Literal["image_only"]
    axes: list[AxisDescriptor] = Field(default_factory=list)
    trace_labels: list[NonEmptyString] = Field(default_factory=list)
    annotated_points: list[ReportedPoint] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(min_length=1)


class QualitativeRepresentation(ContractModel):
    kind: Literal["qualitative"]
    observation: NonEmptyString


class UnavailableRepresentation(ContractModel):
    kind: Literal["unavailable"]
    reason: Literal["not_reported", "illegible", "ambiguous"]
    description: NonEmptyString


ResultRepresentation = Annotated[
    ScalarRepresentation
    | IntervalRepresentation
    | PointCollectionRepresentation
    | SampledSeriesRepresentation
    | MatrixRepresentation
    | AngularPatternRepresentation
    | SpatialMapRepresentation
    | ImageOnlyGraphRepresentation
    | QualitativeRepresentation
    | UnavailableRepresentation,
    Field(discriminator="kind"),
]


class ResultRecord(ContractModel):
    result_id: Identifier
    design_id: Identifier
    setup_id: Identifier | None = None
    origin: ResultOrigin
    metric: NonEmptyString
    conditions: list[ReportedCondition] = Field(default_factory=list)
    representation: ResultRepresentation
    evidence_ids: list[Identifier] = Field(min_length=1)
    uncertainty_note: NonEmptyString | None = None


ReferenceKind = Literal[
    "design",
    "setup",
    "result",
    "evidence",
    "material_observation",
    "parameter_observation",
    "geometry_observation",
    "feed_port_excitation_observation",
    "derivation",
    "conflict",
    "missing_information",
]


class EntityReference(ContractModel):
    kind: ReferenceKind
    id: Identifier


class ConflictRecord(ContractModel):
    conflict_id: Identifier
    description: NonEmptyString
    related_refs: list[EntityReference] = Field(min_length=2)
    evidence_ids: list[Identifier] = Field(default_factory=list)


class MissingInformationRecord(ContractModel):
    missing_information_id: Identifier
    description: NonEmptyString
    related_refs: list[EntityReference] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(default_factory=list)


class ResultsProvenance(ContractModel):
    source_extraction_schema_version: Literal["1.0.0"]
    source_extraction_checksum: NonEmptyString
    generated_at: datetime


class ResultsStatus(ContractModel):
    structural_status: Literal["valid", "invalid"]
    publication_status: Literal["complete_from_extraction", "blocked"]
    scientific_review_status: Literal["not_reviewed", "passed", "failed"]


def ensure_unique_ids(
    items: list[ContractModel],
    attribute: str,
    collection_name: str,
) -> set[str]:
    identifiers = [getattr(item, attribute) for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"duplicate IDs in {collection_name}")
    return set(identifiers)


def validate_shared_references(
    *,
    pages: list[PageRecord],
    evidence: list[EvidenceRecord],
    designs: list[DesignRecord],
    setups: list[Setup],
    results: list[ResultRecord],
    conflicts: list[ConflictRecord],
    missing_information: list[MissingInformationRecord],
    additional_ids: dict[str, set[str]] | None = None,
) -> dict[str, set[str]]:
    page_numbers = [page.page_number for page in pages]
    if len(page_numbers) != len(set(page_numbers)):
        raise ValueError("duplicate page numbers")
    declared_pages = set(page_numbers)

    evidence_ids = ensure_unique_ids(evidence, "evidence_id", "evidence catalog")
    design_ids = ensure_unique_ids(designs, "design_id", "design registry")
    setup_ids = ensure_unique_ids(setups, "setup_id", "setups")
    result_ids = ensure_unique_ids(results, "result_id", "results")
    conflict_ids = ensure_unique_ids(conflicts, "conflict_id", "conflicts")
    missing_ids = ensure_unique_ids(
        missing_information,
        "missing_information_id",
        "missing information",
    )

    for item in evidence:
        if item.page_number not in declared_pages:
            raise ValueError(
                f"evidence {item.evidence_id!r} references undeclared page "
                f"{item.page_number}"
            )

    for design in designs:
        for relation_name, related_id in (
            ("parent", design.parent_design_id),
            ("predecessor", design.predecessor_design_id),
        ):
            if related_id is not None and related_id not in design_ids:
                raise ValueError(
                    f"design {design.design_id!r} has unknown {relation_name} "
                    f"design {related_id!r}"
                )
        _ensure_known_ids(design.evidence_ids, evidence_ids, "evidence")

    setup_by_id = {setup.setup_id: setup for setup in setups}
    for setup in setups:
        _ensure_known_ids(setup.evidence_ids, evidence_ids, "evidence")

    compatible_setup_kind = {
        "simulated": "simulation",
        "measured": "measurement",
        "analytical": "analytical",
    }
    for result in results:
        if result.design_id not in design_ids:
            raise ValueError(
                f"result {result.result_id!r} references unknown design "
                f"{result.design_id!r}"
            )
        if result.setup_id is not None:
            setup = setup_by_id.get(result.setup_id)
            if setup is None:
                raise ValueError(
                    f"result {result.result_id!r} references unknown setup "
                    f"{result.setup_id!r}"
                )
            expected_setup_kind = compatible_setup_kind.get(result.origin)
            if expected_setup_kind is not None and setup.kind != expected_setup_kind:
                raise ValueError(
                    f"result origin {result.origin!r} is incompatible with "
                    f"setup kind {setup.kind!r}"
                )
        _ensure_known_ids(result.evidence_ids, evidence_ids, "evidence")
        if isinstance(result.representation, ImageOnlyGraphRepresentation):
            _ensure_known_ids(
                result.representation.evidence_ids,
                evidence_ids,
                "evidence",
            )
        if isinstance(result.representation, SpatialMapRepresentation) and isinstance(
            result.representation.content,
            ImageOnlySpatialMapContent,
        ):
            _ensure_known_ids(
                result.representation.content.evidence_ids,
                evidence_ids,
                "evidence",
            )

    reference_index: dict[str, set[str]] = {
        "design": design_ids,
        "setup": setup_ids,
        "result": result_ids,
        "evidence": evidence_ids,
        "conflict": conflict_ids,
        "missing_information": missing_ids,
    }
    reference_index.update(additional_ids or {})

    for item in [*conflicts, *missing_information]:
        _ensure_known_ids(item.evidence_ids, evidence_ids, "evidence")
        for reference in item.related_refs:
            known_ids = reference_index.get(reference.kind, set())
            if reference.id not in known_ids:
                raise ValueError(f"unknown {reference.kind} reference {reference.id!r}")
    return reference_index


def _ensure_known_ids(
    referenced_ids: list[str],
    known_ids: set[str],
    reference_name: str,
) -> None:
    unknown = set(referenced_ids) - known_ids
    if unknown:
        rendered = ", ".join(sorted(repr(item) for item in unknown))
        raise ValueError(f"unknown {reference_name} reference(s): {rendered}")
