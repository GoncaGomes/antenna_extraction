from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import fitz

from tests.benchmark.models import (
    PaperExpectations,
    PapersManifest,
    SyntheticCoverageManifest,
)


@dataclass(frozen=True)
class BenchmarkSuite:
    papers: PapersManifest
    expectations: tuple[PaperExpectations, ...]
    synthetic_coverage: SyntheticCoverageManifest


def load_benchmark_suite(
    repository_root: Path,
    benchmark_root: Path | None = None,
) -> BenchmarkSuite:
    repository_root = repository_root.resolve()
    benchmark_root = (
        benchmark_root.resolve()
        if benchmark_root is not None
        else repository_root / "benchmarks" / "v2"
    )
    papers = PapersManifest.model_validate(_read_object(benchmark_root / "papers.json"))
    papers = PapersManifest(
        schema_version=papers.schema_version,
        papers=sorted(papers.papers, key=lambda paper: paper.paper_id),
    )
    _validate_paper_files(repository_root, benchmark_root, papers)

    known_papers = {paper.paper_id: paper for paper in papers.papers}
    expectations: list[PaperExpectations] = []
    for paper in papers.papers:
        for relative_path in sorted(paper.expectation_paths):
            path = _resolve_relative(benchmark_root, relative_path)
            expectation = PaperExpectations.model_validate(_read_object(path))
            if expectation.paper_id != paper.paper_id:
                raise ValueError(
                    f"expectation {relative_path} references unknown paper association"
                )
            _validate_evidence_pages(expectation, paper.page_count)
            expectations.append(expectation)

    if {expectation.paper_id for expectation in expectations} - set(known_papers):
        raise ValueError("expectation references an unknown paper ID")
    _validate_global_expectation_ids(expectations)
    _require_all_expectation_files_referenced(benchmark_root, papers)

    synthetic = SyntheticCoverageManifest.model_validate(
        _read_object(benchmark_root / "synthetic_coverage.json")
    )
    synthetic = SyntheticCoverageManifest(
        schema_version=synthetic.schema_version,
        coverage=sorted(synthetic.coverage, key=lambda entry: entry.category),
    )
    for entry in synthetic.coverage:
        path = _resolve_relative(repository_root, entry.test_path)
        if not path.is_file():
            raise ValueError(f"unknown synthetic test path: {entry.test_path}")
        string_literals = {
            node.value
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        if entry.case_id not in string_literals:
            raise ValueError(
                f"unknown synthetic case {entry.case_id} in {entry.test_path}"
            )

    expectations.sort(key=lambda item: (item.paper_id, item.expectation_id))
    return BenchmarkSuite(papers, tuple(expectations), synthetic)


def _read_object(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def _resolve_relative(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"absolute paths are not permitted: {value}")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"path leaves its allowed root: {value}")
    return resolved


def _validate_paper_files(
    repository_root: Path,
    benchmark_root: Path,
    manifest: PapersManifest,
) -> None:
    raw_root = (repository_root / "tests" / "fixtures" / "papers" / "raw").resolve()
    referenced_paths: set[Path] = set()
    for paper in manifest.papers:
        path = _resolve_relative(repository_root, paper.local_path)
        if path.parent != raw_root or path.suffix.lower() != ".pdf":
            raise ValueError(f"unknown paper file location: {paper.local_path}")
        if path.name != paper.local_filename:
            raise ValueError(f"local filename does not match path: {paper.paper_id}")
        if not path.is_file():
            raise ValueError(f"paper file does not exist: {paper.local_path}")
        if _sha256(path) != paper.sha256:
            raise ValueError(f"checksum mismatch for paper {paper.paper_id}")
        with fitz.open(path) as document:
            if document.page_count != paper.page_count:
                raise ValueError(f"page count mismatch for paper {paper.paper_id}")
        referenced_paths.add(path)
        for expectation_path in paper.expectation_paths:
            if not _resolve_relative(benchmark_root, expectation_path).is_file():
                raise ValueError(f"unknown expectation path: {expectation_path}")

    discovered_paths = {path.resolve() for path in raw_root.glob("*.pdf")}
    if discovered_paths != referenced_paths:
        unknown = sorted(str(path) for path in discovered_paths ^ referenced_paths)
        raise ValueError(f"unknown or unreferenced paper files: {unknown}")


def _require_all_expectation_files_referenced(
    benchmark_root: Path,
    manifest: PapersManifest,
) -> None:
    referenced = {
        _resolve_relative(benchmark_root, path)
        for paper in manifest.papers
        for path in paper.expectation_paths
    }
    discovered = {
        path.resolve()
        for path in (benchmark_root / "expectations").rglob("*.json")
    }
    if referenced != discovered:
        unknown = sorted(str(path) for path in referenced ^ discovered)
        raise ValueError(f"unknown or unreferenced expectation files: {unknown}")


def _validate_global_expectation_ids(
    expectations: list[PaperExpectations],
) -> None:
    expectation_ids = [expectation.expectation_id for expectation in expectations]
    if len(expectation_ids) != len(set(expectation_ids)):
        raise ValueError("duplicate expectation_id values are not permitted")

    assertion_ids = [
        assertion.assertion_id
        for expectation in expectations
        for assertion in expectation.assertions
    ]
    if len(assertion_ids) != len(set(assertion_ids)):
        raise ValueError("duplicate assertion_id values are not permitted")


def _validate_evidence_pages(
    expectation: PaperExpectations,
    page_count: int,
) -> None:
    for assertion in expectation.assertions:
        for evidence in assertion.evidence:
            if evidence.page > page_count:
                raise ValueError(
                    f"evidence page {evidence.page} is outside paper "
                    f"{expectation.paper_id} page range"
                )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
