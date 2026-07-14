from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from antenna_ingest.orchestration.schemas import StrictModel


ScalarValue = str | int | float | bool
FactValue = ScalarValue | list[ScalarValue]

ID_PATTERN = r"^[a-z][a-z0-9_]*$"


class CanonicalFact(StrictModel):
    name: str
    symbol: str | None = None
    raw_value: str | None = None
    value: FactValue | None = None
    unit: str | None = None
    evidence_ids: list[str] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)


class Coordinate3D(StrictModel):
    x: ScalarValue | None = None
    y: ScalarValue | None = None
    z: ScalarValue | None = None
    unit: str | None = None

    @model_validator(mode="after")
    def require_coordinate(self) -> Coordinate3D:
        if self.x is None and self.y is None and self.z is None:
            raise ValueError("at least one coordinate must be populated")
        return self


class GeometryPoint(StrictModel):
    label: str | None = None
    role: str | None = None
    position: Coordinate3D


class Placement(StrictModel):
    reference_object_id: str | None = Field(default=None, pattern=ID_PATTERN)
    position: Coordinate3D | None = None
    orientation: Coordinate3D | None = None
    orientation_type: str | None = None
    description: str | None = None
    evidence_ids: list[str] = Field(min_length=1)


class CanonicalGeometry(StrictModel):
    representation: str | None = None
    geometry_type: str | None = None
    description: str | None = None
    parameters: list[CanonicalFact] = Field(default_factory=list)
    control_points: list[GeometryPoint] = Field(default_factory=list)
    placement: Placement | None = None
    evidence_ids: list[str] = Field(min_length=1)


class CanonicalCoordinateSystem(StrictModel):
    name: str
    length_unit: str | None = None
    origin_description: str | None = None
    axes_description: str | None = None
    evidence_ids: list[str] = Field(min_length=1)


class CanonicalMaterial(StrictModel):
    material_id: str = Field(pattern=ID_PATTERN)
    name: str | None = None
    role: str | None = None
    properties: list[CanonicalFact] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)


class CanonicalObject(StrictModel):
    object_id: str = Field(pattern=ID_PATTERN)
    label: str | None = None
    role: str
    physical_form: Literal[
        "solid",
        "sheet",
        "wire",
        "void",
        "surface",
        "unknown",
    ] = "unknown"
    material_id: str | None = Field(default=None, pattern=ID_PATTERN)
    geometry: CanonicalGeometry | None = None
    properties: list[CanonicalFact] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)


class CanonicalRelationship(StrictModel):
    subject_id: str = Field(pattern=ID_PATTERN)
    relation: str
    object_id: str = Field(pattern=ID_PATTERN)
    description: str | None = None
    parameters: list[CanonicalFact] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)


class CanonicalExcitation(StrictModel):
    excitation_id: str = Field(pattern=ID_PATTERN)
    excitation_type: str
    target_object_ids: list[str] = Field(default_factory=list)
    description: str | None = None
    properties: list[CanonicalFact] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)


class CanonicalSimulationSetup(StrictModel):
    software: str | None = None
    solver: str | None = None
    properties: list[CanonicalFact] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)


class CanonicalResult(StrictModel):
    metric: str
    result_source: Literal["simulated", "measured", "both", "unknown"]
    raw_value: str | None = None
    value: FactValue | None = None
    unit: str | None = None
    condition: str | None = None
    evidence_ids: list[str] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)


class ExcludedVariant(StrictModel):
    variant_id: str = Field(pattern=ID_PATTERN)
    label: str | None = None
    role: str | None = None
    reason_excluded: str
    evidence_ids: list[str] = Field(min_length=1)


class ConflictOption(StrictModel):
    raw_value: str
    evidence_ids: list[str] = Field(min_length=1)


class CanonicalConflict(StrictModel):
    field: str
    options: list[ConflictOption] = Field(min_length=2)
    status: Literal["resolved", "unresolved"]
    selected_value: str | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def validate_selected_value(self) -> CanonicalConflict:
        if self.status == "resolved" and self.selected_value is None:
            raise ValueError("resolved conflicts require selected_value")
        if self.status == "unresolved" and self.selected_value is not None:
            raise ValueError("unresolved conflicts must not contain selected_value")
        return self


class CanonicalMissingInformation(StrictModel):
    field: str
    severity: Literal["critical", "major", "minor"]
    reason: str
    related_object_ids: list[str] = Field(default_factory=list)


class CanonicalDesignIdentity(StrictModel):
    design_label: str | None = None
    antenna_type: str | None = None
    description: str | None = None
    selection_reason: str
    evidence_ids: list[str] = Field(min_length=1)


class CanonicalDesignRecord(StrictModel):
    schema_name: Literal["canonical_design_record_v1"] = (
        "canonical_design_record_v1"
    )
    paper_id: str | None = None
    design: CanonicalDesignIdentity
    reconstruction_status: Literal[
        "buildable",
        "partially_buildable",
        "not_buildable_from_paper",
        "unknown",
    ]
    coordinate_system: CanonicalCoordinateSystem | None = None
    materials: list[CanonicalMaterial] = Field(default_factory=list)
    objects: list[CanonicalObject] = Field(default_factory=list)
    relationships: list[CanonicalRelationship] = Field(default_factory=list)
    excitations: list[CanonicalExcitation] = Field(default_factory=list)
    simulation_setup: CanonicalSimulationSetup | None = None
    reported_results: list[CanonicalResult] = Field(default_factory=list)
    excluded_variants: list[ExcludedVariant] = Field(default_factory=list)
    conflicts: list[CanonicalConflict] = Field(default_factory=list)
    missing_information: list[CanonicalMissingInformation] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_architecture_references(self) -> CanonicalDesignRecord:
        material_ids = [material.material_id for material in self.materials]
        object_ids = [obj.object_id for obj in self.objects]
        excitation_ids = [item.excitation_id for item in self.excitations]
        variant_ids = [variant.variant_id for variant in self.excluded_variants]

        _require_unique(material_ids, "material_id")
        _require_unique(object_ids, "object_id")
        _require_unique(excitation_ids, "excitation_id")
        _require_unique(variant_ids, "variant_id")

        known_material_ids = set(material_ids)
        known_object_ids = set(object_ids)
        for obj in self.objects:
            if obj.material_id is not None:
                _require_reference(
                    obj.material_id,
                    known_material_ids,
                    f"object {obj.object_id} material_id",
                )
            if obj.geometry and obj.geometry.placement:
                reference_id = obj.geometry.placement.reference_object_id
                if reference_id is not None:
                    _require_reference(
                        reference_id,
                        known_object_ids,
                        f"object {obj.object_id} placement reference_object_id",
                    )

        for relationship in self.relationships:
            _require_reference(
                relationship.subject_id,
                known_object_ids,
                "relationship subject_id",
            )
            _require_reference(
                relationship.object_id,
                known_object_ids,
                "relationship object_id",
            )

        for excitation in self.excitations:
            for target_id in excitation.target_object_ids:
                _require_reference(
                    target_id,
                    known_object_ids,
                    f"excitation {excitation.excitation_id} target_object_ids",
                )

        for missing in self.missing_information:
            for related_id in missing.related_object_ids:
                _require_reference(
                    related_id,
                    known_object_ids,
                    f"missing information {missing.field} related_object_ids",
                )
        return self


def _require_unique(values: list[str], field_name: str) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        joined = ", ".join(duplicates)
        raise ValueError(f"duplicate {field_name} values: {joined}")


def _require_reference(value: str, known_ids: set[str], field_name: str) -> None:
    if value not in known_ids:
        raise ValueError(f"{field_name} references unknown object or material: {value}")
