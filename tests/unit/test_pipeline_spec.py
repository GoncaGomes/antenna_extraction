from __future__ import annotations

from antenna_ingest.orchestration.pipeline_spec import (
    GLOBAL_PHASES,
    PER_DESIGN_PHASES,
    PHASE_PREREQUISITES,
    PIPELINE_PHASES,
    is_global_phase,
    is_per_design_phase,
    phase_position,
    phase_prerequisites,
    phase_scope,
    validate_phase_scope,
)


EXPECTED_PHASES = [
    "run_infrastructure",
    "page_asset_rendering",
    "pdf_text_extraction",
    "document_page_parsing",
    "document_region_parsing",
    "document_consolidation",
    "antenna_candidate_extraction",
    "evidence_indexing",
    "design_resolution",
    "visual_task_planning",
    "visual_analysis",
    "architecture_evidence_packet",
    "architecture_claim_generation",
    "architecture_blueprint",
    "architecture_synthesis",
    "architecture_structural_validation",
    "architecture_verification",
    "architecture_finalization",
    "architecture_validation",
    "architecture_set_finalization",
]


def test_pipeline_phase_order_is_exact() -> None:
    assert PIPELINE_PHASES == EXPECTED_PHASES
    assert list(PHASE_PREREQUISITES) == EXPECTED_PHASES
    assert [phase_position(name) for name in EXPECTED_PHASES] == list(range(20))


def test_pipeline_phase_scope_classification_is_exact() -> None:
    assert GLOBAL_PHASES == frozenset((*EXPECTED_PHASES[:9], EXPECTED_PHASES[-1]))
    assert PER_DESIGN_PHASES == frozenset(EXPECTED_PHASES[9:19])
    assert all(is_global_phase(name) for name in GLOBAL_PHASES)
    assert all(is_per_design_phase(name) for name in PER_DESIGN_PHASES)
    assert not GLOBAL_PHASES & PER_DESIGN_PHASES
    assert phase_scope("run_infrastructure") == "global"
    assert phase_scope("visual_analysis") == "per_design"
    validate_phase_scope("run_infrastructure", None)
    validate_phase_scope("visual_analysis", "design_a")


def test_phase_prerequisites_are_available_for_every_phase() -> None:
    assert phase_prerequisites("run_infrastructure") == ()
    assert phase_prerequisites("page_asset_rendering") == ("source_pdf",)
    assert set(PHASE_PREREQUISITES) == set(PIPELINE_PHASES)
