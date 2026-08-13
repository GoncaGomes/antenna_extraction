from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from antenna_ingest.contracts.antenna_architecture import AntennaArchitecture
from architecture_helpers import (
    FIXTURE_PATH,
    component,
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
