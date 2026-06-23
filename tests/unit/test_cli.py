from __future__ import annotations

from pathlib import Path

from antenna_ingest.cli import build_parser


def test_extract_candidate_command_parses() -> None:
    args = build_parser().parse_args(
        ["nuextract", "extract-candidate", "run", "--force"]
    )

    assert args.nuextract_command == "extract-candidate"
    assert args.run_dir == Path("run")
    assert args.force is True
    assert args.temperature == 0.6


def test_parse_candidate_command_parses() -> None:
    args = build_parser().parse_args(
        [
            "nuextract",
            "parse-candidate",
            "paper.pdf",
            "--runs-root",
            "runs",
            "--paper-id",
            "example",
            "--temperature",
            "0.2",
            "--max-tokens",
            "2048",
            "--force",
        ]
    )

    assert args.nuextract_command == "parse-candidate"
    assert args.input_pdf == Path("paper.pdf")
    assert args.runs_root == Path("runs")
    assert args.paper_id == "example"
    assert args.temperature == 0.2
    assert args.max_tokens == 2048
    assert args.force is True
