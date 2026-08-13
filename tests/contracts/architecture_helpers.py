from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path


FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "contracts"
    / "minimal_antenna_architecture.json"
)


def architecture_data() -> dict:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    data["provenance"]["generated_at"] = datetime.fromisoformat(
        data["provenance"]["generated_at"].replace("Z", "+00:00")
    )
    return data


def empty_architecture() -> dict:
    data = architecture_data()
    data["parameters"] = []
    data["materials"] = []
    data["blocks"] = []
    data["relationships"] = []
    data["ports_and_excitations"] = []
    data["derivations"] = []
    data["unresolved_items"] = []
    data["proposed_completions"] = []
    return data


def zero() -> dict:
    return {"kind": "zero"}


def component(parameter_id: str) -> dict:
    return {"kind": "parameter", "parameter_id": parameter_id}


def parameter_ref(parameter_id: str) -> dict:
    return {"parameter_id": parameter_id}


def point2(x: str | None = None, y: str | None = None) -> dict:
    return {
        "x": zero() if x is None else component(x),
        "y": zero() if y is None else component(y),
    }


def point3(
    x: str | None = None,
    y: str | None = None,
    z: str | None = None,
) -> dict:
    return {
        "x": zero() if x is None else component(x),
        "y": zero() if y is None else component(y),
        "z": zero() if z is None else component(z),
    }


def identity_transform() -> dict:
    return {
        "translation": point3(),
        "rotation": point3(),
    }


def reported_parameter(
    parameter_id: str,
    quantity_kind: str,
    affected_kind: str,
    affected_id: str,
    *,
    value: str = "1.0",
    unit: str | None = None,
    source_symbol: str | None = None,
) -> dict:
    return {
        "parameter_id": parameter_id,
        "name": parameter_id.replace("_", " "),
        "source_symbol": source_symbol,
        "quantity_kind": quantity_kind,
        "definition": {
            "kind": "reported",
            "value": {
                "value": value,
                "unit": unit,
                "qualifier": None,
                "legibility": "clear",
            },
            "origin": "reported_visual",
            "evidence_ids": ["ev_geometry"],
        },
        "affected_refs": [{"kind": affected_kind, "id": affected_id}],
    }


def block(
    block_id: str,
    geometry: dict,
    dependencies: list[str],
    *,
    role: str = "other",
    state: str = "physical",
    material_id: str | None = None,
    placement: dict | None = None,
    unresolved_item_ids: list[str] | None = None,
) -> dict:
    return {
        "block_id": block_id,
        "name": block_id.replace("_", " "),
        "role": role,
        "state": state,
        "material_id": material_id,
        "geometry": deepcopy(geometry),
        "placement": identity_transform() if placement is None else placement,
        "parameter_dependencies": list(dependencies),
        "evidence_ids": ["ev_geometry"],
        "derivation_ids": [],
        "unresolved_item_ids": list(unresolved_item_ids or []),
    }


def material(material_id: str, identity: str = "Reported material") -> dict:
    return {
        "material_id": material_id,
        "reported_identity": identity,
        "evidence_ids": ["ev_material"],
        "property_claims": [],
    }
