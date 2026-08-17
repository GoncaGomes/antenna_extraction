from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from antenna_ingest.contracts.common import SourceValue
from antenna_ingest.contracts.paper_extraction import (
    GeometryObservation,
    PaperExtraction,
)


FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "contracts"
    / "minimal_paper_extraction.json"
)


def test_json_fixture_validates_at_the_serialized_boundary() -> None:
    validated = PaperExtraction.model_validate_json(
        FIXTURE_PATH.read_text(encoding="utf-8")
    )

    assert validated.schema_name == "paper_extraction"
    assert validated.schema_version == "1.0.0"


def test_synthetic_paper_extraction_validates_and_preserves_source_lexemes(
    paper_extraction_data,
) -> None:
    extraction = PaperExtraction.model_validate(paper_extraction_data)

    scalar = extraction.results[0].representation
    series = extraction.results[1].representation
    assert scalar.value.value == "47.98"
    assert scalar.value.unit == "ohm"
    assert series.points[0].x.value == "2.450"
    assert series.points[0].y.qualifier == "<"
    assert series.points[0].y.value == "-10"
    assert extraction.feed_port_excitation_observations[0].reported_impedance is None

    dumped = extraction.model_dump(mode="json")
    assert dumped["results"][0]["representation"]["value"]["value"] == "47.98"
    assert dumped["results"][1]["representation"]["points"][0]["x"]["value"] == "2.450"


def test_source_values_require_available_non_empty_lexemes() -> None:
    approximate = SourceValue(
        value="50",
        unit="Ω",
        qualifier="≈",
        legibility="clear",
    )

    assert approximate.model_dump(mode="json") == {
        "value": "50",
        "unit": "Ω",
        "qualifier": "≈",
        "legibility": "clear",
    }
    with pytest.raises(ValidationError):
        SourceValue(value="", unit="dB", legibility="clear")
    with pytest.raises(ValidationError):
        SourceValue(value=None, unit="dB", legibility="clear")
    with pytest.raises(ValidationError):
        SourceValue(value="2.45", unit="GHz", legibility="missing")
    with pytest.raises(ValidationError):
        SourceValue(value="2.45", unit="GHz", legibility="illegible")
    with pytest.raises(ValidationError) as exc_info:
        SourceValue(value="2.45", unit="GHz")

    error = exc_info.value.errors()[0]
    assert error["loc"] == ("legibility",)
    assert error["type"] == "missing"


def test_source_value_legibility_accepts_only_clear_or_uncertain() -> None:
    clear = SourceValue(value="2.45", legibility="clear")
    uncertain = SourceValue(value="2.45", legibility="uncertain")

    assert clear.legibility == "clear"
    assert uncertain.legibility == "uncertain"


def test_contracts_reject_unknown_fields_and_type_coercion(
    paper_extraction_data,
) -> None:
    top_level = deepcopy(paper_extraction_data)
    top_level["unexpected"] = True
    with pytest.raises(ValidationError):
        PaperExtraction.model_validate(top_level)

    nested = deepcopy(paper_extraction_data)
    nested["results"][0]["representation"]["value"]["unexpected"] = True
    with pytest.raises(ValidationError):
        PaperExtraction.model_validate(nested)

    coerced = deepcopy(paper_extraction_data)
    coerced["document"]["page_count"] = "2"
    with pytest.raises(ValidationError):
        PaperExtraction.model_validate(coerced)

    numeric_source_value = deepcopy(paper_extraction_data)
    numeric_source_value["results"][0]["representation"]["value"]["value"] = 47.98
    with pytest.raises(ValidationError):
        PaperExtraction.model_validate(numeric_source_value)

    missing_version = deepcopy(paper_extraction_data)
    del missing_version["schema_version"]
    with pytest.raises(ValidationError):
        PaperExtraction.model_validate(missing_version)


def test_geometry_observation_is_source_oriented_not_constructive() -> None:
    field_names = set(GeometryObservation.model_fields)

    assert field_names == {
        "observation_id",
        "design_id",
        "description",
        "evidence_ids",
        "legibility",
        "uncertainty_note",
        "source_feature_label",
    }
    assert (
        not {
            "blocks",
            "placement",
            "faces",
            "boolean_operations",
            "solver_commands",
            "expression",
        }
        & field_names
    )
