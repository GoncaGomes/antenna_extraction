from __future__ import annotations

import json
from typing import Literal

from numind.nuextract_utils import convert_json_schema_to_nuextract_template
from pydantic import Field, model_validator

from antenna_ingest.contracts.base import ContractModel
from antenna_ingest.contracts.common import (
    AngularPoint,
    AxisDescriptor,
    BoundingRegion,
    DesignRole,
    DocumentReference,
    EvidenceRecord,
    EvidenceSourceKind,
    Identifier,
    LegibilityState,
    NonEmptyString,
    PageRecord,
    ReportedCondition,
    ReportedPoint,
    ResultOrigin,
    SeriesPoint,
    SourceValue,
)
from antenna_ingest.contracts.paper_extraction import PaperExtraction


class InlineEvidence(ContractModel):
    page_number: int = Field(ge=1)
    source_kind: EvidenceSourceKind
    excerpt_or_description: NonEmptyString
    source_label: NonEmptyString | None = None
    bounding_region: BoundingRegion | None = None
    legibility_note: NonEmptyString | None = None


class NuExtractDocumentMetadata(ContractModel):
    title: NonEmptyString | None = None
    doi: NonEmptyString | None = None


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


class NuExtractSetupRecord(ContractModel):
    setup_id: Identifier
    description: NonEmptyString
    evidence: list[InlineEvidence] = Field(min_length=1)
    legibility: LegibilityState = "clear"
    uncertainty_note: NonEmptyString | None = None
    kind: Literal["simulation", "measurement", "analytical"]
    software: NonEmptyString | None = None
    solver_or_method: NonEmptyString | None = None
    model: NonEmptyString | None = None
    conditions: list[ReportedCondition] = Field(default_factory=list)
    equipment: list[NonEmptyString] = Field(default_factory=list)
    calibration: NonEmptyString | None = None
    fixture: NonEmptyString | None = None
    environment: NonEmptyString | None = None
    method: NonEmptyString | None = None
    assumptions: list[NonEmptyString] = Field(default_factory=list)


class NuExtractObservationRecord(ContractModel):
    observation_id: Identifier
    design_id: Identifier | None = None
    description: NonEmptyString
    evidence: list[InlineEvidence] = Field(min_length=1)
    legibility: LegibilityState = "clear"
    uncertainty_note: NonEmptyString | None = None
    kind: Literal[
        "material",
        "parameter",
        "geometry",
        "feed",
        "port",
        "excitation",
    ]
    material_name: NonEmptyString | None = None
    reported_properties: list[ReportedCondition] = Field(default_factory=list)
    symbol: NonEmptyString | None = None
    reported_value: SourceValue | None = None
    source_feature_label: NonEmptyString | None = None
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
    evidence: list[InlineEvidence] = Field(default_factory=list)


class NuExtractResultRepresentation(ContractModel):
    kind: Literal[
        "scalar",
        "interval",
        "point_collection",
        "sampled_series",
        "matrix",
        "sampled_angular_pattern",
        "sampled_spatial_map",
        "image_spatial_map",
        "image_only",
        "qualitative",
        "unavailable",
    ]

    scalar_value: SourceValue | None = None
    interval_lower: SourceValue | None = None
    interval_upper: SourceValue | None = None
    collection_points: list[ReportedPoint] = Field(default_factory=list)
    series_x_axis: AxisDescriptor | None = None
    series_y_axis: AxisDescriptor | None = None
    series_trace_label: NonEmptyString | None = None
    series_points: list[SeriesPoint] = Field(default_factory=list)
    matrix_rows: list[list[SourceValue]] = Field(default_factory=list)
    matrix_row_labels: list[NonEmptyString] = Field(default_factory=list)
    matrix_column_labels: list[NonEmptyString] = Field(default_factory=list)
    angular_coordinate: NonEmptyString | None = None
    angular_unit: NonEmptyString | None = None
    angular_plane_or_cut: NonEmptyString | None = None
    angular_fixed_angle: SourceValue | None = None
    angular_component_or_polarization: NonEmptyString | None = None
    angular_radial_quantity: NonEmptyString | None = None
    angular_points: list[AngularPoint] = Field(default_factory=list)
    spatial_quantity: NonEmptyString | None = None
    spatial_coordinate_description: NonEmptyString | None = None
    spatial_samples: list[ReportedPoint] = Field(default_factory=list)
    spatial_map_type_or_component: NonEmptyString | None = None
    spatial_plane_or_cut: NonEmptyString | None = None
    spatial_legend_or_scale_label: NonEmptyString | None = None
    spatial_annotated_points: list[ReportedPoint] = Field(default_factory=list)
    image_axes: list[AxisDescriptor] = Field(default_factory=list)
    image_trace_labels: list[NonEmptyString] = Field(default_factory=list)
    image_annotated_points: list[ReportedPoint] = Field(default_factory=list)
    qualitative_observation: NonEmptyString | None = None
    unavailable_reason: (
        Literal[
            "not_reported",
            "illegible",
            "ambiguous",
        ]
        | None
    ) = None
    unavailable_description: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_selected_representation(self) -> NuExtractResultRepresentation:
        self._validate_required_fields()
        return self

    def _validate_required_fields(self) -> None:
        required_values: dict[str, tuple[object, ...]] = {
            "scalar": (self.scalar_value,),
            "interval": (self.interval_lower, self.interval_upper),
            "point_collection": (self.collection_points,),
            "sampled_series": (
                self.series_x_axis,
                self.series_y_axis,
                self.series_points,
            ),
            "matrix": (self.matrix_rows,),
            "sampled_angular_pattern": (
                self.angular_coordinate,
                self.angular_radial_quantity,
                self.angular_points,
            ),
            "sampled_spatial_map": (
                self.spatial_quantity,
                self.spatial_coordinate_description,
                self.spatial_samples,
            ),
            "image_spatial_map": (self.spatial_quantity,),
            "image_only": (),
            "qualitative": (self.qualitative_observation,),
            "unavailable": (
                self.unavailable_reason,
                self.unavailable_description,
            ),
        }
        if any(not _is_populated(value) for value in required_values[self.kind]):
            raise ValueError(f"required fields are missing for {self.kind!r}")
        if self.kind == "matrix" and any(not row for row in self.matrix_rows):
            raise ValueError("matrix rows must be non-empty")


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
    document: NuExtractDocumentMetadata
    designs: list[NuExtractDesignRecord]
    observations: list[NuExtractObservationRecord]
    setups: list[NuExtractSetupRecord]
    results: list[NuExtractResultRecord]
    derivations: list[NuExtractReportedDerivation]
    conflicts: list[NuExtractConflictRecord]
    missing_information: list[NuExtractMissingInformationRecord]


def build_nuextract_template() -> dict:
    schema = NuExtractPaperExtraction.model_json_schema(mode="validation")
    template, dropped_branches, _descriptions = (
        convert_json_schema_to_nuextract_template(schema)
    )
    if dropped_branches:
        raise ValueError(
            "NuExtract template conversion dropped schema branches: "
            + json.dumps(dropped_branches, ensure_ascii=False, sort_keys=True)
        )
    if not isinstance(template, dict):
        raise TypeError("NuExtract template must be a JSON object")
    return template


def _is_populated(value: object) -> bool:
    return value is not None and value != []


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
    *,
    document: DocumentReference,
    pages: list[PageRecord],
) -> PaperExtraction:
    """Normalize inline evidence in deterministic top-level collection order.

    Evidence is visited through designs, observations, setups, results,
    derivations, conflicts, then missing_information.
    """
    catalog = _EvidenceCatalogBuilder()

    designs = [
        _record_with_evidence(record, record.evidence, catalog)
        for record in extraction.designs
    ]
    material_observations: list[dict] = []
    parameter_observations: list[dict] = []
    geometry_observations: list[dict] = []
    feed_observations: list[dict] = []
    for observation in extraction.observations:
        kind, data = _normalize_observation(observation, catalog)
        if kind == "material":
            material_observations.append(data)
        elif kind == "parameter":
            parameter_observations.append(data)
        elif kind == "geometry":
            geometry_observations.append(data)
        else:
            data["observation_kind"] = kind
            feed_observations.append(data)
    setups = [_normalize_setup(record, catalog) for record in extraction.setups]
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
    architecture_page_refs = sorted(
        {
            evidence.page_number
            for record in [
                *extraction.designs,
                *extraction.observations,
                *extraction.derivations,
            ]
            for evidence in record.evidence
        }
    )

    return PaperExtraction.model_validate(
        {
            "schema_name": "paper_extraction",
            "schema_version": "1.0.0",
            "document": document.model_dump(mode="json"),
            "pages": [page.model_dump(mode="json") for page in pages],
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
            "architecture_page_refs": architecture_page_refs,
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


def _normalize_observation(
    observation: NuExtractObservationRecord,
    catalog: _EvidenceCatalogBuilder,
) -> tuple[str, dict]:
    data = _record_with_evidence(observation, observation.evidence, catalog)
    kind = data.pop("kind")
    common_fields = {
        "observation_id",
        "design_id",
        "description",
        "evidence_ids",
        "legibility",
        "uncertainty_note",
    }
    active_fields = {
        "material": {"material_name", "reported_properties"},
        "parameter": {"symbol", "reported_value"},
        "geometry": {"source_feature_label"},
        "feed": {"reported_impedance"},
        "port": {"reported_impedance"},
        "excitation": {"reported_impedance"},
    }[kind]
    return kind, {
        field: value
        for field, value in data.items()
        if field in common_fields | active_fields
    }


def _normalize_setup(
    setup: NuExtractSetupRecord,
    catalog: _EvidenceCatalogBuilder,
) -> dict:
    data = _record_with_evidence(setup, setup.evidence, catalog)
    common_fields = {
        "setup_id",
        "description",
        "evidence_ids",
        "legibility",
        "uncertainty_note",
        "kind",
    }
    active_fields = {
        "simulation": {"software", "solver_or_method", "model", "conditions"},
        "measurement": {"equipment", "calibration", "fixture", "environment"},
        "analytical": {"method", "assumptions"},
    }[setup.kind]
    return {
        field: value
        for field, value in data.items()
        if field in common_fields | active_fields
    }


def _normalize_result(
    result: NuExtractResultRecord,
    catalog: _EvidenceCatalogBuilder,
) -> dict:
    data = _record_with_evidence(result, result.evidence, catalog)
    data["representation"] = _normalize_result_representation(
        result.representation,
        evidence_ids=list(data["evidence_ids"]),
    )
    return data


def _normalize_result_representation(
    representation: NuExtractResultRepresentation,
    *,
    evidence_ids: list[str],
) -> dict:
    data = representation.model_dump(mode="json")
    kind = representation.kind
    if kind == "scalar":
        return {"kind": kind, "value": data["scalar_value"]}
    if kind == "interval":
        return {
            "kind": kind,
            "lower": data["interval_lower"],
            "upper": data["interval_upper"],
        }
    if kind == "point_collection":
        return {"kind": kind, "points": data["collection_points"]}
    if kind == "sampled_series":
        return {
            "kind": kind,
            "x_axis": data["series_x_axis"],
            "y_axis": data["series_y_axis"],
            "trace_label": data["series_trace_label"],
            "points": data["series_points"],
        }
    if kind == "matrix":
        return {
            "kind": kind,
            "rows": data["matrix_rows"],
            "row_labels": data["matrix_row_labels"],
            "column_labels": data["matrix_column_labels"],
        }
    if kind == "sampled_angular_pattern":
        return {
            "kind": "angular_pattern",
            "angular_coordinate": data["angular_coordinate"],
            "angular_unit": data["angular_unit"],
            "plane_or_cut": data["angular_plane_or_cut"],
            "fixed_angle": data["angular_fixed_angle"],
            "component_or_polarization": data["angular_component_or_polarization"],
            "radial_quantity": data["angular_radial_quantity"],
            "points": data["angular_points"],
        }
    if kind == "sampled_spatial_map":
        return {
            "kind": "spatial_map",
            "quantity": data["spatial_quantity"],
            "content": {
                "kind": "sampled",
                "coordinate_description": data["spatial_coordinate_description"],
                "samples": data["spatial_samples"],
            },
        }
    if kind == "image_spatial_map":
        return {
            "kind": "spatial_map",
            "quantity": data["spatial_quantity"],
            "content": {
                "kind": "image_only",
                "map_type_or_component": data["spatial_map_type_or_component"],
                "plane_or_cut": data["spatial_plane_or_cut"],
                "legend_or_scale_label": data["spatial_legend_or_scale_label"],
                "annotated_points": data["spatial_annotated_points"],
                "evidence_ids": list(evidence_ids),
            },
        }
    if kind == "image_only":
        return {
            "kind": kind,
            "axes": data["image_axes"],
            "trace_labels": data["image_trace_labels"],
            "annotated_points": data["image_annotated_points"],
            "evidence_ids": list(evidence_ids),
        }
    if kind == "qualitative":
        return {"kind": kind, "observation": data["qualitative_observation"]}
    return {
        "kind": kind,
        "reason": data["unavailable_reason"],
        "description": data["unavailable_description"],
    }
