from __future__ import annotations

from collections.abc import Iterator
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
ResultOrigin = Literal["simulated", "measured", "analytical"]
ExtractionCompleteness = Literal[
    "complete",
    "partial_numeric",
    "illegible",
    "missing",
]
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
    value: NonEmptyString | None = Field(
        description=(
            "Exact value lexeme preserved from the source. "
            "It must be non-null when legibility is clear or uncertain, "
            "and null only when legibility is missing or illegible."
        )
    )
    unit: NonEmptyString | None = None
    qualifier: NonEmptyString | None = None
    legibility: LegibilityState = Field(
        description=(
            "Explicit source-value legibility. "
            "Use clear or uncertain with a non-null value. "
            "Use missing or illegible with a null value."
        )
    )

    @model_validator(mode="after")
    def validate_value_and_legibility(self) -> SourceValue:
        if self.value is None and self.legibility in {"clear", "uncertain"}:
            raise ValueError(
                "a clear or uncertain source value must preserve its lexeme"
            )
        if self.value is not None and self.legibility in {"missing", "illegible"}:
            raise ValueError(
                "a missing or illegible source value cannot contain a value lexeme"
            )
        return self


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
    evidence_ids: list[Identifier] = Field(default_factory=list)


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

class IntervalEndpointValue(SourceValue):
    value: NonEmptyString = Field(
        description=(
            "Exact non-null endpoint lexeme explicitly reported by the source."
        )
    )
    legibility: Literal["clear", "uncertain"] = Field(
        description=(
            "Endpoint legibility. An interval endpoint must be clear or uncertain."
        )
    )

class IntervalRepresentation(ContractModel):
    """A source-reported range with two explicit endpoints."""

    kind: Literal["interval"]
    lower: IntervalEndpointValue = Field(
        description=(
            "Exact lower endpoint explicitly reported by the source. "
            "Do not derive it from a center value and range width."
        )
    )
    upper: IntervalEndpointValue = Field(
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


class SampledFieldMapContent(ContractModel):
    kind: Literal["sampled"]
    coordinate_description: NonEmptyString
    samples: list[ReportedPoint] = Field(min_length=1)


class ImageOnlyFieldMapContent(ContractModel):
    kind: Literal["image_only"]
    map_type_or_component: NonEmptyString | None = None
    plane_or_cut: NonEmptyString | None = None
    legend_or_scale_label: NonEmptyString | None = None
    annotated_points: list[ReportedPoint] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(min_length=1)


FieldMapContent = Annotated[
    SampledFieldMapContent | ImageOnlyFieldMapContent,
    Field(discriminator="kind"),
]


class FieldMapRepresentation(ContractModel):
    kind: Literal["field_map"]
    field_or_current: Literal["field", "current"]
    quantity: NonEmptyString
    content: FieldMapContent


class ImageOnlyGraphRepresentation(ContractModel):
    kind: Literal["image_only"]
    axes: list[AxisDescriptor] = Field(default_factory=list)
    trace_labels: list[NonEmptyString] = Field(default_factory=list)
    annotated_points: list[ReportedPoint] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(min_length=1)


class QualitativeRepresentation(ContractModel):
    kind: Literal["qualitative"]
    observation: NonEmptyString


ResultRepresentation = Annotated[
    ScalarRepresentation
    | IntervalRepresentation
    | PointCollectionRepresentation
    | SampledSeriesRepresentation
    | MatrixRepresentation
    | AngularPatternRepresentation
    | FieldMapRepresentation
    | ImageOnlyGraphRepresentation
    | QualitativeRepresentation,
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
    legibility: LegibilityState = "clear"
    uncertainty_note: NonEmptyString | None = None
    extraction_completeness: ExtractionCompleteness = "complete"

    @model_validator(mode="after")
    def validate_representation_completeness(self) -> ResultRecord:
        kind = self.representation.kind
        if self.extraction_completeness == "partial_numeric" and kind not in {
            "sampled_series",
            "angular_pattern",
        }:
            raise ValueError(
                "partial_numeric is supported only for sampled series and angular patterns"
            )
        if self.extraction_completeness in {"missing", "illegible"}:
            if self.legibility != self.extraction_completeness:
                raise ValueError(
                    "missing and illegible results require the matching legibility state"
                )
        if self.legibility in {"missing", "illegible"}:
            if self.extraction_completeness != self.legibility:
                raise ValueError(
                    "missing and illegible legibility requires matching completeness"
                )

        source_values = list(_iter_source_values(self.representation))
        unavailable_states = {"missing", "illegible"}
        if self.extraction_completeness in {"complete", "partial_numeric"}:
            if any(value.legibility in unavailable_states for value in source_values):
                raise ValueError(
                    "complete and partial_numeric results cannot contain missing "
                    "or illegible source values"
                )
        if self.extraction_completeness in {"missing", "illegible"}:
            expected_state = self.extraction_completeness
            if not source_values or any(
                value.legibility != expected_state for value in source_values
            ):
                raise ValueError(
                    f"a {expected_state} result requires every source value to be "
                    f"{expected_state}"
                )
        return self


def _iter_source_values(value: object) -> Iterator[SourceValue]:
    if isinstance(value, SourceValue):
        yield value
        return
    if isinstance(value, ContractModel):
        for field_name in type(value).model_fields:
            yield from _iter_source_values(getattr(value, field_name))
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_source_values(item)


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
            if setup.kind != compatible_setup_kind[result.origin]:
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
        if isinstance(result.representation, FieldMapRepresentation) and isinstance(
            result.representation.content,
            ImageOnlyFieldMapContent,
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
                raise ValueError(
                    f"unknown {reference.kind} reference {reference.id!r}"
                )
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
