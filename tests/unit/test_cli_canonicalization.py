from __future__ import annotations

from pathlib import Path

from antenna_ingest.cli import build_parser


def test_canonicalization_run_command_parses_defaults() -> None:
    args = build_parser().parse_args(
        ["canonicalization", "run", "runs/example"]
    )

    assert args.command == "canonicalization"
    assert args.canonicalization_command == "run"
    assert args.run_dir == Path("runs/example")
    assert args.force is False
    assert args.max_tool_calls == 12


def test_canonicalization_run_command_parses_options() -> None:
    args = build_parser().parse_args(
        [
            "canonicalization",
            "run",
            "runs/example",
            "--force",
            "--max-tool-calls",
            "6",
        ]
    )

    assert args.command == "canonicalization"
    assert args.canonicalization_command == "run"
    assert args.run_dir == Path("runs/example")
    assert args.force is True
    assert args.max_tool_calls == 6
