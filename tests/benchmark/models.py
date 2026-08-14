from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


def _reject_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be blank")
    return value


NonEmptyString = Annotated[
    str,
    StringConstraints(strict=True, min_length=1),
    AfterValidator(_reject_blank),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

PaperGroup = Literal["regression", "geometry_coverage"]
ReviewStatus = Literal[
    "draft",
    "needs_review",
    "reviewed",
    "disputed",
    "illegible",
    "unable_to_conclude",
]
AssertionStage = Literal["extraction", "results", "architecture"]
AssertionMode = Literal["automatic", "manual"]
Criticality = Literal["critical", "major", "minor"]
EvidenceKind = Literal["text", "figure", "table", "equation"]
SourceIssueKind = Literal["disagreement", "illegible", "unable_to_conclude"]
KnownFailure = Literal[
    "exact_reported_result_loss",
    "derived_geometry_loss",
    "inset_notch_loss",
    "variant_association_loss",
    "false_complete_architecture",
]
SyntheticCategory = Literal[
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
]


class StrictBenchmarkModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LicenseEvidence(StrictBenchmarkModel):
    source: Literal["pdf", "publisher_policy"]
    reference: NonEmptyString
    license_name: NonEmptyString
    note: NonEmptyString | None = None


class PaperRecord(StrictBenchmarkModel):
    paper_id: Annotated[str, StringConstraints(pattern=r"^[0-9]{3}$")]
    group: PaperGroup
    title: NonEmptyString
    doi: NonEmptyString | None = None
    local_filename: NonEmptyString
    local_path: NonEmptyString
    sha256: Sha256
    page_count: int = Field(ge=1)
    acquisition_url: NonEmptyString
    license_status: Literal["verified", "requires_reacquisition", "not_redistributable"]
    license_evidence: LicenseEvidence
    redistribution_policy: Literal[
        "permitted_with_attribution",
        "permitted_noncommercial_no_derivatives",
        "local_acquisition_only",
    ]
    expectation_paths: list[NonEmptyString] = Field(min_length=1)

    @field_validator("acquisition_url")
    @classmethod
    def validate_acquisition_url(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("acquisition_url must be an HTTP(S) URL")
        return value


class PapersManifest(StrictBenchmarkModel):
    schema_version: Literal["1.0.0"]
    papers: list[PaperRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_references(self) -> PapersManifest:
        _require_unique([paper.paper_id for paper in self.papers], "paper IDs")
        _require_unique([paper.local_path for paper in self.papers], "paper paths")
        expectation_paths = [
            path for paper in self.papers for path in paper.expectation_paths
        ]
        _require_unique(expectation_paths, "expectation paths")
        return self


class ReviewRecord(StrictBenchmarkModel):
    status: ReviewStatus
    reviewer_identity: NonEmptyString
    reviewer_role: NonEmptyString
    review_version: NonEmptyString
    reviewed_at: NonEmptyString | None = None
    human_review_confirmed: bool
    prepared_by: NonEmptyString

    @field_validator("reviewed_at")
    @classmethod
    def validate_review_date(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("reviewed_at must be an ISO calendar date") from exc
        return value

    @model_validator(mode="after")
    def validate_review_state(self) -> ReviewRecord:
        if self.status == "reviewed":
            if not self.human_review_confirmed or self.reviewed_at is None:
                raise ValueError(
                    "reviewed expectations require dated human confirmation"
                )
        elif self.human_review_confirmed:
            raise ValueError("human confirmation requires reviewed status")
        return self


class EvidenceLocator(StrictBenchmarkModel):
    page: int = Field(ge=1)
    source_kind: EvidenceKind
    source_label: NonEmptyString | None = None
    excerpt_or_description: NonEmptyString


class SourceIssue(StrictBenchmarkModel):
    kind: SourceIssueKind
    note: NonEmptyString


class ExpectedOutcome(StrictBenchmarkModel):
    summary: NonEmptyString
    value: NonEmptyString | None = None
    unit: NonEmptyString | None = None
    acceptable_alternative: NonEmptyString | None = None
    forbidden_condition: NonEmptyString | None = None


class VerifiableCondition(StrictBenchmarkModel):
    operator: Literal[
        "contains_exact_text",
        "contains_required_structure",
        "excludes_unsupported_content",
        "preserves_association",
        "status_equals",
    ]
    target: NonEmptyString
    expected_text: NonEmptyString | None = None
    forbidden_text: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_condition(self) -> VerifiableCondition:
        if self.expected_text is None and self.forbidden_text is None:
            raise ValueError("a verifiable condition requires expected or forbidden text")
        return self


class BenchmarkAssertion(StrictBenchmarkModel):
    assertion_id: NonEmptyString
    stage: AssertionStage
    mode: AssertionMode
    criticality: Criticality
    blocking: bool
    known_failure: KnownFailure | None = None
    evidence: list[EvidenceLocator] = Field(min_length=1)
    expected: ExpectedOutcome
    verifiable_condition: VerifiableCondition | None = None
    review_instruction: NonEmptyString | None = None
    source_issues: list[SourceIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> BenchmarkAssertion:
        if self.mode == "automatic" and self.verifiable_condition is None:
            raise ValueError("automatic assertions require a verifiable condition")
        if self.mode == "manual" and self.review_instruction is None:
            raise ValueError("manual assertions require a review instruction")
        return self


class PaperExpectations(StrictBenchmarkModel):
    schema_version: Literal["1.0.0"]
    expectation_id: NonEmptyString
    paper_id: Annotated[str, StringConstraints(pattern=r"^[0-9]{3}$")]
    version: NonEmptyString
    review: ReviewRecord
    assertions: list[BenchmarkAssertion] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_assertions(self) -> PaperExpectations:
        _require_unique(
            [assertion.assertion_id for assertion in self.assertions],
            "assertion IDs",
        )
        return self


class SyntheticCoverageEntry(StrictBenchmarkModel):
    category: SyntheticCategory
    test_path: NonEmptyString
    case_id: NonEmptyString


class SyntheticCoverageManifest(StrictBenchmarkModel):
    schema_version: Literal["1.0.0"]
    coverage: list[SyntheticCoverageEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_categories(self) -> SyntheticCoverageManifest:
        _require_unique(
            [entry.category for entry in self.coverage],
            "synthetic categories",
        )
        return self


def _require_unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} are not permitted")
