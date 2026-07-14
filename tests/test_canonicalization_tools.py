from __future__ import annotations

from pathlib import Path

import pytest

from antenna_ingest.canonicalization.tools import search_evidence
from antenna_ingest.retrieval.index import (
    EVIDENCE_INDEX_PATH,
    EvidenceIndexItem,
    write_jsonl,
)


def test_matching_paragraph_is_returned(tmp_path: Path) -> None:
    run_dir = make_index(tmp_path)

    response = search_evidence(run_dir, "FR4 thickness", top_k=1, context_window=0)

    assert response.results[0].evidence_id == "block_paragraph"
    assert "FR4" in response.results[0].text


def test_pipe_markdown_table_is_returned_unchanged(tmp_path: Path) -> None:
    run_dir = make_index(tmp_path)
    expected = "TABLE I PARAMETERS\n\n| Name | Value |\n|---|---|\n| Width | 20 mm |"

    response = search_evidence(run_dir, "Width 20 mm", top_k=1, context_window=0)

    assert response.results[0].evidence_id == "table_001"
    assert response.results[0].text == expected


def test_figure_caption_is_retrievable(tmp_path: Path) -> None:
    run_dir = make_index(tmp_path)

    response = search_evidence(run_dir, "geometry top view", context_window=0)

    assert response.results[0].evidence_id == "block_figure"
    assert response.results[0].kind == "figure_caption"


def test_exact_evidence_ids_are_preserved(tmp_path: Path) -> None:
    run_dir = make_index(tmp_path)

    response = search_evidence(run_dir, "FR4", top_k=1, context_window=0)

    assert response.results[0].evidence_id == "block_paragraph"


def test_section_and_caption_metadata_are_preserved(tmp_path: Path) -> None:
    run_dir = make_index(tmp_path)

    paragraph = search_evidence(run_dir, "FR4", top_k=1, context_window=0)
    table = search_evidence(run_dir, "PARAMETERS", top_k=1, context_window=0)

    assert paragraph.results[0].section == "Antenna Design"
    assert table.results[0].caption == "TABLE I PARAMETERS"


def test_context_expansion_returns_neighbouring_blocks(tmp_path: Path) -> None:
    run_dir = make_index(tmp_path)

    response = search_evidence(run_dir, "FR4", top_k=1, context_window=1)

    assert {result.evidence_id for result in response.results} == {
        "block_heading",
        "block_paragraph",
        "block_figure",
    }
    assert any(
        reason.startswith("context:")
        for result in response.results
        for reason in result.match_reasons
    )


def test_empty_query_is_rejected(tmp_path: Path) -> None:
    run_dir = make_index(tmp_path)

    with pytest.raises(ValueError, match="query must not be empty"):
        search_evidence(run_dir, "   ")


@pytest.mark.parametrize("top_k", [0, 13])
def test_invalid_top_k_is_rejected(tmp_path: Path, top_k: int) -> None:
    run_dir = make_index(tmp_path)

    with pytest.raises(ValueError, match="top_k must be between 1 and 12"):
        search_evidence(run_dir, "antenna", top_k=top_k)


@pytest.mark.parametrize("context_window", [-1, 3])
def test_invalid_context_window_is_rejected(
    tmp_path: Path,
    context_window: int,
) -> None:
    run_dir = make_index(tmp_path)

    with pytest.raises(ValueError, match="context_window must be between 0 and 2"):
        search_evidence(run_dir, "antenna", context_window=context_window)


def test_missing_evidence_index_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="evidence index does not exist"):
        search_evidence(tmp_path / "missing_run", "antenna")


def test_adapter_does_not_require_or_create_manifest(tmp_path: Path) -> None:
    run_dir = make_index(tmp_path)
    manifest_path = run_dir / "manifest.json"

    search_evidence(run_dir, "FR4", top_k=1, context_window=0)

    assert not manifest_path.exists()


def make_index(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    items = [
        index_item(
            evidence_id="block_heading",
            page=1,
            kind="heading",
            order=0,
            text="Antenna Design",
            next_id="block_paragraph",
        ),
        index_item(
            evidence_id="block_paragraph",
            page=1,
            kind="paragraph",
            order=1,
            text="The antenna uses an FR4 substrate with thickness 1.6 mm.",
            section="Antenna Design",
            previous_id="block_heading",
            next_id="block_figure",
        ),
        index_item(
            evidence_id="block_figure",
            page=2,
            kind="figure_caption",
            order=2,
            text="Figure 1. Geometry top view of the antenna.",
            section="Antenna Design",
            previous_id="block_paragraph",
        ),
        index_item(
            evidence_id="table_001",
            page=3,
            kind="table",
            order=3,
            text=(
                "TABLE I PARAMETERS\n\n"
                "| Name | Value |\n"
                "|---|---|\n"
                "| Width | 20 mm |"
            ),
            source_type="table",
            caption="TABLE I PARAMETERS",
        ),
    ]
    write_jsonl(run_dir / EVIDENCE_INDEX_PATH, items)
    return run_dir


def index_item(
    evidence_id: str,
    page: int,
    kind: str,
    order: int,
    text: str,
    source_type: str = "block",
    section: str | None = None,
    caption: str | None = None,
    previous_id: str | None = None,
    next_id: str | None = None,
) -> EvidenceIndexItem:
    return EvidenceIndexItem(
        evidence_id=evidence_id,
        source_type=source_type,
        source_id=evidence_id,
        page=page,
        kind=kind,
        order=order,
        text=text,
        section=section,
        caption=caption,
        tokens=text.replace("|", " ").split(),
        key_tokens=text.replace("|", " ").split(),
        numbers=["1.6", "20"],
        units=["mm"],
        previous_id=previous_id,
        next_id=next_id,
        source_artifact="retrieval/evidence_index.jsonl",
    )
