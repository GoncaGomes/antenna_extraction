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
    assert args.enable_thinking is True


def test_extract_candidate_command_can_disable_thinking() -> None:
    args = build_parser().parse_args(
        ["nuextract", "extract-candidate", "run", "--disable-thinking"]
    )

    assert args.nuextract_command == "extract-candidate"
    assert args.enable_thinking is False


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
            "--disable-thinking",
            "--force",
        ]
    )

    assert args.nuextract_command == "parse-candidate"
    assert args.input_pdf == Path("paper.pdf")
    assert args.runs_root == Path("runs")
    assert args.paper_id == "example"
    assert args.temperature == 0.2
    assert args.max_tokens == 2048
    assert args.enable_thinking is False
    assert args.force is True


def test_parse_candidate_command_defaults_to_thinking_enabled() -> None:
    args = build_parser().parse_args(
        ["nuextract", "parse-candidate", "paper.pdf"]
    )

    assert args.nuextract_command == "parse-candidate"
    assert args.enable_thinking is True


def test_parse_all_command_parses() -> None:
    args = build_parser().parse_args(
        [
            "nuextract",
            "parse-all",
            "paper.pdf",
            "--runs-root",
            "runs",
            "--pipeline-version",
            "0.2.0",
            "--paper-id",
            "example",
            "--dpi",
            "200",
            "--temperature",
            "0.2",
            "--max-tokens",
            "2048",
            "--disable-thinking",
            "--force",
        ]
    )

    assert args.nuextract_command == "parse-all"
    assert args.input_pdf == Path("paper.pdf")
    assert args.runs_root == Path("runs")
    assert args.pipeline_version == "0.2.0"
    assert args.paper_id == "example"
    assert args.dpi == 200
    assert args.temperature == 0.2
    assert args.max_tokens == 2048
    assert args.enable_thinking is False
    assert args.force is True


def test_parse_all_command_defaults_to_thinking_enabled() -> None:
    args = build_parser().parse_args(["nuextract", "parse-all", "paper.pdf"])

    assert args.nuextract_command == "parse-all"
    assert args.enable_thinking is True
