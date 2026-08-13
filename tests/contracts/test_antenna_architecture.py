from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from antenna_ingest.contracts.antenna_architecture import AntennaArchitecture
from architecture_helpers import (
    FIXTURE_PATH,
    block_placement,
    component,
    empty_architecture,
    identity_transform,
    reported_parameter,
)


def test_minimal_architecture_fixture_validates_at_json_boundary() -> None:
    architecture = AntennaArchitecture.model_validate_json(
        FIXTURE_PATH.read_text(encoding="utf-8")
    )

    assert architecture.schema_name == "antenna_architecture"
    assert architecture.schema_version == "1.0.0"
    assert architecture.status.reconstruction_status == "complete"


def test_top_level_architecture_contract_is_explicit_and_closed() -> None:
    assert set(AntennaArchitecture.model_fields) == {
        "schema_name",
        "schema_version",
        "document_ref",
        "selected_design",
        "coordinate_system",
        "frames",
        "parameters",
        "materials",
        "blocks",
        "relationships",
        "ports_and_excitations",
        "derivations",
        "unresolved_items",
        "proposed_completions",
        "provenance",
        "status",
    }


@pytest.mark.parametrize("reconstruction_status", ["complete", "incomplete"])
def test_architecture_requires_at_least_one_block(reconstruction_status) -> None:
    data = empty_architecture()
    data["status"]["reconstruction_status"] = reconstruction_status

    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(data)


def test_architecture_round_trip_preserves_exact_source_values_and_units(
    antenna_architecture_data,
) -> None:
    architecture = AntennaArchitecture.model_validate(antenna_architecture_data)
    serialized = architecture.model_dump_json()
    revalidated = AntennaArchitecture.model_validate_json(serialized)

    width = revalidated.parameters[0].definition.value
    assert width.value == "10.00"
    assert width.unit == "mm"
    assert revalidated == architecture


def test_architecture_rejects_extra_fields_and_coercion(
    antenna_architecture_data,
) -> None:
    extra = deepcopy(antenna_architecture_data)
    extra["blocks"][0]["geometry"]["normalized_width"] = "0.01 m"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AntennaArchitecture.model_validate(extra)

    coerced = deepcopy(antenna_architecture_data)
    coerced["document_ref"]["page_count"] = "1"
    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(coerced)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", "cylindrical"),
        ("handedness", "left_handed"),
        ("rotation_representation", "quaternion"),
        ("rotation_order", "z_then_y_then_x"),
        ("rotation_composition", "Rx(x) @ Ry(y) @ Rz(z)"),
    ],
)
def test_coordinate_and_rotation_convention_is_fixed(
    antenna_architecture_data,
    field,
    value,
) -> None:
    data = deepcopy(antenna_architecture_data)
    data["coordinate_system"][field] = value

    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_coordinates", "global_xy"),
        ("centered_2d_primitives", "corner_at_local_origin"),
        ("box_extent", "centered_xyz"),
        ("axial_solid_extent", "centered_on_z"),
        ("sphere_origin", "offset_from_local_origin"),
        ("path_coordinates", "global_frame"),
        ("arc_direction_view", "towards_positive_plane_normal"),
    ],
)
def test_geometry_conventions_are_fixed_literals(
    antenna_architecture_data,
    field,
    value,
) -> None:
    data = deepcopy(antenna_architecture_data)
    data["coordinate_system"]["geometry_conventions"][field] = value

    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(data)


def test_global_frame_is_unique_and_uses_zero_sentinels(
    antenna_architecture_data,
) -> None:
    extra_root = deepcopy(antenna_architecture_data)
    frame = deepcopy(extra_root["frames"][0])
    frame["frame_id"] = "another_root"
    extra_root["frames"].append(frame)
    with pytest.raises(ValidationError, match="exactly one root frame"):
        AntennaArchitecture.model_validate(extra_root)

    moved_global = deepcopy(antenna_architecture_data)
    moved_global["frames"][0]["transform"]["translation"]["x"] = component(
        "width"
    )
    with pytest.raises(ValidationError, match="global frame transform"):
        AntennaArchitecture.model_validate(moved_global)


def test_local_frame_tree_and_transform_dimensions_are_validated(
    antenna_architecture_data,
) -> None:
    valid = deepcopy(antenna_architecture_data)
    valid["parameters"].append(
        reported_parameter(
            "offset",
            "length",
            "frame",
            "frame_local",
            unit="mm",
        )
    )
    transform = identity_transform()
    transform["translation"]["x"] = component("offset")
    valid["frames"].append(
        {
            "frame_id": "frame_local",
            "name": "Local frame",
            "parent_frame_id": "frame_global",
            "transform": transform,
        }
    )
    assert AntennaArchitecture.model_validate(valid).frames[1].parent_frame_id == (
        "frame_global"
    )

    wrong_dimension = deepcopy(valid)
    wrong_dimension["frames"][1]["transform"]["rotation"]["z"] = component(
        "offset"
    )
    with pytest.raises(ValidationError, match="requires a angle parameter"):
        AntennaArchitecture.model_validate(wrong_dimension)

    cycle = deepcopy(antenna_architecture_data)
    cycle["frames"].extend(
        [
            {
                "frame_id": "frame_a",
                "name": "Frame A",
                "parent_frame_id": "frame_b",
                "transform": identity_transform(),
            },
            {
                "frame_id": "frame_b",
                "name": "Frame B",
                "parent_frame_id": "frame_a",
                "transform": identity_transform(),
            },
        ]
    )
    with pytest.raises(ValidationError, match="frame cycle"):
        AntennaArchitecture.model_validate(cycle)


def test_blocks_use_explicit_local_frames_with_translation_and_rotation(
    antenna_architecture_data,
) -> None:
    data = deepcopy(antenna_architecture_data)
    for parameter_id, quantity_kind, affected_kind, affected_id in (
        ("front_offset", "length", "block", "radiator"),
        ("front_rotation", "angle", "block", "radiator"),
        ("back_offset", "length", "frame", "frame_back"),
        ("back_rotation", "angle", "frame", "frame_back"),
    ):
        data["parameters"].append(
            reported_parameter(
                parameter_id,
                quantity_kind,
                affected_kind,
                affected_id,
                unit="mm" if quantity_kind == "length" else "degree",
            )
        )

    back_transform = identity_transform()
    back_transform["translation"]["z"] = component("back_offset")
    back_transform["rotation"]["y"] = component("back_rotation")
    data["frames"].extend(
        [
            {
                "frame_id": "frame_front",
                "name": "Front layer frame",
                "parent_frame_id": "frame_global",
                "transform": identity_transform(),
            },
            {
                "frame_id": "frame_back",
                "name": "Back layer frame",
                "parent_frame_id": "frame_global",
                "transform": back_transform,
            },
        ]
    )

    front_transform = identity_transform()
    front_transform["translation"]["x"] = component("front_offset")
    front_transform["rotation"]["z"] = component("front_rotation")
    data["blocks"][0]["placement"] = block_placement(
        "frame_front",
        front_transform,
    )
    data["blocks"][0]["parameter_dependencies"].extend(
        ["front_offset", "front_rotation"]
    )
    back = deepcopy(data["blocks"][0])
    back["block_id"] = "back_layer"
    back["name"] = "Back layer"
    back["placement"] = block_placement("frame_back")
    back["parameter_dependencies"] = ["width", "height"]
    data["blocks"].append(back)

    architecture = AntennaArchitecture.model_validate(data)

    assert architecture.blocks[0].placement.frame_id == "frame_front"
    assert architecture.blocks[1].placement.frame_id == "frame_back"
    assert architecture.blocks[0].placement.transform.rotation.z.parameter_id == (
        "front_rotation"
    )


def test_block_placement_requires_known_frame_and_correct_dimensions(
    antenna_architecture_data,
) -> None:
    missing = deepcopy(antenna_architecture_data)
    del missing["blocks"][0]["placement"]["frame_id"]
    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(missing)

    unknown = deepcopy(antenna_architecture_data)
    unknown["blocks"][0]["placement"]["frame_id"] = "unknown_frame"
    with pytest.raises(ValidationError, match="unknown placement frame"):
        AntennaArchitecture.model_validate(unknown)

    wrong_dimension = deepcopy(antenna_architecture_data)
    wrong_dimension["blocks"][0]["placement"]["transform"]["rotation"]["z"] = (
        component("width")
    )
    with pytest.raises(ValidationError, match="requires a angle parameter"):
        AntennaArchitecture.model_validate(wrong_dimension)


def test_material_properties_are_typed_and_source_faithful(
    antenna_architecture_data,
) -> None:
    data = deepcopy(antenna_architecture_data)
    data["materials"][0]["property_claims"] = [
        {
            "property_claim_id": "claim_permittivity",
            "property_name": "relative permittivity",
            "value": {
                "value": "4.40",
                "unit": None,
                "qualifier": "≈",
                "legibility": "clear",
            },
            "conditions": [],
            "evidence_ids": ["ev_material"],
            "origin": "reported_table",
        }
    ]

    architecture = AntennaArchitecture.model_validate(data)
    claim = architecture.materials[0].property_claims[0]
    assert claim.value.value == "4.40"
    assert claim.value.qualifier == "≈"

    unapproved = deepcopy(data)
    unapproved["materials"][0]["property_claims"][0]["origin"] = (
        "engineering_inference"
    )
    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(unapproved)


@pytest.mark.parametrize("legibility", ["missing", "illegible"])
def test_material_property_claim_rejects_unreadable_values(
    antenna_architecture_data,
    legibility,
) -> None:
    data = deepcopy(antenna_architecture_data)
    data["materials"][0]["property_claims"] = [
        {
            "property_claim_id": "claim_unknown_property",
            "property_name": "reported material property",
            "value": {
                "value": None,
                "unit": None,
                "qualifier": None,
                "legibility": legibility,
            },
            "conditions": [],
            "evidence_ids": ["ev_material"],
            "origin": "reported_table",
        }
    ]

    with pytest.raises(ValidationError, match="belong in unresolved_items"):
        AntennaArchitecture.model_validate(data)


@pytest.mark.parametrize(
    "checksum",
    ["short", "g" * 64, "a" * 63, "a" * 65],
)
def test_source_extraction_checksum_is_strict_sha256(
    antenna_architecture_data,
    checksum,
) -> None:
    data = deepcopy(antenna_architecture_data)
    data["provenance"]["source_extraction_checksum"] = checksum

    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(data)


def test_ambiguous_selection_and_invalid_structure_cannot_be_complete(
    antenna_architecture_data,
) -> None:
    ambiguous = deepcopy(antenna_architecture_data)
    ambiguous["selected_design"]["ambiguity_state"] = "ambiguous"
    with pytest.raises(ValidationError, match="ambiguous selection"):
        AntennaArchitecture.model_validate(ambiguous)

    invalid = deepcopy(antenna_architecture_data)
    invalid["status"]["structural_status"] = "invalid"
    with pytest.raises(ValidationError, match="structural validity"):
        AntennaArchitecture.model_validate(invalid)


def test_unapplied_proposal_is_valid_only_for_incomplete_reconstruction(
    antenna_architecture_data,
) -> None:
    data = deepcopy(antenna_architecture_data)
    data["status"]["reconstruction_status"] = "incomplete"
    data["unresolved_items"] = [
        {
            "unresolved_item_id": "missing_thickness",
            "category": "parameter",
            "description": "The conductor thickness is not reported.",
            "criticality": "reconstruction_critical",
            "affected_refs": [{"kind": "block", "id": "radiator"}],
            "evidence_ids": [],
        }
    ]
    data["proposed_completions"] = [
        {
            "completion_id": "propose_thickness",
            "addresses_unresolved_item_ids": ["missing_thickness"],
            "proposal": "Choose a conductor thickness downstream.",
            "rationale": "The source omits this construction value.",
            "affected_refs": [{"kind": "block", "id": "radiator"}],
            "requires_confirmation": True,
            "applied": False,
        }
    ]

    architecture = AntennaArchitecture.model_validate(data)
    assert architecture.proposed_completions
    revalidated = AntennaArchitecture.model_validate_json(
        architecture.model_dump_json()
    )
    assert revalidated.status.reconstruction_status == "incomplete"

    complete = deepcopy(data)
    complete["status"]["reconstruction_status"] = "complete"
    with pytest.raises(ValidationError, match="critical unresolved|proposed"):
        AntennaArchitecture.model_validate(complete)

    applied = deepcopy(data)
    applied["proposed_completions"][0]["applied"] = True
    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(applied)

    confirmation_free = deepcopy(data)
    confirmation_free["proposed_completions"][0]["requires_confirmation"] = False
    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(confirmation_free)


@pytest.mark.parametrize(
    "category",
    ["parameter", "material", "asset", "geometry", "placement"],
)
def test_unresolved_construction_data_blocks_complete_even_if_noncritical(
    antenna_architecture_data,
    category,
) -> None:
    data = deepcopy(antenna_architecture_data)
    data["unresolved_items"] = [
        {
            "unresolved_item_id": f"unresolved_{category}",
            "category": category,
            "description": f"The source leaves {category} unresolved.",
            "criticality": "non_critical",
            "affected_refs": [{"kind": "block", "id": "radiator"}],
            "evidence_ids": [],
        }
    ]

    with pytest.raises(ValidationError, match="unresolved construction data"):
        AntennaArchitecture.model_validate(data)
