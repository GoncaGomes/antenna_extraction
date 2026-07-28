from __future__ import annotations

from typing import Literal

PIPELINE_PHASES = [
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

GLOBAL_PHASES = frozenset((*PIPELINE_PHASES[:9], PIPELINE_PHASES[-1]))
PER_DESIGN_PHASES = frozenset(PIPELINE_PHASES[9:19])

PHASE_PREREQUISITES: dict[str, tuple[str, ...]] = {
    "run_infrastructure": (),
    "page_asset_rendering": ("source_pdf",),
    "pdf_text_extraction": ("source_pdf",),
    "document_page_parsing": ("page_assets", "pdf_text_layers"),
    "document_region_parsing": ("document_page_parses",),
    "document_consolidation": (
        "document_page_parses",
        "document_region_parses",
    ),
    "antenna_candidate_extraction": ("multimodal_document_model",),
    "evidence_indexing": ("multimodal_document_model",),
    "design_resolution": ("antenna_candidate_v3", "evidence_index"),
    "visual_task_planning": ("design_resolution",),
    "visual_analysis": ("visual_task_plan",),
    "architecture_evidence_packet": ("design_resolution", "evidence_index"),
    "architecture_claim_generation": ("architecture_evidence_packet",),
    "architecture_blueprint": ("architecture_claim_graph",),
    "architecture_synthesis": (
        "architecture_evidence_packet",
        "architecture_claim_graph",
        "architecture_blueprint",
    ),
    "architecture_structural_validation": (
        "antenna_architecture_draft",
        "architecture_provenance_draft",
    ),
    "architecture_verification": (
        "antenna_architecture_draft",
        "architecture_provenance_draft",
        "architecture_claim_graph",
    ),
    "architecture_finalization": (
        "antenna_architecture_draft",
        "architecture_provenance_draft",
        "architecture_verification",
    ),
    "architecture_validation": (
        "antenna_architecture",
        "architecture_provenance",
        "architecture_corrections",
    ),
    "architecture_set_finalization": (
        "design_resolution",
        "architecture_design_outputs",
    ),
}


def is_pipeline_phase(phase_name: str) -> bool:
    return phase_name in PHASE_PREREQUISITES


def is_global_phase(phase_name: str) -> bool:
    return phase_name in GLOBAL_PHASES


def is_per_design_phase(phase_name: str) -> bool:
    return phase_name in PER_DESIGN_PHASES


def phase_scope(phase_name: str) -> Literal["global", "per_design"]:
    if is_global_phase(phase_name):
        return "global"
    if is_per_design_phase(phase_name):
        return "per_design"
    raise ValueError(f"unknown pipeline phase: {phase_name}")


def validate_phase_scope(phase_name: str, design_id: str | None) -> None:
    scope = phase_scope(phase_name)
    if scope == "global" and design_id is not None:
        raise ValueError(f"global phase {phase_name!r} cannot have a design scope")
    if scope == "per_design" and design_id is None:
        raise ValueError(f"per-design phase {phase_name!r} requires a design_id")


def phase_prerequisites(phase_name: str) -> tuple[str, ...]:
    return PHASE_PREREQUISITES.get(phase_name, ())


def phase_position(phase_name: str) -> int:
    try:
        return PIPELINE_PHASES.index(phase_name)
    except ValueError as error:
        raise ValueError(f"unknown pipeline phase: {phase_name}") from error
