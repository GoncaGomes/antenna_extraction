from __future__ import annotations


EVIDENCE_TEMPLATE = {
    "page": "integer",
    "quote": "verbatim-string",
    "confidence": "number",
}

PROPERTY_TEMPLATE = {
    "name": "string",
    "symbol": "string",
    "raw_value": "verbatim-string",
    "value": "verbatim-string",
    "unit": "unit-code",
    "evidence": [EVIDENCE_TEMPLATE],
    "notes": ["verbatim-string"],
}

RESULT_TEMPLATE = {
    "metric": "string",
    "raw_value": "verbatim-string",
    "value": "verbatim-string",
    "unit": "unit-code",
    "condition": "verbatim-string",
    "evidence": [EVIDENCE_TEMPLATE],
    "notes": ["verbatim-string"],
}

ANTENNA_DESIGN_CANDIDATE_TEMPLATE = {
    "schema_name": "antenna_design_candidate_v2",
    "document": {
        "title": "verbatim-string",
        "authors": ["verbatim-string"],
        "year": "integer",
        "doi": "verbatim-string",
        "venue": "verbatim-string",
    },
    "summary": {
        "antenna_name": "verbatim-string",
        "antenna_class": "string",
        "application": "verbatim-string",
        "operating_band": "verbatim-string",
        "reconstruction_status": "string",
        "evidence": [EVIDENCE_TEMPLATE],
    },
    "final_design": {
        "design_label": "verbatim-string",
        "is_explicitly_final_or_proposed": "boolean",
        "evidence": [EVIDENCE_TEMPLATE],
        "materials": [
            {
                "material_id": "string",
                "name": "verbatim-string",
                "role": "string",
                "properties": [PROPERTY_TEMPLATE],
                "evidence": [EVIDENCE_TEMPLATE],
            }
        ],
        "components": [
            {
                "component_id": "string",
                "label": "verbatim-string",
                "role": "string",
                "material_id": "string",
                "geometry": {
                    "representation": "string",
                    "primitive_type": "string",
                    "shape_family": "string",
                    "description": "verbatim-string",
                    "properties": [PROPERTY_TEMPLATE],
                    "topological_relationship": "verbatim-string",
                    "reconstruction_status": "string",
                    "evidence": [EVIDENCE_TEMPLATE],
                },
                "properties": [PROPERTY_TEMPLATE],
                "evidence": [EVIDENCE_TEMPLATE],
            }
        ],
        "features": [
            {
                "feature_id": "string",
                "label": "verbatim-string",
                "feature_type": "string",
                "associated_component_id": "string",
                "description": "verbatim-string",
                "properties": [PROPERTY_TEMPLATE],
                "topological_relationship": "verbatim-string",
                "evidence": [EVIDENCE_TEMPLATE],
            }
        ],
        "feeds": [
            {
                "feed_id": "string",
                "feed_type": "string",
                "associated_component_id": "string",
                "description": "verbatim-string",
                "properties": [PROPERTY_TEMPLATE],
                "evidence": [EVIDENCE_TEMPLATE],
            }
        ],
        "simulation_setup": {
            "software": "verbatim-string",
            "solver": "verbatim-string",
            "boundary_conditions": "verbatim-string",
            "frequency_sweep": [PROPERTY_TEMPLATE],
            "properties": [PROPERTY_TEMPLATE],
            "notes": ["verbatim-string"],
            "evidence": [EVIDENCE_TEMPLATE],
        },
        "results": [RESULT_TEMPLATE],
    },
    "variants": [
        {
            "variant_id": "string",
            "label": "verbatim-string",
            "role": "string",
            "relationship_to_final": "verbatim-string",
            "description": "verbatim-string",
            "properties": [PROPERTY_TEMPLATE],
            "results": [RESULT_TEMPLATE],
            "evidence": [EVIDENCE_TEMPLATE],
        }
    ],
    "conflicts": [
        {
            "field": "string",
            "values": ["verbatim-string"],
            "evidence": [EVIDENCE_TEMPLATE],
            "notes": "verbatim-string",
        }
    ],
    "missing_information": [
        {
            "field": "string",
            "severity": "string",
            "reason": "verbatim-string",
            "evidence": [EVIDENCE_TEMPLATE],
        }
    ],
    "notes": [
        {
            "note": "verbatim-string",
            "evidence": [EVIDENCE_TEMPLATE],
        }
    ],
}

ANTENNA_DESIGN_CANDIDATE_INSTRUCTIONS = """\
Extract a compact, near-final antenna design candidate from the full scientific paper.
 
Use schema_name exactly as antenna_design_candidate_v2.
 
─────────────────────────────────────────────
PAGE NUMBERING
─────────────────────────────────────────────
The input images are the pages of one PDF. The request includes explicit text labels
in the form PDF_INPUT_PAGE=N before each image. Use ONLY those PDF_INPUT_PAGE numbers
in evidence.page. Do not use journal page numbers, footer page numbers, article page
numbers, or printed page labels. If you are uncertain which number is the
PDF_INPUT_PAGE index versus a printed page number, always prefer the explicit
PDF_INPUT_PAGE=N label.
 
─────────────────────────────────────────────
ZERO HALLUCINATION POLICY
─────────────────────────────────────────────
Extract ONLY information explicitly stated in visible text, tables, captions, figure
labels, equations, or numerical annotations on the page.
 
Do NOT infer, guess, calculate, or complete missing parameters based on:
- Visual plot style or axis scale
- Standard RF or microwave engineering practice
- Typical material property defaults
- Engineering assumptions or common antenna configurations
 
If a parameter, software name, boundary condition, material, dimension, coordinate,
or result is not explicitly stated, output null or an empty array and report it under
missing_information when relevant.
 
─────────────────────────────────────────────
EVIDENCE AND PROVENANCE
─────────────────────────────────────────────
Use evidence arrays for provenance. Every important material, component, geometry,
feed, result, conflict, and missing-information item MUST include evidence when
available.
 
For each EvidenceRef:
- page: the PDF_INPUT_PAGE=N number where the information appears
- figure_ref: the figure or table label exactly as printed (e.g., "Fig. 3",
  "Table II", "Fig. 5(b)"). Use this whenever the information comes from a figure
  or table rather than running prose.
- quote: a short verbatim excerpt of the text, caption, or label that supports the
  extracted fact.
- confidence: your confidence in the extraction (0.0–1.0).
 
When a result, dimension, or property is visible only in a figure plot (e.g., a
gain value readable from a radiation pattern curve) but is NOT numerically stated
in text or a table:
- Set the result value to null.
- Describe what is visible in the notes field.
- Set confidence below 0.6.
- Populate figure_ref with the figure label.
 
─────────────────────────────────────────────
CONFLICT DETECTION
─────────────────────────────────────────────
Aggressively cross-reference numerical values found in prose, tables, captions,
equations, and figure labels. If the same apparent field has different values in
different places, do NOT resolve the conflict yourself. Add a conflict item
containing ALL values and evidence for each value.
 
Report conflicts when:
- Prose values and table values differ for the same parameter
- Different operating bands or frequencies are stated inconsistently
- Ground plane type or size is described differently in text versus figures
- Final-design wording conflicts with parametric variant descriptions
- Simulated and measured results appear to contradict each other
 
─────────────────────────────────────────────
SIMULATED VS. MEASURED RESULTS
─────────────────────────────────────────────
For every ResultCandidate, populate result_source:
- "simulated": result comes from a simulation tool (CST, HFSS, FEKO, ADS, etc.)
- "measured": result comes from a physical prototype measurement (VNA, anechoic
  chamber, etc.)
- "both": paper explicitly presents both and they agree
- "unknown": source cannot be determined from the text
 
This field is mandatory for every result. Do not leave it null unless the paper
genuinely provides no indication.
 
When a paper presents both simulated and measured results for the same metric with
different values, create two separate ResultCandidate entries (one per source) and
also add a conflict entry if the values differ significantly.
 
─────────────────────────────────────────────
MULTI-BAND AND FREQUENCY-CONDITIONAL RESULTS
─────────────────────────────────────────────
When a result applies to a specific frequency, band, or operating mode, populate
the condition field with that context verbatim from the text (e.g., "at 2.45 GHz",
"in Band 2", "for theta=0 deg", "co-polarization").
 
For multi-band antennas, create one ResultCandidate per band per metric. Do not
collapse multiple bands into a single result entry.
 
─────────────────────────────────────────────
PROPERTIES, COMPONENTS, FEATURES, AND FEEDS
─────────────────────────────────────────────
Use properties for all extracted scalar facts. Do not split facts into dimensions
versus parameters.
 
Use components for physical antenna parts (patch, ground plane, substrate, feedline,
stub, parasitic element, reflector, etc.).
 
Use features ONLY for geometric modifications or special features of components,
such as: slots, notches, cut-outs, meanders, gaps, defected ground structures (DGS),
truncations, chamfered corners, branches, apertures, and fractal features. Do NOT
create features for basic component shapes already represented in geometry.
 
Use feeds for feed type, feed location, feed impedance, feed dimensions, and
port-related descriptions.
 
Do NOT create a physical component for a coaxial probe or abstract port unless the
paper explicitly provides physical 3D dimensions (e.g., inner radius, outer radius,
probe length). If the paper describes a physical microstrip feedline with dimensions,
extract it strictly as a Component. Log all electrical excitation properties (e.g.,
50 Ohm port impedance, lumped port type) strictly in the Feed section.
 
─────────────────────────────────────────────
PARAMETRIC TABLES
─────────────────────────────────────────────
When a table lists geometric parameters by symbol (e.g., W1, L1, Wf, Lg) with
values and units:
- Map each row to an ExtractedProperty.
- Assign it to the most logically associated component based on label or context.
- If the component association is ambiguous, place the property in
  final_design.properties and add a note describing the ambiguity.
- Always populate the symbol field with the exact symbol as printed in the table.
 
─────────────────────────────────────────────
SYMBOL CAPTURE
─────────────────────────────────────────────
Whenever a dimension, material property, feed parameter, simulation parameter,
result, or physical property is associated with an algebraic symbol or variable in
text, table, equation, caption, or diagram, extract that symbol into the symbol
field exactly as written.
 
Examples: W, L, Wp, Lg, Wg, Xf, Yf, h, epsilon_r, tan_delta, Wf, Lf, W1, L2.
 
─────────────────────────────────────────────
TOPOLOGICAL RELATIONSHIPS
─────────────────────────────────────────────
Use topological_relationship for verbatim relational placement, not calculated
coordinates. Capture phrases such as: printed on, etched in, located on the opposite
side of, connected to, centered on, above, below, surrounding, stacked over, offset
from center by.
 
Do NOT invent absolute coordinates from these phrases.
 
─────────────────────────────────────────────
MATERIAL SPECIFICITY
─────────────────────────────────────────────
Do NOT use generic background statements as final-design facts. If a sentence says
"patches are generally made of copper or gold", treat it as background knowledge
unless the proposed antenna is explicitly stated to use that material.
 
Substrate thickness must NOT be used as patch or conductor thickness unless the
paper explicitly states it is the conductor thickness.
 
─────────────────────────────────────────────
RECONSTRUCTION STATUS
─────────────────────────────────────────────
Use reconstruction_status only from this exact set:
- buildable
- partially_buildable
- not_buildable_from_paper
- unknown
 
Do NOT mark a design or component as buildable if any build-critical detail is
missing (e.g., substrate thickness, conductor material, feedline dimensions).
 
─────────────────────────────────────────────
RESULT METRIC NAMES
─────────────────────────────────────────────
Preferred metric names (use exactly):
- resonant_frequency
- operating_frequency_range
- bandwidth
- return_loss
- s11
- s11_magnitude
- vswr
- gain
- directivity
- efficiency
- input_impedance
- axial_ratio
- radiation_pattern
- sar
- current_distribution
- unknown
 
─────────────────────────────────────────────
SIMULATION SOFTWARE
─────────────────────────────────────────────
When extracting simulation software names, populate both:
- software: the canonical tool name in normalized form (e.g., "CST Studio Suite",
  "ANSYS HFSS", "FEKO", "ADS")
- In notes, record the raw name exactly as it appears in the paper
 
Do NOT include an operations field. Do NOT output CST commands, CAD build steps,
boolean operations, or simulation execution steps.
 
─────────────────────────────────────────────
UNITS
─────────────────────────────────────────────
Preserve original units in raw_value and unit. Do NOT normalize units in this
candidate phase (e.g., do not convert mm to meters, or dBi to linear).
 
─────────────────────────────────────────────
OUTPUT FORMAT
─────────────────────────────────────────────
Do not use null for *_id fields. If an object exists but the paper does not name
it, create a stable descriptive ID such as substrate_1, conductor_1,
ground_plane_1, feed_1, feature_1, component_1, or variant_1. If no stable ID can
be created, omit the object and report the missing information instead.

Return a single valid JSON object. Do not use trailing commas. Do not include
comments. All object keys must be enclosed in double quotes. Escape inner quotation
marks inside strings. Return null or empty arrays for missing information.
"""
