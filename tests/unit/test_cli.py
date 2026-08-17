from __future__ import annotations

from pathlib import Path

import pytest

from antenna_ingest.cli import build_parser, main


def test_init_run_command_parses() -> None:
    args = build_parser().parse_args(
        [
            "init-run",
            "paper.pdf",
            "--runs-root",
            "run-root",
            "--paper-id",
            "paper-1",
            "--force",
        ]
    )

    assert args.command == "init-run"
    assert args.input_pdf == Path("paper.pdf")
    assert args.runs_root == Path("run-root")
    assert args.paper_id == "paper-1"
    assert args.force is True


def test_render_pages_is_a_direct_command() -> None:
    args = build_parser().parse_args(
        ["render-pages", "runs/example", "--dpi", "200", "--force"]
    )

    assert args.command == "render-pages"
    assert args.run_dir == Path("runs/example")
    assert args.dpi == 200
    assert args.force is True


@pytest.mark.parametrize(
    ("option", "expected"),
    [("--thinking", True), ("--no-thinking", False)],
)
def test_extract_paper_requires_an_explicit_thinking_mode(
    option: str,
    expected: bool,
) -> None:
    args = build_parser().parse_args(["extract-paper", "runs/example", option])

    assert args.command == "extract-paper"
    assert args.run_dir == Path("runs/example")
    assert args.enable_thinking is expected


@pytest.mark.parametrize(
    "arguments",
    [
        ["extract-paper", "runs/example"],
        ["extract-paper", "runs/example", "--thinking", "--no-thinking"],
    ],
)
def test_extract_paper_rejects_missing_or_multiple_thinking_modes(
    arguments: list[str],
) -> None:
    with pytest.raises(SystemExit, match="2"):
        build_parser().parse_args(arguments)


def test_extract_paper_is_a_direct_command(monkeypatch, capsys) -> None:
    calls = []
    monkeypatch.setattr(
        "antenna_ingest.cli.extract_paper_from_run",
        lambda **kwargs: calls.append(kwargs),
    )

    result = main(
        ["extract-paper", "runs/example", "--thinking", "--force"]
    )

    assert result == 0
    assert calls == [
        {
            "run_dir": Path("runs/example"),
            "enable_thinking": True,
            "force": True,
        }
    ]
    output = capsys.readouterr().out
    assert "paper_extraction.json" in output
    assert "extraction_validation.json" in output


def test_doctor_requires_explicit_model_role() -> None:
    args = build_parser().parse_args(["doctor", "document_extractor"])

    assert args.command == "doctor"
    assert args.model_role == "document_extractor"


def test_cli_help_does_not_load_endpoint_settings(capsys) -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["--help"])

    help_text = capsys.readouterr().out
    assert "init-run" in help_text
    assert "render-pages" in help_text
    assert "extract-paper" in help_text
    assert "doctor" in help_text
    assert "nuextract" not in help_text
    assert "retrieval" not in help_text
    assert "canonicalization" not in help_text
