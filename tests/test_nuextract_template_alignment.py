from antenna_ingest.nuextract.candidate_template import (
    ANTENNA_DESIGN_CANDIDATE_TEMPLATE,
    EVIDENCE_TEMPLATE,
    RESULT_TEMPLATE,
)


def test_evidence_template_contains_figure_ref() -> None:
    assert "figure_ref" in EVIDENCE_TEMPLATE


def test_result_template_contains_result_source() -> None:
    assert "result_source" in RESULT_TEMPLATE


def test_final_design_template_contains_properties() -> None:
    assert "properties" in ANTENNA_DESIGN_CANDIDATE_TEMPLATE["final_design"]


def test_simulation_setup_template_contains_mesh_and_port_settings() -> None:
    simulation_setup = ANTENNA_DESIGN_CANDIDATE_TEMPLATE["final_design"][
        "simulation_setup"
    ]
    assert "mesh_settings" in simulation_setup
    assert "port_settings" in simulation_setup
