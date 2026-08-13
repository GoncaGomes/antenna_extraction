# Planned NewPipeline Architecture

> **Status:** This document describes the planned runtime architecture. The
> legacy active paths have been removed. Strict Pydantic contracts and generated
> JSON Schemas now exist for extraction, results, and the solver-neutral block
> architecture. Model calls, results publication, architecture generation,
> global output-integrity reports, and the end-to-end runner remain planned.

## Target flow

```text
Scientific PDF
  |
  v
Create run and render every page in source order
  |
  v
NuExtract3 full-document extraction
  |
  v
Validate paper_extraction.json
  |
  +-------------------------------+
  |                               |
  v                               v
Publish antenna_results.json      Prepare architecture-author input
without another model call        from the validated extraction and pages
                                  |
                                  v
                         Selected architecture author
                                  |
                                  v
                         antenna_architecture.json
                                  |
                                  v
                         Objective structural validation
```

`paper_extraction.json` is an internal, auditable artifact. The only
consumer-facing outputs are:

```text
outputs/antenna_results.json
outputs/antenna_architecture.json
```

Normal execution is synchronous and sequential. It uses one NuExtract3 call
and one call to a benchmark-selected architecture author. Results publication
requires no model call.

## Responsibility boundaries

### Deterministic code may

- create runs;
- copy and fingerprint inputs;
- render every page in source order;
- persist raw and validated artifacts;
- validate schemas and references;
- follow exact evidence and page references;
- publish results losslessly from validated extraction;
- calculate objective integrity statuses.

### Deterministic code must not

- select the scientifically correct antenna design;
- infer missing geometry;
- choose antenna blocks or topology;
- apply antenna-family recipes;
- convert unsupported assumptions into reported facts;
- rewrite the architecture output into a more plausible construction.

### NuExtract3

NuExtract3 is the full-document extractor. It records designs, variants,
materials, parameters, geometry observations, simulation and measurement
setups, results, evidence, reproducible derivations, conflicts, ambiguity, and
missing information.

Its internal planned output is `paper_extraction.json`. NuExtract3 does not
write either consumer-facing document.

### Architecture author

The architecture author:

- selects the primary final or fabricated design using evidence;
- maps source information to generic blocks and relationships;
- writes `antenna_architecture.json` directly;
- preserves ambiguity and unresolved information;
- keeps unsupported proposals explicit and unapplied.

The author model will be selected later through the controlled benchmark in
the implementation plan. No model has been selected permanently.

### Results output

`antenna_results.json` is a deterministic, lossless projection of the
validated extraction. It bypasses the architecture author and requires no
additional model call.

Architecture generation or validation failure must not invalidate or delete a
valid results output.

## Validation boundary

Objective validation may check schemas, identifiers, references, expressions,
dependencies, source-backed values, and declared completeness. It must not
claim that the selected topology is scientifically correct or that the antenna
will simulate, fabricate, or perform as reported.

Structural validity, reconstruction completeness, and scientific review remain
separate states.

## Scope boundary

The initial architecture excludes:

- CST and solver-specific planning;
- optimisation and automatic simulation;
- RAG and retrieval;
- agent loops;
- automatic retries;
- fallback models;
- parallel processing;
- automatic repair;
- general preview generation.

The implemented Pydantic models and their generated JSON Schemas are the
executable contract source of truth. This document intentionally does not
reproduce complete schemas. The next planned phase is the Commit 5 scientific
acceptance suite.
