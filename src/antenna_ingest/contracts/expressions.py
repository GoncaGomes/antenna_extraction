from __future__ import annotations

import ast
import math
import re
from collections.abc import Mapping
from typing import TypeAlias


Dimension: TypeAlias = tuple[int, int, int, int]

DIMENSIONLESS: Dimension = (0, 0, 0, 0)
QUANTITY_DIMENSIONS: dict[str, Dimension] = {
    "length": (1, 0, 0, 0),
    "angle": (0, 1, 0, 0),
    "frequency": (0, 0, 1, 0),
    "impedance": (0, 0, 0, 1),
    "dimensionless": DIMENSIONLESS,
}

_BINDING_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ExpressionError(ValueError):
    """Raised when a bounded derivation expression is invalid."""


def validate_binding_name(name: str) -> str:
    if name == "pi" or not _BINDING_PATTERN.fullmatch(name):
        raise ExpressionError(
            "binding names must be ASCII identifiers and cannot be 'pi'"
        )
    return name


def expression_identifiers(expression: str) -> frozenset[str]:
    tree = _parse_expression(expression)
    identifiers: set[str] = set()
    _validate_node(tree.body, identifiers)
    return frozenset(identifiers)


def expression_dimension(
    expression: str,
    binding_dimensions: Mapping[str, Dimension],
) -> Dimension:
    identifiers = expression_identifiers(expression)
    supplied = set(binding_dimensions)
    if supplied != set(identifiers):
        missing = sorted(set(identifiers) - supplied)
        unused = sorted(supplied - set(identifiers))
        details: list[str] = []
        if missing:
            details.append(f"missing bindings: {', '.join(missing)}")
        if unused:
            details.append(f"unused bindings: {', '.join(unused)}")
        raise ExpressionError("; ".join(details))

    tree = _parse_expression(expression)
    return _dimension_of(tree.body, binding_dimensions)


def _parse_expression(expression: str) -> ast.Expression:
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise ExpressionError("invalid expression syntax") from exc
    if not isinstance(tree, ast.Expression):
        raise ExpressionError("expression must contain one value")
    return tree


def _validate_node(node: ast.AST, identifiers: set[str]) -> None:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ExpressionError("only finite numeric constants are allowed")
        if not math.isfinite(float(node.value)):
            raise ExpressionError("numeric constants must be finite")
        return

    if isinstance(node, ast.Name):
        if node.id == "pi":
            return
        if not _BINDING_PATTERN.fullmatch(node.id):
            raise ExpressionError("expression identifiers must be ASCII bindings")
        identifiers.add(node.id)
        return

    if isinstance(node, ast.BinOp) and isinstance(
        node.op,
        (ast.Add, ast.Sub, ast.Mult, ast.Div),
    ):
        _validate_node(node.left, identifiers)
        _validate_node(node.right, identifiers)
        return

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        _validate_node(node.operand, identifiers)
        return

    if isinstance(node, ast.Call):
        if (
            not isinstance(node.func, ast.Name)
            or node.func.id != "sqrt"
            or len(node.args) != 1
            or node.keywords
        ):
            raise ExpressionError("only sqrt(value) is allowed")
        _validate_node(node.args[0], identifiers)
        return

    raise ExpressionError(f"unsupported expression syntax: {type(node).__name__}")


def _dimension_of(
    node: ast.AST,
    binding_dimensions: Mapping[str, Dimension],
) -> Dimension:
    if isinstance(node, ast.Constant):
        return DIMENSIONLESS
    if isinstance(node, ast.Name):
        if node.id == "pi":
            return DIMENSIONLESS
        return binding_dimensions[node.id]
    if isinstance(node, ast.UnaryOp):
        return _dimension_of(node.operand, binding_dimensions)
    if isinstance(node, ast.BinOp):
        left = _dimension_of(node.left, binding_dimensions)
        right = _dimension_of(node.right, binding_dimensions)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            if left != right:
                raise ExpressionError(
                    "addition and subtraction require equal dimensions"
                )
            return left
        if isinstance(node.op, ast.Mult):
            return tuple(a + b for a, b in zip(left, right, strict=True))
        if isinstance(node.op, ast.Div):
            return tuple(a - b for a, b in zip(left, right, strict=True))
    if isinstance(node, ast.Call):
        argument = _dimension_of(node.args[0], binding_dimensions)
        if any(exponent % 2 != 0 for exponent in argument):
            raise ExpressionError("sqrt requires even dimension exponents")
        return tuple(exponent // 2 for exponent in argument)
    raise ExpressionError("unsupported expression syntax")
