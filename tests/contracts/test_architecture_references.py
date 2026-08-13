from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from antenna_ingest.contracts.antenna_architecture import AntennaArchitecture
from architecture_helpers import (
    architecture_data,
    block,
    empty_architecture,
    identity_transform,
    parameter_ref,
    point3,
    reported_parameter,
)
from test_architecture_geometry import (
    _explicit_instances,
    _polygon_with_circular_subtraction,
    _remaining_geometry_case,
)


def test_duplicate_and_unknown_internal_ids_fail(antenna_architecture_data) -> None:
    duplicate = deepcopy(antenna_architecture_data)
    duplicate["blocks"].append(deepcopy(duplicate["blocks"][0]))
    with pytest.raises(ValidationError, match="duplicate IDs in blocks"):
        AntennaArchitecture.model_validate(duplicate)

    unknown_parameter = deepcopy(antenna_architecture_data)
    unknown_parameter["blocks"][0]["geometry"]["width"]["parameter_id"] = (
        "unknown"
    )
    with pytest.raises(ValidationError, match="unknown parameter"):
        AntennaArchitecture.model_validate(unknown_parameter)

    unknown_material = deepcopy(antenna_architecture_data)
    unknown_material["blocks"][0]["material_id"] = "unknown"
    with pytest.raises(ValidationError, match="unknown material"):
        AntennaArchitecture.model_validate(unknown_material)

    unknown_affected_ref = deepcopy(antenna_architecture_data)
    unknown_affected_ref["parameters"][0]["affected_refs"][0]["id"] = "unknown"
    with pytest.raises(ValidationError, match="unknown block"):
        AntennaArchitecture.model_validate(unknown_affected_ref)


def test_parameter_origins_and_dependencies_are_strict(
    antenna_architecture_data,
) -> None:
    inferred = deepcopy(antenna_architecture_data)
    inferred["parameters"][0]["definition"]["origin"] = "engineering_inference"
    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(inferred)

    missing_dependency = deepcopy(antenna_architecture_data)
    missing_dependency["blocks"][0]["parameter_dependencies"] = ["height"]
    with pytest.raises(ValidationError, match="must exactly match"):
        AntennaArchitecture.model_validate(missing_dependency)

    unused_dependency = deepcopy(antenna_architecture_data)
    unused_dependency["blocks"][0]["parameter_dependencies"].append("height")
    with pytest.raises(ValidationError, match="duplicate block parameter"):
        AntennaArchitecture.model_validate(unused_dependency)

    wrong_geometry_dimension = deepcopy(antenna_architecture_data)
    wrong_geometry_dimension["parameters"][0]["quantity_kind"] = "angle"
    with pytest.raises(ValidationError, match="requires a length parameter"):
        AntennaArchitecture.model_validate(wrong_geometry_dimension)


def test_instance_references_and_cycles_are_rejected() -> None:
    unknown = _explicit_instances()
    unknown["blocks"][1]["geometry"]["prototype_block_id"] = "unknown"
    with pytest.raises(ValidationError, match="unknown prototype"):
        AntennaArchitecture.model_validate(unknown)

    cycle = _explicit_instances()
    cycle["blocks"][0]["state"] = "instance"
    cycle["blocks"][0]["geometry"] = {
        "kind": "instance",
        "prototype_block_id": "instance_1",
        "prototype_copy_semantics": (
            "copy_local_geometry_and_material_without_placement"
        ),
    }
    cycle["blocks"][0]["parameter_dependencies"] = []
    cycle["blocks"][1]["geometry"]["prototype_block_id"] = "prototype"
    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(cycle)


def test_placement_and_revolution_axis_frame_references_must_resolve() -> None:
    placement = architecture_data()
    placement["blocks"][0]["placement"]["frame_id"] = "missing_frame"
    with pytest.raises(ValidationError, match="unknown placement frame"):
        AntennaArchitecture.model_validate(placement)

    revolution = _remaining_geometry_case("revolution")
    revolution["blocks"][-1]["geometry"]["axis"]["frame_id"] = "missing_frame"
    with pytest.raises(ValidationError, match="unknown revolution axis frame"):
        AntennaArchitecture.model_validate(revolution)


def test_boolean_references_and_relationship_result_consistency() -> None:
    unknown_tool = _polygon_with_circular_subtraction()
    unknown_tool["relationships"][0]["tool_block_ids"] = ["unknown"]
    with pytest.raises(ValidationError, match="unknown block"):
        AntennaArchitecture.model_validate(unknown_tool)

    wrong_result = _polygon_with_circular_subtraction()
    wrong_result["blocks"][2]["geometry"]["relationship_id"] = "other"
    with pytest.raises(ValidationError, match="unknown relationship|must agree"):
        AntennaArchitecture.model_validate(wrong_result)

    direct_result = _polygon_with_circular_subtraction()
    direct_result["blocks"][2]["geometry"] = {
        "kind": "circle",
        "radius": {"parameter_id": "slot_radius"},
    }
    direct_result["blocks"][2]["parameter_dependencies"] = ["slot_radius"]
    with pytest.raises(ValidationError, match="relationship-result"):
        AntennaArchitecture.model_validate(direct_result)


def test_boolean_dependency_cycles_fail() -> None:
    data = empty_architecture()
    data["parameters"].extend(
        [
            reported_parameter("tool_radius", "length", "block", "tool", unit="mm"),
        ]
    )
    data["blocks"] = [
        block(
            "tool",
            {"kind": "circle", "radius": parameter_ref("tool_radius")},
            ["tool_radius"],
            state="auxiliary",
        ),
        block(
            "result_a",
            {"kind": "relationship_result", "relationship_id": "rel_a"},
            [],
        ),
        block(
            "result_b",
            {"kind": "relationship_result", "relationship_id": "rel_b"},
            [],
        ),
    ]
    data["relationships"] = [
        {
            "relationship_id": "rel_a",
            "kind": "subtract",
            "target_block_id": "result_b",
            "tool_block_ids": ["tool"],
            "result_block_id": "result_a",
            "evidence_ids": ["ev_geometry"],
        },
        {
            "relationship_id": "rel_b",
            "kind": "subtract",
            "target_block_id": "result_a",
            "tool_block_ids": ["tool"],
            "result_block_id": "result_b",
            "evidence_ids": ["ev_geometry"],
        },
    ]

    with pytest.raises(ValidationError, match="block and boolean dependency cycle"):
        AntennaArchitecture.model_validate(data)


def test_remaining_relationship_variants_are_typed() -> None:
    data = empty_architecture()
    for block_id in ("a", "b"):
        width = f"{block_id}_width"
        height = f"{block_id}_height"
        data["parameters"].extend(
            [
                reported_parameter(width, "length", "block", block_id, unit="mm"),
                reported_parameter(height, "length", "block", block_id, unit="mm"),
            ]
        )
        data["blocks"].append(
            block(
                block_id,
                {
                    "kind": "rectangle",
                    "width": parameter_ref(width),
                    "height": parameter_ref(height),
                },
                [width, height],
                state="auxiliary",
            )
        )
    data["blocks"].extend(
        [
            block(
                "united",
                {"kind": "relationship_result", "relationship_id": "rel_unite"},
                [],
            ),
            block(
                "intersected",
                {
                    "kind": "relationship_result",
                    "relationship_id": "rel_intersect",
                },
                [],
            ),
        ]
    )
    data["relationships"] = [
        {
            "relationship_id": "rel_unite",
            "kind": "unite",
            "operand_block_ids": ["a", "b"],
            "result_block_id": "united",
            "evidence_ids": ["ev_geometry"],
        },
        {
            "relationship_id": "rel_intersect",
            "kind": "intersect",
            "operand_block_ids": ["a", "b"],
            "result_block_id": "intersected",
            "evidence_ids": ["ev_geometry"],
        },
        {
            "relationship_id": "rel_align",
            "kind": "aligned_with",
            "subject_block_id": "a",
            "reference_block_id": "b",
            "alignments": [
                {"axis": "x", "subject_anchor": "center", "reference_anchor": "center"},
                {"axis": "y", "subject_anchor": "min", "reference_anchor": "max"},
            ],
            "evidence_ids": ["ev_geometry"],
        },
    ]

    architecture = AntennaArchitecture.model_validate(data)
    assert {relationship.kind for relationship in architecture.relationships} == {
        "unite",
        "intersect",
        "aligned_with",
    }

    vague = deepcopy(data)
    vague["relationships"][2]["description"] = "centre both blocks"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AntennaArchitecture.model_validate(vague)


def _architecture_with_all_port_anchors() -> dict:
    data = architecture_data()
    data["parameters"].extend(
        [
            reported_parameter(
                "path_x",
                "length",
                "block",
                "feed_path",
                unit="mm",
            ),
            reported_parameter(
                "surface_width",
                "length",
                "block",
                "port_surface",
                unit="mm",
            ),
            reported_parameter(
                "surface_height",
                "length",
                "block",
                "port_surface",
                unit="mm",
            ),
            reported_parameter(
                "point_x",
                "length",
                "port_or_excitation",
                "point_port",
                unit="mm",
            ),
            reported_parameter(
                "impedance",
                "impedance",
                "port_or_excitation",
                "point_port",
                value="47.98",
                unit="ohm",
            ),
        ]
    )
    data["blocks"].extend(
        [
            block(
                "feed_path",
                {
                    "kind": "wire_path",
                    "segments": [
                        {
                            "kind": "line_segment",
                            "start": point3(),
                            "end": point3("path_x"),
                        }
                    ],
                },
                ["path_x"],
                state="auxiliary",
                role="feed",
            ),
            block(
                "port_surface",
                {
                    "kind": "rectangle",
                    "width": parameter_ref("surface_width"),
                    "height": parameter_ref("surface_height"),
                },
                ["surface_width", "surface_height"],
                state="auxiliary",
                role="port_region",
            ),
        ]
    )
    anchors = {
        "point_port": {
            "kind": "point",
            "point": {
                "frame_id": "frame_global",
                "coordinates": point3("point_x"),
            },
        },
        "pair_port": {
            "kind": "point_pair",
            "first": {"frame_id": "frame_global", "coordinates": point3()},
            "second": {
                "frame_id": "frame_global",
                "coordinates": point3("point_x"),
            },
        },
        "path_port": {"kind": "path", "block_id": "feed_path"},
        "surface_port": {"kind": "surface_block", "block_id": "port_surface"},
        "frame_excitation": {"kind": "frame", "frame_id": "frame_global"},
        "block_excitation": {"kind": "block", "block_id": "radiator"},
    }
    data["ports_and_excitations"] = []
    for record_id, anchor in anchors.items():
        data["ports_and_excitations"].append(
            {
                "port_or_excitation_id": record_id,
                "kind": "port" if "port" in record_id else "excitation",
                "reported_type": "reported source type",
                "description": "Solver-neutral source description.",
                "associated_block_ids": ["radiator"],
                "anchor": anchor,
                "orientation": {
                    "frame_id": "frame_global",
                    "rotation": identity_transform()["rotation"],
                },
                "impedance_parameter_id": (
                    "impedance" if record_id == "point_port" else None
                ),
                "evidence_ids": ["ev_port"],
                "unresolved_item_ids": [],
            }
        )
    return data


def test_all_solver_neutral_port_anchor_variants_validate() -> None:
    architecture = AntennaArchitecture.model_validate(
        _architecture_with_all_port_anchors()
    )

    assert {record.anchor.kind for record in architecture.ports_and_excitations} == {
        "point",
        "point_pair",
        "path",
        "surface_block",
        "frame",
        "block",
    }


def test_unknown_or_invalid_port_anchors_fail() -> None:
    unknown = _architecture_with_all_port_anchors()
    unknown["ports_and_excitations"][0]["anchor"] = {
        "kind": "top_face",
        "block_id": "radiator",
    }
    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(unknown)

    wrong_path = _architecture_with_all_port_anchors()
    wrong_path["ports_and_excitations"][2]["anchor"]["block_id"] = "radiator"
    with pytest.raises(ValidationError, match="wire-path"):
        AntennaArchitecture.model_validate(wrong_path)

    wrong_impedance = _architecture_with_all_port_anchors()
    wrong_impedance["ports_and_excitations"][0]["impedance_parameter_id"] = "width"
    with pytest.raises(ValidationError, match="requires a impedance parameter"):
        AntennaArchitecture.model_validate(wrong_impedance)
