from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from antenna_ingest.extraction.full_document import (
    EXTRACTION_VALIDATION_PATH,
    PAPER_EXTRACTION_PATH,
    extract_paper_from_run,
)
from antenna_ingest.models.doctor import run_endpoint_doctor
from antenna_ingest.orchestration.runs import create_run
from antenna_ingest.rendering import (
    PAGE_RENDER_REPORT_PATH,
    PAGES_DIR,
    render_run_pages,
)
from antenna_ingest.settings import ModelRole


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="antenna-ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_run = subparsers.add_parser("init-run")
    init_run.add_argument("input_pdf", type=Path)
    init_run.add_argument("--runs-root", type=Path, default=Path("runs"))
    init_run.add_argument("--pipeline-version", default="0.1.0")
    init_run.add_argument("--paper-id")
    init_run.add_argument("--force", action="store_true")

    render_pages = subparsers.add_parser("render-pages")
    render_pages.add_argument("run_dir", type=Path)
    render_pages.add_argument("--dpi", type=int, default=170)
    render_pages.add_argument("--force", action="store_true")

    extract_paper = subparsers.add_parser("extract-paper")
    extract_paper.add_argument("run_dir", type=Path)
    thinking = extract_paper.add_mutually_exclusive_group(required=True)
    thinking.add_argument(
        "--thinking",
        dest="enable_thinking",
        action="store_true",
    )
    thinking.add_argument(
        "--no-thinking",
        dest="enable_thinking",
        action="store_false",
    )
    extract_paper.add_argument("--force", action="store_true")

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument(
        "model_role",
        choices=[role.value for role in ModelRole],
    )

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

    if args.command == "render-pages":
        report = render_run_pages(
            run_dir=args.run_dir,
            dpi=args.dpi,
            force=args.force,
        )
        print(f"Rendered pages: {report.page_count}")
        print(f"Pages directory: {args.run_dir / PAGES_DIR}")
        print(f"Report: {args.run_dir / PAGE_RENDER_REPORT_PATH}")
        return 0

    if args.command == "extract-paper":
        extract_paper_from_run(
            run_dir=args.run_dir,
            enable_thinking=args.enable_thinking,
            force=args.force,
        )
        print(f"Extraction: {args.run_dir / PAPER_EXTRACTION_PATH}")
        print(f"Validation: {args.run_dir / EXTRACTION_VALIDATION_PATH}")
        return 0

    if args.command == "doctor":
        result = run_endpoint_doctor(ModelRole(args.model_role))
        print(f"Base URL: {result.base_url}")
        print(f"Model role: {result.model_role.value}")
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
