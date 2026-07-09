from __future__ import annotations

from antenna_ingest.retrieval.index import build_evidence_index_from_run
from antenna_ingest.retrieval.search import (
    QUERY_TRACE_PATH,
    search_evidence_index,
)
from antenna_ingest.utils.json_io import read_json
from tests.test_retrieval_index import make_retrieval_run


def test_search_retrieves_geometry_table(tmp_path) -> None:
    run_dir = make_retrieval_run(tmp_path)
    build_evidence_index_from_run(run_dir)

    response = search_evidence_index(
        run_dir,
        query="S1 S2 P1 P2 L1 dimensions mm",
        top_k=3,
    )

    first = response.results[0]
    assert first.evidence_id == "table_001"
    assert first.source_type == "table"
    assert "key:S1" in first.match_reasons
    assert "key:S2" in first.match_reasons
    assert "unit:mm" in first.match_reasons


def test_search_retrieves_material_paragraph(tmp_path) -> None:
    run_dir = make_retrieval_run(tmp_path)
    build_evidence_index_from_run(run_dir)

    response = search_evidence_index(
        run_dir,
        query="FR4 substrate thickness 1.6 mm",
        top_k=3,
    )

    paragraph = next(
        result for result in response.results if "FR4 substrate" in result.text
    )
    assert "number:1.6" in paragraph.match_reasons
    assert "unit:mm" in paragraph.match_reasons


def test_search_context_window_adds_neighbour_without_duplicates(tmp_path) -> None:
    run_dir = make_retrieval_run(tmp_path)
    build_evidence_index_from_run(run_dir)

    response = search_evidence_index(
        run_dir,
        query="geometry proposed antenna",
        top_k=1,
        context_window=1,
    )

    evidence_ids = [result.evidence_id for result in response.results]
    assert len(evidence_ids) == len(set(evidence_ids))
    assert any(
        "context:previous" in result.match_reasons
        or "context:next" in result.match_reasons
        for result in response.results
    )


def test_nonstandard_table_headers_are_preserved_and_searchable(tmp_path) -> None:
    table = {
        "table_id": "table_002",
        "page": 4,
        "caption": "Optimized structural parameters",
        "headers": ["alpha_gap", "rho2", "stubA", "edge_len", "g"],
        "rows": [["0.8", "12", "3.5", "22", "1.2"]],
        "units": ["mm"],
        "raw_markdown": "<table>...</table>",
        "source": "parsed/document.nuextract.md",
    }
    run_dir = make_retrieval_run(tmp_path, additional_tables=[table])
    build_evidence_index_from_run(run_dir)

    response = search_evidence_index(
        run_dir,
        query="alpha_gap rho2 stubA edge_len mm",
        top_k=3,
    )

    assert response.results[0].evidence_id == "table_002"
    key_tokens = read_jsonl_item(run_dir, "table_002")["key_tokens"]
    assert {"alpha_gap", "rho2", "stubA", "edge_len", "g"} <= set(key_tokens)


def test_search_can_append_query_trace(tmp_path) -> None:
    run_dir = make_retrieval_run(tmp_path)
    build_evidence_index_from_run(run_dir)

    search_evidence_index(run_dir, "FR4", write_trace=True)
    search_evidence_index(run_dir, "dimensions", write_trace=True)

    trace = read_json(run_dir / QUERY_TRACE_PATH)
    assert [query["query"] for query in trace["queries"]] == [
        "FR4",
        "dimensions",
    ]
    manifest = read_json(run_dir / "manifest.json")
    assert manifest["phase_status"]["evidence_search"] == "completed"
    assert "query_trace" in {
        artifact["name"] for artifact in manifest["artifacts"]
    }


def read_jsonl_item(run_dir, evidence_id: str) -> dict:
    from antenna_ingest.retrieval.index import read_jsonl

    return next(
        item
        for item in read_jsonl(run_dir / "retrieval/evidence_index.jsonl")
        if item["evidence_id"] == evidence_id
    )
