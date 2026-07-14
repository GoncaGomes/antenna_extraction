from __future__ import annotations

from pathlib import Path

from antenna_ingest.canonicalization.schemas import CanonicalDesignRecord
from antenna_ingest.canonicalization.validation import (
    collect_evidence_ids,
    load_valid_evidence_ids,
    validate_evidence_references,
)
from antenna_ingest.retrieval.index import (
    EVIDENCE_INDEX_PATH,
    EvidenceIndexItem,
    write_jsonl,
)


def test_collects_evidence_ids_from_every_nested_schema_location() -> None:
    record = nested_record()

    evidence_ids = collect_evidence_ids(record)

    assert evidence_ids == expected_nested_ids()


def test_duplicate_evidence_ids_are_returned_once() -> None:
    record = nested_record()

    evidence_ids = collect_evidence_ids(record)

    assert evidence_ids.count("e_design") == 1


def test_first_seen_order_is_preserved() -> None:
    record = nested_record()

    evidence_ids = collect_evidence_ids(record)

    assert evidence_ids[:4] == [
        "e_design",
        "e_coordinate_system",
        "e_material_property",
        "e_material",
    ]


def test_record_with_only_valid_ids_passes() -> None:
    record = nested_record()

    report = validate_evidence_references(record, set(expected_nested_ids()))

    assert report.valid is True
    assert report.unknown_evidence_ids == []


def test_record_with_invented_evidence_id_fails() -> None:
    record = nested_record()

    report = validate_evidence_references(record, {"e_design"})

    assert report.valid is False
    assert report.unknown_evidence_ids


def test_all_unknown_evidence_ids_are_reported() -> None:
    record = nested_record()
    valid_ids = set(expected_nested_ids()) - {"e_geometry", "e_result"}

    report = validate_evidence_references(record, valid_ids)

    assert report.unknown_evidence_ids == ["e_geometry", "e_result"]


def test_validation_does_not_modify_record() -> None:
    record = nested_record()
    before = record.model_dump(mode="json")

    validate_evidence_references(record, {"e_design"})

    assert record.model_dump(mode="json") == before


def test_valid_ids_load_from_synthetic_index(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    items = [index_item("block_a", 0), index_item("table_001", 1)]
    write_jsonl(run_dir / EVIDENCE_INDEX_PATH, items)

    valid_ids = load_valid_evidence_ids(run_dir)

    assert valid_ids == {"block_a", "table_001"}


def nested_record() -> CanonicalDesignRecord:
    return CanonicalDesignRecord.model_validate(
        {
            "design": {
                "selection_reason": "Final reported design.",
                "evidence_ids": ["e_design"],
            },
            "reconstruction_status": "partially_buildable",
            "coordinate_system": {
                "name": "paper coordinates",
                "evidence_ids": ["e_coordinate_system"],
            },
            "materials": [
                {
                    "material_id": "substrate_material",
                    "properties": [
                        {
                            "name": "relative permittivity",
                            "value": 4.4,
                            "evidence_ids": ["e_material_property"],
                        }
                    ],
                    "evidence_ids": ["e_material", "e_design"],
                }
            ],
            "objects": [
                {
                    "object_id": "substrate",
                    "role": "substrate",
                    "physical_form": "solid",
                    "material_id": "substrate_material",
                    "geometry": {
                        "parameters": [
                            {
                                "name": "width",
                                "value": 40,
                                "unit": "mm",
                                "evidence_ids": ["e_geometry_parameter"],
                            }
                        ],
                        "placement": {
                            "position": {"x": 0},
                            "evidence_ids": ["e_placement"],
                        },
                        "evidence_ids": ["e_geometry"],
                    },
                    "properties": [
                        {
                            "name": "surface finish",
                            "value": "unspecified",
                            "evidence_ids": ["e_object_property"],
                        }
                    ],
                    "evidence_ids": ["e_object"],
                },
                {
                    "object_id": "radiator",
                    "role": "radiator",
                    "physical_form": "sheet",
                    "evidence_ids": ["e_radiator"],
                },
            ],
            "relationships": [
                {
                    "subject_id": "radiator",
                    "relation": "printed_on",
                    "object_id": "substrate",
                    "parameters": [
                        {
                            "name": "offset",
                            "value": 0,
                            "unit": "mm",
                            "evidence_ids": ["e_relationship_parameter"],
                        }
                    ],
                    "evidence_ids": ["e_relationship"],
                }
            ],
            "excitations": [
                {
                    "excitation_id": "port_1",
                    "excitation_type": "lumped port",
                    "target_object_ids": ["radiator"],
                    "properties": [
                        {
                            "name": "impedance",
                            "value": 50,
                            "unit": "ohm",
                            "evidence_ids": ["e_excitation_property"],
                        }
                    ],
                    "evidence_ids": ["e_excitation"],
                }
            ],
            "simulation_setup": {
                "software": "Example Solver",
                "properties": [
                    {
                        "name": "frequency range",
                        "value": [2.4, 2.5],
                        "unit": "GHz",
                        "evidence_ids": ["e_simulation_property"],
                    }
                ],
                "evidence_ids": ["e_simulation"],
            },
            "reported_results": [
                {
                    "metric": "gain",
                    "result_source": "simulated",
                    "value": 4.2,
                    "unit": "dBi",
                    "evidence_ids": ["e_result"],
                }
            ],
            "excluded_variants": [
                {
                    "variant_id": "early_variant",
                    "reason_excluded": "Not the final design.",
                    "evidence_ids": ["e_variant"],
                }
            ],
            "conflicts": [
                {
                    "field": "substrate thickness",
                    "options": [
                        {"raw_value": "1.5 mm", "evidence_ids": ["e_conflict_a"]},
                        {"raw_value": "1.6 mm", "evidence_ids": ["e_conflict_b"]},
                    ],
                    "status": "unresolved",
                }
            ],
        }
    )


def expected_nested_ids() -> list[str]:
    return [
        "e_design",
        "e_coordinate_system",
        "e_material_property",
        "e_material",
        "e_geometry_parameter",
        "e_placement",
        "e_geometry",
        "e_object_property",
        "e_object",
        "e_radiator",
        "e_relationship_parameter",
        "e_relationship",
        "e_excitation_property",
        "e_excitation",
        "e_simulation_property",
        "e_simulation",
        "e_result",
        "e_variant",
        "e_conflict_a",
        "e_conflict_b",
    ]


def index_item(evidence_id: str, order: int) -> EvidenceIndexItem:
    return EvidenceIndexItem(
        evidence_id=evidence_id,
        source_type="block",
        source_id=evidence_id,
        page=1,
        kind="paragraph",
        order=order,
        text=f"Evidence text for {evidence_id}",
        source_artifact="parsed/evidence_blocks.jsonl",
    )
