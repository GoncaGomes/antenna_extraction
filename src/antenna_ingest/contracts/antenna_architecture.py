from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from antenna_ingest.contracts.base import ContractModel
from antenna_ingest.contracts.common import (
    DocumentReference,
    Identifier,
    NonEmptyString,
    ReportedCondition,
    SourceValue,
    ensure_unique_ids,
)
from antenna_ingest.contracts.expressions import (
    QUANTITY_DIMENSIONS,
    ExpressionError,
    expression_dimension,
    expression_identifiers,
    validate_binding_name,
)


QuantityKind = Literal[
    "length",
    "angle",
    "frequency",
    "impedance",
    "dimensionless",
]
ReportedOrigin = Literal[
    "reported_text",
    "reported_table",
    "reported_equation",
    "reported_visual",
]


class ArchitectureElementReference(ContractModel):
    kind: Literal[
        "parameter",
        "material",
        "block",
        "relationship",
        "port_or_excitation",
        "frame",
        "derivation",
        "unresolved_item",
        "proposed_completion",
    ]
    id: Identifier


class SelectedDesign(ContractModel):
    design_id: Identifier
    role: Literal[
        "final",
        "fabricated",
        "measured_prototype",
        "selected_candidate",
    ]
    rationale: NonEmptyString
    selection_evidence_ids: list[Identifier] = Field(min_length=1)
    ambiguity_state: Literal["unambiguous", "ambiguous", "unresolved"]


class CoordinateSystem(ContractModel):
    kind: Literal["cartesian"]
    handedness: Literal["right_handed"]
    global_frame_id: Identifier
    rotation_representation: Literal["active_euler_xyz"]
    rotation_order: Literal["x_then_y_then_z"]
    rotation_composition: Literal["Rz(z) @ Ry(y) @ Rx(x)"]


class ZeroComponent(ContractModel):
    kind: Literal["zero"]


class ParameterComponent(ContractModel):
    kind: Literal["parameter"]
    parameter_id: Identifier


TransformComponent = Annotated[
    ZeroComponent | ParameterComponent,
    Field(discriminator="kind"),
]


class Vector3Components(ContractModel):
    x: TransformComponent
    y: TransformComponent
    z: TransformComponent


class EulerRotation(ContractModel):
    x: TransformComponent
    y: TransformComponent
    z: TransformComponent


class Transform(ContractModel):
    translation: Vector3Components
    rotation: EulerRotation


class FrameRecord(ContractModel):
    frame_id: Identifier
    name: NonEmptyString
    parent_frame_id: Identifier | None
    transform: Transform


class ParameterReference(ContractModel):
    parameter_id: Identifier


class ReportedParameterDefinition(ContractModel):
    kind: Literal["reported"]
    value: SourceValue
    origin: ReportedOrigin
    evidence_ids: list[Identifier] = Field(min_length=1)

    @model_validator(mode="after")
    def require_readable_value(self) -> ReportedParameterDefinition:
        if self.value.value is None or self.value.legibility in {"missing", "illegible"}:
            raise ValueError("a reported parameter requires a readable source value")
        return self


class DerivedParameterDefinition(ContractModel):
    kind: Literal["derived"]
    derivation_id: Identifier


class UnresolvedParameterDefinition(ContractModel):
    kind: Literal["unresolved"]
    unresolved_item_id: Identifier


ParameterDefinition = Annotated[
    ReportedParameterDefinition
    | DerivedParameterDefinition
    | UnresolvedParameterDefinition,
    Field(discriminator="kind"),
]


class ParameterRecord(ContractModel):
    parameter_id: Identifier
    name: NonEmptyString
    source_symbol: NonEmptyString | None = None
    quantity_kind: QuantityKind
    definition: ParameterDefinition
    affected_refs: list[ArchitectureElementReference] = Field(min_length=1)


AsciiBinding = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    ),
]


class ExpressionBinding(ContractModel):
    name: AsciiBinding
    parameter_id: Identifier

    @field_validator("name")
    @classmethod
    def validate_ascii_name(cls, value: str) -> str:
        try:
            return validate_binding_name(value)
        except ExpressionError as exc:
            raise ValueError(str(exc)) from exc


class DerivationRecord(ContractModel):
    derivation_id: Identifier
    target_parameter_id: Identifier
    expression: NonEmptyString
    bindings: list[ExpressionBinding]
    explanation: NonEmptyString
    evidence_ids: list[Identifier] = Field(min_length=1)


class MaterialPropertyClaim(ContractModel):
    property_claim_id: Identifier
    property_name: NonEmptyString
    value: SourceValue
    conditions: list[ReportedCondition] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(min_length=1)
    origin: ReportedOrigin


class MaterialRecord(ContractModel):
    material_id: Identifier
    reported_identity: NonEmptyString
    evidence_ids: list[Identifier] = Field(min_length=1)
    property_claims: list[MaterialPropertyClaim] = Field(default_factory=list)


class Point2D(ContractModel):
    x: TransformComponent
    y: TransformComponent


class Point3D(ContractModel):
    x: TransformComponent
    y: TransformComponent
    z: TransformComponent


class FramedPoint(ContractModel):
    frame_id: Identifier
    coordinates: Point3D


class LineSegment2D(ContractModel):
    kind: Literal["line_segment"]
    start: Point2D
    end: Point2D

    @model_validator(mode="after")
    def require_distinct_endpoints(self) -> LineSegment2D:
        if self.start == self.end:
            raise ValueError("line segment endpoints must be distinct")
        return self


class CircularArc2D(ContractModel):
    kind: Literal["circular_arc"]
    start: Point2D
    end: Point2D
    center: Point2D
    direction: Literal["clockwise", "counterclockwise"]

    @model_validator(mode="after")
    def require_distinct_endpoints(self) -> CircularArc2D:
        if self.start == self.end:
            raise ValueError("circular arc endpoints must be distinct")
        if self.center == self.start or self.center == self.end:
            raise ValueError("circular arc center must differ from its endpoints")
        return self


ProfileSegment = Annotated[
    LineSegment2D | CircularArc2D,
    Field(discriminator="kind"),
]


class LineSegment3D(ContractModel):
    kind: Literal["line_segment"]
    start: Point3D
    end: Point3D

    @model_validator(mode="after")
    def require_distinct_endpoints(self) -> LineSegment3D:
        if self.start == self.end:
            raise ValueError("line segment endpoints must be distinct")
        return self


class CircularArc3D(ContractModel):
    kind: Literal["circular_arc"]
    start: Point3D
    end: Point3D
    center: Point3D
    plane_normal: Literal["x", "y", "z"]
    direction: Literal["clockwise", "counterclockwise"]

    @model_validator(mode="after")
    def require_distinct_endpoints(self) -> CircularArc3D:
        if self.start == self.end:
            raise ValueError("circular arc endpoints must be distinct")
        if self.center == self.start or self.center == self.end:
            raise ValueError("circular arc center must differ from its endpoints")
        return self


class HelixSegment3D(ContractModel):
    kind: Literal["helix_segment"]
    start: Point3D
    axis_point: Point3D
    axis_direction: Literal["x", "y", "z"]
    radius: ParameterReference
    pitch: ParameterReference
    turn_count: ParameterReference
    handedness: Literal["left_handed", "right_handed"]


PathSegment = Annotated[
    LineSegment3D | CircularArc3D | HelixSegment3D,
    Field(discriminator="kind"),
]


class AxisLine(ContractModel):
    point: Point3D
    direction: Literal["x", "y", "z"]


class RectangleGeometry(ContractModel):
    kind: Literal["rectangle"]
    width: ParameterReference
    height: ParameterReference


class CircleGeometry(ContractModel):
    kind: Literal["circle"]
    radius: ParameterReference


class EllipseGeometry(ContractModel):
    kind: Literal["ellipse"]
    major_radius: ParameterReference
    minor_radius: ParameterReference


class AnnulusGeometry(ContractModel):
    kind: Literal["annulus"]
    inner_radius: ParameterReference
    outer_radius: ParameterReference

    @model_validator(mode="after")
    def require_distinct_radii(self) -> AnnulusGeometry:
        if self.inner_radius == self.outer_radius:
            raise ValueError("annulus radii must reference distinct parameters")
        return self


class PolygonGeometry(ContractModel):
    kind: Literal["polygon"]
    vertices: list[Point2D] = Field(min_length=3)


class SegmentedProfileGeometry(ContractModel):
    kind: Literal["segmented_profile"]
    segments: list[ProfileSegment] = Field(min_length=2)

    @model_validator(mode="after")
    def require_closed_connected_profile(self) -> SegmentedProfileGeometry:
        for current, following in zip(
            self.segments,
            [*self.segments[1:], self.segments[0]],
            strict=True,
        ):
            if current.end != following.start:
                raise ValueError("segmented profile must be connected and closed")
        return self


class BoxGeometry(ContractModel):
    kind: Literal["box"]
    width: ParameterReference
    depth: ParameterReference
    height: ParameterReference


class CylinderGeometry(ContractModel):
    kind: Literal["cylinder"]
    radius: ParameterReference
    height: ParameterReference


class ConeGeometry(ContractModel):
    kind: Literal["cone"]
    base_radius: ParameterReference
    top_radius: ParameterReference
    height: ParameterReference


class SphereGeometry(ContractModel):
    kind: Literal["sphere"]
    radius: ParameterReference


class ExtrusionGeometry(ContractModel):
    kind: Literal["extrusion"]
    profile_block_id: Identifier
    distance: ParameterReference


class RevolutionGeometry(ContractModel):
    kind: Literal["revolution"]
    profile_block_id: Identifier
    axis: AxisLine
    angle: ParameterReference


class WirePathGeometry(ContractModel):
    kind: Literal["wire_path"]
    segments: list[PathSegment] = Field(min_length=1)

    @model_validator(mode="after")
    def require_connected_segments(self) -> WirePathGeometry:
        for current, following in zip(
            self.segments,
            self.segments[1:],
            strict=False,
        ):
            if isinstance(current, HelixSegment3D) or current.end != following.start:
                raise ValueError("wire-path segments must be connected in order")
        return self


class SweepGeometry(ContractModel):
    kind: Literal["sweep"]
    profile_block_id: Identifier
    path_block_id: Identifier


Checksum = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-fA-F]{64}$"),
]


class ExternalGeometryAsset(ContractModel):
    asset_ref: NonEmptyString
    format: NonEmptyString
    source_length_unit: NonEmptyString | None = None
    availability: Literal[
        "locally_available",
        "externally_referenced",
        "unavailable",
    ]
    sha256: Checksum | None = None
    evidence_ids: list[Identifier] = Field(min_length=1)

    @model_validator(mode="after")
    def require_checksum_for_local_asset(self) -> ExternalGeometryAsset:
        if self.availability == "locally_available" and self.sha256 is None:
            raise ValueError("a locally available asset requires a SHA-256 checksum")
        return self


class SurfaceGeometry(ContractModel):
    kind: Literal["surface"]
    asset: ExternalGeometryAsset


class MeshGeometry(ContractModel):
    kind: Literal["mesh"]
    asset: ExternalGeometryAsset


class InstanceGeometry(ContractModel):
    kind: Literal["instance"]
    prototype_block_id: Identifier


class UnresolvedGeometry(ContractModel):
    kind: Literal["unresolved"]
    unresolved_item_id: Identifier


class RelationshipResultGeometry(ContractModel):
    kind: Literal["relationship_result"]
    relationship_id: Identifier


Geometry = Annotated[
    RectangleGeometry
    | CircleGeometry
    | EllipseGeometry
    | AnnulusGeometry
    | PolygonGeometry
    | SegmentedProfileGeometry
    | BoxGeometry
    | CylinderGeometry
    | ConeGeometry
    | SphereGeometry
    | ExtrusionGeometry
    | RevolutionGeometry
    | WirePathGeometry
    | SweepGeometry
    | SurfaceGeometry
    | MeshGeometry
    | InstanceGeometry
    | UnresolvedGeometry
    | RelationshipResultGeometry,
    Field(discriminator="kind"),
]


BlockRole = Literal[
    "radiator",
    "ground",
    "feed",
    "substrate",
    "dielectric",
    "conductor",
    "slot_tool",
    "via",
    "shorting_element",
    "environmental_layer",
    "port_region",
    "array_element",
    "other",
]


class BlockRecord(ContractModel):
    block_id: Identifier
    name: NonEmptyString
    role: BlockRole
    state: Literal["physical", "auxiliary", "instance", "unresolved"]
    material_id: Identifier | None = None
    geometry: Geometry
    placement: Transform
    parameter_dependencies: list[Identifier] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(min_length=1)
    derivation_ids: list[Identifier] = Field(default_factory=list)
    unresolved_item_ids: list[Identifier] = Field(default_factory=list)


class SubtractRelationship(ContractModel):
    relationship_id: Identifier
    kind: Literal["subtract"]
    target_block_id: Identifier
    tool_block_ids: list[Identifier] = Field(min_length=1)
    result_block_id: Identifier
    evidence_ids: list[Identifier] = Field(min_length=1)


class UniteRelationship(ContractModel):
    relationship_id: Identifier
    kind: Literal["unite"]
    operand_block_ids: list[Identifier] = Field(min_length=2)
    result_block_id: Identifier
    evidence_ids: list[Identifier] = Field(min_length=1)


class IntersectRelationship(ContractModel):
    relationship_id: Identifier
    kind: Literal["intersect"]
    operand_block_ids: list[Identifier] = Field(min_length=2)
    result_block_id: Identifier
    evidence_ids: list[Identifier] = Field(min_length=1)


class ContactRelationship(ContractModel):
    relationship_id: Identifier
    kind: Literal["contact"]
    subject_block_id: Identifier
    reference_block_id: Identifier
    evidence_ids: list[Identifier] = Field(min_length=1)


class ContainedInRelationship(ContractModel):
    relationship_id: Identifier
    kind: Literal["contained_in"]
    inner_block_id: Identifier
    container_block_id: Identifier
    evidence_ids: list[Identifier] = Field(min_length=1)


class AxisAlignment(ContractModel):
    axis: Literal["x", "y", "z"]
    subject_anchor: Literal["min", "center", "max"]
    reference_anchor: Literal["min", "center", "max"]


class AlignedWithRelationship(ContractModel):
    relationship_id: Identifier
    kind: Literal["aligned_with"]
    subject_block_id: Identifier
    reference_block_id: Identifier
    alignments: list[AxisAlignment] = Field(min_length=1)
    evidence_ids: list[Identifier] = Field(min_length=1)


class PatternInstanceRelationship(ContractModel):
    relationship_id: Identifier
    kind: Literal["pattern_instance"]
    prototype_block_id: Identifier
    instance_block_ids: list[Identifier] = Field(min_length=1)
    evidence_ids: list[Identifier] = Field(min_length=1)


Relationship = Annotated[
    SubtractRelationship
    | UniteRelationship
    | IntersectRelationship
    | ContactRelationship
    | ContainedInRelationship
    | AlignedWithRelationship
    | PatternInstanceRelationship,
    Field(discriminator="kind"),
]


class PointAnchor(ContractModel):
    kind: Literal["point"]
    point: FramedPoint


class PointPairAnchor(ContractModel):
    kind: Literal["point_pair"]
    first: FramedPoint
    second: FramedPoint


class PathAnchor(ContractModel):
    kind: Literal["path"]
    block_id: Identifier


class SurfaceBlockAnchor(ContractModel):
    kind: Literal["surface_block"]
    block_id: Identifier


class FrameAnchor(ContractModel):
    kind: Literal["frame"]
    frame_id: Identifier


class BlockAnchor(ContractModel):
    kind: Literal["block"]
    block_id: Identifier


PortAnchor = Annotated[
    PointAnchor
    | PointPairAnchor
    | PathAnchor
    | SurfaceBlockAnchor
    | FrameAnchor
    | BlockAnchor,
    Field(discriminator="kind"),
]


class Orientation(ContractModel):
    frame_id: Identifier
    rotation: EulerRotation


class PortOrExcitationRecord(ContractModel):
    port_or_excitation_id: Identifier
    kind: Literal["port", "excitation"]
    reported_type: NonEmptyString
    description: NonEmptyString
    associated_block_ids: list[Identifier] = Field(min_length=1)
    anchor: PortAnchor
    orientation: Orientation
    impedance_parameter_id: Identifier | None = None
    evidence_ids: list[Identifier] = Field(min_length=1)
    unresolved_item_ids: list[Identifier] = Field(default_factory=list)


class UnresolvedItem(ContractModel):
    unresolved_item_id: Identifier
    category: Literal[
        "selection",
        "parameter",
        "material",
        "geometry",
        "placement",
        "relationship",
        "port",
        "other",
    ]
    description: NonEmptyString
    criticality: Literal["reconstruction_critical", "non_critical"]
    affected_refs: list[ArchitectureElementReference] = Field(min_length=1)
    evidence_ids: list[Identifier] = Field(default_factory=list)


class ProposedCompletion(ContractModel):
    completion_id: Identifier
    addresses_unresolved_item_ids: list[Identifier] = Field(min_length=1)
    proposal: NonEmptyString
    rationale: NonEmptyString
    affected_refs: list[ArchitectureElementReference] = Field(min_length=1)
    requires_confirmation: Literal[True]
    applied: Literal[False]


class ArchitectureProvenance(ContractModel):
    source_extraction_schema_version: Literal["1.0.0"]
    source_extraction_checksum: NonEmptyString
    generated_at: datetime


class ArchitectureStatus(ContractModel):
    structural_status: Literal["valid", "invalid"]
    reconstruction_status: Literal["complete", "incomplete"]
    scientific_review_status: Literal["not_reviewed", "passed", "failed"]


class AntennaArchitecture(ContractModel):
    schema_name: Literal["antenna_architecture"]
    schema_version: Literal["1.0.0"]
    document_ref: DocumentReference
    selected_design: SelectedDesign
    coordinate_system: CoordinateSystem
    frames: list[FrameRecord] = Field(min_length=1)
    parameters: list[ParameterRecord]
    materials: list[MaterialRecord]
    blocks: list[BlockRecord]
    relationships: list[Relationship]
    ports_and_excitations: list[PortOrExcitationRecord]
    derivations: list[DerivationRecord]
    unresolved_items: list[UnresolvedItem]
    proposed_completions: list[ProposedCompletion]
    provenance: ArchitectureProvenance
    status: ArchitectureStatus

    @model_validator(mode="after")
    def validate_architecture(self) -> AntennaArchitecture:
        indexes = self._build_indexes()
        self._validate_element_references(indexes)
        self._validate_frames(indexes)
        self._validate_parameters_and_derivations(indexes)
        self._validate_blocks(indexes)
        self._validate_relationships(indexes)
        self._validate_ports(indexes)
        self._validate_status()
        return self

    def _build_indexes(self) -> dict[str, set[str]]:
        frame_ids = ensure_unique_ids(self.frames, "frame_id", "frames")
        parameter_ids = ensure_unique_ids(
            self.parameters,
            "parameter_id",
            "parameters",
        )
        material_ids = ensure_unique_ids(self.materials, "material_id", "materials")
        block_ids = ensure_unique_ids(self.blocks, "block_id", "blocks")
        relationship_ids = ensure_unique_ids(
            self.relationships,
            "relationship_id",
            "relationships",
        )
        port_ids = ensure_unique_ids(
            self.ports_and_excitations,
            "port_or_excitation_id",
            "ports and excitations",
        )
        derivation_ids = ensure_unique_ids(
            self.derivations,
            "derivation_id",
            "derivations",
        )
        unresolved_ids = ensure_unique_ids(
            self.unresolved_items,
            "unresolved_item_id",
            "unresolved items",
        )
        completion_ids = ensure_unique_ids(
            self.proposed_completions,
            "completion_id",
            "proposed completions",
        )
        property_claims = [
            claim for material in self.materials for claim in material.property_claims
        ]
        ensure_unique_ids(property_claims, "property_claim_id", "material properties")
        return {
            "frame": frame_ids,
            "parameter": parameter_ids,
            "material": material_ids,
            "block": block_ids,
            "relationship": relationship_ids,
            "port_or_excitation": port_ids,
            "derivation": derivation_ids,
            "unresolved_item": unresolved_ids,
            "proposed_completion": completion_ids,
        }

    def _validate_element_references(self, indexes: dict[str, set[str]]) -> None:
        references = [
            *(ref for parameter in self.parameters for ref in parameter.affected_refs),
            *(ref for item in self.unresolved_items for ref in item.affected_refs),
            *(
                ref
                for completion in self.proposed_completions
                for ref in completion.affected_refs
            ),
        ]
        for reference in references:
            _ensure_known(reference.id, indexes[reference.kind], reference.kind)

        unresolved_ids = indexes["unresolved_item"]
        for completion in self.proposed_completions:
            _ensure_known_many(
                completion.addresses_unresolved_item_ids,
                unresolved_ids,
                "unresolved item",
            )

    def _validate_frames(self, indexes: dict[str, set[str]]) -> None:
        frame_ids = indexes["frame"]
        global_id = self.coordinate_system.global_frame_id
        _ensure_known(global_id, frame_ids, "global frame")
        root_frames = [frame for frame in self.frames if frame.parent_frame_id is None]
        if len(root_frames) != 1 or root_frames[0].frame_id != global_id:
            raise ValueError("exactly one root frame must be the declared global frame")
        if not _transform_is_zero(root_frames[0].transform):
            raise ValueError("the global frame transform must use only zero sentinels")

        parents: dict[str, set[str]] = {}
        parameters = _index_by(self.parameters, "parameter_id")
        for frame in self.frames:
            if frame.parent_frame_id is not None:
                _ensure_known(frame.parent_frame_id, frame_ids, "parent frame")
                if frame.parent_frame_id == frame.frame_id:
                    raise ValueError("a frame cannot parent itself")
                parents[frame.frame_id] = {frame.parent_frame_id}
            _validate_transform_dimensions(frame.transform, parameters, frame.frame_id)
        _ensure_acyclic(parents, "frame")

    def _validate_parameters_and_derivations(
        self,
        indexes: dict[str, set[str]],
    ) -> None:
        parameter_ids = indexes["parameter"]
        unresolved_ids = indexes["unresolved_item"]
        derivation_ids = indexes["derivation"]
        parameters = _index_by(self.parameters, "parameter_id")
        derivations = _index_by(self.derivations, "derivation_id")

        derived_parameter_ids: set[str] = set()
        for parameter in self.parameters:
            definition = parameter.definition
            if isinstance(definition, DerivedParameterDefinition):
                _ensure_known(definition.derivation_id, derivation_ids, "derivation")
                derivation = derivations[definition.derivation_id]
                if derivation.target_parameter_id != parameter.parameter_id:
                    raise ValueError("derived parameter and derivation target must agree")
                derived_parameter_ids.add(parameter.parameter_id)
            elif isinstance(definition, UnresolvedParameterDefinition):
                _ensure_known(
                    definition.unresolved_item_id,
                    unresolved_ids,
                    "unresolved item",
                )

        dependency_graph: dict[str, set[str]] = {}
        derivation_targets: set[str] = set()
        for derivation in self.derivations:
            _ensure_known(
                derivation.target_parameter_id,
                parameter_ids,
                "derivation target parameter",
            )
            if derivation.target_parameter_id in derivation_targets:
                raise ValueError("a parameter can have only one derivation")
            derivation_targets.add(derivation.target_parameter_id)
            target = parameters[derivation.target_parameter_id]
            if not isinstance(target.definition, DerivedParameterDefinition):
                raise ValueError("a derivation target must be a derived parameter")

            binding_names = [binding.name for binding in derivation.bindings]
            if len(binding_names) != len(set(binding_names)):
                raise ValueError("duplicate expression bindings")
            try:
                identifiers = expression_identifiers(derivation.expression)
            except ExpressionError as exc:
                raise ValueError(str(exc)) from exc
            if set(binding_names) != set(identifiers):
                missing = set(identifiers) - set(binding_names)
                unused = set(binding_names) - set(identifiers)
                if missing:
                    raise ValueError(
                        "missing expression binding(s): " + ", ".join(sorted(missing))
                    )
                raise ValueError(
                    "unused expression binding(s): " + ", ".join(sorted(unused))
                )

            inputs: set[str] = set()
            dimensions = {}
            for binding in derivation.bindings:
                _ensure_known(binding.parameter_id, parameter_ids, "parameter")
                if binding.parameter_id == derivation.target_parameter_id:
                    raise ValueError("a derivation cannot depend on its target")
                source_parameter = parameters[binding.parameter_id]
                if isinstance(
                    source_parameter.definition,
                    UnresolvedParameterDefinition,
                ):
                    raise ValueError("a derivation cannot use an unresolved parameter")
                inputs.add(binding.parameter_id)
                dimensions[binding.name] = QUANTITY_DIMENSIONS[
                    source_parameter.quantity_kind
                ]

            try:
                result_dimension = expression_dimension(
                    derivation.expression,
                    dimensions,
                )
            except ExpressionError as exc:
                raise ValueError(str(exc)) from exc
            target_dimension = QUANTITY_DIMENSIONS[target.quantity_kind]
            if result_dimension != target_dimension:
                raise ValueError("derivation dimension does not match its target")
            dependency_graph[derivation.target_parameter_id] = inputs

        if derivation_targets != derived_parameter_ids:
            raise ValueError("every derived parameter requires exactly one derivation")
        _ensure_acyclic(dependency_graph, "parameter dependency")

    def _validate_blocks(self, indexes: dict[str, set[str]]) -> None:
        parameters = _index_by(self.parameters, "parameter_id")
        materials = indexes["material"]
        derivations = indexes["derivation"]
        unresolved = indexes["unresolved_item"]
        blocks = _index_by(self.blocks, "block_id")
        block_ids = indexes["block"]
        dependency_graph: dict[str, set[str]] = {}

        profile_kinds = {
            "rectangle",
            "circle",
            "ellipse",
            "annulus",
            "polygon",
            "segmented_profile",
        }
        for block in self.blocks:
            if block.material_id is not None:
                _ensure_known(block.material_id, materials, "material")
            _ensure_known_many(block.derivation_ids, derivations, "derivation")
            _ensure_known_many(
                block.unresolved_item_ids,
                unresolved,
                "unresolved item",
            )
            if len(block.parameter_dependencies) != len(
                set(block.parameter_dependencies)
            ):
                raise ValueError("duplicate block parameter dependencies")

            used_parameters = _geometry_parameter_ids(block.geometry, parameters)
            used_parameters.update(
                _transform_parameter_ids(block.placement, parameters, block.block_id)
            )
            if set(block.parameter_dependencies) != used_parameters:
                raise ValueError(
                    f"block {block.block_id!r} parameter dependencies must exactly "
                    "match its geometry and placement"
                )

            geometry = block.geometry
            dependencies: set[str] = set()
            if isinstance(geometry, (ExtrusionGeometry, RevolutionGeometry)):
                _ensure_known(geometry.profile_block_id, block_ids, "profile block")
                profile = blocks[geometry.profile_block_id]
                if profile.state != "auxiliary" or profile.geometry.kind not in profile_kinds:
                    raise ValueError("extrusion and revolution require an auxiliary profile")
                dependencies.add(geometry.profile_block_id)
            elif isinstance(geometry, SweepGeometry):
                _ensure_known(geometry.profile_block_id, block_ids, "profile block")
                _ensure_known(geometry.path_block_id, block_ids, "path block")
                profile = blocks[geometry.profile_block_id]
                path = blocks[geometry.path_block_id]
                if profile.state != "auxiliary" or profile.geometry.kind not in profile_kinds:
                    raise ValueError("sweep requires an auxiliary profile")
                if path.state != "auxiliary" or path.geometry.kind != "wire_path":
                    raise ValueError("sweep requires an auxiliary wire path")
                dependencies.update(
                    {geometry.profile_block_id, geometry.path_block_id}
                )
            elif isinstance(geometry, InstanceGeometry):
                _ensure_known(geometry.prototype_block_id, block_ids, "prototype block")
                prototype = blocks[geometry.prototype_block_id]
                if block.state != "instance":
                    raise ValueError("instance geometry requires instance block state")
                if prototype.state not in {"physical", "auxiliary"}:
                    raise ValueError("instance prototype must be physical or auxiliary")
                dependencies.add(geometry.prototype_block_id)
            elif block.state == "instance":
                raise ValueError("instance block state requires instance geometry")
            elif isinstance(geometry, UnresolvedGeometry):
                _ensure_known(
                    geometry.unresolved_item_id,
                    unresolved,
                    "unresolved item",
                )
                if block.state != "unresolved":
                    raise ValueError("unresolved geometry requires unresolved block state")
            elif block.state == "unresolved":
                raise ValueError("unresolved block state requires unresolved geometry")
            dependency_graph[block.block_id] = dependencies

        _ensure_acyclic(dependency_graph, "block dependency")

    def _validate_relationships(self, indexes: dict[str, set[str]]) -> None:
        block_ids = indexes["block"]
        blocks = _index_by(self.blocks, "block_id")
        relationship_ids = indexes["relationship"]
        dependency_graph: dict[str, set[str]] = {
            block.block_id: set() for block in self.blocks
        }
        boolean_results: dict[str, str] = {}

        for block in self.blocks:
            geometry = block.geometry
            if isinstance(geometry, (ExtrusionGeometry, RevolutionGeometry)):
                dependency_graph[block.block_id].add(geometry.profile_block_id)
            elif isinstance(geometry, SweepGeometry):
                dependency_graph[block.block_id].update(
                    {geometry.profile_block_id, geometry.path_block_id}
                )
            elif isinstance(geometry, InstanceGeometry):
                dependency_graph[block.block_id].add(geometry.prototype_block_id)

        for relationship in self.relationships:
            if isinstance(relationship, SubtractRelationship):
                operands = [relationship.target_block_id, *relationship.tool_block_ids]
                result = relationship.result_block_id
                _require_distinct_ids(operands, "subtract operands")
                _ensure_known_many(operands, block_ids, "block")
                _validate_boolean_result(
                    relationship.relationship_id,
                    result,
                    operands,
                    blocks,
                    boolean_results,
                )
                dependency_graph[result].update(operands)
            elif isinstance(relationship, (UniteRelationship, IntersectRelationship)):
                operands = relationship.operand_block_ids
                result = relationship.result_block_id
                _require_distinct_ids(operands, "boolean operands")
                _ensure_known_many(operands, block_ids, "block")
                _validate_boolean_result(
                    relationship.relationship_id,
                    result,
                    operands,
                    blocks,
                    boolean_results,
                )
                dependency_graph[result].update(operands)
            elif isinstance(relationship, ContactRelationship):
                _validate_distinct_known_pair(
                    relationship.subject_block_id,
                    relationship.reference_block_id,
                    block_ids,
                    "contact",
                )
            elif isinstance(relationship, ContainedInRelationship):
                _validate_distinct_known_pair(
                    relationship.inner_block_id,
                    relationship.container_block_id,
                    block_ids,
                    "contained_in",
                )
            elif isinstance(relationship, AlignedWithRelationship):
                _validate_distinct_known_pair(
                    relationship.subject_block_id,
                    relationship.reference_block_id,
                    block_ids,
                    "aligned_with",
                )
                axes = [alignment.axis for alignment in relationship.alignments]
                if len(axes) != len(set(axes)):
                    raise ValueError("aligned_with axes must be unique")
            elif isinstance(relationship, PatternInstanceRelationship):
                _ensure_known(
                    relationship.prototype_block_id,
                    block_ids,
                    "prototype block",
                )
                _require_distinct_ids(
                    relationship.instance_block_ids,
                    "pattern instances",
                )
                _ensure_known_many(
                    relationship.instance_block_ids,
                    block_ids,
                    "instance block",
                )
                if relationship.prototype_block_id in relationship.instance_block_ids:
                    raise ValueError("pattern prototype cannot be one of its instances")
                for instance_id in relationship.instance_block_ids:
                    instance = blocks[instance_id]
                    if not isinstance(instance.geometry, InstanceGeometry) or (
                        instance.geometry.prototype_block_id
                        != relationship.prototype_block_id
                    ):
                        raise ValueError(
                            "pattern instances must explicitly reference the prototype"
                        )

        for block in self.blocks:
            geometry = block.geometry
            if isinstance(geometry, RelationshipResultGeometry):
                _ensure_known(
                    geometry.relationship_id,
                    relationship_ids,
                    "relationship",
                )
                if boolean_results.get(block.block_id) != geometry.relationship_id:
                    raise ValueError(
                        "relationship-result geometry must match its producing relationship"
                    )
        _ensure_acyclic(dependency_graph, "block and boolean dependency")

    def _validate_ports(self, indexes: dict[str, set[str]]) -> None:
        block_ids = indexes["block"]
        frame_ids = indexes["frame"]
        unresolved_ids = indexes["unresolved_item"]
        parameters = _index_by(self.parameters, "parameter_id")
        blocks = _index_by(self.blocks, "block_id")
        surface_kinds = {
            "rectangle",
            "circle",
            "ellipse",
            "annulus",
            "polygon",
            "segmented_profile",
            "surface",
        }

        for record in self.ports_and_excitations:
            _ensure_known_many(record.associated_block_ids, block_ids, "block")
            _ensure_known_many(
                record.unresolved_item_ids,
                unresolved_ids,
                "unresolved item",
            )
            _ensure_known(record.orientation.frame_id, frame_ids, "orientation frame")
            _validate_rotation_dimensions(
                record.orientation.rotation,
                parameters,
                record.port_or_excitation_id,
            )
            if record.impedance_parameter_id is not None:
                _require_parameter_kind(
                    record.impedance_parameter_id,
                    "impedance",
                    parameters,
                    "port impedance",
                )

            anchor = record.anchor
            if isinstance(anchor, PointAnchor):
                _validate_framed_point(anchor.point, frame_ids, parameters)
            elif isinstance(anchor, PointPairAnchor):
                _validate_framed_point(anchor.first, frame_ids, parameters)
                _validate_framed_point(anchor.second, frame_ids, parameters)
                if anchor.first == anchor.second:
                    raise ValueError("point-pair anchor requires distinct points")
            elif isinstance(anchor, PathAnchor):
                _ensure_known(anchor.block_id, block_ids, "path anchor block")
                if blocks[anchor.block_id].geometry.kind != "wire_path":
                    raise ValueError("path anchor must reference a wire-path block")
            elif isinstance(anchor, SurfaceBlockAnchor):
                _ensure_known(anchor.block_id, block_ids, "surface anchor block")
                block = blocks[anchor.block_id]
                if block.state != "auxiliary" or block.geometry.kind not in surface_kinds:
                    raise ValueError(
                        "surface anchor must reference an auxiliary surface block"
                    )
            elif isinstance(anchor, FrameAnchor):
                _ensure_known(anchor.frame_id, frame_ids, "anchor frame")
            elif isinstance(anchor, BlockAnchor):
                _ensure_known(anchor.block_id, block_ids, "anchor block")

    def _validate_status(self) -> None:
        if self.status.reconstruction_status != "complete":
            return
        if self.status.structural_status != "valid":
            raise ValueError("complete reconstruction requires structural validity")
        if self.selected_design.ambiguity_state != "unambiguous":
            raise ValueError("ambiguous selection cannot be reconstruction-complete")
        if any(
            item.criticality == "reconstruction_critical"
            for item in self.unresolved_items
        ):
            raise ValueError("critical unresolved items block complete reconstruction")
        if any(
            isinstance(parameter.definition, UnresolvedParameterDefinition)
            for parameter in self.parameters
        ):
            raise ValueError("unresolved parameters block complete reconstruction")
        if any(
            isinstance(block.geometry, UnresolvedGeometry)
            or block.state == "unresolved"
            for block in self.blocks
        ):
            raise ValueError("unresolved geometry blocks complete reconstruction")
        if self.proposed_completions:
            raise ValueError("proposed completions block complete reconstruction")


def _index_by(items: list[ContractModel], attribute: str) -> dict[str, ContractModel]:
    return {getattr(item, attribute): item for item in items}


def _ensure_known(identifier: str, known: set[str], label: str) -> None:
    if identifier not in known:
        raise ValueError(f"unknown {label} reference {identifier!r}")


def _ensure_known_many(identifiers: list[str], known: set[str], label: str) -> None:
    unknown = set(identifiers) - known
    if unknown:
        rendered = ", ".join(repr(item) for item in sorted(unknown))
        raise ValueError(f"unknown {label} reference(s): {rendered}")


def _require_distinct_ids(identifiers: list[str], label: str) -> None:
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{label} must be distinct")


def _validate_distinct_known_pair(
    first: str,
    second: str,
    known: set[str],
    label: str,
) -> None:
    _ensure_known_many([first, second], known, "block")
    if first == second:
        raise ValueError(f"{label} requires distinct blocks")


def _ensure_acyclic(graph: dict[str, set[str]], label: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError(f"{label} cycle detected")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, set()):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def _component_parameter_ids(components: object) -> set[str]:
    if isinstance(components, ParameterComponent):
        return {components.parameter_id}
    if isinstance(components, ContractModel):
        result: set[str] = set()
        for field_name in type(components).model_fields:
            result.update(_component_parameter_ids(getattr(components, field_name)))
        return result
    if isinstance(components, list):
        result = set()
        for item in components:
            result.update(_component_parameter_ids(item))
        return result
    return set()


def _transform_is_zero(transform: Transform) -> bool:
    components = [
        transform.translation.x,
        transform.translation.y,
        transform.translation.z,
        transform.rotation.x,
        transform.rotation.y,
        transform.rotation.z,
    ]
    return all(isinstance(component, ZeroComponent) for component in components)


def _require_parameter_kind(
    parameter_id: str,
    expected: QuantityKind,
    parameters: dict[str, ContractModel],
    context: str,
) -> None:
    parameter = parameters.get(parameter_id)
    if parameter is None:
        raise ValueError(f"unknown parameter reference {parameter_id!r}")
    if not isinstance(parameter, ParameterRecord):
        raise TypeError("invalid parameter index")
    if parameter.quantity_kind != expected:
        raise ValueError(f"{context} requires a {expected} parameter")


def _validate_component_group(
    value: ContractModel,
    expected: QuantityKind,
    parameters: dict[str, ContractModel],
    context: str,
) -> set[str]:
    parameter_ids = _component_parameter_ids(value)
    for parameter_id in parameter_ids:
        _require_parameter_kind(parameter_id, expected, parameters, context)
    return parameter_ids


def _validate_transform_dimensions(
    transform: Transform,
    parameters: dict[str, ContractModel],
    context: str,
) -> set[str]:
    result = _validate_component_group(
        transform.translation,
        "length",
        parameters,
        f"{context} translation",
    )
    result.update(
        _validate_component_group(
            transform.rotation,
            "angle",
            parameters,
            f"{context} rotation",
        )
    )
    return result


def _validate_rotation_dimensions(
    rotation: EulerRotation,
    parameters: dict[str, ContractModel],
    context: str,
) -> set[str]:
    return _validate_component_group(
        rotation,
        "angle",
        parameters,
        f"{context} rotation",
    )


def _validate_point_dimensions(
    point: Point2D | Point3D,
    parameters: dict[str, ContractModel],
    context: str,
) -> set[str]:
    return _validate_component_group(point, "length", parameters, context)


def _validate_framed_point(
    point: FramedPoint,
    frame_ids: set[str],
    parameters: dict[str, ContractModel],
) -> None:
    _ensure_known(point.frame_id, frame_ids, "point frame")
    _validate_point_dimensions(point.coordinates, parameters, "point coordinates")


def _geometry_parameter_ids(
    geometry: Geometry,
    parameters: dict[str, ContractModel],
) -> set[str]:
    result: set[str] = set()

    def length_ref(reference: ParameterReference, context: str) -> None:
        _require_parameter_kind(
            reference.parameter_id,
            "length",
            parameters,
            context,
        )
        result.add(reference.parameter_id)

    def angle_ref(reference: ParameterReference, context: str) -> None:
        _require_parameter_kind(
            reference.parameter_id,
            "angle",
            parameters,
            context,
        )
        result.add(reference.parameter_id)

    def point(value: Point2D | Point3D, context: str) -> None:
        result.update(_validate_point_dimensions(value, parameters, context))

    if isinstance(geometry, RectangleGeometry):
        length_ref(geometry.width, "rectangle width")
        length_ref(geometry.height, "rectangle height")
    elif isinstance(geometry, CircleGeometry):
        length_ref(geometry.radius, "circle radius")
    elif isinstance(geometry, EllipseGeometry):
        length_ref(geometry.major_radius, "ellipse major radius")
        length_ref(geometry.minor_radius, "ellipse minor radius")
    elif isinstance(geometry, AnnulusGeometry):
        length_ref(geometry.inner_radius, "annulus inner radius")
        length_ref(geometry.outer_radius, "annulus outer radius")
    elif isinstance(geometry, PolygonGeometry):
        for vertex in geometry.vertices:
            point(vertex, "polygon vertex")
    elif isinstance(geometry, SegmentedProfileGeometry):
        for segment in geometry.segments:
            point(segment.start, "profile segment start")
            point(segment.end, "profile segment end")
            if isinstance(segment, CircularArc2D):
                point(segment.center, "profile arc center")
    elif isinstance(geometry, BoxGeometry):
        length_ref(geometry.width, "box width")
        length_ref(geometry.depth, "box depth")
        length_ref(geometry.height, "box height")
    elif isinstance(geometry, CylinderGeometry):
        length_ref(geometry.radius, "cylinder radius")
        length_ref(geometry.height, "cylinder height")
    elif isinstance(geometry, ConeGeometry):
        length_ref(geometry.base_radius, "cone base radius")
        length_ref(geometry.top_radius, "cone top radius")
        length_ref(geometry.height, "cone height")
    elif isinstance(geometry, SphereGeometry):
        length_ref(geometry.radius, "sphere radius")
    elif isinstance(geometry, ExtrusionGeometry):
        length_ref(geometry.distance, "extrusion distance")
    elif isinstance(geometry, RevolutionGeometry):
        point(geometry.axis.point, "revolution axis")
        angle_ref(geometry.angle, "revolution angle")
    elif isinstance(geometry, WirePathGeometry):
        for segment in geometry.segments:
            point(segment.start, "path segment start")
            if isinstance(segment, (LineSegment3D, CircularArc3D)):
                point(segment.end, "path segment end")
            if isinstance(segment, CircularArc3D):
                point(segment.center, "path arc center")
            if isinstance(segment, HelixSegment3D):
                point(segment.axis_point, "helix axis point")
                length_ref(segment.radius, "helix radius")
                length_ref(segment.pitch, "helix pitch")
                _require_parameter_kind(
                    segment.turn_count.parameter_id,
                    "dimensionless",
                    parameters,
                    "helix turn count",
                )
                result.add(segment.turn_count.parameter_id)
    return result


def _transform_parameter_ids(
    transform: Transform,
    parameters: dict[str, ContractModel],
    context: str,
) -> set[str]:
    return _validate_transform_dimensions(transform, parameters, context)


def _validate_boolean_result(
    relationship_id: str,
    result_id: str,
    operands: list[str],
    blocks: dict[str, ContractModel],
    boolean_results: dict[str, str],
) -> None:
    if result_id in operands:
        raise ValueError("a boolean result must be distinct from its operands")
    result = blocks.get(result_id)
    if result is None:
        raise ValueError(f"unknown boolean result block reference {result_id!r}")
    if result_id in boolean_results:
        raise ValueError("a block can be produced by only one boolean relationship")
    if not isinstance(result, BlockRecord) or not isinstance(
        result.geometry,
        RelationshipResultGeometry,
    ):
        raise ValueError("a boolean result block requires relationship-result geometry")
    if result.geometry.relationship_id != relationship_id:
        raise ValueError("boolean relationship and result geometry must agree")
    boolean_results[result_id] = relationship_id
