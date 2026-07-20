from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from antenna_ingest.orchestration.runs import load_run_manifest
from antenna_ingest.utils.json_io import write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze metadata for existing pipeline runs.",
    )
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--benchmark-id", default="antenna_ingest_v1")
    return parser


def build_benchmark_manifest(
    run_dirs: Sequence[Path],
    *,
    benchmark_id: str,
) -> dict:
    runs = []
    for supplied_path in run_dirs:
        run_dir = Path(supplied_path)
        if not run_dir.is_dir():
            raise ValueError(f"run directory does not exist: {run_dir}")
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"run manifest does not exist: {manifest_path}")
        try:
            manifest = load_run_manifest(manifest_path)
        except Exception as error:
            raise ValueError(
                f"run manifest is not readable: {manifest_path}: {error}"
            ) from error

        canonicalization = manifest.phases.get("canonicalization")
        runs.append(
            {
                "run_id": manifest.run_id,
                "paper_id": manifest.paper_id,
                "document_id": manifest.document_id,
                "input_filename": Path(manifest.input_file).name,
                "input_sha256": manifest.input_sha256,
                "pipeline_version": manifest.pipeline_version,
                "canonicalization_phase_result": (
                    canonicalization.status.value
                    if canonicalization is not None
                    else None
                ),
                "source_run_path": _relative_source_path(run_dir),
            }
        )
    return {
        "benchmark_id": benchmark_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runs": runs,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = build_benchmark_manifest(
            args.run_dirs,
            benchmark_id=args.benchmark_id,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    write_json(args.output, manifest)
    print(f"Benchmark manifest: {args.output}")
    print(f"Runs: {len(manifest['runs'])}")
    return 0


def _relative_source_path(run_dir: Path) -> str:
    relative = os.path.relpath(run_dir.resolve(), Path.cwd().resolve())
    return Path(relative).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
