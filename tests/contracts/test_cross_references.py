from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from antenna_ingest.contracts.antenna_results import AntennaResults
from antenna_ingest.contracts.paper_extraction import PaperExtraction


def test_duplicate_ids_fail(paper_extraction_data) -> None:
    data = deepcopy(paper_extraction_data)
    data["results"].append(deepcopy(data["results"][0]))

    with pytest.raises(ValidationError, match="duplicate IDs in results"):
        PaperExtraction.model_validate(data)


def test_unknown_design_fails(antenna_results_data) -> None:
    data = deepcopy(antenna_results_data)
    data["results"][0]["design_id"] = "unknown"

    with pytest.raises(ValidationError, match="unknown design"):
        AntennaResults.model_validate(data)


def test_unknown_or_incompatible_setup_fails(antenna_results_data) -> None:
    unknown = deepcopy(antenna_results_data)
    unknown["results"][0]["setup_id"] = "unknown"
    with pytest.raises(ValidationError, match="unknown setup"):
        AntennaResults.model_validate(unknown)

    incompatible = deepcopy(antenna_results_data)
    incompatible["results"][0]["setup_id"] = "setup_measurement"
    with pytest.raises(ValidationError, match="incompatible"):
        AntennaResults.model_validate(incompatible)


def test_missing_setup_is_valid_when_source_has_none(antenna_results_data) -> None:
    data = deepcopy(antenna_results_data)
    data["results"][0]["setup_id"] = None

    validated = AntennaResults.model_validate(data)

    assert validated.results[0].setup_id is None


def test_unknown_evidence_and_undeclared_page_fail(paper_extraction_data) -> None:
    unknown = deepcopy(paper_extraction_data)
    unknown["results"][0]["evidence_ids"] = ["unknown"]
    with pytest.raises(ValidationError, match="unknown evidence"):
        PaperExtraction.model_validate(unknown)

    undeclared_page = deepcopy(paper_extraction_data)
    undeclared_page["evidence_catalog"][0]["page_number"] = 3
    with pytest.raises(ValidationError, match="undeclared page"):
        PaperExtraction.model_validate(undeclared_page)


@pytest.mark.parametrize("relation_field", ["parent_design_id", "predecessor_design_id"])
def test_unknown_variant_relation_fails(
    paper_extraction_data,
    relation_field,
) -> None:
    data = deepcopy(paper_extraction_data)
    data["designs"][1][relation_field] = "unknown"
    expected_relation = "parent" if relation_field == "parent_design_id" else "predecessor"
    with pytest.raises(ValidationError, match=f"unknown {expected_relation}"):
        PaperExtraction.model_validate(data)


def test_unknown_architecture_page_fails(paper_extraction_data) -> None:
    unknown_page = deepcopy(paper_extraction_data)
    unknown_page["architecture_page_refs"] = [3]

    with pytest.raises(ValidationError, match="undeclared pages"):
        PaperExtraction.model_validate(unknown_page)


def test_result_requires_a_design_association(antenna_results_data) -> None:
    data = deepcopy(antenna_results_data)
    del data["results"][0]["design_id"]

    with pytest.raises(ValidationError, match="design_id"):
        AntennaResults.model_validate(data)


def test_conflict_and_missing_information_references_resolve(
    paper_extraction_data,
) -> None:
    bad_conflict = deepcopy(paper_extraction_data)
    bad_conflict["conflicts"][0]["related_refs"][0]["id"] = "unknown"
    with pytest.raises(ValidationError, match="unknown result reference"):
        PaperExtraction.model_validate(bad_conflict)

    bad_missing = deepcopy(paper_extraction_data)
    bad_missing["missing_information"][0]["related_refs"][0]["id"] = "unknown"
    with pytest.raises(ValidationError, match="unknown design reference"):
        PaperExtraction.model_validate(bad_missing)


def test_shared_records_allow_lossless_future_projection(
    paper_extraction_data,
    antenna_results_data,
) -> None:
    extraction = PaperExtraction.model_validate(paper_extraction_data)
    results = AntennaResults.model_validate(antenna_results_data)

    assert [item.model_dump(mode="json") for item in extraction.designs] == [
        item.model_dump(mode="json") for item in results.design_registry
    ]
    assert [item.model_dump(mode="json") for item in extraction.setups] == [
        item.model_dump(mode="json") for item in results.setups
    ]
    assert [item.model_dump(mode="json") for item in extraction.results] == [
        item.model_dump(mode="json") for item in results.results
    ]
    assert [
        item.model_dump(mode="json") for item in extraction.evidence_catalog
    ] == [item.model_dump(mode="json") for item in results.evidence_catalog]

    serialized_results = [
        item.model_dump(mode="json") for item in results.results
    ]
    assert serialized_results[0]["representation"]["value"]["value"] == "47.98"
    assert serialized_results[1]["representation"]["points"][0]["x"][
        "value"
    ] == "2.450"
