from __future__ import annotations

import json
from pathlib import Path

from antenna_ingest.contracts.antenna_architecture import AntennaArchitecture
from antenna_ingest.contracts.antenna_results import AntennaResults
from antenna_ingest.contracts.paper_extraction import PaperExtraction
from antenna_ingest.contracts.schema_generation import (
    DEFAULT_SCHEMA_DIRECTORY,
    generate_json_schemas,
    render_json_schema,
)


def test_schema_rendering_is_deterministic() -> None:
    for model in (PaperExtraction, AntennaResults, AntennaArchitecture):
        assert render_json_schema(model) == render_json_schema(model)


def test_source_value_schema_requires_explicit_legibility() -> None:
    schema = json.loads(render_json_schema(PaperExtraction))
    source_value_schema = schema["$defs"]["SourceValue"]
    properties = source_value_schema["properties"]

    assert set(source_value_schema["required"]) == {
        "value",
        "legibility",
    }
    assert properties["value"]["type"] == "string"
    assert properties["value"]["minLength"] == 1
    assert properties["legibility"]["enum"] == ["clear", "uncertain"]
    assert "default" not in properties["legibility"]


def test_generated_schemas_match_checked_in_files(tmp_path: Path) -> None:
    generated = generate_json_schemas(tmp_path)

    assert {path.name for path in generated} == {
        "paper_extraction.schema.json",
        "antenna_results.schema.json",
        "antenna_architecture.schema.json",
    }
    for generated_path in generated:
        checked_in = DEFAULT_SCHEMA_DIRECTORY / generated_path.name
        assert generated_path.read_bytes() == checked_in.read_bytes()


def test_schemas_expose_strict_discriminated_contracts() -> None:
    for model in (PaperExtraction, AntennaResults, AntennaArchitecture):
        schema = json.loads(render_json_schema(model))
        serialized = json.dumps(schema, sort_keys=True).lower()

        assert schema["additionalProperties"] is False
        assert '"discriminator"' in serialized
        assert '"normalized"' not in serialized
        assert '"normalised"' not in serialized
        assert '"solver_commands"' not in serialized
        assert '"boolean_operations"' not in serialized
        assert '"safe_expression"' not in serialized
        assert '"patchantenna"' not in serialized
        assert '"cst"' not in serialized


def test_nested_object_schemas_forbid_unknown_fields() -> None:
    schema = json.loads(render_json_schema(PaperExtraction))
    object_definitions = [
        definition
        for definition in schema["$defs"].values()
        if definition.get("type") == "object"
    ]

    assert object_definitions
    assert all(
        definition.get("additionalProperties") is False
        for definition in object_definitions
    )


def test_setup_discriminator_has_exact_approved_kinds() -> None:
    schema = json.loads(render_json_schema(PaperExtraction))

    setup_kinds = {
        schema["$defs"][definition]["properties"]["kind"]["const"]
        for definition in (
            "SimulationSetup",
            "MeasurementSetup",
            "AnalyticalSetup",
        )
    }

    assert setup_kinds == {"simulation", "measurement", "analytical"}


def test_spatial_map_content_schema_has_explicit_discriminated_variants() -> None:
    schema = json.loads(render_json_schema(PaperExtraction))
    representation = schema["$defs"]["SpatialMapRepresentation"]
    content_schema = representation["properties"]["content"]

    assert representation["properties"]["kind"]["const"] == "spatial_map"
    assert representation["properties"]["quantity"]["minLength"] == 1
    assert "field_or_current" not in representation["properties"]
    assert content_schema["discriminator"]["propertyName"] == "kind"
    assert set(content_schema["discriminator"]["mapping"]) == {
        "image_only",
        "sampled",
    }


def test_architecture_schema_has_exact_geometry_and_relationship_kinds() -> None:
    schema = json.loads(render_json_schema(AntennaArchitecture))

    geometry_kinds = {
        schema["$defs"][definition]["properties"]["kind"]["const"]
        for definition in (
            "RectangleGeometry",
            "CircleGeometry",
            "EllipseGeometry",
            "AnnulusGeometry",
            "PolygonGeometry",
            "SegmentedProfileGeometry",
            "BoxGeometry",
            "CylinderGeometry",
            "ConeGeometry",
            "SphereGeometry",
            "ExtrusionGeometry",
            "RevolutionGeometry",
            "WirePathGeometry",
            "SweepGeometry",
            "SurfaceGeometry",
            "MeshGeometry",
            "InstanceGeometry",
            "UnresolvedGeometry",
            "RelationshipResultGeometry",
        )
    }
    relationship_kinds = {
        schema["$defs"][definition]["properties"]["kind"]["const"]
        for definition in (
            "SubtractRelationship",
            "UniteRelationship",
            "IntersectRelationship",
            "ContactRelationship",
            "ContainedInRelationship",
            "AlignedWithRelationship",
            "PatternInstanceRelationship",
        )
    }

    assert geometry_kinds == {
        "rectangle",
        "circle",
        "ellipse",
        "annulus",
        "polygon",
        "segmented_profile",
        "box",
        "cylinder",
        "cone",
        "sphere",
        "extrusion",
        "revolution",
        "wire_path",
        "sweep",
        "surface",
        "mesh",
        "instance",
        "unresolved",
        "relationship_result",
    }
    assert relationship_kinds == {
        "subtract",
        "unite",
        "intersect",
        "contact",
        "contained_in",
        "aligned_with",
        "pattern_instance",
    }


def test_architecture_schema_encodes_placement_and_geometry_conventions() -> None:
    schema = json.loads(render_json_schema(AntennaArchitecture))
    definitions = schema["$defs"]

    assert set(definitions["BlockPlacement"]["required"]) == {
        "frame_id",
        "transform",
    }
    conventions = definitions["GeometryConventions"]["properties"]
    assert conventions["profile_coordinates"]["const"] == "local_xy"
    assert conventions["box_extent"]["const"] == (
        "centered_xy_z_zero_to_positive_height"
    )
    assert conventions["path_coordinates"]["const"] == ("containing_block_local_frame")
    assert conventions["arc_direction_view"]["const"] == (
        "positive_plane_normal_towards_plane"
    )

    extrusion = definitions["ExtrusionGeometry"]["properties"]
    assert extrusion["direction"]["const"] == ("referenced_profile_local_positive_z")
    sweep = definitions["SweepGeometry"]["properties"]
    assert sweep["transport_convention"]["const"] == ("parallel_transport_zero_twist")
    assert sweep["initial_profile_orientation"]["const"] == ("placed_profile_local_xy")
    assert set(definitions["ExtrusionGeometry"]["required"]) >= {
        "direction",
        "reference_placement_semantics",
    }
    assert set(definitions["RevolutionGeometry"]["required"]) >= {
        "reference_placement_semantics"
    }
    assert set(definitions["SweepGeometry"]["required"]) >= {
        "transport_convention",
        "initial_profile_orientation",
        "reference_placement_semantics",
    }
    assert set(definitions["InstanceGeometry"]["required"]) >= {
        "prototype_copy_semantics"
    }
    assert set(definitions["RelationshipResultGeometry"]["required"]) >= {
        "operand_placement_semantics"
    }
    provenance = definitions["ArchitectureProvenance"]["properties"]
    assert provenance["source_extraction_checksum"]["pattern"] == ("^[0-9a-fA-F]{64}$")


def test_architecture_schema_excludes_deferred_and_family_specific_contracts() -> None:
    schema = json.loads(render_json_schema(AntennaArchitecture))
    serialized = json.dumps(schema, sort_keys=True).lower()

    for forbidden in (
        "normalized",
        "normalised",
        "patchantenna",
        "pifa",
        "hornantenna",
        "helixantenna",
        "cst",
        "solver_commands",
        "model_client",
        "endpoint",
    ):
        assert forbidden not in serialized


def test_interval_schema_uses_source_values_for_both_endpoints() -> None:
    schema = json.loads(render_json_schema(PaperExtraction))
    definitions = schema["$defs"]
    interval = definitions["IntervalRepresentation"]

    assert interval["properties"]["lower"]["$ref"] == "#/$defs/SourceValue"
    assert interval["properties"]["upper"]["$ref"] == "#/$defs/SourceValue"
    assert set(interval["required"]) == {"kind", "lower", "upper"}
    assert "IntervalEndpointValue" not in definitions


def test_result_schema_encodes_availability_and_origin_constraints() -> None:
    schema = json.loads(render_json_schema(PaperExtraction))
    definitions = schema["$defs"]
    result = definitions["ResultRecord"]
    properties = result["properties"]
    representation_mapping = properties["representation"]["discriminator"]["mapping"]
    unavailable = definitions["UnavailableRepresentation"]

    assert "legibility" not in properties
    assert "extraction_completeness" not in properties
    assert "uncertainty_note" in properties
    assert set(properties["origin"]["enum"]) == {
        "simulated",
        "measured",
        "analytical",
        "unspecified",
    }
    assert "spatial_map" in representation_mapping
    assert "unavailable" in representation_mapping
    assert "field_map" not in representation_mapping
    assert unavailable["properties"]["kind"]["const"] == "unavailable"
    assert set(unavailable["properties"]["reason"]["enum"]) == {
        "not_reported",
        "illegible",
        "ambiguous",
    }
    assert unavailable["properties"]["description"]["minLength"] == 1
    assert set(unavailable["required"]) == {"kind", "reason", "description"}
