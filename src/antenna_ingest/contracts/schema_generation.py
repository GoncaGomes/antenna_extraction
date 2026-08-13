from __future__ import annotations

import json
from pathlib import Path
from typing import TypeAlias

from antenna_ingest.contracts.antenna_architecture import AntennaArchitecture
from antenna_ingest.contracts.antenna_results import AntennaResults
from antenna_ingest.contracts.base import ContractModel
from antenna_ingest.contracts.paper_extraction import PaperExtraction


ContractType: TypeAlias = type[ContractModel]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCHEMA_DIRECTORY = REPOSITORY_ROOT / "schemas" / "generated"
SCHEMA_MODELS: tuple[tuple[str, ContractType], ...] = (
    ("paper_extraction.schema.json", PaperExtraction),
    ("antenna_results.schema.json", AntennaResults),
    ("antenna_architecture.schema.json", AntennaArchitecture),
)


def render_json_schema(model: ContractType) -> bytes:
    schema = model.model_json_schema(mode="validation")
    rendered = json.dumps(
        schema,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return f"{rendered}\n".encode()


def generate_json_schemas(
    output_directory: Path = DEFAULT_SCHEMA_DIRECTORY,
) -> list[Path]:
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    generated_paths: list[Path] = []
    for filename, model in SCHEMA_MODELS:
        output_path = output_directory / filename
        output_path.write_bytes(render_json_schema(model))
        generated_paths.append(output_path)
    return generated_paths


def main() -> int:
    for path in generate_json_schemas():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
