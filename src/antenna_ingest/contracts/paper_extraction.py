from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from antenna_ingest.contracts.base import ContractModel
from antenna_ingest.contracts.common import (
    ConflictRecord,
    DesignRecord,
    DocumentReference,
    EvidenceRecord,
    Identifier,
    LegibilityState,
    MissingInformationRecord,
    NonEmptyString,
    PageRecord,
    ReportedCondition,
    ResultRecord,
    Setup,
    SourceValue,
    ensure_unique_ids,
    validate_shared_references,
)


class ObservationBase(ContractModel):
    observation_id: Identifier
    design_id: Identifier | None = None
    description: NonEmptyString
    evidence_ids: list[Identifier] = Field(min_length=1)
    legibility: LegibilityState = "clear"
    uncertainty_note: NonEmptyString | None = None


class MaterialObservation(ObservationBase):
    material_name: NonEmptyString | None = None
    reported_properties: list[ReportedCondition] = Field(default_factory=list)


class ParameterObservation(ObservationBase):
    symbol: NonEmptyString | None = None
    reported_value: SourceValue | None = None


class GeometryObservation(ObservationBase):
    source_feature_label: NonEmptyString | None = None


class FeedPortExcitationObservation(ObservationBase):
    observation_kind: Literal["feed", "port", "excitation"]
    reported_impedance: SourceValue | None = None


class ReportedDerivation(ContractModel):
    derivation_id: Identifier
    description: NonEmptyString
    expression_text: NonEmptyString | None = None
    symbols: list[NonEmptyString] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(min_length=1)


class PaperExtraction(ContractModel):
    schema_name: Literal["paper_extraction"]
    schema_version: Literal["1.0.0"]
    document: DocumentReference
    pages: list[PageRecord] = Field(min_length=1)
    evidence_catalog: list[EvidenceRecord] = Field(
        description=(
            "Minimal catalog of distinct source items that directly support emitted "
            "records; exclude unreferenced source material."
        )
    )
    designs: list[DesignRecord] = Field(
        description=(
            "Distinct antenna designs studied by this paper, excluding designs "
            "mentioned only as related work."
        )
    )
    material_observations: list[MaterialObservation] = Field(
        description=(
            "Materials and material properties actually used in reported designs, "
            "fabrication, simulation, or measurement."
        )
    )
    parameter_observations: list[ParameterObservation] = Field(
        description=(
            "Specific antenna, simulation, or measurement parameters; exclude "
            "paper organisation, general prose, and literature-review statements."
        )
    )
    geometry_observations: list[GeometryObservation] = Field(
        description=(
            "Physical geometry, topology, dimensions, placement, and structural "
            "relationships; exclude descriptions of paper organisation."
        )
    )
    feed_port_excitation_observations: list[FeedPortExcitationObservation] = Field(
        description=(
            "Reported feeds, feeding arrangements, ports, excitation methods, and "
            "impedances for extracted designs."
        )
    )
    setups: list[Setup] = Field(
        description=(
            "Simulation, measurement, or analytical configurations used by this "
            "paper; exclude configurations belonging only to cited related work."
        )
    )
    results: list[ResultRecord] = Field(
        description=(
            "Source-supported antenna performance values or qualitative findings "
            "with their reported origin."
        )
    )
    derivations: list[ReportedDerivation] = Field(
        description=(
            "Source-reported equations, formulas, or calculation procedures; a "
            "reported value or dimension alone is not a derivation."
        )
    )
    conflicts: list[ConflictRecord] = Field(
        description=(
            "Incompatible scientific values, claims, design descriptions, or "
            "findings; exclude conflict-of-interest declarations."
        )
    )
    missing_information: list[MissingInformationRecord] = Field(
        description=(
            "Technically relevant information that is genuinely absent, unavailable, "
            "or required to interpret an emitted record; exclude reported conclusions "
            "and positive findings."
        )
    )
    architecture_page_refs: list[int] = Field(
        description=(
            "Globally one-based input page numbers containing evidence relevant to "
            "later antenna-architecture reconstruction."
        )
    )

    @model_validator(mode="after")
    def validate_referential_integrity(self) -> PaperExtraction:
        expected_pages = list(range(1, self.document.page_count + 1))
        declared_pages = [page.page_number for page in self.pages]
        if declared_pages != expected_pages:
            raise ValueError(
                "declared pages must be complete, globally one-based, and ordered"
            )

        material_ids = ensure_unique_ids(
            self.material_observations,
            "observation_id",
            "material observations",
        )
        parameter_ids = ensure_unique_ids(
            self.parameter_observations,
            "observation_id",
            "parameter observations",
        )
        geometry_ids = ensure_unique_ids(
            self.geometry_observations,
            "observation_id",
            "geometry observations",
        )
        feed_port_ids = ensure_unique_ids(
            self.feed_port_excitation_observations,
            "observation_id",
            "feed, port, and excitation observations",
        )
        derivation_ids = ensure_unique_ids(
            self.derivations,
            "derivation_id",
            "derivations",
        )

        reference_index = validate_shared_references(
            pages=self.pages,
            evidence=self.evidence_catalog,
            designs=self.designs,
            setups=self.setups,
            results=self.results,
            conflicts=self.conflicts,
            missing_information=self.missing_information,
            additional_ids={
                "material_observation": material_ids,
                "parameter_observation": parameter_ids,
                "geometry_observation": geometry_ids,
                "feed_port_excitation_observation": feed_port_ids,
                "derivation": derivation_ids,
            },
        )

        design_ids = reference_index["design"]
        evidence_ids = reference_index["evidence"]
        for observation in [
            *self.material_observations,
            *self.parameter_observations,
            *self.geometry_observations,
            *self.feed_port_excitation_observations,
        ]:
            if observation.design_id is not None and observation.design_id not in design_ids:
                raise ValueError(
                    f"observation {observation.observation_id!r} references "
                    f"unknown design {observation.design_id!r}"
                )
            _ensure_known_evidence(observation.evidence_ids, evidence_ids)

        for derivation in self.derivations:
            _ensure_known_evidence(derivation.evidence_ids, evidence_ids)

        declared_page_numbers = set(declared_pages)
        unknown_page_refs = set(self.architecture_page_refs) - declared_page_numbers
        if unknown_page_refs:
            raise ValueError(
                "architecture page references undeclared pages: "
                + ", ".join(str(item) for item in sorted(unknown_page_refs))
            )
        if len(self.architecture_page_refs) != len(set(self.architecture_page_refs)):
            raise ValueError("duplicate architecture page references")
        return self


def _ensure_known_evidence(
    referenced_ids: list[str],
    evidence_ids: set[str],
) -> None:
    unknown = set(referenced_ids) - evidence_ids
    if unknown:
        rendered = ", ".join(sorted(repr(item) for item in unknown))
        raise ValueError(f"unknown evidence reference(s): {rendered}")
