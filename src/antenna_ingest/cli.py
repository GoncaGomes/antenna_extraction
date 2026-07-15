from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from antenna_ingest.canonicalization.canonicalize import (
    CANONICAL_DESIGN_RECORD_PATH,
    CANONICALIZATION_REPORT_PATH,
    canonicalize_run,
)
from antenna_ingest.evidence.blocks import (
    EVIDENCE_BLOCKS_PATH,
    EVIDENCE_BLOCKS_REPORT_PATH,
    build_evidence_blocks_from_run,
)
from antenna_ingest.evidence.tables import (
    TABLES_PATH,
    TABLES_REPORT_PATH,
    extract_tables_from_run,
)
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
from antenna_ingest.nuextract.raw_extraction import (
    ANTENNA_CANDIDATE_PATH,
    EXTRACTION_REPORT_PATH,
    extract_antenna_candidate_from_run,
    parse_pdf_to_candidate,
)
from antenna_ingest.orchestration.runs import create_run
from antenna_ingest.retrieval.index import (
    EVIDENCE_INDEX_PATH,
    EVIDENCE_INDEX_REPORT_PATH,
    build_evidence_index_from_run,
)
from antenna_ingest.retrieval.search import search_evidence_index


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
    evidence_blocks = nuextract_subparsers.add_parser("evidence-blocks")
    evidence_blocks.add_argument("run_dir", type=Path)
    evidence_blocks.add_argument("--force", action="store_true")
    extract_tables = nuextract_subparsers.add_parser("extract-tables")
    extract_tables.add_argument("run_dir", type=Path)
    extract_tables.add_argument("--force", action="store_true")
    parse_markdown = nuextract_subparsers.add_parser("parse-markdown")
    parse_markdown.add_argument("input_pdf", type=Path)
    parse_markdown.add_argument("--runs-root", type=Path, default=Path("runs"))
    parse_markdown.add_argument("--pipeline-version", default="0.1.0")
    parse_markdown.add_argument("--paper-id")
    parse_markdown.add_argument("--dpi", type=int, default=170)
    parse_markdown.add_argument("--force", action="store_true")
    extract_candidate = nuextract_subparsers.add_parser("extract-candidate")
    extract_candidate.add_argument("run_dir", type=Path)
    extract_candidate.add_argument("--force", action="store_true")
    extract_candidate.add_argument("--temperature", type=float, default=0.0)
    extract_candidate.add_argument("--max-tokens", type=int)
    extract_candidate.add_argument(
        "--enable-thinking",
        dest="enable_thinking",
        action="store_true",
        default=True,
    )
    extract_candidate.add_argument(
        "--disable-thinking",
        dest="enable_thinking",
        action="store_false",
    )
    parse_candidate = nuextract_subparsers.add_parser("parse-candidate")
    parse_candidate.add_argument("input_pdf", type=Path)
    parse_candidate.add_argument("--runs-root", type=Path, default=Path("runs"))
    parse_candidate.add_argument("--paper-id")
    parse_candidate.add_argument("--dpi", type=int, default=170)
    parse_candidate.add_argument("--force", action="store_true")
    parse_candidate.add_argument("--temperature", type=float, default=0.0)
    parse_candidate.add_argument("--max-tokens", type=int)
    parse_candidate.add_argument(
        "--enable-thinking",
        dest="enable_thinking",
        action="store_true",
        default=True,
    )
    parse_candidate.add_argument(
        "--disable-thinking",
        dest="enable_thinking",
        action="store_false",
    )
    parse_all = nuextract_subparsers.add_parser("parse-all")
    parse_all.add_argument("input_pdf", type=Path)
    parse_all.add_argument("--runs-root", type=Path, default=Path("runs"))
    parse_all.add_argument("--pipeline-version", default="0.1.0")
    parse_all.add_argument("--paper-id")
    parse_all.add_argument("--dpi", type=int, default=170)
    parse_all.add_argument("--force", action="store_true")
    parse_all.add_argument("--temperature", type=float, default=0.0)
    parse_all.add_argument("--max-tokens", type=int)
    parse_all.add_argument(
        "--enable-thinking",
        dest="enable_thinking",
        action="store_true",
        default=True,
    )
    parse_all.add_argument(
        "--disable-thinking",
        dest="enable_thinking",
        action="store_false",
    )

    retrieval = subparsers.add_parser("retrieval")
    retrieval_subparsers = retrieval.add_subparsers(
        dest="retrieval_command",
        required=True,
    )
    build_index = retrieval_subparsers.add_parser("build-index")
    build_index.add_argument("run_dir", type=Path)
    build_index.add_argument("--force", action="store_true")
    search = retrieval_subparsers.add_parser("search")
    search.add_argument("run_dir", type=Path)
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=5)
    search.add_argument("--context-window", type=int, default=0)
    search.add_argument("--write-trace", action="store_true")

    canonicalization = subparsers.add_parser("canonicalization")
    canonicalization_subparsers = canonicalization.add_subparsers(
        dest="canonicalization_command",
        required=True,
    )
    canonicalization_run = canonicalization_subparsers.add_parser("run")
    canonicalization_run.add_argument("run_dir", type=Path)
    canonicalization_run.add_argument("--force", action="store_true")
    canonicalization_run.add_argument("--max-tool-calls", type=int, default=12)

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

    if args.command == "nuextract" and args.nuextract_command == "evidence-blocks":
        report = build_evidence_blocks_from_run(
            run_dir=args.run_dir,
            force=args.force,
        )
        print(f"Evidence blocks: {args.run_dir / EVIDENCE_BLOCKS_PATH}")
        print(f"Report: {args.run_dir / EVIDENCE_BLOCKS_REPORT_PATH}")
        print(f"Blocks: {report.block_count}")
        return 0

    if args.command == "nuextract" and args.nuextract_command == "extract-tables":
        report = extract_tables_from_run(
            run_dir=args.run_dir,
            force=args.force,
        )
        print(f"Tables: {args.run_dir / TABLES_PATH}")
        print(f"Report: {args.run_dir / TABLES_REPORT_PATH}")
        print(f"Tables found: {report.table_count}")
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

    if args.command == "nuextract" and args.nuextract_command == "extract-candidate":
        extract_antenna_candidate_from_run(
            run_dir=args.run_dir,
            force=args.force,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            enable_thinking=args.enable_thinking,
        )
        print(f"Candidate: {args.run_dir / ANTENNA_CANDIDATE_PATH}")
        print(f"Report: {args.run_dir / EXTRACTION_REPORT_PATH}")
        return 0

    if args.command == "nuextract" and args.nuextract_command == "parse-candidate":
        context, _candidate, _report = parse_pdf_to_candidate(
            input_pdf=args.input_pdf,
            runs_root=args.runs_root,
            paper_id=args.paper_id,
            dpi=args.dpi,
            force=args.force,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            enable_thinking=args.enable_thinking,
        )
        print(f"Created run: {context.run_dir}")
        print(f"Candidate: {context.run_dir / ANTENNA_CANDIDATE_PATH}")
        print(f"Report: {context.run_dir / EXTRACTION_REPORT_PATH}")
        return 0

    if args.command == "retrieval" and args.retrieval_command == "build-index":
        report = build_evidence_index_from_run(
            run_dir=args.run_dir,
            force=args.force,
        )
        print(f"Evidence index: {args.run_dir / EVIDENCE_INDEX_PATH}")
        print(f"Report: {args.run_dir / EVIDENCE_INDEX_REPORT_PATH}")
        print(f"Items: {report.item_count}")
        return 0

    if args.command == "retrieval" and args.retrieval_command == "search":
        response = search_evidence_index(
            run_dir=args.run_dir,
            query=args.query,
            top_k=args.top_k,
            context_window=args.context_window,
            write_trace=args.write_trace,
        )
        print(f"Query: {response.query}")
        print(f"Results: {response.result_count}")
        for rank, result in enumerate(response.results, start=1):
            print()
            print(
                f"[{rank}] {result.evidence_id} | {result.source_type} | "
                f"page {result.page} | score {result.score:.2f}"
            )
            print(f"Reasons: {', '.join(result.match_reasons) or 'none'}")
            if result.caption:
                print(f"Caption: {result.caption}")
            print("Text:")
            text = result.text[:600]
            if len(result.text) > 600:
                text += "..."
            print(text)
        return 0

    if (
        args.command == "canonicalization"
        and args.canonicalization_command == "run"
    ):
        _record, report = canonicalize_run(
            run_dir=args.run_dir,
            force=args.force,
            max_tool_calls=args.max_tool_calls,
        )
        print(f"Canonical design: {args.run_dir / CANONICAL_DESIGN_RECORD_PATH}")
        print(f"Validation report: {args.run_dir / CANONICALIZATION_REPORT_PATH}")
        print(f"Validation: {'valid' if report.valid else 'invalid'}")
        print(f"Objects: {report.object_count}")
        print(f"Materials: {report.material_count}")
        print(f"Relationships: {report.relationship_count}")
        print(f"Excitations: {report.excitation_count}")
        return 0

    if args.command == "nuextract" and args.nuextract_command == "parse-all":
        context = create_run(
            input_pdf=args.input_pdf,
            runs_root=args.runs_root,
            force=args.force,
            pipeline_version=args.pipeline_version,
            paper_id=args.paper_id,
        )
        render_report = render_run_pages(
            run_dir=context.run_dir,
            dpi=args.dpi,
            force=args.force,
        )
        markdown_report = convert_run_pages_to_markdown(
            run_dir=context.run_dir,
            force=args.force,
        )
        evidence_report = build_evidence_blocks_from_run(
            run_dir=context.run_dir,
            force=args.force,
        )
        tables_report = extract_tables_from_run(
            run_dir=context.run_dir,
            force=args.force,
        )
        build_evidence_index_from_run(
            run_dir=context.run_dir,
            force=args.force,
        )
        extract_antenna_candidate_from_run(
            run_dir=context.run_dir,
            force=args.force,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            enable_thinking=args.enable_thinking,
        )
        print(f"Created run: {context.run_dir}")
        print(f"Rendered pages: {render_report.page_count}")
        print(f"Markdown written to: {context.run_dir / DOCUMENT_MARKDOWN_PATH}")
        print(f"Markdown report: {context.run_dir / MARKDOWN_REPORT_PATH}")
        print(f"Characters: {markdown_report.character_count}")
        print(f"Evidence blocks: {context.run_dir / EVIDENCE_BLOCKS_PATH}")
        print(
            "Evidence blocks report: "
            f"{context.run_dir / EVIDENCE_BLOCKS_REPORT_PATH}"
        )
        print(f"Blocks: {evidence_report.block_count}")
        print(f"Tables: {context.run_dir / TABLES_PATH}")
        print(f"Tables report: {context.run_dir / TABLES_REPORT_PATH}")
        print(f"Tables found: {tables_report.table_count}")
        print(f"Evidence index: {context.run_dir / EVIDENCE_INDEX_PATH}")
        print(
            "Evidence index report: "
            f"{context.run_dir / EVIDENCE_INDEX_REPORT_PATH}"
        )
        print(f"Candidate: {context.run_dir / ANTENNA_CANDIDATE_PATH}")
        print(f"Extraction report: {context.run_dir / EXTRACTION_REPORT_PATH}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
