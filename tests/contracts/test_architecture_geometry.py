from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

import pytest
from pydantic import ValidationError

from antenna_ingest.contracts.antenna_architecture import AntennaArchitecture
from architecture_helpers import (
    block,
    block_placement,
    component,
    empty_architecture,
    identity_transform,
    material,
    parameter_ref,
    point2,
    point3,
    reported_parameter,
)


CaseBuilder = Callable[[], dict]


def _add_parameter(
    data: dict,
    parameter_id: str,
    block_id: str,
    quantity_kind: str = "length",
) -> None:
    unit = {
        "length": "mm",
        "angle": "degree",
        "dimensionless": None,
    }.get(quantity_kind)
    data["parameters"].append(
        reported_parameter(
            parameter_id,
            quantity_kind,
            "block",
            block_id,
            unit=unit,
        )
    )


def _rectangular_stack() -> dict:
    data = empty_architecture()
    data["materials"] = [material("dielectric"), material("conductor")]
    for parameter_id in ("stack_width", "stack_depth", "stack_height"):
        _add_parameter(data, parameter_id, "substrate")
    for parameter_id in ("radiator_width", "radiator_height"):
        _add_parameter(data, parameter_id, "radiator")
    data["blocks"] = [
        block(
            "substrate",
            {
                "kind": "box",
                "width": parameter_ref("stack_width"),
                "depth": parameter_ref("stack_depth"),
                "height": parameter_ref("stack_height"),
            },
            ["stack_width", "stack_depth", "stack_height"],
            role="substrate",
            material_id="dielectric",
        ),
        block(
            "radiator",
            {
                "kind": "rectangle",
                "width": parameter_ref("radiator_width"),
                "height": parameter_ref("radiator_height"),
            },
            ["radiator_width", "radiator_height"],
            role="radiator",
            material_id="conductor",
        ),
    ]
    return data


def _polygon_with_circular_subtraction() -> dict:
    data = empty_architecture()
    for parameter_id, block_id in (
        ("triangle_x", "triangle"),
        ("triangle_y", "triangle"),
        ("slot_radius", "slot_tool"),
    ):
        _add_parameter(data, parameter_id, block_id)
    data["blocks"] = [
        block(
            "triangle",
            {
                "kind": "polygon",
                "vertices": [
                    point2(),
                    point2("triangle_x"),
                    point2(None, "triangle_y"),
                ],
            },
            ["triangle_x", "triangle_y"],
            state="auxiliary",
            role="conductor",
        ),
        block(
            "slot_tool",
            {"kind": "circle", "radius": parameter_ref("slot_radius")},
            ["slot_radius"],
            state="auxiliary",
            role="slot_tool",
        ),
        block(
            "radiator_result",
            {"kind": "relationship_result", "relationship_id": "subtract_slot"},
            [],
            role="radiator",
        ),
    ]
    data["relationships"] = [
        {
            "relationship_id": "subtract_slot",
            "kind": "subtract",
            "target_block_id": "triangle",
            "tool_block_ids": ["slot_tool"],
            "result_block_id": "radiator_result",
            "evidence_ids": ["ev_geometry"],
        }
    ]
    return data


def _explicit_notch() -> dict:
    data = empty_architecture()
    for parameter_id, block_id in (
        ("body_width", "body"),
        ("body_height", "body"),
        ("notch_width", "notch_tool"),
        ("notch_height", "notch_tool"),
    ):
        _add_parameter(data, parameter_id, block_id)
    data["blocks"] = [
        block(
            "body",
            {
                "kind": "rectangle",
                "width": parameter_ref("body_width"),
                "height": parameter_ref("body_height"),
            },
            ["body_width", "body_height"],
            state="auxiliary",
        ),
        block(
            "notch_tool",
            {
                "kind": "rectangle",
                "width": parameter_ref("notch_width"),
                "height": parameter_ref("notch_height"),
            },
            ["notch_width", "notch_height"],
            state="auxiliary",
            role="slot_tool",
        ),
        block(
            "notched_result",
            {"kind": "relationship_result", "relationship_id": "subtract_notch"},
            [],
            role="radiator",
        ),
    ]
    data["relationships"] = [
        {
            "relationship_id": "subtract_notch",
            "kind": "subtract",
            "target_block_id": "body",
            "tool_block_ids": ["notch_tool"],
            "result_block_id": "notched_result",
            "evidence_ids": ["ev_geometry"],
        }
    ]
    return data


def _multilayer_structure() -> dict:
    data = empty_architecture()
    for index in range(3):
        block_id = f"layer_{index}"
        for suffix in ("width", "depth", "height"):
            _add_parameter(data, f"{block_id}_{suffix}", block_id)
        transform = identity_transform()
        dependencies = [
            f"{block_id}_width",
            f"{block_id}_depth",
            f"{block_id}_height",
        ]
        if index:
            offset = f"{block_id}_offset"
            _add_parameter(data, offset, block_id)
            transform["translation"]["z"] = component(offset)
            dependencies.append(offset)
        data["blocks"].append(
            block(
                block_id,
                {
                    "kind": "box",
                    "width": parameter_ref(f"{block_id}_width"),
                    "depth": parameter_ref(f"{block_id}_depth"),
                    "height": parameter_ref(f"{block_id}_height"),
                },
                dependencies,
                role="dielectric",
                placement=block_placement(transform=transform),
            )
        )
    return data


def _via_with_contact() -> dict:
    data = empty_architecture()
    for parameter_id, block_id in (
        ("via_radius", "via"),
        ("via_height", "via"),
        ("ground_width", "ground"),
        ("ground_depth", "ground"),
        ("ground_height", "ground"),
    ):
        _add_parameter(data, parameter_id, block_id)
    data["blocks"] = [
        block(
            "via",
            {
                "kind": "cylinder",
                "radius": parameter_ref("via_radius"),
                "height": parameter_ref("via_height"),
            },
            ["via_radius", "via_height"],
            role="via",
        ),
        block(
            "ground",
            {
                "kind": "box",
                "width": parameter_ref("ground_width"),
                "depth": parameter_ref("ground_depth"),
                "height": parameter_ref("ground_height"),
            },
            ["ground_width", "ground_depth", "ground_height"],
            role="ground",
        ),
    ]
    data["relationships"] = [
        {
            "relationship_id": "via_contact",
            "kind": "contact",
            "subject_block_id": "via",
            "reference_block_id": "ground",
            "evidence_ids": ["ev_geometry"],
        }
    ]
    return data


def _meander_path() -> dict:
    data = empty_architecture()
    _add_parameter(data, "path_x", "trace")
    _add_parameter(data, "path_y", "trace")
    data["blocks"] = [
        block(
            "trace",
            {
                "kind": "wire_path",
                "segments": [
                    {
                        "kind": "line_segment",
                        "start": point3(),
                        "end": point3("path_x"),
                    },
                    {
                        "kind": "line_segment",
                        "start": point3("path_x"),
                        "end": point3("path_x", "path_y"),
                    },
                    {
                        "kind": "circular_arc",
                        "start": point3("path_x", "path_y"),
                        "end": point3(None, "path_y"),
                        "center": point3("path_x"),
                        "plane_normal": "z",
                        "direction": "counterclockwise",
                    },
                ],
            },
            ["path_x", "path_y"],
            role="radiator",
        )
    ]
    return data


def _helix_path() -> dict:
    data = empty_architecture()
    for parameter_id, kind in (
        ("helix_radius", "length"),
        ("helix_pitch", "length"),
        ("helix_turns", "dimensionless"),
    ):
        _add_parameter(data, parameter_id, "helix_trace", kind)
    data["blocks"] = [
        block(
            "helix_trace",
            {
                "kind": "wire_path",
                "segments": [
                    {
                        "kind": "helix_segment",
                        "start": point3(),
                        "axis_point": point3(),
                        "axis_direction": "z",
                        "radius": parameter_ref("helix_radius"),
                        "pitch": parameter_ref("helix_pitch"),
                        "turn_count": parameter_ref("helix_turns"),
                        "handedness": "right_handed",
                    }
                ],
            },
            ["helix_radius", "helix_pitch", "helix_turns"],
            role="radiator",
        )
    ]
    return data


def _explicit_instances() -> dict:
    data = empty_architecture()
    _add_parameter(data, "element_width", "prototype")
    _add_parameter(data, "element_height", "prototype")
    data["blocks"] = [
        block(
            "prototype",
            {
                "kind": "rectangle",
                "width": parameter_ref("element_width"),
                "height": parameter_ref("element_height"),
            },
            ["element_width", "element_height"],
            role="array_element",
        )
    ]
    for index in (1, 2):
        block_id = f"instance_{index}"
        offset = f"offset_{index}"
        _add_parameter(data, offset, block_id)
        transform = identity_transform()
        transform["translation"]["x"] = component(offset)
        data["blocks"].append(
            block(
                block_id,
                {"kind": "instance", "prototype_block_id": "prototype"},
                [offset],
                role="array_element",
                state="instance",
                placement=block_placement(transform=transform),
            )
        )
    data["relationships"] = [
        {
            "relationship_id": "reported_pattern",
            "kind": "pattern_instance",
            "prototype_block_id": "prototype",
            "instance_block_ids": ["instance_1", "instance_2"],
            "evidence_ids": ["ev_geometry"],
        }
    ]
    return data


def _tapered_volume() -> dict:
    data = empty_architecture()
    for parameter_id in ("base_radius", "aperture_radius", "taper_length"):
        _add_parameter(data, parameter_id, "taper")
    data["blocks"] = [
        block(
            "taper",
            {
                "kind": "cone",
                "base_radius": parameter_ref("base_radius"),
                "top_radius": parameter_ref("aperture_radius"),
                "height": parameter_ref("taper_length"),
            },
            ["base_radius", "aperture_radius", "taper_length"],
            role="radiator",
        )
    ]
    return data


def _dielectric_resonator_volume() -> dict:
    data = empty_architecture()
    data["materials"] = [material("reported_dielectric")]
    _add_parameter(data, "resonator_radius", "resonator")
    data["blocks"] = [
        block(
            "resonator",
            {"kind": "sphere", "radius": parameter_ref("resonator_radius")},
            ["resonator_radius"],
            role="dielectric",
            material_id="reported_dielectric",
        )
    ]
    return data


def _source_backed_assets() -> dict:
    data = empty_architecture()
    checksum = "a" * 64
    data["blocks"] = [
        block(
            "conformal_surface",
            {
                "kind": "surface",
                "asset": {
                    "asset_ref": "assets/conformal.step",
                    "format": "STEP",
                    "source_length_unit": "mm",
                    "availability": "locally_available",
                    "sha256": checksum,
                    "evidence_ids": ["ev_geometry"],
                },
            },
            [],
            role="radiator",
        ),
        block(
            "external_mesh",
            {
                "kind": "mesh",
                "asset": {
                    "asset_ref": "publisher supplement mesh",
                    "format": "STL",
                    "source_length_unit": "mm",
                    "availability": "externally_referenced",
                    "sha256": None,
                    "evidence_ids": ["ev_geometry"],
                },
            },
            [],
            role="environmental_layer",
        ),
    ]
    return data


def _implant_with_surrounding_material() -> dict:
    data = empty_architecture()
    data["materials"] = [material("implant_material"), material("surrounding_medium")]
    _add_parameter(data, "implant_radius", "implant")
    _add_parameter(data, "environment_radius", "environment")
    data["blocks"] = [
        block(
            "implant",
            {"kind": "sphere", "radius": parameter_ref("implant_radius")},
            ["implant_radius"],
            role="radiator",
            material_id="implant_material",
        ),
        block(
            "environment",
            {"kind": "sphere", "radius": parameter_ref("environment_radius")},
            ["environment_radius"],
            role="environmental_layer",
            material_id="surrounding_medium",
        ),
    ]
    data["relationships"] = [
        {
            "relationship_id": "implant_environment",
            "kind": "contained_in",
            "inner_block_id": "implant",
            "container_block_id": "environment",
            "evidence_ids": ["ev_geometry"],
        }
    ]
    return data


def _incomplete_geometry() -> dict:
    data = empty_architecture()
    data["status"]["reconstruction_status"] = "incomplete"
    data["unresolved_items"] = [
        {
            "unresolved_item_id": "missing_profile",
            "category": "geometry",
            "description": "The source does not define the full profile.",
            "criticality": "reconstruction_critical",
            "affected_refs": [{"kind": "block", "id": "unknown_part"}],
            "evidence_ids": ["ev_geometry"],
        }
    ]
    data["blocks"] = [
        block(
            "unknown_part",
            {"kind": "unresolved", "unresolved_item_id": "missing_profile"},
            [],
            role="other",
            state="unresolved",
            unresolved_item_ids=["missing_profile"],
        )
    ]
    data["proposed_completions"] = [
        {
            "completion_id": "propose_profile",
            "addresses_unresolved_item_ids": ["missing_profile"],
            "proposal": "Supply the missing source-backed profile.",
            "rationale": "No supported geometry is available.",
            "affected_refs": [{"kind": "block", "id": "unknown_part"}],
            "requires_confirmation": True,
            "applied": False,
        }
    ]
    return data


GEOMETRY_CASES: list[tuple[str, CaseBuilder]] = [
    ("rectangular_planar_stack", _rectangular_stack),
    ("polygonal_radiator_with_circular_subtraction", _polygon_with_circular_subtraction),
    ("explicit_inset_or_notch", _explicit_notch),
    ("multilayer_structure", _multilayer_structure),
    ("via_or_shorting_element", _via_with_contact),
    ("wire_or_meander_path", _meander_path),
    ("helix_path", _helix_path),
    ("explicit_array_instances", _explicit_instances),
    ("tapered_volumetric_profile", _tapered_volume),
    ("dielectric_resonator_volume", _dielectric_resonator_volume),
    ("source_backed_surface_and_mesh", _source_backed_assets),
    ("implant_with_surrounding_material", _implant_with_surrounding_material),
    ("incomplete_geometry", _incomplete_geometry),
]


@pytest.mark.parametrize(
    ("case_name", "builder"),
    GEOMETRY_CASES,
    ids=[case[0] for case in GEOMETRY_CASES],
)
def test_required_synthetic_geometry_cases_are_representable(
    case_name,
    builder,
) -> None:
    architecture = AntennaArchitecture.model_validate(builder())

    assert architecture.blocks, case_name


def _remaining_geometry_case(kind: str) -> dict:
    data = empty_architecture()
    for parameter_id, quantity_kind in (
        ("a", "length"),
        ("b", "length"),
        ("c", "length"),
        ("angle", "angle"),
    ):
        _add_parameter(data, parameter_id, "geometry", quantity_kind)

    if kind == "ellipse":
        geometry = {
            "kind": "ellipse",
            "major_radius": parameter_ref("a"),
            "minor_radius": parameter_ref("b"),
        }
        dependencies = ["a", "b"]
    elif kind == "annulus":
        geometry = {
            "kind": "annulus",
            "inner_radius": parameter_ref("a"),
            "outer_radius": parameter_ref("b"),
        }
        dependencies = ["a", "b"]
    elif kind == "segmented_profile":
        geometry = {
            "kind": "segmented_profile",
            "segments": [
                {
                    "kind": "circular_arc",
                    "start": point2(),
                    "end": point2("a"),
                    "center": point2(None, "b"),
                    "direction": "counterclockwise",
                },
                {
                    "kind": "line_segment",
                    "start": point2("a"),
                    "end": point2(),
                },
            ],
        }
        dependencies = ["a", "b"]
    else:
        profile = block(
            "profile",
            {
                "kind": "rectangle",
                "width": parameter_ref("a"),
                "height": parameter_ref("b"),
            },
            ["a", "b"],
            state="auxiliary",
        )
        data["parameters"][0]["affected_refs"] = [{"kind": "block", "id": "profile"}]
        data["parameters"][1]["affected_refs"] = [{"kind": "block", "id": "profile"}]
        data["blocks"].append(profile)
        if kind == "extrusion":
            geometry = {
                "kind": "extrusion",
                "profile_block_id": "profile",
                "distance": parameter_ref("c"),
            }
            dependencies = ["c"]
        elif kind == "revolution":
            geometry = {
                "kind": "revolution",
                "profile_block_id": "profile",
                "axis": {"point": point3(), "direction": "z"},
                "angle": parameter_ref("angle"),
            }
            dependencies = ["angle"]
        else:
            path = block(
                "path",
                {
                    "kind": "wire_path",
                    "segments": [
                        {
                            "kind": "line_segment",
                            "start": point3(),
                            "end": point3("c"),
                        }
                    ],
                },
                ["c"],
                state="auxiliary",
            )
            data["parameters"][2]["affected_refs"] = [
                {"kind": "block", "id": "path"}
            ]
            data["blocks"].append(path)
            geometry = {
                "kind": "sweep",
                "profile_block_id": "profile",
                "path_block_id": "path",
            }
            dependencies = []
    data["blocks"].append(block("geometry", geometry, dependencies))
    return data


@pytest.mark.parametrize(
    "kind",
    ["ellipse", "annulus", "segmented_profile", "extrusion", "revolution", "sweep"],
)
def test_remaining_geometry_basis_is_representable(kind) -> None:
    assert AntennaArchitecture.model_validate(_remaining_geometry_case(kind))


def test_invalid_polygon_profile_and_path_cardinality_fail() -> None:
    polygon = _polygon_with_circular_subtraction()
    polygon["blocks"][0]["geometry"]["vertices"] = [point2(), point2("triangle_x")]
    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(polygon)

    profile = _remaining_geometry_case("segmented_profile")
    profile["blocks"][0]["geometry"]["segments"] = profile["blocks"][0][
        "geometry"
    ]["segments"][:1]
    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(profile)

    path = _meander_path()
    path["blocks"][0]["geometry"]["segments"] = []
    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(path)

    disconnected = _meander_path()
    disconnected["blocks"][0]["geometry"]["segments"][1]["start"] = point3()
    with pytest.raises(ValidationError, match="connected in order"):
        AntennaArchitecture.model_validate(disconnected)


def test_polygon_requires_three_structurally_distinct_vertices() -> None:
    data = _polygon_with_circular_subtraction()
    data["blocks"][0]["geometry"]["vertices"] = [
        point2(),
        point2(),
        point2("triangle_x"),
    ]

    with pytest.raises(ValidationError, match="structurally distinct"):
        AntennaArchitecture.model_validate(data)


def test_segmented_profile_rejects_structurally_degenerate_segment() -> None:
    data = _remaining_geometry_case("segmented_profile")
    data["blocks"][0]["geometry"]["segments"][1] = {
        "kind": "line_segment",
        "start": point2("a"),
        "end": point2("a"),
    }

    with pytest.raises(ValidationError, match="endpoints must be distinct"):
        AntennaArchitecture.model_validate(data)


def test_local_mesh_requires_checksum_and_rejects_embedded_geometry() -> None:
    missing_checksum = _source_backed_assets()
    missing_checksum["blocks"][1]["geometry"]["asset"]["availability"] = (
        "locally_available"
    )
    missing_checksum["blocks"][1]["geometry"]["asset"]["sha256"] = None
    with pytest.raises(ValidationError, match="requires a SHA-256"):
        AntennaArchitecture.model_validate(missing_checksum)

    embedded = _source_backed_assets()
    embedded["blocks"][1]["geometry"]["vertices"] = [[0, 0, 0]]
    embedded["blocks"][1]["geometry"]["faces"] = [[0, 0, 0]]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AntennaArchitecture.model_validate(embedded)


def test_unavailable_geometry_asset_blocks_only_complete_reconstruction() -> None:
    complete = _source_backed_assets()
    complete["blocks"][1]["geometry"]["asset"]["availability"] = "unavailable"
    with pytest.raises(ValidationError, match="unavailable geometry assets"):
        AntennaArchitecture.model_validate(complete)

    incomplete = deepcopy(complete)
    incomplete["status"]["reconstruction_status"] = "incomplete"
    architecture = AntennaArchitecture.model_validate(incomplete)
    assert architecture.status.reconstruction_status == "incomplete"


@pytest.mark.parametrize("kind", ["extrusion", "revolution", "sweep"])
def test_constructive_results_consume_placed_references_once(kind: str) -> None:
    data = _remaining_geometry_case(kind)
    profile = data["blocks"][0]
    profile["placement"]["transform"]["translation"]["x"] = component("a")
    if kind == "sweep":
        path = data["blocks"][1]
        path["placement"]["transform"]["translation"]["z"] = component("c")

    architecture = AntennaArchitecture.model_validate(data)
    result = architecture.blocks[-1]

    assert result.placement.frame_id == "frame_global"
    assert result.geometry.reference_placement_semantics.startswith("use_placed_")
    if kind == "extrusion":
        assert result.geometry.direction == "referenced_profile_local_positive_z"
    if kind == "sweep":
        assert result.geometry.transport_convention == "parallel_transport_zero_twist"
        assert result.geometry.initial_profile_orientation == "placed_profile_local_xy"


def test_constructive_result_rejects_second_independent_transform() -> None:
    data = _remaining_geometry_case("extrusion")
    result = data["blocks"][-1]
    result["placement"]["transform"]["translation"]["x"] = component("c")

    with pytest.raises(ValidationError, match="global identity"):
        AntennaArchitecture.model_validate(data)


def test_boolean_results_use_placed_operands_without_second_transform() -> None:
    data = _polygon_with_circular_subtraction()
    data["blocks"][0]["placement"]["transform"]["translation"]["x"] = component(
        "triangle_x"
    )
    data["blocks"][1]["placement"]["transform"]["translation"]["y"] = component(
        "slot_radius"
    )

    architecture = AntennaArchitecture.model_validate(data)
    result = architecture.blocks[2]
    assert result.geometry.operand_placement_semantics == "use_placed_operands_once"

    invalid = deepcopy(data)
    invalid["blocks"][2]["placement"]["transform"]["translation"]["x"] = (
        component("triangle_x")
    )
    invalid["blocks"][2]["parameter_dependencies"] = ["triangle_x"]
    with pytest.raises(ValidationError, match="global identity"):
        AntennaArchitecture.model_validate(invalid)


def test_instance_copies_local_geometry_and_material_but_not_placement() -> None:
    data = _explicit_instances()
    data["materials"] = [material("array_material")]
    data["blocks"][0]["material_id"] = "array_material"
    data["blocks"][0]["placement"]["transform"]["translation"]["x"] = component(
        "element_width"
    )
    for instance in data["blocks"][1:]:
        instance["material_id"] = "array_material"

    architecture = AntennaArchitecture.model_validate(data)
    prototype = architecture.blocks[0]
    instance = architecture.blocks[1]
    assert instance.geometry.prototype_copy_semantics == (
        "copy_local_geometry_and_material_without_placement"
    )
    assert instance.material_id == prototype.material_id
    assert instance.placement != prototype.placement

    invalid = deepcopy(data)
    invalid["materials"].append(material("other_material"))
    invalid["blocks"][1]["material_id"] = "other_material"
    with pytest.raises(ValidationError, match="copy the prototype material"):
        AntennaArchitecture.model_validate(invalid)
