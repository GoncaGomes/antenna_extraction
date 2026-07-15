from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from antenna_ingest.canonicalization.canonicalize import (
    CANONICAL_DESIGN_RECORD_PATH,
    CANONICALIZATION_REPORT_PATH,
    canonicalize_run,
)
from antenna_ingest.canonicalization.schemas import CanonicalDesignRecord
from antenna_ingest.nuextract.raw_extraction import ANTENNA_CANDIDATE_PATH
from antenna_ingest.nuextract.settings import NuExtractSettings
from antenna_ingest.orchestration.schemas import PhaseStatus, RunManifest
from antenna_ingest.retrieval.index import (
    EVIDENCE_INDEX_PATH,
    EvidenceIndexItem,
    write_jsonl,
)
from antenna_ingest.utils.json_io import read_json, write_json


def test_successful_canonicalization_run_persists_outputs(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(valid_response())

    record, report = canonicalize_run(
        run_dir,
        settings=make_settings(),
        client=client,
        enable_thinking=False,
    )

    assert isinstance(record, CanonicalDesignRecord)
    assert report.valid is True
    assert (run_dir / CANONICAL_DESIGN_RECORD_PATH).is_file()
    assert (run_dir / CANONICALIZATION_REPORT_PATH).is_file()
    assert read_json(run_dir / CANONICAL_DESIGN_RECORD_PATH) == record.model_dump(
        mode="json"
    )
    assert read_json(run_dir / CANONICALIZATION_REPORT_PATH) == report.model_dump(
        mode="json"
    )

    manifest = load_manifest(run_dir)
    assert manifest.phase_status["canonicalization"] == PhaseStatus.COMPLETED
    artifacts = {
        artifact.name: artifact
        for artifact in manifest.artifacts
        if artifact.name in {"canonical_design_record", "canonicalization_report"}
    }
    assert set(artifacts) == {
        "canonical_design_record",
        "canonicalization_report",
    }
    assert all(artifact.checksum for artifact in artifacts.values())
    assert client.completions.calls[0]["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }


def test_existing_outputs_require_force_to_replace(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(valid_response())
    canonicalize_run(run_dir, settings=make_settings(), client=client)

    with pytest.raises(
        FileExistsError,
        match="canonicalization output already exists",
    ):
        canonicalize_run(run_dir, settings=make_settings(), client=client)

    write_json(run_dir / CANONICAL_DESIGN_RECORD_PATH, {"stale": True})
    record, report = canonicalize_run(
        run_dir,
        force=True,
        settings=make_settings(),
        client=client,
    )

    assert read_json(run_dir / CANONICAL_DESIGN_RECORD_PATH) == record.model_dump(
        mode="json"
    )
    assert report.valid is True
    manifest = load_manifest(run_dir)
    canonical_artifact_names = [
        artifact.name
        for artifact in manifest.artifacts
        if artifact.name in {"canonical_design_record", "canonicalization_report"}
    ]
    assert canonical_artifact_names.count("canonical_design_record") == 1
    assert canonical_artifact_names.count("canonicalization_report") == 1


def test_failed_canonicalization_marks_phase_failed(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)

    with pytest.raises(ValidationError):
        canonicalize_run(
            run_dir,
            settings=make_settings(),
            client=FakeClient("not valid canonical JSON"),
        )

    manifest = load_manifest(run_dir)
    assert manifest.phase_status["canonicalization"] == PhaseStatus.FAILED
    assert not (run_dir / CANONICAL_DESIGN_RECORD_PATH).exists()
    assert not (run_dir / CANONICALIZATION_REPORT_PATH).exists()


class FakeClient:
    def __init__(self, response_text: str) -> None:
        self.completions = FakeCompletions(response_text)
        self.chat = SimpleNamespace(completions=self.completions)


class FakeCompletions:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[dict] = []

    def create(self, **kwargs) -> SimpleNamespace:
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.response_text, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    manifest = RunManifest(
        run_id="run_test",
        input_file="input/test.pdf",
        pipeline_version="0.1.0",
        phase_status={
            "run_infrastructure": PhaseStatus.COMPLETED,
            "nuextract_raw_extraction": PhaseStatus.COMPLETED,
            "evidence_indexing": PhaseStatus.COMPLETED,
            "canonicalization": PhaseStatus.PENDING,
        },
    )
    write_json(run_dir / "manifest.json", manifest.model_dump(mode="json"))
    write_json(
        run_dir / ANTENNA_CANDIDATE_PATH,
        {"paper_title": "Synthetic antenna paper"},
    )
    write_jsonl(
        run_dir / EVIDENCE_INDEX_PATH,
        [
            EvidenceIndexItem(
                evidence_id="block_design",
                source_type="block",
                source_id="block_design",
                page=1,
                kind="paragraph",
                order=0,
                text="The paper identifies the final antenna design.",
                source_artifact="parsed/evidence_blocks.jsonl",
            )
        ],
    )
    return run_dir


def load_manifest(run_dir: Path) -> RunManifest:
    return RunManifest.model_validate(read_json(run_dir / "manifest.json"))


def valid_response() -> str:
    return json.dumps(
        {
            "schema_name": "canonical_design_record_v1",
            "design": {
                "selection_reason": "Selected from the reported final design.",
                "evidence_ids": ["block_design"],
            },
            "reconstruction_status": "unknown",
        }
    )


def make_settings() -> NuExtractSettings:
    return NuExtractSettings(
        _env_file=None,
        SKYNET_BASE_URL="https://example.invalid/v1",
        SKYNET_API_KEY="test-key",
        NUEXTRACT_MODEL="test-nuextract",
        CANONICALIZER_MODEL="test-canonicalizer",
        CANONICALIZER_TIMEOUT_SECONDS=30,
    )
