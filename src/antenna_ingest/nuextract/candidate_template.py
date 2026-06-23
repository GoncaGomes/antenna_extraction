from __future__ import annotations


EVIDENCE_TEMPLATE = {
    "page": "integer",
    "quote": "verbatim-string",
    "confidence": "number",
}

PROPERTY_TEMPLATE = {
    "name": "string",
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
                    "location": "verbatim-string",
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
                "location": "verbatim-string",
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

The input images are the pages of one PDF. The request includes explicit text labels in the form PDF_INPUT_PAGE=N before each image. Use only those PDF_INPUT_PAGE numbers in evidence.page. Do not use journal page numbers, footer page numbers, article page numbers, or printed page labels.

Use evidence arrays for provenance. Every important material, component, geometry, feed, result, conflict, and missing-information item should include evidence when available.

Use properties for all extracted scalar facts. Do not split facts into dimensions versus parameters.

Use components for physical antenna parts.

Use features only for geometric modifications or special features of components, such as slots, notches, cut-outs, meanders, gaps, defected ground structures, truncations, branches, apertures, and fractal features.

Do not create features for basic component shapes that are already represented in geometry.

Use feeds for feed type, feed location, feed impedance, feed dimensions, and port-related descriptions.

Do not create a feed component for a coaxial probe unless the paper explicitly provides physical feed geometry. If the paper describes a microstrip feedline with dimensions, it may be represented as a component and also referenced by the feed.

Do not include an operations field. Do not output CST commands, CAD build steps, boolean operations, or simulation execution steps.

Use reconstruction_status only from:
- buildable
- partially_buildable
- not_buildable_from_paper
- unknown

Do not mark a design or component as buildable if build-critical details are missing.

Do not use generic background statements as final-design facts. If a sentence says patches are generally made of copper or gold, treat it as background unless the proposed antenna is explicitly stated to use copper or gold.

Preserve original units in raw_value and unit. Do not normalize units in this candidate phase.

Preferred result metric names are:
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

If a value is visible only in a figure but not numerically specified, describe it but do not invent a number.

Report conflicts when prose values and table values differ, when different operating bands are stated, when ground type is described inconsistently, or when final-design wording conflicts with variants.

Return null or empty arrays for missing information. Return only valid JSON matching the template.
"""
