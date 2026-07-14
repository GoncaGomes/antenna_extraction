from __future__ import annotations

from pathlib import Path

from pydantic import Field

from antenna_ingest.orchestration.schemas import StrictModel
from antenna_ingest.retrieval.index import (
    EVIDENCE_INDEX_PATH,
    EvidenceIndexItem,
    read_jsonl,
)
from antenna_ingest.retrieval.search import search_items


class EvidenceToolResult(StrictModel):
    evidence_id: str
    source_type: str
    page: int
    kind: str
    section: str | None = None
    caption: str | None = None
    text: str
    score: float
    match_reasons: list[str] = Field(default_factory=list)


class EvidenceToolResponse(StrictModel):
    query: str
    result_count: int
    results: list[EvidenceToolResult] = Field(default_factory=list)


def search_evidence(
    run_dir: Path,
    query: str,
    top_k: int = 8,
    context_window: int = 1,
) -> EvidenceToolResponse:
    run_dir = Path(run_dir).resolve()
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("query must not be empty")
    if not 1 <= top_k <= 12:
        raise ValueError("top_k must be between 1 and 12")
    if not 0 <= context_window <= 2:
        raise ValueError("context_window must be between 0 and 2")

    index_path = run_dir / EVIDENCE_INDEX_PATH
    if not index_path.is_file():
        raise FileNotFoundError(f"evidence index does not exist: {index_path}")

    items = [
        EvidenceIndexItem.model_validate(item) for item in read_jsonl(index_path)
    ]
    response = search_items(
        items,
        query=cleaned_query,
        top_k=top_k,
        context_window=context_window,
    )
    results = [
        EvidenceToolResult(
            evidence_id=result.evidence_id,
            source_type=result.source_type,
            page=result.page,
            kind=result.kind,
            section=result.section,
            caption=result.caption,
            text=result.text,
            score=result.score,
            match_reasons=result.match_reasons,
        )
        for result in response.results
    ]
    return EvidenceToolResponse(
        query=response.query,
        result_count=len(results),
        results=results,
    )
