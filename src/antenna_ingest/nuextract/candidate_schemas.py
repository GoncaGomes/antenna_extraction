from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_NAME = "antenna_design_candidate_v2"
 
RECONSTRUCTION_STATUSES = (
    "buildable",
    "partially_buildable",
    "not_buildable_from_paper",
    "unknown",
)
 
RESULT_SOURCES = (
    "simulated",
    "measured",
    "both",
    "unknown",
)
 
RESULT_METRICS = (
    "resonant_frequency",
    "operating_frequency_range",
    "bandwidth",
    "return_loss",
    "s11",
    "s11_magnitude",
    "vswr",
    "gain",
    "directivity",
    "efficiency",
    "input_impedance",
    "axial_ratio",
    "radiation_pattern",
    "sar",
    "current_distribution",
    "unknown",
)
 
 
# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------
 
class StrictModel(BaseModel):
    """Base model that forbids extra fields."""
 
    model_config = ConfigDict(extra="forbid")
 
 
# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------
 
class EvidenceRef(StrictModel):
    """Provenance pointer to a specific location in the source PDF."""
 
    page: int | None = Field(
        default=None,
        ge=1,
        description="PDF_INPUT_PAGE=N index (not printed page number).",
    )
    figure_ref: str | None = Field(
        default=None,
        description=(
            "Figure or table label exactly as printed, e.g. 'Fig. 3', "
            "'Table II', 'Fig. 5(b)'. Populate whenever the source is a "
            "figure or table rather than running prose."
        ),
    )
    quote: str | None = Field(
        default=None,
        description="Short verbatim excerpt supporting the extracted fact.",
    )
    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Extraction confidence in [0, 1].",
    )
 
 
class ExtractedProperty(StrictModel):
    """A single scalar fact with symbol, value, unit, and provenance."""
 
    name: str | None = None
    symbol: str | None = Field(
        default=None,
        description=(
            "Algebraic symbol exactly as written in the paper "
            "(e.g., W, Lg, Xf, epsilon_r, tan_delta)."
        ),
    )
    raw_value: str | None = Field(
        default=None,
        description="Value as it appears in the paper, including units if printed together.",
    )
    value: float | str | bool | None = None
    unit: str | None = Field(
        default=None,
        description="Unit exactly as printed. Do not normalize.",
    )
    evidence: list[EvidenceRef] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
 
    def is_empty(self) -> bool:
        return (
            self.name is None
            and self.symbol is None
            and self.raw_value is None
            and self.value is None
            and self.unit is None
            and not self.evidence
            and not self.notes
        )
 
 
# ---------------------------------------------------------------------------
# Document metadata
# ---------------------------------------------------------------------------
 
class DocumentMetadata(StrictModel):
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    venue: str | None = None
 
 
# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
 
class CandidateSummary(StrictModel):
    antenna_name: str | None = None
    antenna_class: str | None = Field(
        default=None,
        description=(
            "High-level antenna class, e.g. 'microstrip patch', 'PIFA', "
            "'Vivaldi', 'monopole', 'dipole', 'slot', 'helical'."
        ),
    )
    application: str | None = None
    operating_band: str | None = None
    reconstruction_status: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
 
    @field_validator("reconstruction_status")
    @classmethod
    def validate_reconstruction_status(cls, value: str | None) -> str | None:
        return _validate_reconstruction_status(value)
 
 
# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
 
class MaterialCandidate(StrictModel):
    material_id: str
    name: str | None = None
    role: str | None = Field(
        default=None,
        description=(
            "Role in the antenna structure, e.g. 'substrate', 'conductor', "
            "'superstrate', 'absorber'."
        ),
    )
    properties: list[ExtractedProperty] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
 
 
# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
 
class GeometryDescription(StrictModel):
    representation: str | None = Field(
        default=None,
        description="Parametric, CSG, mesh, or other representation type.",
    )
    primitive_type: str | None = Field(
        default=None,
        description="Basic primitive shape: rectangle, circle, polygon, etc.",
    )
    shape_family: str | None = Field(
        default=None,
        description="Higher-level family: patch, strip, ring, spiral, fractal, etc.",
    )
    description: str | None = None
    coordinate_system: str | None = Field(
        default=None,
        description=(
            "Reference frame or coordinate system explicitly stated in the paper, "
            "e.g. 'origin at patch center', 'x along feedline axis'. "
            "Verbatim from text when available."
        ),
    )
    properties: list[ExtractedProperty] = Field(default_factory=list)
    topological_relationship: str | None = Field(
        default=None,
        description=(
            "Verbatim relational placement phrase from the paper, e.g. "
            "'printed on the top surface of the substrate', "
            "'etched in the ground plane', 'centered on the patch'."
        ),
    )
    reconstruction_status: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
 
    @field_validator("reconstruction_status")
    @classmethod
    def validate_reconstruction_status(cls, value: str | None) -> str | None:
        return _validate_reconstruction_status(value)
 
 
# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------
 
class ComponentCandidate(StrictModel):
    component_id: str
    label: str | None = None
    role: str | None = Field(
        default=None,
        description=(
            "Functional role: 'radiating patch', 'ground plane', 'substrate', "
            "'feedline', 'parasitic element', 'stub', 'reflector', etc."
        ),
    )
    material_id: str | None = Field(
        default=None,
        description="References a material_id in final_design.materials.",
    )
    geometry: GeometryDescription = Field(default_factory=GeometryDescription)
    properties: list[ExtractedProperty] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
 
 
# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------
 
class FeatureCandidate(StrictModel):
    feature_id: str
    label: str | None = None
    feature_type: str | None = Field(
        default=None,
        description=(
            "Type of geometric modification: slot, notch, cut-out, meander, gap, "
            "DGS, truncation, chamfer, branch, aperture, fractal, etc."
        ),
    )
    associated_component_id: str | None = Field(
        default=None,
        description="component_id of the component this feature modifies.",
    )
    description: str | None = None
    properties: list[ExtractedProperty] = Field(default_factory=list)
    topological_relationship: str | None = Field(
        default=None,
        description="Verbatim relational placement phrase from the paper.",
    )
    evidence: list[EvidenceRef] = Field(default_factory=list)
 
 
# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------
 
class FeedCandidate(StrictModel):
    feed_id: str
    feed_type: str | None = Field(
        default=None,
        description=(
            "Feed mechanism type: microstrip line, coaxial probe, aperture "
            "coupling, proximity coupling, CPW, SMA connector, etc."
        ),
    )
    associated_component_id: str | None = Field(
        default=None,
        description="component_id of the feedline component, if one exists.",
    )
    description: str | None = None
    properties: list[ExtractedProperty] = Field(
        default_factory=list,
        description=(
            "Electrical excitation properties: port impedance, port type, "
            "feed offset coordinates (Xf, Yf), inset depth, etc."
        ),
    )
    evidence: list[EvidenceRef] = Field(default_factory=list)
 
 
# ---------------------------------------------------------------------------
# Simulation setup
# ---------------------------------------------------------------------------
 
class SimulationSetupCandidate(StrictModel):
    software: str | None = Field(
        default=None,
        description=(
            "Canonical software name: 'CST Studio Suite', 'ANSYS HFSS', "
            "'FEKO', 'ADS', 'IE3D', 'COMSOL', etc. "
            "Record raw name from paper in notes."
        ),
    )
    solver: str | None = Field(
        default=None,
        description="Solver type if stated: FEM, MoM, FDTD, FIT, etc.",
    )
    boundary_conditions: str | None = None
    frequency_sweep: list[ExtractedProperty] = Field(default_factory=list)
    mesh_settings: list[ExtractedProperty] = Field(
        default_factory=list,
        description="Mesh size, cells per wavelength, or adaptive mesh settings.",
    )
    port_settings: list[ExtractedProperty] = Field(
        default_factory=list,
        description="Waveguide port, lumped port, or discrete port settings.",
    )
    properties: list[ExtractedProperty] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
 
 
# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
 
class ResultCandidate(StrictModel):
    metric: str = Field(
        description=(
            "Use preferred metric names: resonant_frequency, "
            "operating_frequency_range, bandwidth, return_loss, s11, "
            "s11_magnitude, vswr, gain, directivity, efficiency, "
            "input_impedance, axial_ratio, radiation_pattern, sar, "
            "current_distribution, unknown."
        )
    )
    result_source: str | None = Field(
        default=None,
        description=(
            "Origin of the result: 'simulated', 'measured', 'both', or 'unknown'. "
            "Mandatory for every result entry."
        ),
    )
    raw_value: str | None = None
    value: float | str | bool | None = None
    unit: str | None = None
    condition: str | None = Field(
        default=None,
        description=(
            "Verbatim frequency, band, mode, or angular condition under which "
            "this result applies, e.g. 'at 2.45 GHz', 'in Band 2', "
            "'theta=0 deg', 'co-polarization'."
        ),
    )
    evidence: list[EvidenceRef] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
 
    @field_validator("result_source")
    @classmethod
    def validate_result_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in RESULT_SOURCES:
            allowed = ", ".join(RESULT_SOURCES)
            raise ValueError(f"result_source must be one of: {allowed}")
        return value
 
 
# ---------------------------------------------------------------------------
# Final design
# ---------------------------------------------------------------------------
 
class FinalDesignCandidate(StrictModel):
    design_label: str | None = None
    is_explicitly_final_or_proposed: bool | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    properties: list[ExtractedProperty] = Field(
        default_factory=list,
        description=(
            "Design-level scalar facts not belonging to a specific component, "
            "e.g. overall antenna footprint, total height, ground plane overall size, "
            "parameters from parametric tables with ambiguous component association."
        ),
    )
    materials: list[MaterialCandidate] = Field(default_factory=list)
    components: list[ComponentCandidate] = Field(default_factory=list)
    features: list[FeatureCandidate] = Field(default_factory=list)
    feeds: list[FeedCandidate] = Field(default_factory=list)
    simulation_setup: SimulationSetupCandidate = Field(
        default_factory=SimulationSetupCandidate
    )
    results: list[ResultCandidate] = Field(default_factory=list)
 
 
# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------
 
class VariantDesignSnapshot(StrictModel):
    """Structural snapshot for a variant that differs from the final design."""
 
    materials: list[MaterialCandidate] = Field(default_factory=list)
    components: list[ComponentCandidate] = Field(default_factory=list)
    features: list[FeatureCandidate] = Field(default_factory=list)
    feeds: list[FeedCandidate] = Field(default_factory=list)
 
 
class VariantCandidate(StrictModel):
    variant_id: str | None = None
    label: str | None = None
    role: str | None = Field(
        default=None,
        description=(
            "Role in the paper: 'reference', 'intermediate', 'ablation', "
            "'parametric_sweep_point', 'competitor', etc."
        ),
    )
    relationship_to_final: str | None = Field(
        default=None,
        description=(
            "How this variant differs from or relates to the final design, "
            "verbatim or closely paraphrased from the paper."
        ),
    )
    description: str | None = None
    design_snapshot: VariantDesignSnapshot | None = Field(
        default=None,
        description=(
            "Structural differences from the final design: fill only fields "
            "that differ. Leave None if the variant only differs in results."
        ),
    )
    properties: list[ExtractedProperty] = Field(default_factory=list)
    results: list[ResultCandidate] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
 
 
# ---------------------------------------------------------------------------
# Quality and diagnostics
# ---------------------------------------------------------------------------
 
class MissingInformation(StrictModel):
    field: str
    severity: str | None = Field(
        default=None,
        description=(
            "Impact on downstream use: 'critical' (blocks reconstruction), "
            "'major' (degrades result accuracy), 'minor' (cosmetic or optional)."
        ),
    )
    reason: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
 
 
class ConflictCandidate(StrictModel):
    field: str = Field(
        description="The parameter or fact that has conflicting values."
    )
    values: list[str] = Field(
        default_factory=list,
        description="All conflicting values found, each paired with its evidence.",
    )
    evidence: list[EvidenceRef] = Field(default_factory=list)
    notes: str | None = None
 
 
class ExtractionNote(StrictModel):
    note: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
 
 
# ---------------------------------------------------------------------------
# Root document
# ---------------------------------------------------------------------------
 
class AntennaDesignCandidate(StrictModel):
    schema_name: Literal["antenna_design_candidate_v2"] = (
        "antenna_design_candidate_v2"
    )
    document: DocumentMetadata = Field(default_factory=DocumentMetadata)
    summary: CandidateSummary = Field(default_factory=CandidateSummary)
    final_design: FinalDesignCandidate = Field(default_factory=FinalDesignCandidate)
    variants: list[VariantCandidate] = Field(default_factory=list)
    conflicts: list[ConflictCandidate] = Field(default_factory=list)
    missing_information: list[MissingInformation] = Field(default_factory=list)
    notes: list[ExtractionNote] = Field(default_factory=list)
 
    @model_validator(mode="after")
    def validate_unique_ids(self) -> Self:
        fd = self.final_design
        _ensure_unique(
            [m.material_id for m in fd.materials],
            "material_id",
        )
        _ensure_unique(
            [c.component_id for c in fd.components],
            "component_id",
        )
        _ensure_unique(
            [f.feature_id for f in fd.features],
            "feature_id",
        )
        _ensure_unique(
            [feed.feed_id for feed in fd.feeds],
            "feed_id",
        )
        return self
 
 
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
 
def _ensure_unique(values: list[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {field_name} values are not allowed")
 
 
def _validate_reconstruction_status(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in RECONSTRUCTION_STATUSES:
        allowed = ", ".join(RECONSTRUCTION_STATUSES)
        raise ValueError(
            f"reconstruction_status must be one of: {allowed}"
        )
    return value
