# Pipeline v2 Architecture

Pipeline v2 converts one scientific antenna paper into an evidence-grounded,
solver-neutral `antenna_design.json`. This document specifies the intended v2
architecture; the existing v1 pipeline remains unchanged until an explicit
cutover.

## Sequential flow

```text
PDF
  -> mechanically render every page in source order
  -> one NuExtract3 full-document multimodal extraction
  -> structurally validate document_extraction.json
  -> deterministically build an evidence packet
  -> one Gemma4 design-selection and geometry-compilation call
  -> keep source-grounded construction separate from proposed completions
  -> deterministically compose without information loss
  -> validate structure and evidence coverage
  -> derive a preview from the ACIR
  -> antenna_design.json
```

The normal single-paper path is synchronous and sequential:

- `parallelism=1`;
- one NuExtract3 call;
- one Gemma4 call;
- no RAG, embedding retrieval, vector store, agent tool loop, or parallel
  processing.

Sequential batching is permitted only after a real endpoint image, payload, or
context limit is verified. Batches follow source order and transport limits.
They must not perform semantic page selection.

## Responsibility boundaries

### Deterministic code

Before NuExtract3, deterministic code only renders all pages and records their
order and metadata. It does not classify antenna families or detect and select
figures, tables, captions, equations, or important pages.

After extraction, deterministic code may:

- validate schemas and references;
- collect pages referenced by NuExtract3;
- deduplicate and order evidence;
- record why each evidence page was included;
- compose validated contracts without semantic reinterpretation;
- check identifiers, expressions, units, dependencies, and evidence links;
- generate a preview from the same ACIR used in the final output.

It must not choose geometric blocks, infer missing geometry, apply
antenna-family construction recipes, or convert engineering assumptions into
paper-grounded facts.

### NuExtract3

NuExtract3 receives the complete ordered page set and extracts what the paper
contains and reports into `document_extraction.json`. Its contract preserves
designs, variants, observations, values, units, results, conflicts, missing
information, evidence references, and geometry-relevant page references. It
does not emit solver commands or silently complete missing information.

### Gemma4

Gemma4 receives the validated document extraction and deterministic evidence
packet. It selects the relevant design and compiles the evidence into an
Antenna Construction Intermediate Representation (ACIR): a solver-neutral,
block-oriented description of geometry, placement, materials, relationships,
feeds, and excitations.

Gemma4 must preserve ambiguity and distinguish source-grounded construction
from `proposed_completions`. It must not emit CST commands.

## Evidence packet

`geometry_relevant_pages` is one input to evidence-packet construction, not the
only page-selection mechanism. The packet also follows evidence and page
references already present in NuExtract3 observations, design records,
parameters, results, conflicts, and unresolved information.

Python resolves those references, collects the referenced pages, deduplicates
them, restores source order, and records an inclusion reason for every page. It
does not introduce new semantic page classifications.

## Construction and proposed completions

Source-grounded construction contains explicit observations and reproducible
derivations supported by evidence. Every derivation records its expression,
inputs, and evidence.

`proposed_completions` contains unsupported engineering hypotheses that could
make an incomplete design constructible. Each completion must:

- be separate from extracted facts;
- identify the missing information it addresses;
- record its rationale and affected ACIR elements;
- require explicit confirmation;
- never be applied automatically.

## Composition and validation

Composition copies and links the validated extraction and geometry compilation
without dropping variants, results, conflicts, evidence, derivations, or
unresolved information. It performs no scientific reinterpretation.

Validation reports three independent states:

- `structural_status`: `valid | invalid`;
- `reconstruction_status`:
  `complete | requires_confirmed_completions | incomplete`;
- `scientific_review_status`: `not_reviewed | passed | failed`.

Structural validity means only that the declared schema, references, and
objective invariants are satisfied. It does not establish scientific,
geometric, electromagnetic, or fabrication correctness.

## Intended run artifacts

```text
runs/<run_id>/
  input/<source>.pdf
  parsed/pages/page_0001.png
  parsed/page_render_report.json
  extraction/document_extraction.json
  extraction/nuextract3_raw_response.txt
  extraction/nuextract3_request_metadata.json
  evidence/evidence_packet.json
  compilation/geometry_compilation.json
  compilation/gemma4_raw_response.txt
  compilation/gemma4_request_metadata.json
  outputs/antenna_design.json
  reports/validation_report.json
  reports/previews/
```

These names document the intended v2 contracts; this documentation change does
not create runtime support for them.

## Scope boundary

The ACIR is solver-neutral. CST commands, a CST agent, model repair, retrieval
infrastructure, parallel execution, and pipeline-v1 removal are outside this
documentation change.
