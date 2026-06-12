from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from antenna_ingest.orchestration.runs import create_run
from antenna_ingest.parsing.docling_text_parser import parse_run_with_docling


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="antenna-ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_run = subparsers.add_parser("init-run")
    init_run.add_argument("input_pdf", type=Path)
    init_run.add_argument("--runs-root", type=Path, default=Path("runs"))
    init_run.add_argument("--pipeline-version", default="0.1.0")
    init_run.add_argument("--paper-id")
    init_run.add_argument("--force", action="store_true")

    parse_docling = subparsers.add_parser("parse-docling")
    parse_docling.add_argument("run_dir", type=Path)
    parse_docling.add_argument("--force", action="store_true")

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

    if args.command == "parse-docling":
        report = parse_run_with_docling(run_dir=args.run_dir, force=args.force)
        run_dir = args.run_dir
        print(f"Parsed Markdown written to: {run_dir / report.outputs.markdown}")
        print(f"Parsed text written to: {run_dir / report.outputs.text}")
        print(f"Docling JSON written to: {run_dir / report.outputs.docling_json}")
        print(f"Evidence written to: {run_dir / report.outputs.evidence}")
        print(f"Parse report written to: {run_dir / 'parsed/parse_report.json'}")
        print(f"Tables written to: {run_dir / 'parsed/tables.json'}")
        print(f"Layout report written to: {run_dir / 'parsed/layout_report.json'}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
