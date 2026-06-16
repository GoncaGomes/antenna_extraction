from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from antenna_ingest.nuextract.doctor import run_nuextract_doctor
from antenna_ingest.orchestration.runs import create_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="antenna-ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_run = subparsers.add_parser("init-run")
    init_run.add_argument("input_pdf", type=Path)
    init_run.add_argument("--runs-root", type=Path, default=Path("runs"))
    init_run.add_argument("--pipeline-version", default="0.1.0")
    init_run.add_argument("--paper-id")
    init_run.add_argument("--force", action="store_true")

    nuextract = subparsers.add_parser("nuextract")
    nuextract_subparsers = nuextract.add_subparsers(
        dest="nuextract_command",
        required=True,
    )
    nuextract_subparsers.add_parser("doctor")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-run":
        context = create_run(
            input_pdf=args.input_pdf,
            runs_root=args.runs_root,
            force=args.force,
            pipeline_version=args.pipeline_version,
            paper_id=args.paper_id,
        )
        print(f"Created run: {context.run_dir}")
        print(f"Manifest: {context.run_dir / 'manifest.json'}")
        return 0

    if args.command == "nuextract" and args.nuextract_command == "doctor":
        result = run_nuextract_doctor()
        print(f"Base URL: {result.base_url}")
        print(f"Model: {result.model}")
        if result.ok:
            print("Status: OK")
            print(f"Response: {result.response_text}")
            return 0
        print("Status: FAILED")
        print(f"Error: {result.error}")
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
