from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from antenna_ingest.nuextract.doctor import run_nuextract_doctor
from antenna_ingest.nuextract.markdown_conversion import (
    DOCUMENT_MARKDOWN_PATH,
    MARKDOWN_REPORT_PATH,
    convert_run_pages_to_markdown,
    parse_pdf_to_markdown,
)
from antenna_ingest.nuextract.pdf_rendering import (
    PAGE_RENDER_REPORT_PATH,
    PAGES_DIR,
    render_run_pages,
)
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
    render_pages = nuextract_subparsers.add_parser("render-pages")
    render_pages.add_argument("run_dir", type=Path)
    render_pages.add_argument("--dpi", type=int, default=170)
    render_pages.add_argument("--force", action="store_true")
    markdown = nuextract_subparsers.add_parser("markdown")
    markdown.add_argument("run_dir", type=Path)
    markdown.add_argument("--force", action="store_true")
    parse_markdown = nuextract_subparsers.add_parser("parse-markdown")
    parse_markdown.add_argument("input_pdf", type=Path)
    parse_markdown.add_argument("--runs-root", type=Path, default=Path("runs"))
    parse_markdown.add_argument("--pipeline-version", default="0.1.0")
    parse_markdown.add_argument("--paper-id")
    parse_markdown.add_argument("--dpi", type=int, default=170)
    parse_markdown.add_argument("--force", action="store_true")

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

    if args.command == "nuextract" and args.nuextract_command == "render-pages":
        report = render_run_pages(
            run_dir=args.run_dir,
            dpi=args.dpi,
            force=args.force,
        )
        print(f"Rendered pages: {report.page_count}")
        print(f"Pages directory: {args.run_dir / PAGES_DIR}")
        print(f"Report: {args.run_dir / PAGE_RENDER_REPORT_PATH}")
        return 0

    if args.command == "nuextract" and args.nuextract_command == "markdown":
        report = convert_run_pages_to_markdown(
            run_dir=args.run_dir,
            force=args.force,
        )
        print(f"Markdown written to: {args.run_dir / DOCUMENT_MARKDOWN_PATH}")
        print(f"Report: {args.run_dir / MARKDOWN_REPORT_PATH}")
        print(f"Pages converted: {report.page_count}")
        print(f"Characters: {report.character_count}")
        return 0

    if args.command == "nuextract" and args.nuextract_command == "parse-markdown":
        context, report = parse_pdf_to_markdown(
            input_pdf=args.input_pdf,
            runs_root=args.runs_root,
            dpi=args.dpi,
            pipeline_version=args.pipeline_version,
            paper_id=args.paper_id,
            force=args.force,
        )
        print(f"Created run: {context.run_dir}")
        print(f"Markdown written to: {context.run_dir / DOCUMENT_MARKDOWN_PATH}")
        print(f"Report: {context.run_dir / MARKDOWN_REPORT_PATH}")
        print(f"Rendered/converted pages: {report.page_count}")
        print(f"Characters: {report.character_count}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
