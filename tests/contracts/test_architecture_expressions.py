from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from antenna_ingest.contracts.antenna_architecture import AntennaArchitecture
from antenna_ingest.contracts.expressions import (
    QUANTITY_DIMENSIONS,
    ExpressionError,
    expression_dimension,
    expression_identifiers,
)
from architecture_helpers import reported_parameter


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2 * x", {"x"}),
        ("sqrt(y * y - x * x)", {"x", "y"}),
        ("2 * pi * radius", {"radius"}),
        ("-(x / 2) + +x", {"x"}),
    ],
)
def test_safe_expression_vocabulary(expression, expected) -> None:
    assert expression_identifiers(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "x ** 2",
        "x % 2",
        "sin(x)",
        "sqrt(value=x)",
        "sqrt(x, x)",
        "obj.value",
        "items[0]",
        "[x]",
        "x > 0",
        "x and y",
        "1e309",
    ],
)
def test_unsafe_expression_syntax_is_rejected(expression) -> None:
    with pytest.raises(ExpressionError):
        expression_identifiers(expression)


def _add_derived_parameter(
    data: dict,
    *,
    parameter_id: str,
    quantity_kind: str,
    expression: str,
    bindings: list[tuple[str, str]],
) -> None:
    derivation_id = f"derive_{parameter_id}"
    data["parameters"].append(
        {
            "parameter_id": parameter_id,
            "name": parameter_id,
            "source_symbol": None,
            "quantity_kind": quantity_kind,
            "definition": {
                "kind": "derived",
                "derivation_id": derivation_id,
            },
            "affected_refs": [{"kind": "derivation", "id": derivation_id}],
        }
    )
    data["derivations"].append(
        {
            "derivation_id": derivation_id,
            "target_parameter_id": parameter_id,
            "expression": expression,
            "bindings": [
                {"name": name, "parameter_id": source_id}
                for name, source_id in bindings
            ],
            "explanation": "Source-grounded synthetic derivation.",
            "evidence_ids": ["ev_geometry"],
        }
    )


@pytest.mark.parametrize(
    ("target", "expression", "bindings"),
    [
        ("base", "2 * x", [("x", "width")]),
        ("diagonal", "sqrt(y * y - x * x)", [("x", "height"), ("y", "width")]),
        ("circumference", "2 * pi * radius", [("radius", "width")]),
    ],
)
def test_required_derivations_are_dimensionally_valid(
    antenna_architecture_data,
    target,
    expression,
    bindings,
) -> None:
    data = deepcopy(antenna_architecture_data)
    _add_derived_parameter(
        data,
        parameter_id=target,
        quantity_kind="length",
        expression=expression,
        bindings=bindings,
    )

    architecture = AntennaArchitecture.model_validate(data)
    derivation = architecture.derivations[-1]
    assert derivation.expression == expression


def test_expression_bindings_are_exact_and_ascii(
    antenna_architecture_data,
) -> None:
    missing = deepcopy(antenna_architecture_data)
    _add_derived_parameter(
        missing,
        parameter_id="base",
        quantity_kind="length",
        expression="2 * x",
        bindings=[],
    )
    with pytest.raises(ValidationError, match="missing expression binding"):
        AntennaArchitecture.model_validate(missing)

    unused = deepcopy(antenna_architecture_data)
    _add_derived_parameter(
        unused,
        parameter_id="base",
        quantity_kind="length",
        expression="2 * x",
        bindings=[("x", "width"), ("unused", "height")],
    )
    with pytest.raises(ValidationError, match="unused expression binding"):
        AntennaArchitecture.model_validate(unused)

    unicode_binding = deepcopy(antenna_architecture_data)
    _add_derived_parameter(
        unicode_binding,
        parameter_id="base",
        quantity_kind="length",
        expression="2 * λ",
        bindings=[("λ", "width")],
    )
    with pytest.raises(ValidationError):
        AntennaArchitecture.model_validate(unicode_binding)


def test_incompatible_dimensions_and_unresolved_inputs_fail(
    antenna_architecture_data,
) -> None:
    incompatible = deepcopy(antenna_architecture_data)
    incompatible["parameters"].append(
        reported_parameter(
            "angle",
            "angle",
            "block",
            "radiator",
            unit="degree",
        )
    )
    _add_derived_parameter(
        incompatible,
        parameter_id="invalid_sum",
        quantity_kind="length",
        expression="width + angle",
        bindings=[("width", "width"), ("angle", "angle")],
    )
    with pytest.raises(ValidationError, match="equal dimensions"):
        AntennaArchitecture.model_validate(incompatible)

    unresolved = deepcopy(antenna_architecture_data)
    unresolved["status"]["reconstruction_status"] = "incomplete"
    unresolved["unresolved_items"] = [
        {
            "unresolved_item_id": "missing_x",
            "category": "parameter",
            "description": "x is missing",
            "criticality": "reconstruction_critical",
            "affected_refs": [{"kind": "parameter", "id": "x"}],
            "evidence_ids": [],
        }
    ]
    unresolved["parameters"].append(
        {
            "parameter_id": "x",
            "name": "x",
            "source_symbol": "x",
            "quantity_kind": "length",
            "definition": {
                "kind": "unresolved",
                "unresolved_item_id": "missing_x",
            },
            "affected_refs": [{"kind": "block", "id": "radiator"}],
        }
    )
    _add_derived_parameter(
        unresolved,
        parameter_id="base",
        quantity_kind="length",
        expression="2 * x",
        bindings=[("x", "x")],
    )
    with pytest.raises(ValidationError, match="unresolved parameter"):
        AntennaArchitecture.model_validate(unresolved)


def test_parameter_dependency_cycles_fail(antenna_architecture_data) -> None:
    data = deepcopy(antenna_architecture_data)
    _add_derived_parameter(
        data,
        parameter_id="a",
        quantity_kind="length",
        expression="b",
        bindings=[("b", "b")],
    )
    _add_derived_parameter(
        data,
        parameter_id="b",
        quantity_kind="length",
        expression="a",
        bindings=[("a", "a")],
    )

    with pytest.raises(ValidationError, match="parameter dependency cycle"):
        AntennaArchitecture.model_validate(data)


def test_dimension_helper_does_not_evaluate_numeric_values() -> None:
    assert expression_dimension(
        "sqrt(x * x)",
        {"x": QUANTITY_DIMENSIONS["length"]},
    ) == QUANTITY_DIMENSIONS["length"]
