from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from pydantic import Field

from antenna_ingest.orchestration.runs import sha256_file
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    PhaseStatus,
    RunManifest,
    StrictModel,
)
from antenna_ingest.utils.json_io import read_json, write_json


EVIDENCE_BLOCKS_PHASE = "evidence_blocks"
EVIDENCE_BLOCKS_PATH = "parsed/evidence_blocks.jsonl"
EVIDENCE_BLOCKS_REPORT_PATH = "parsed/evidence_blocks_report.json"
SOURCE_MARKDOWN_PATH = "parsed/document.nuextract.md"
PAGE_MARKER_RE = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")


class EvidenceBlock(StrictModel):
    block_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    kind: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source: str = Field(min_length=1)


class EvidenceBlocksReport(StrictModel):
    source_markdown: str = Field(min_length=1)
    output_blocks: str = Field(min_length=1)
    block_count: int = Field(ge=0)
    page_count: int = Field(ge=1)
    kinds: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def build_evidence_blocks_from_run(
    run_dir: Path,
    force: bool = False,
) -> EvidenceBlocksReport:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    manifest = RunManifest.model_validate(read_json(manifest_path))
    refuse_existing_evidence_block_outputs(run_dir, force)

    manifest.phase_status[EVIDENCE_BLOCKS_PHASE] = PhaseStatus.RUNNING
    write_json(manifest_path, manifest.model_dump(mode="json"))

    try:
        markdown = (run_dir / SOURCE_MARKDOWN_PATH).read_text(encoding="utf-8")
        pages = split_markdown_pages(markdown)
        if not pages:
            raise ValueError("source Markdown contains no page markers")

        blocks = []
        for page, page_text in pages:
            for block_number, text in enumerate(
                split_page_blocks(page_text),
                start=1,
            ):
                blocks.append(
                    EvidenceBlock(
                        block_id=f"page_{page}_block_{block_number:03d}",
                        page=page,
                        kind=classify_block(text),
                        text=text,
                        source=SOURCE_MARKDOWN_PATH,
                    )
                )

        write_jsonl(run_dir / EVIDENCE_BLOCKS_PATH, blocks)
        report = EvidenceBlocksReport(
            source_markdown=SOURCE_MARKDOWN_PATH,
            output_blocks=EVIDENCE_BLOCKS_PATH,
            block_count=len(blocks),
            page_count=len(pages),
            kinds=dict(Counter(block.kind for block in blocks)),
            warnings=[],
        )
        write_json(
            run_dir / EVIDENCE_BLOCKS_REPORT_PATH,
            report.model_dump(mode="json"),
        )

        manifest = RunManifest.model_validate(read_json(manifest_path))
        manifest.phase_status[EVIDENCE_BLOCKS_PHASE] = PhaseStatus.COMPLETED
        replace_evidence_block_artifacts(manifest, run_dir)
        write_json(manifest_path, manifest.model_dump(mode="json"))
        return report
    except Exception:
        failed_manifest = RunManifest.model_validate(read_json(manifest_path))
        failed_manifest.phase_status[EVIDENCE_BLOCKS_PHASE] = PhaseStatus.FAILED
        write_json(manifest_path, failed_manifest.model_dump(mode="json"))
        raise


def classify_block(text: str) -> str:
    stripped = text.strip()
    lowered = stripped.lower()

    if stripped.startswith("#"):
        return "heading"
    if "<table" in lowered or stripped.startswith("|"):
        return "table"
    if lowered.startswith(("fig.", "figure")) or "figure" in lowered[:100]:
        return "figure_caption"
    if lowered.startswith(("table", "tab.", "**table")) or "table" in lowered[:100]:
        return "table_caption"
    if "$" in stripped or "\\begin{equation}" in stripped:
        return "equation"
    if stripped.startswith(("-", "*")):
        return "list"
    return "paragraph"


def split_markdown_pages(markdown: str) -> list[tuple[int, str]]:
    markers = list(PAGE_MARKER_RE.finditer(markdown))
    pages = []
    for index, marker in enumerate(markers):
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(markdown)
        pages.append((int(marker.group(1)), markdown[start:end].strip()))
    return pages


def split_page_blocks(page_text: str) -> list[str]:
    return [
        block.strip()
        for block in re.split(r"\n\s*\n", page_text)
        if block.strip()
    ]


def write_jsonl(path: Path, blocks: list[EvidenceBlock]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for block in blocks:
            json.dump(block.model_dump(mode="json"), file, ensure_ascii=False)
            file.write("\n")


def refuse_existing_evidence_block_outputs(run_dir: Path, force: bool) -> None:
    paths = [
        Path(run_dir) / EVIDENCE_BLOCKS_PATH,
        Path(run_dir) / EVIDENCE_BLOCKS_REPORT_PATH,
    ]
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        raise FileExistsError(f"evidence block output already exists: {existing[0]}")
    for path in existing:
        path.unlink()


def replace_evidence_block_artifacts(
    manifest: RunManifest,
    run_dir: Path,
) -> None:
    artifact_names = {"evidence_blocks", "evidence_blocks_report"}
    manifest.artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.name not in artifact_names
    ]
    for name, relative_path in (
        ("evidence_blocks", EVIDENCE_BLOCKS_PATH),
        ("evidence_blocks_report", EVIDENCE_BLOCKS_REPORT_PATH),
    ):
        manifest.add_artifact(
            ArtifactReference(
                name=name,
                relative_path=relative_path,
                producing_phase=EVIDENCE_BLOCKS_PHASE,
                checksum=sha256_file(Path(run_dir) / relative_path),
            )
        )
