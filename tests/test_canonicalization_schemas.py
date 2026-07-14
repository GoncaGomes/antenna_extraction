from __future__ import annotations

import pytest
from pydantic import ValidationError

from antenna_ingest.canonicalization.schemas import (
    CanonicalConflict,
    CanonicalDesignRecord,
    Coordinate3D,
)


def minimal_record_data() -> dict:
    return {
        "design": {
            "design_label": "Reported design",
            "selection_reason": "Selected as the final reported design.",
            "evidence_ids": ["block_design"],
        },
        "reconstruction_status": "unknown",
    }


def test_minimal_valid_canonical_record() -> None:
    record = CanonicalDesignRecord.model_validate(minimal_record_data())

    assert record.schema_name == "canonical_design_record_v1"
    assert record.materials == []
    assert record.objects == []


def test_rectangular_printed_antenna_uses_generic_parts() -> None:
    data = minimal_record_data()
    data["materials"] = [
        {
            "material_id": "fr4",
            "name": "FR4",
            "role": "substrate",
            "evidence_ids": ["block_material"],
        },
        {
            "material_id": "copper",
            "name": "Copper",
            "role": "conductor",
            "evidence_ids": ["block_material"],
        },
    ]
    data["objects"] = [
        object_data("substrate", "substrate", "solid", "fr4", "rectangular prism"),
        object_data("radiator", "radiator", "sheet", "copper", "rectangle"),
        object_data("ground", "ground plane", "sheet", "copper", "rectangle"),
        object_data("feedline", "feedline", "sheet", "copper", "rectangle"),
    ]

    record = CanonicalDesignRecord.model_validate(data)

    assert [obj.role for obj in record.objects] == [
        "substrate",
        "radiator",
        "ground plane",
        "feedline",
    ]


def test_helical_wire_uses_generic_geometry_parameters() -> None:
    data = minimal_record_data()
    data["objects"] = [
        {
            "object_id": "helix",
            "role": "radiator",
            "physical_form": "wire",
            "geometry": {
                "representation": "parametric",
                "geometry_type": "helix",
                "parameters": [
                    fact("radius", 12, "mm"),
                    fact("pitch", 4, "mm"),
                    fact("turns", 6),
                ],
                "evidence_ids": ["block_geometry"],
            },
            "evidence_ids": ["block_geometry"],
        }
    ]

    record = CanonicalDesignRecord.model_validate(data)

    assert [item.name for item in record.objects[0].geometry.parameters] == [
        "radius",
        "pitch",
        "turns",
    ]


def test_arbitrary_polygonal_sheet_uses_control_points() -> None:
    data = minimal_record_data()
    data["objects"] = [
        {
            "object_id": "radiator",
            "role": "radiator",
            "physical_form": "sheet",
            "geometry": {
                "representation": "polygon",
                "geometry_type": "arbitrary polygonal sheet",
                "control_points": [
                    {"label": "p1", "role": "vertex", "position": {"x": 0, "y": 0}},
                    {"label": "p2", "role": "vertex", "position": {"x": 5, "y": 0}},
                    {"label": "p3", "role": "vertex", "position": {"x": 2, "y": 4}},
                ],
                "evidence_ids": ["figure_geometry"],
            },
            "evidence_ids": ["figure_geometry"],
        }
    ]

    record = CanonicalDesignRecord.model_validate(data)

    assert len(record.objects[0].geometry.control_points) == 3


def test_slot_is_void_subtracted_from_radiator() -> None:
    data = minimal_record_data()
    data["objects"] = [
        object_data("radiator", "radiator", "sheet"),
        object_data("slot", "slot", "void"),
    ]
    data["relationships"] = [
        {
            "subject_id": "slot",
            "relation": "subtracted_from",
            "object_id": "radiator",
            "evidence_ids": ["figure_slot"],
        }
    ]

    record = CanonicalDesignRecord.model_validate(data)

    assert record.objects[1].physical_form == "void"
    assert record.relationships[0].relation == "subtracted_from"


def test_array_uses_generic_relationship_parameters() -> None:
    data = minimal_record_data()
    data["objects"] = [
        object_data("element", "unit radiator", "sheet"),
        object_data("substrate", "substrate", "solid"),
    ]
    data["relationships"] = [
        {
            "subject_id": "element",
            "relation": "arranged_in_rectangular_array_on",
            "object_id": "substrate",
            "parameters": [
                fact("row count", 2),
                fact("column count", 4),
                fact("element spacing", 18, "mm"),
            ],
            "evidence_ids": ["table_array"],
        }
    ]

    record = CanonicalDesignRecord.model_validate(data)

    assert record.relationships[0].parameters[2].value == 18


def test_relative_placement_references_an_object() -> None:
    data = minimal_record_data()
    radiator = object_data("radiator", "radiator", "sheet")
    radiator["geometry"]["placement"] = {
        "reference_object_id": "substrate",
        "position": {"x": "W/2", "y": "L/2", "unit": "mm"},
        "evidence_ids": ["figure_placement"],
    }
    data["objects"] = [
        object_data("substrate", "substrate", "solid"),
        radiator,
    ]

    record = CanonicalDesignRecord.model_validate(data)

    assert (
        record.objects[1].geometry.placement.reference_object_id == "substrate"
    )


def test_excitation_allows_multiple_targets() -> None:
    data = minimal_record_data()
    data["objects"] = [
        object_data("feed", "feed conductor", "wire"),
        object_data("ground", "ground plane", "sheet"),
    ]
    data["excitations"] = [
        {
            "excitation_id": "port_1",
            "excitation_type": "discrete port",
            "target_object_ids": ["feed", "ground"],
            "evidence_ids": ["block_port"],
        }
    ]

    record = CanonicalDesignRecord.model_validate(data)

    assert record.excitations[0].target_object_ids == ["feed", "ground"]


def test_duplicate_material_ids_are_rejected() -> None:
    data = minimal_record_data()
    material = {
        "material_id": "copper",
        "name": "Copper",
        "evidence_ids": ["block_material"],
    }
    data["materials"] = [material, material]

    with pytest.raises(ValidationError, match="duplicate material_id"):
        CanonicalDesignRecord.model_validate(data)


def test_duplicate_object_ids_are_rejected() -> None:
    data = minimal_record_data()
    data["objects"] = [
        object_data("radiator", "radiator", "sheet"),
        object_data("radiator", "parasitic element", "sheet"),
    ]

    with pytest.raises(ValidationError, match="duplicate object_id"):
        CanonicalDesignRecord.model_validate(data)


def test_unknown_material_reference_is_rejected() -> None:
    data = minimal_record_data()
    data["objects"] = [
        object_data("radiator", "radiator", "sheet", "unknown_material")
    ]

    with pytest.raises(ValidationError, match="unknown_material"):
        CanonicalDesignRecord.model_validate(data)


def test_unknown_relationship_endpoint_is_rejected() -> None:
    data = minimal_record_data()
    data["objects"] = [object_data("radiator", "radiator", "sheet")]
    data["relationships"] = [
        {
            "subject_id": "radiator",
            "relation": "printed_on",
            "object_id": "missing_substrate",
            "evidence_ids": ["block_relation"],
        }
    ]

    with pytest.raises(ValidationError, match="missing_substrate"):
        CanonicalDesignRecord.model_validate(data)


def test_unknown_placement_reference_is_rejected() -> None:
    data = minimal_record_data()
    radiator = object_data("radiator", "radiator", "sheet")
    radiator["geometry"]["placement"] = {
        "reference_object_id": "missing_object",
        "description": "Centred on the substrate.",
        "evidence_ids": ["figure_placement"],
    }
    data["objects"] = [radiator]

    with pytest.raises(ValidationError, match="missing_object"):
        CanonicalDesignRecord.model_validate(data)


def test_unknown_excitation_target_is_rejected() -> None:
    data = minimal_record_data()
    data["excitations"] = [
        {
            "excitation_id": "port_1",
            "excitation_type": "lumped port",
            "target_object_ids": ["missing_feed"],
            "evidence_ids": ["block_port"],
        }
    ]

    with pytest.raises(ValidationError, match="missing_feed"):
        CanonicalDesignRecord.model_validate(data)


def test_unknown_missing_information_object_is_rejected() -> None:
    data = minimal_record_data()
    data["missing_information"] = [
        {
            "field": "feed dimensions",
            "severity": "major",
            "reason": "Not reported.",
            "related_object_ids": ["missing_feed"],
        }
    ]

    with pytest.raises(ValidationError, match="missing_feed"):
        CanonicalDesignRecord.model_validate(data)


def test_invalid_identifier_format_is_rejected() -> None:
    data = minimal_record_data()
    data["objects"] = [object_data("Invalid-ID", "radiator", "sheet")]

    with pytest.raises(ValidationError):
        CanonicalDesignRecord.model_validate(data)


def test_extra_fields_are_rejected() -> None:
    data = minimal_record_data()
    data["operations"] = []

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CanonicalDesignRecord.model_validate(data)


def test_empty_coordinate_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one coordinate"):
        Coordinate3D()


def test_resolved_conflict_requires_selected_value() -> None:
    with pytest.raises(ValidationError, match="require selected_value"):
        CanonicalConflict(
            field="substrate thickness",
            options=conflict_options(),
            status="resolved",
        )


def test_unresolved_conflict_must_not_have_selected_value() -> None:
    with pytest.raises(ValidationError, match="must not contain selected_value"):
        CanonicalConflict(
            field="substrate thickness",
            options=conflict_options(),
            status="unresolved",
            selected_value="1.6 mm",
        )


def object_data(
    object_id: str,
    role: str,
    physical_form: str,
    material_id: str | None = None,
    geometry_type: str = "descriptive",
) -> dict:
    value = {
        "object_id": object_id,
        "role": role,
        "physical_form": physical_form,
        "geometry": {
            "representation": "descriptive",
            "geometry_type": geometry_type,
            "evidence_ids": ["block_geometry"],
        },
        "evidence_ids": ["block_geometry"],
    }
    if material_id is not None:
        value["material_id"] = material_id
    return value


def fact(name: str, value: str | int | float, unit: str | None = None) -> dict:
    result = {
        "name": name,
        "value": value,
        "evidence_ids": ["table_parameters"],
    }
    if unit is not None:
        result["unit"] = unit
    return result


def conflict_options() -> list[dict]:
    return [
        {"raw_value": "1.5 mm", "evidence_ids": ["block_a"]},
        {"raw_value": "1.6 mm", "evidence_ids": ["table_b"]},
    ]
