from __future__ import annotations

from pathlib import Path

from pydantic import Field

from antenna_ingest.orchestration.phases import complete_phase, fail_phase, start_phase
from antenna_ingest.orchestration.runs import load_run_manifest, sha256_file
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    RunManifest,
    StrictModel,
)
from antenna_ingest.retrieval.index import (
    EVIDENCE_INDEX_PATH,
    EvidenceIndexItem,
    extract_numbers_from_tokens,
    extract_units_from_tokens,
    read_jsonl,
    tokenize_text,
)
from antenna_ingest.utils.json_io import read_json, write_json


EVIDENCE_SEARCH_PHASE = "evidence_search"
QUERY_TRACE_PATH = "retrieval/query_trace.json"


class EvidenceSearchResult(StrictModel):
    evidence_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    kind: str = Field(min_length=1)
    score: float
    lexical_score: float = 0.0
    exact_score: float = 0.0
    rrf_score: float = 0.0
    match_reasons: list[str] = Field(default_factory=list)
    text: str = Field(min_length=1)
    section: str | None = None
    caption: str | None = None
    previous_id: str | None = None
    next_id: str | None = None


class EvidenceSearchResponse(StrictModel):
    query: str = Field(min_length=1)
    top_k: int = Field(ge=1)
    result_count: int = Field(ge=0)
    results: list[EvidenceSearchResult] = Field(default_factory=list)


class QueryTrace(StrictModel):
    queries: list[EvidenceSearchResponse] = Field(default_factory=list)


def search_evidence_index(
    run_dir: Path,
    query: str,
    top_k: int = 5,
    context_window: int = 0,
    write_trace: bool = False,
) -> EvidenceSearchResponse:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    manifest = load_run_manifest(manifest_path)
    start_phase(manifest, EVIDENCE_SEARCH_PHASE)
    write_json(manifest_path, manifest.model_dump(mode="json"))

    try:
        items = [
            EvidenceIndexItem.model_validate(item)
            for item in read_jsonl(run_dir / EVIDENCE_INDEX_PATH)
        ]
        response = search_items(
            items,
            query=query,
            top_k=top_k,
            context_window=context_window,
        )
        manifest = load_run_manifest(manifest_path)
        complete_phase(manifest, EVIDENCE_SEARCH_PHASE)
        if write_trace:
            append_query_trace(run_dir, response)
            replace_query_trace_artifact(manifest, run_dir)
        write_json(manifest_path, manifest.model_dump(mode="json"))
        return response
    except Exception:
        failed_manifest = load_run_manifest(manifest_path)
        fail_phase(failed_manifest, EVIDENCE_SEARCH_PHASE, None)
        write_json(manifest_path, failed_manifest.model_dump(mode="json"))
        raise


def search_items(
    items: list[EvidenceIndexItem],
    query: str,
    top_k: int = 5,
    context_window: int = 0,
) -> EvidenceSearchResponse:
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("query must not be empty")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if context_window < 0:
        raise ValueError("context_window must not be negative")

    query_tokens = tokenize_text(cleaned_query)
    query_token_map = {token.lower(): token for token in query_tokens}
    query_numbers = extract_numbers_from_tokens(query_tokens)
    query_units = extract_units_from_tokens(query_tokens)

    scoring = {}
    for item in items:
        lexical_score, lexical_matches = _lexical_score(item, query_token_map)
        exact_score, exact_reasons = _exact_score(
            item,
            query_token_map,
            query_numbers,
            query_units,
        )
        scoring[item.evidence_id] = {
            "item": item,
            "lexical_score": lexical_score,
            "exact_score": exact_score,
            "reasons": [*exact_reasons, *lexical_matches],
        }

    lexical_ranking = sorted(
        items,
        key=lambda item: (-scoring[item.evidence_id]["lexical_score"], item.order),
    )
    exact_ranking = sorted(
        items,
        key=lambda item: (-scoring[item.evidence_id]["exact_score"], item.order),
    )
    lexical_ranks = {
        item.evidence_id: rank for rank, item in enumerate(lexical_ranking, start=1)
    }
    exact_ranks = {
        item.evidence_id: rank for rank, item in enumerate(exact_ranking, start=1)
    }

    results = []
    for item in items:
        values = scoring[item.evidence_id]
        if values["lexical_score"] == 0 and values["exact_score"] == 0:
            continue
        rrf_score = 1 / (60 + lexical_ranks[item.evidence_id]) + 1 / (
            60 + exact_ranks[item.evidence_id]
        )
        results.append(
            _result_from_item(
                item,
                score=(
                    values["lexical_score"]
                    + values["exact_score"]
                    + (100 * rrf_score)
                ),
                lexical_score=values["lexical_score"],
                exact_score=values["exact_score"],
                rrf_score=rrf_score,
                match_reasons=values["reasons"],
            )
        )

    results.sort(key=lambda result: (-result.score, _item_order(items, result.evidence_id)))
    results = results[:top_k]
    if context_window:
        results = expand_context(results, items, context_window)

    return EvidenceSearchResponse(
        query=cleaned_query,
        top_k=top_k,
        result_count=len(results),
        results=results,
    )


def expand_context(
    results: list[EvidenceSearchResult],
    items: list[EvidenceIndexItem],
    context_window: int,
) -> list[EvidenceSearchResult]:
    item_by_id = {item.evidence_id: item for item in items}
    expanded = list(results)
    result_by_id = {result.evidence_id: result for result in expanded}

    for result in list(results):
        if result.source_type != "block":
            continue
        for direction, reason in (
            ("previous_id", "context:previous"),
            ("next_id", "context:next"),
        ):
            current_id = getattr(result, direction)
            for _ in range(context_window):
                if current_id is None or current_id not in item_by_id:
                    break
                if current_id in result_by_id:
                    context_result = result_by_id[current_id]
                    if reason not in context_result.match_reasons:
                        context_result.match_reasons.append(reason)
                else:
                    context_result = _result_from_item(
                        item_by_id[current_id],
                        score=0.0,
                        match_reasons=[reason],
                    )
                    expanded.append(context_result)
                    result_by_id[current_id] = context_result
                current_id = getattr(item_by_id[current_id], direction)
    return expanded


def append_query_trace(run_dir: Path, response: EvidenceSearchResponse) -> None:
    trace_path = Path(run_dir) / QUERY_TRACE_PATH
    if trace_path.exists():
        trace = QueryTrace.model_validate(read_json(trace_path))
    else:
        trace = QueryTrace()
    trace.queries.append(response)
    write_json(trace_path, trace.model_dump(mode="json"))


def replace_query_trace_artifact(manifest: RunManifest, run_dir: Path) -> None:
    manifest.artifacts = [
        artifact for artifact in manifest.artifacts if artifact.name != "query_trace"
    ]
    manifest.add_artifact(
        ArtifactReference(
            name="query_trace",
            relative_path=QUERY_TRACE_PATH,
            producing_phase=EVIDENCE_SEARCH_PHASE,
            checksum=sha256_file(Path(run_dir) / QUERY_TRACE_PATH),
        )
    )


def _lexical_score(
    item: EvidenceIndexItem,
    query_token_map: dict[str, str],
) -> tuple[float, list[str]]:
    item_tokens = {
        token.lower() for token in [*item.tokens, *tokenize_text(item.text)]
    }
    matches = [
        query_token_map[token]
        for token in query_token_map
        if token in item_tokens
    ]
    return float(len(matches)), [f"lexical:{token}" for token in matches]


def _exact_score(
    item: EvidenceIndexItem,
    query_token_map: dict[str, str],
    query_numbers: list[str],
    query_units: list[str],
) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []
    key_tokens = {token.lower() for token in item.key_tokens}
    item_numbers = set(item.numbers)
    item_units = {unit.lower() for unit in item.units}
    caption_tokens = {token.lower() for token in tokenize_text(item.caption or "")}
    section_tokens = {token.lower() for token in tokenize_text(item.section or "")}

    for lowered, original in query_token_map.items():
        if lowered in key_tokens:
            score += 5
            reasons.append(f"key:{original}")
        if lowered in caption_tokens:
            score += 1
            reasons.append(f"caption:{original}")
        if lowered in section_tokens:
            score += 1
            reasons.append(f"section:{original}")
    for number in query_numbers:
        if number in item_numbers:
            score += 3
            reasons.append(f"number:{number}")
    for unit in query_units:
        if unit.lower() in item_units:
            score += 2
            reasons.append(f"unit:{unit}")
    return score, reasons


def _result_from_item(
    item: EvidenceIndexItem,
    score: float,
    lexical_score: float = 0.0,
    exact_score: float = 0.0,
    rrf_score: float = 0.0,
    match_reasons: list[str] | None = None,
) -> EvidenceSearchResult:
    return EvidenceSearchResult(
        evidence_id=item.evidence_id,
        source_type=item.source_type,
        source_id=item.source_id,
        page=item.page,
        kind=item.kind,
        score=score,
        lexical_score=lexical_score,
        exact_score=exact_score,
        rrf_score=rrf_score,
        match_reasons=match_reasons or [],
        text=item.text,
        section=item.section,
        caption=item.caption,
        previous_id=item.previous_id,
        next_id=item.next_id,
    )


def _item_order(items: list[EvidenceIndexItem], evidence_id: str) -> int:
    return next(item.order for item in items if item.evidence_id == evidence_id)
