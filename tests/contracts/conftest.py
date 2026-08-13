from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest


FIXTURE_DIRECTORY = Path(__file__).parents[1] / "fixtures" / "contracts"


@pytest.fixture
def paper_extraction_data() -> dict:
    return _load_fixture("minimal_paper_extraction.json")


@pytest.fixture
def antenna_results_data() -> dict:
    return _load_fixture("minimal_antenna_results.json")


@pytest.fixture
def antenna_architecture_data() -> dict:
    return _load_fixture("minimal_antenna_architecture.json")


def _load_fixture(filename: str) -> dict:
    data = json.loads((FIXTURE_DIRECTORY / filename).read_text(encoding="utf-8"))
    provenance = data.get("provenance")
    if provenance is not None:
        provenance["generated_at"] = datetime.fromisoformat(
            provenance["generated_at"].replace("Z", "+00:00")
        )
    return data
