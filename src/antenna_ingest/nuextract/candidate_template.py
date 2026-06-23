from __future__ import annotations


EXTRACTED_VALUE_TEMPLATE = {
    "name": "string",
    "value": "verbatim-string",
    "numeric_value": "number",
    "unit": "unit-code",
    "source_page": "integer",
    "source_text": "verbatim-string",
    "confidence": "number",
}

RESULT_TEMPLATE = {
    "metric": "string",
    "value": "verbatim-string",
    "numeric_value": "number",
    "unit": "unit-code",
    "condition": "verbatim-string",
    "source_page": "integer",
    "source_text": "verbatim-string",
    "confidence": "number",
}

ANTENNA_DESIGN_CANDIDATE_TEMPLATE = {
    "schema_name": "string",
    "document": {
        "title": "verbatim-string",
        "authors": ["verbatim-string"],
        "year": "integer",
        "doi": "verbatim-string",
        "venue": "verbatim-string",
    },
    "candidate_summary": {
        "antenna_name": "verbatim-string",
        "antenna_class": "string",
        "application": "verbatim-string",
        "operating_band": "verbatim-string",
        "final_design_claim": "verbatim-string",
        "reconstruction_status": "string",
        "source_page": "integer",
        "source_text": "verbatim-string",
    },
    "final_design_candidate": {
        "design_label": "verbatim-string",
        "is_explicitly_final_or_proposed": "boolean",
        "final_design_evidence": [
            {
                "source_page": "integer",
                "source_text": "verbatim-string",
                "confidence": "number",
            }
        ],
        "materials": [
            {
                "material_id": "string",
                "name": "verbatim-string",
                "role": "string",
                "properties": [EXTRACTED_VALUE_TEMPLATE],
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
                    "dimensions": [EXTRACTED_VALUE_TEMPLATE],
                    "parameters": [EXTRACTED_VALUE_TEMPLATE],
                    "location_description": "verbatim-string",
                    "reconstruction_status": "string",
                },
                "source_pages": ["integer"],
                "source_texts": ["verbatim-string"],
            }
        ],
        "geometry_features": [
            {
                "feature_id": "string",
                "label": "verbatim-string",
                "feature_type": "string",
                "associated_component_id": "string",
                "description": "verbatim-string",
                "parameters": [EXTRACTED_VALUE_TEMPLATE],
                "location_description": "verbatim-string",
                "source_page": "integer",
                "source_text": "verbatim-string",
                "confidence": "number",
            }
        ],
        "feeds": [
            {
                "feed_id": "string",
                "feed_type": "string",
                "associated_component_id": "string",
                "description": "verbatim-string",
                "parameters": [EXTRACTED_VALUE_TEMPLATE],
                "source_page": "integer",
                "source_text": "verbatim-string",
                "confidence": "number",
            }
        ],
        "simulation_setup": {
            "software": EXTRACTED_VALUE_TEMPLATE,
            "frequency_range": [EXTRACTED_VALUE_TEMPLATE],
            "solver": EXTRACTED_VALUE_TEMPLATE,
            "boundary_conditions": EXTRACTED_VALUE_TEMPLATE,
            "notes": ["verbatim-string"],
        },
        "results": [RESULT_TEMPLATE],
    },
    "design_variants": [
        {
            "variant_label": "verbatim-string",
            "variant_role": "string",
            "relationship_to_final": "string",
            "description": "verbatim-string",
            "key_parameters": [EXTRACTED_VALUE_TEMPLATE],
            "reported_results": [RESULT_TEMPLATE],
            "source_pages": ["integer"],
            "source_texts": ["verbatim-string"],
        }
    ],
    "missing_information": [
        {
            "missing_field": "string",
            "severity": "string",
            "reason": "verbatim-string",
        }
    ],
    "conflicts": [
        {
            "field": "string",
            "values": ["verbatim-string"],
            "source_pages": ["integer"],
            "notes": "verbatim-string",
        }
    ],
    "extraction_notes": [
        {
            "note": "verbatim-string",
            "source_page": "integer",
        }
    ],
}

ANTENNA_DESIGN_CANDIDATE_INSTRUCTIONS = """\
Extract a near-final antenna design candidate from the full scientific paper.

The input images are the pages of one PDF, provided in correct page order. Use 1-based page numbers when filling source_page.

The output must follow the provided JSON template.

Focus on the antenna that the paper presents as the proposed, final, optimized, selected, fabricated, simulated, or main contribution.

Do not mix intermediate design variants into final_design_candidate.

If the paper contains multiple design stages, configurations, radiators, cases, steps, iterations, parametric variants, or comparison antennas, place non-final versions under design_variants.

Use a generic component-based geometry description. Do not assume the antenna is a rectangular patch.

Use components for physical antenna parts, such as substrate, ground plane, radiating element, patch, feedline, parasitic element, via, shorting pin, reflector, director, dielectric resonator, array element, or similar.

Use geometry_features for descriptive physical features of components, such as slots, notches, cut-outs, meanders, gaps, defected ground structures, truncations, branches, apertures, or fractal features.

Do not include an operations field.

For every numeric value, include:
- value as written when possible
- numeric_value when explicitly available
- unit when available
- source_page
- shortest supporting source_text
- confidence from 0 to 1

If a value is visible only in a figure but not numerically specified, describe it in text and do not invent a number.

If a page has tables, preserve table-derived values accurately.

If the exact geometry cannot be reconstructed from the paper, set reconstruction_status to partially_buildable or not_buildable_from_paper and explain missing fields under missing_information.

Return null or empty arrays for missing information. Do not infer missing dimensions, materials, feed positions, solver settings, or results.

Keep source_text short but sufficient to verify the extraction.

Return only valid JSON matching the template.
"""
