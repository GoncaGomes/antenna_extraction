from __future__ import annotations

import ast
import json
import shutil
import socket
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.benchmark.loader import load_benchmark_suite
from tests.benchmark.models import (
    BenchmarkAssertion,
    PaperExpectations,
    PapersManifest,
    SyntheticCoverageManifest,
)


REPOSITORY_ROOT = Path(__file__).parents[2]
BENCHMARK_ROOT = REPOSITORY_ROOT / "benchmarks" / "v2"
REQUIRED_FAILURES = {
    "exact_reported_result_loss",
    "derived_geometry_loss",
    "inset_notch_loss",
    "variant_association_loss",
    "false_complete_architecture",
}
REQUIRED_SYNTHETIC_CATEGORIES = {
    "planar_stack",
    "polygon_with_circular_subtraction",
    "inset_notch",
    "multilayer_stacked",
    "via_short",
    "wire_meander",
    "helix_sweep",
    "array_instances",
    "horn_tapered_volume",
    "dielectric_resonator",
    "conformal_surface_mesh",
    "implantable_surroundings",
    "incomplete_architecture",
}


def test_benchmark_loads_in_deterministic_order() -> None:
    first = load_benchmark_suite(REPOSITORY_ROOT)
    second = load_benchmark_suite(REPOSITORY_ROOT)

    assert [paper.paper_id for paper in first.papers.papers] == [
        "001",
        "002",
        "003",
        "004",
        "005",
        "006",
        "007",
        "008",
    ]
    assert first == second


def test_extra_fields_are_rejected() -> None:
    data = _read_json(BENCHMARK_ROOT / "papers.json")
    data["unexpected"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PapersManifest.model_validate(data)


@pytest.mark.parametrize("duplicate_field", ["paper_id", "local_path"])
def test_duplicate_paper_ids_and_paths_are_rejected(duplicate_field: str) -> None:
    data = _read_json(BENCHMARK_ROOT / "papers.json")
    data["papers"][1][duplicate_field] = data["papers"][0][duplicate_field]

    with pytest.raises(ValidationError, match="duplicate"):
        PapersManifest.model_validate(data)


def test_unknown_paper_id_is_rejected(tmp_path: Path) -> None:
    root = _copy_benchmark(tmp_path)
    expectation_path = root / "expectations/regression/001_rectangular_patch_coaxial.json"
    data = _read_json(expectation_path)
    data["paper_id"] = "999"
    _write_json(expectation_path, data)

    with pytest.raises(ValueError, match="unknown paper association"):
        load_benchmark_suite(REPOSITORY_ROOT, root)


def test_duplicate_expectation_ids_across_files_are_rejected(
    tmp_path: Path,
) -> None:
    root = _copy_benchmark(tmp_path)
    first_path = root / "expectations/regression/001_rectangular_patch_coaxial.json"
    second_path = (
        root
        / "expectations/regression/002_circular_slotted_triangular_patch.json"
    )
    first = _read_json(first_path)
    second = _read_json(second_path)
    second["expectation_id"] = first["expectation_id"]
    _write_json(second_path, second)

    with pytest.raises(ValueError, match="duplicate expectation_id"):
        load_benchmark_suite(REPOSITORY_ROOT, root)


def test_duplicate_assertion_ids_across_files_are_rejected(
    tmp_path: Path,
) -> None:
    root = _copy_benchmark(tmp_path)
    first_path = root / "expectations/regression/001_rectangular_patch_coaxial.json"
    second_path = (
        root
        / "expectations/regression/002_circular_slotted_triangular_patch.json"
    )
    first = _read_json(first_path)
    second = _read_json(second_path)
    second["assertions"][0]["assertion_id"] = first["assertions"][0][
        "assertion_id"
    ]
    _write_json(second_path, second)

    with pytest.raises(ValueError, match="duplicate assertion_id"):
        load_benchmark_suite(REPOSITORY_ROOT, root)


def test_unknown_paper_and_expectation_paths_are_rejected(tmp_path: Path) -> None:
    root = _copy_benchmark(tmp_path)
    papers_path = root / "papers.json"
    data = _read_json(papers_path)
    data["papers"][0]["local_path"] = "tests/fixtures/papers/raw/not-a-paper.pdf"
    data["papers"][0]["local_filename"] = "not-a-paper.pdf"
    _write_json(papers_path, data)

    with pytest.raises(ValueError, match="does not exist"):
        load_benchmark_suite(REPOSITORY_ROOT, root)

    root = _copy_benchmark(tmp_path, "expectation-path")
    papers_path = root / "papers.json"
    data = _read_json(papers_path)
    data["papers"][0]["expectation_paths"] = ["expectations/missing.json"]
    _write_json(papers_path, data)

    with pytest.raises(ValueError, match="unknown expectation path"):
        load_benchmark_suite(REPOSITORY_ROOT, root)


def test_unreferenced_expectation_file_is_rejected(tmp_path: Path) -> None:
    root = _copy_benchmark(tmp_path)
    source = root / "expectations/regression/001_rectangular_patch_coaxial.json"
    shutil.copyfile(source, root / "expectations/regression/unknown.json")

    with pytest.raises(ValueError, match="unreferenced expectation files"):
        load_benchmark_suite(REPOSITORY_ROOT, root)


def test_unknown_group_is_rejected() -> None:
    data = _read_json(BENCHMARK_ROOT / "papers.json")
    data["papers"][0]["group"] = "other"

    with pytest.raises(ValidationError):
        PapersManifest.model_validate(data)


def test_malformed_and_mismatched_checksums_are_rejected(tmp_path: Path) -> None:
    malformed = _read_json(BENCHMARK_ROOT / "papers.json")
    malformed["papers"][0]["sha256"] = "not-a-checksum"
    with pytest.raises(ValidationError):
        PapersManifest.model_validate(malformed)

    root = _copy_benchmark(tmp_path)
    papers_path = root / "papers.json"
    mismatch = _read_json(papers_path)
    mismatch["papers"][0]["sha256"] = "0" * 64
    _write_json(papers_path, mismatch)
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_benchmark_suite(REPOSITORY_ROOT, root)


def test_page_count_mismatch_is_rejected(tmp_path: Path) -> None:
    root = _copy_benchmark(tmp_path)
    papers_path = root / "papers.json"
    data = _read_json(papers_path)
    data["papers"][0]["page_count"] += 1
    _write_json(papers_path, data)

    with pytest.raises(ValueError, match="page count mismatch"):
        load_benchmark_suite(REPOSITORY_ROOT, root)


def test_evidence_page_outside_paper_is_rejected(tmp_path: Path) -> None:
    root = _copy_benchmark(tmp_path)
    expectation_path = root / "expectations/regression/001_rectangular_patch_coaxial.json"
    data = _read_json(expectation_path)
    data["assertions"][0]["evidence"][0]["page"] = 6
    _write_json(expectation_path, data)

    with pytest.raises(ValueError, match="outside paper 001 page range"):
        load_benchmark_suite(REPOSITORY_ROOT, root)


@pytest.mark.parametrize(
    ("target", "field", "invalid"),
    [
        ("expectation", "stage", "publication"),
        ("expectation", "mode", "assisted"),
        ("review", "status", "approved"),
        ("synthetic", "category", "unknown_geometry"),
    ],
)
def test_unknown_enumerated_values_are_rejected(
    target: str,
    field: str,
    invalid: str,
) -> None:
    if target == "expectation":
        data = _read_json(
            BENCHMARK_ROOT
            / "expectations/regression/001_rectangular_patch_coaxial.json"
        )
        data["assertions"][0][field] = invalid
        model = PaperExpectations
    elif target == "review":
        data = _read_json(
            BENCHMARK_ROOT
            / "expectations/regression/001_rectangular_patch_coaxial.json"
        )
        data["review"][field] = invalid
        model = PaperExpectations
    else:
        data = _read_json(BENCHMARK_ROOT / "synthetic_coverage.json")
        data["coverage"][0][field] = invalid
        model = SyntheticCoverageManifest

    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_automatic_assertion_requires_verifiable_condition() -> None:
    data = _assertion_data("001", 0)
    data["verifiable_condition"] = None

    with pytest.raises(ValidationError, match="verifiable condition"):
        BenchmarkAssertion.model_validate(data)


@pytest.mark.parametrize("missing", ["review_instruction", "evidence"])
def test_manual_assertion_requires_instruction_and_evidence(missing: str) -> None:
    data = _assertion_data("002", 0)
    data[missing] = None if missing == "review_instruction" else []

    with pytest.raises(ValidationError):
        BenchmarkAssertion.model_validate(data)


def test_exact_regression_value_and_unit_are_preserved() -> None:
    suite = load_benchmark_suite(REPOSITORY_ROOT)
    assertion = suite.expectations[0].assertions[0]

    assert assertion.expected.value == "47.98"
    assert assertion.expected.unit == "ohm"
    assert assertion.verifiable_condition is not None
    assert assertion.verifiable_condition.expected_text == "47.98 ohm"


def test_all_five_known_failure_classes_are_present() -> None:
    suite = load_benchmark_suite(REPOSITORY_ROOT)
    failures = {
        assertion.known_failure
        for expectation in suite.expectations
        for assertion in expectation.assertions
        if assertion.known_failure is not None
    }

    assert failures == REQUIRED_FAILURES


def test_paper_005_prohibits_invented_architecture_materials() -> None:
    suite = load_benchmark_suite(REPOSITORY_ROOT)
    expectation = next(
        item for item in suite.expectations if item.paper_id == "005"
    )
    assertion = next(
        item
        for item in expectation.assertions
        if item.assertion_id == "005-architecture-no-invented-material-properties"
    )

    assert expectation.review.status == "reviewed"
    assert expectation.review.human_review_confirmed is True
    assert expectation.review.reviewed_at == "2026-08-14"
    assert assertion.stage == "architecture"
    assert assertion.mode == "manual"
    assert assertion.expected.forbidden_condition is not None
    assert "unsupported" in assertion.expected.forbidden_condition


def test_geometry_coverage_contains_required_papers() -> None:
    suite = load_benchmark_suite(REPOSITORY_ROOT)
    geometry = {
        paper.paper_id: (paper.title, paper.doi)
        for paper in suite.papers.papers
        if paper.group == "geometry_coverage"
    }

    assert geometry == {
        "006": (
            "Design of a Deployable Helix Antenna at L-Band for a 1-Unit "
            "CubeSat: From Theoretical Analysis to Flight Model Results",
            "10.3390/s22103633",
        ),
        "007": (
            "Performance Analysis of X Band Horn Antennas using Additive "
            "Manufacturing Method Coated with Different Techniques",
            "10.1590/2179-10742019v18i21337",
        ),
        "008": (
            "Design and implementation of compact dual-band conformal antenna "
            "for leadless cardiac pacemaker system",
            "10.1038/s41598-022-06904-2",
        ),
    }


def test_synthetic_coverage_is_complete_and_links_real_cases() -> None:
    suite = load_benchmark_suite(REPOSITORY_ROOT)
    entries = suite.synthetic_coverage.coverage
    assert {entry.category for entry in entries} == REQUIRED_SYNTHETIC_CATEGORIES

    source_path = REPOSITORY_ROOT / "tests/contracts/test_architecture_geometry.py"
    source = ast.parse(source_path.read_text(encoding="utf-8"))
    source_strings = {
        node.value
        for node in ast.walk(source)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    for entry in entries:
        assert (REPOSITORY_ROOT / entry.test_path).is_file()
        assert entry.case_id in source_strings


def test_unknown_synthetic_case_is_rejected(tmp_path: Path) -> None:
    root = _copy_benchmark(tmp_path)
    path = root / "synthetic_coverage.json"
    data = _read_json(path)
    data["coverage"][0]["case_id"] = "not_a_real_case"
    _write_json(path, data)

    with pytest.raises(ValueError, match="unknown synthetic case"):
        load_benchmark_suite(REPOSITORY_ROOT, root)


def test_review_statuses_distinguish_regression_and_geometry_coverage() -> None:
    suite = load_benchmark_suite(REPOSITORY_ROOT)
    expectations = {
        expectation.paper_id: expectation for expectation in suite.expectations
    }

    for paper_id in ("001", "002", "003", "004", "005"):
        expectation = expectations[paper_id]
        assert expectation.review.status == "reviewed"
        assert expectation.review.human_review_confirmed is True
        assert expectation.review.reviewed_at == "2026-08-14"

    for paper_id in ("006", "007", "008"):
        expectation = expectations[paper_id]
        assert expectation.review.status == "needs_review"
        assert expectation.review.human_review_confirmed is False
        assert expectation.review.reviewed_at is None


def test_loader_does_not_require_network_or_remote_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("benchmark validation attempted network access")

    monkeypatch.setattr(socket, "socket", reject_network)

    suite = load_benchmark_suite(REPOSITORY_ROOT)

    assert len(suite.papers.papers) == 8


def _copy_benchmark(tmp_path: Path, name: str = "benchmark") -> Path:
    destination = tmp_path / name
    return Path(shutil.copytree(BENCHMARK_ROOT, destination))


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _assertion_data(paper_id: str, index: int) -> dict:
    path = next(
        (BENCHMARK_ROOT / "expectations").rglob(f"{paper_id}_*.json")
    )
    return _read_json(path)["assertions"][index]
