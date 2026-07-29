# NewPipeline Implementation Plan

Status: proposed implementation source of truth  
Target branch: `feat/antenna-pipeline-v2`  
Last repository review: 2026-07-29  
Reviewed remote head: `7aefac9`

## 1. Purpose

This document is the implementation roadmap for rebuilding the branch as a
small, sequential, VLM-first antenna-paper pipeline.

The immediate product is exactly two consumer-facing documents:

1. `outputs/antenna_architecture.json`
2. `outputs/antenna_results.json`

The first describes the selected antenna as evidence-grounded geometric blocks,
placements, materials, ports, and relationships. The second preserves all
reported simulated, measured, and analytical results with their design, setup,
conditions, and evidence associations.

The plan is designed to support one implementation chat per commit, or one chat
per phase when several commits need to be discussed together. It deliberately
separates:

- decisions already fixed;
- questions that must be answered from evidence;
- deterministic responsibilities;
- model responsibilities;
- implementation work;
- scientific acceptance work.

This is not an instruction to implement all commits at once. Every commit has a
completion gate. Do not begin the next commit merely because the code runs.

## 2. How to use this plan

For each commit:

1. Start a new chat and identify the branch and proposed commit number.
2. Ask the chat to read this complete document and inspect the current branch.
3. Verify the current commit, working tree, relevant files, and completed
   earlier commits.
4. Discuss any open decision listed for that commit.
5. Agree on the smallest coherent change.
6. Generate one local Codex implementation prompt for that change.
7. Implement without committing.
8. Review the diff, tests, generated schemas, and representative artefacts.
9. Commit manually only after the completion gate is satisfied.
10. Record the accepted commit SHA before starting the next chat.

The repository is authoritative for implemented behaviour. This plan is
authoritative for intended scope. When they disagree, stop, inspect the reason,
and update one or the other deliberately. Never silently implement around a
contradiction.

At the beginning of every chat, re-check facts recorded here. Branch names,
commit hashes, test counts, endpoint capabilities, and model behaviour are
observations, not permanent assumptions.

## 3. Verified branch baseline

The following was verified against the remote branch on 2026-07-29:

| Item | Verified state |
| --- | --- |
| Repository | `GoncaGomes/antenna_extraction` |
| Branch | `feat/antenna-pipeline-v2` |
| Remote head | `7aefac9` |
| Relation to `main` | 13 commits ahead, 0 behind |
| `main` comparison base | `018c24b6f10e7ff02272d177811bcf06c2b9feb9` |
| Local test baseline on a clean snapshot | `247 passed` |
| Local lint baseline | `ruff check .` passed |
| Current plan blob | `9ac943f0901a35907bfe10f2ff92be90121a2ce8` |

The attached previous `implementation_plan.md` is byte-identical to the plan at
the reviewed remote head. It is therefore safe to treat that document as the
old plan being replaced here.

### 3.1 What is implemented

The branch currently contains:

- run creation with copied input PDF;
- SHA-256 document identity;
- repository and environment fingerprints;
- atomic JSON writes;
- structured failure records and secret redaction;
- phase and attempt tracking;
- ordered PDF page rendering with PyMuPDF;
- an OpenAI-compatible client for the Skynet endpoint;
- request and response traces for model calls;
- a full-document NuExtract3 candidate call;
- a separate page-to-Markdown path;
- deterministic Markdown block and HTML table parsing;
- lexical evidence indexing and search;
- a tool-using canonicalization agent;
- strict schemas and tests for the legacy candidate and canonical record;
- five PDF fixtures and a historical v1 run manifest.

### 3.2 What is not implemented

The branch does not yet implement the architecture defined by this plan:

- no `paper_extraction.json` contract;
- no `antenna_results.json` publisher;
- no geometry-independent block contract with the required breadth;
- no Gemma4 versus Qwen 3.6 author comparison;
- no direct `antenna_architecture.json` generation;
- no two-call end-to-end runner;
- no scientifically reviewed, geometry-diverse v2 benchmark.

The documentation added at the remote head describes a future pipeline. It is
not evidence that the future pipeline exists.

### 3.3 Current architectural conflict

Three incompatible paths are visible in the current branch:

1. The executable v1 path based on Markdown, deterministic evidence parsing,
   lexical retrieval, and canonicalization.
2. A 20-phase orchestration specification with per-design phase state.
3. A documented two-call VLM-first path ending in one combined
   `antenna_design.json`.

The cleanup phase removes this ambiguity before new functional work starts.

### 3.4 Lessons from the five existing runs

The existing runs remain useful as failure evidence, but not as scientific
ground truth:

- Paper 001 demonstrates that a schema-valid output can lose the reported
  `47.98 ohm` result.
- Paper 002 demonstrates the need to represent a circular slot as subtraction
  and preserve the derivation `base = 2 * x`.
- Paper 003 demonstrates that an inset or notch can disappear while the design
  is still labelled buildable.
- Paper 004 demonstrates that variants and their results can be lost when the
  pipeline focuses only on the selected design.
- Paper 005 demonstrates symbol-to-geometry mapping failures, false buildability,
  unsupported material assumptions, and incorrect treatment of simulated and
  measured differences as conflicts.

The new benchmark must test these specific failures. JSON validity alone is not
an acceptance criterion.

## 4. Fixed product decisions

The following decisions are fixed for the initial implementation.

### 4.1 Final outputs

There are two final documents and no combined third document:

```text
antenna_architecture.json
antenna_results.json
```

`paper_extraction.json` is an internal, auditable model artefact. Request
metadata, raw responses, validation reports, and failure reports are also
internal artefacts.

There is no `antenna_design.json`, `geometry_compilation.json`, or deterministic
final geometry assembler in the target path.

### 4.2 Normal model-call budget

The normal run uses exactly two model calls:

1. NuExtract3 reads the complete paper and produces `paper_extraction.json`.
2. One selected multimodal author, initially chosen by a benchmark between
   Gemma4 and Qwen 3.6, produces `antenna_architecture.json`.

`antenna_results.json` is published deterministically from the validated paper
extraction. It does not require another model call.

Calls are synchronous and sequential. `parallelism` is always one.

No model reviewer, repair call, fallback model, ensemble, or agent tool loop is
part of the initial normal path. Such a capability may be proposed later only
after a measured failure justifies it.

### 4.3 No RAG in the single-paper path

The normal path has no:

- embeddings;
- vector database;
- semantic top-k retrieval;
- lexical evidence index;
- reranker;
- tool-driven evidence search loop.

The task is exhaustive extraction from one paper, not question answering over a
large corpus. Top-k retrieval can omit a small dimension, visual feature,
symbol, equation, or variant that is essential to reconstruction.

Evidence is resolved through explicit IDs and page references:

```text
observation
  -> evidence_id
  -> one-based page number
  -> rendered page image
```

This is deterministic reference resolution, not semantic search.

RAG may be reconsidered only for a different requirement, such as corpus-wide
search, interactive questions across many papers, or a demonstrated context
limit that exact reference closure cannot handle. Even then, retrieval must not
be the sole gate controlling which source evidence is available.

### 4.4 No semantic deterministic assembler

Python may copy, validate, link, project, and persist information. It must not:

- decide which blocks make up an antenna;
- select the final design from scientific meaning;
- interpret a figure as a slot, notch, via, feed, or radiator;
- introduce a missing boolean operation;
- infer placement or dimensions;
- apply antenna-family recipes;
- turn an engineering proposal into reported geometry;
- rewrite the author output into a construction it considers more plausible.

The architecture author writes the final architecture contract directly.

### 4.5 No unconfirmed inference in the constructed architecture

Reproducible derivations are allowed when every input is source-grounded and the
expression is explicit.

Unsupported engineering hypotheses are not applied to blocks or parameters.
They may appear only in `proposed_completions`, where they:

- identify the missing information they address;
- state their rationale;
- identify affected elements;
- require explicit confirmation;
- keep the architecture incomplete until confirmed in a separate downstream
  revision.

The initial pipeline never changes an inferred value into a paper-grounded
fact.

### 4.6 Scope boundary

The following are outside the initial implementation:

- CST commands or CST execution;
- construction planning for a specific solver;
- optimisation;
- automatic simulation;
- general graph digitisation;
- universal 3D preview generation;
- model-based review;
- automatic repair;
- multi-paper scheduling;
- parallel processing;
- a web interface;
- a general agent framework.

## 5. Target end-to-end flow

```text
Scientific PDF
  |
  v
Create run, copy input, compute identity
  |
  v
Render every page in source order
  |
  v
Call 1: NuExtract3 full-document extraction
  |
  v
Validate paper_extraction.json
  |
  +------------------------------+
  |                              |
  v                              v
Publish antenna_results.json     Prepare architecture-author input
without a model call             from extraction references
                                 |
                                 v
                       Call 2: Gemma4 or Qwen 3.6
                                 |
                                 v
                       antenna_architecture.json
                                 |
                                 v
                       Objective structural validation
```

The results output is published before the architecture call. If architecture
generation fails, the valid extraction and results output remain available.

### 5.1 Visual input policy for the architecture author

The highest-recall initial benchmark should give the architecture author:

- the complete validated `paper_extraction.json`;
- all rendered pages in source order;
- the architecture JSON Schema;
- a concise role prompt.

This protects the second stage from an incomplete NuExtract3 page-selection
list and gives the author an independent visual view of the paper.

Before this becomes the fixed production policy, the real endpoint must be
probed for image count, payload, context, and latency. If all pages are not
practical, the fallback is deterministic evidence-reference closure:

1. start from the selected-design candidates, geometry, material, parameter,
   feed, port, conflict, and missing-information observations;
2. follow their evidence IDs;
3. resolve the exact referenced page numbers;
4. deduplicate and restore source order;
5. record why every page was included.

The fallback must not rank pages by semantic similarity. It is activated only
by a verified transport or context constraint, not by speculation.

### 5.2 Oversized paper policy

The first NuExtract3 attempt uses one complete request. If the endpoint rejects
the request because of a measured technical limit:

- use sequential, source-ordered batches;
- base boundaries only on image count, payload size, or context limits;
- preserve global one-based page numbers;
- never classify pages by importance;
- persist each batch response;
- merge only by lossless concatenation, ID remapping, and objective duplicate
  identity;
- preserve cross-batch ambiguity rather than resolving it with Python.

Batching changes the number of extraction calls and therefore is not part of
the normal two-call claim. Any benchmark run using batching must report that
fact explicitly.

## 6. Model roles and selection

### 6.1 NuExtract3

NuExtract3 is the document extractor. It receives the ordered page images and
describes what the paper contains:

- designs and design evolution;
- the likely final or fabricated design candidates;
- materials;
- parameters, symbols, values, and units;
- geometry and topology observations;
- feeds, ports, and excitations;
- simulation, measurement, and analytical setups;
- every reported result;
- evidence;
- equations and reproducible derivations;
- conflicts, ambiguity, and missing information.

It must not produce CST commands or the final block architecture.

Thinking enabled versus disabled is a development-time benchmark decision. Test
both on the same fixed papers and choose one default. Do not use thinking mode
as an automatic retry or fallback in normal runs.

### 6.2 Architecture author

The architecture author receives the validated extraction and visual pages. It:

- selects the primary final or fabricated design;
- records its selection evidence and unresolved ambiguity;
- maps source symbols and observations to parameters;
- defines coordinate frames, materials, blocks, geometry, placement,
  relationships, ports, and excitations;
- represents source-supported derivations;
- marks unresolved geometry precisely;
- places unsupported suggestions only in `proposed_completions`;
- writes `antenna_architecture.json` directly.

It does not rewrite the results inventory and does not emit solver commands.

### 6.3 Gemma4 versus Qwen 3.6

Do not choose the architecture author solely from model size or reputation.
Both available candidates must receive identical frozen inputs in a sequential
development benchmark.

Selection priority:

1. correct primary-design selection;
2. correct topology and boolean intent;
3. complete symbol-to-geometry mapping;
4. zero unsupported numeric mutations;
5. evidence-grounded parameters and blocks;
6. correct incomplete status when the paper is insufficient;
7. schema-valid output;
8. latency.

Correctness has priority over latency. A faster model does not win if it
silently invents geometry or produces false `complete` outcomes.

The comparison is a development experiment, not an ensemble at runtime. After
selection, one model name is configured for the normal second call. The losing
model receives no automatic runtime role.

If neither model meets the minimum benchmark gate, stop and improve the
contract, prompt, or evidence input. Do not hide the problem with a third model
call.

## 7. Artefacts and run layout

The target run layout is:

```text
runs/<run_id>/
  manifest.json
  input/
    <source>.pdf
  pages/
    page_0001.png
    page_0002.png
    ...
    render_report.json
  extraction/
    paper_extraction.json
    nuextract3_request_metadata.json
    nuextract3_raw_response.txt
    extraction_report.json
  architecture/
    author_input_manifest.json
    author_request_metadata.json
    author_raw_response.txt
  outputs/
    antenna_results.json
    antenna_architecture.json
  reports/
    extraction_validation.json
    results_validation.json
    architecture_validation.json
    benchmark_report.json
    failures/
      <phase>_attempt_<n>.json
```

Only the two files under `outputs/` are consumer-facing.

Raw responses must be persisted immediately after receipt and before strict
parsing. Request metadata must not contain secrets or complete base64 image
payloads.

The manifest uses a small fixed phase set:

```text
run_initialization
page_rendering
paper_extraction
results_publication
architecture_generation
output_validation
```

There is no per-design phase state and no 20-phase prerequisite graph.

For every model call, record when available:

- model role and exact model name;
- request start and finish timestamps;
- latency;
- temperature and thinking setting;
- input artefact checksums;
- page numbers and image checksums;
- schema and prompt hashes;
- finish reason;
- endpoint request or invocation ID;
- token usage;
- raw response path;
- parsing and schema-validation outcome.

## 8. Data-contract boundaries

Pydantic models and generated JSON Schema are the only executable contract
source of truth. Documentation explains intent and examples. It must not contain
a second manually maintained full schema.

All boundary models use strict validation and reject unknown fields unless a
specific extensibility field has been deliberately defined.

### 8.1 Internal `paper_extraction.json`

The extraction is source-oriented. It records observations and evidence, not
construction commands.

Conceptual top-level shape:

```json
{
  "schema_name": "paper_extraction",
  "schema_version": "1.0.0",
  "document": {},
  "pages": [],
  "evidence_catalog": [],
  "designs": [],
  "material_observations": [],
  "parameter_observations": [],
  "geometry_observations": [],
  "feed_and_excitation_observations": [],
  "setups": [],
  "results": [],
  "derivations": [],
  "conflicts": [],
  "missing_information": [],
  "architecture_page_refs": []
}
```

Each reported design or variant has its own `design_id`. Variants are related
through fields such as `parent_design_id`, `predecessor_design_id`, or a small
reviewed relation vocabulary. Results link to one `design_id`. This avoids the
ambiguous combination of a design ID plus an optional variant ID.

Each factual observation includes:

- a stable ID;
- its design association when applicable;
- source-faithful value, symbol, unit, or description;
- an optional normalised representation that never replaces the original;
- evidence IDs;
- uncertainty or legibility state;
- conflict membership when applicable.

An evidence record includes:

- `evidence_id`;
- one-based page number;
- source kind such as text, caption, figure, table, equation, or graph;
- source label when visible;
- source-faithful excerpt or concise visual description;
- optional bounding region only if reliably available;
- optional legibility note.

Evidence confidence is not permission to invent. Low-confidence observations
remain low confidence or unresolved.

### 8.2 Final `antenna_results.json`

The results document is a deterministic projection of validated extraction
records. It is never summarised or rewritten by the architecture author.

Conceptual top-level shape:

```json
{
  "schema_name": "antenna_results",
  "schema_version": "1.0.0",
  "document": {},
  "design_registry": [],
  "setups": [],
  "results": [],
  "evidence_catalog": [],
  "conflicts": [],
  "missing_information": [],
  "provenance": {},
  "status": {}
}
```

Each result includes:

- `result_id`;
- `design_id`;
- `setup_id` when a setup is reported;
- source category such as `simulated`, `measured`, or `analytical`;
- metric or quantity;
- frequency and other conditions;
- representation type;
- exact reported values and units;
- optional normalised values;
- evidence IDs;
- uncertainty, extraction limitation, or trace identity.

The value representation supports:

- scalar;
- interval or range;
- explicit point collection;
- sampled series;
- matrix;
- angular pattern;
- field or current map;
- image-only graph evidence;
- qualitative observation.

General curve digitisation is not required initially. When a graph cannot be
digitised safely, preserve:

- axis names and units;
- legend and trace labels;
- explicitly annotated points;
- design and setup association;
- the visual evidence reference;
- a clear `image_only` or `partial_numeric` representation.

Differences between simulated and measured results are not conflicts. A
conflict requires incompatible claims for the same design, origin, setup,
condition, and quantity.

The publisher must prove that every extraction result was copied exactly once
or report a blocking error. It cannot prove that NuExtract3 found every result
in the paper. That requires benchmark or scientific review.

### 8.3 Final `antenna_architecture.json`

The architecture is a declarative, solver-neutral description of one selected
primary design. It is centred on blocks and their relationships, not an ordered
history of solver commands.

Conceptual top-level shape:

```json
{
  "schema_name": "antenna_architecture",
  "schema_version": "1.0.0",
  "document_ref": {},
  "selected_design": {},
  "coordinate_system": {},
  "parameters": [],
  "materials": [],
  "blocks": [],
  "relationships": [],
  "ports_and_excitations": [],
  "derivations": [],
  "unresolved_items": [],
  "proposed_completions": [],
  "provenance": {},
  "status": {}
}
```

#### Selected design

The selected design records:

- `design_id`;
- its role, such as final, fabricated, measured prototype, or selected
  candidate;
- selection rationale;
- selection evidence IDs;
- ambiguity state.

When the source does not support a unique selection, the architecture is
incomplete. The model must not choose silently.

#### Parameters

A parameter records:

- stable ID;
- source symbol when reported;
- exact reported value and unit;
- optional normalised value and unit;
- optional expression;
- origin;
- evidence IDs;
- affected block or relationship IDs;
- resolution state.

Allowed origins in the constructed architecture:

- `reported_text`;
- `reported_table`;
- `reported_equation`;
- `reported_visual`;
- `derived`.

`engineering_inference` is not an allowed origin for an applied construction
parameter. Unsupported ideas belong to `proposed_completions`.

#### Materials

A material records the reported identity and only the properties supported by
the source. It may include frequency-dependent properties when the paper
reports them. It must not silently add typical copper thickness, conductivity,
loss tangent, tissue properties, or solver defaults.

#### Blocks

Every block records:

- `block_id`;
- name and semantic role;
- physical, auxiliary, instance, or unresolved state;
- material reference when applicable;
- geometry definition;
- placement or local frame;
- parameter dependencies;
- evidence IDs;
- derivation references;
- unresolved fields.

A block can represent, without antenna-family-specific schemas:

- a conductor or dielectric volume;
- a sheet or surface;
- a substrate or environmental layer;
- a wire, trace, meander, loop, or helix path;
- a radiator, ground, feed, shorting element, or via;
- an auxiliary additive or subtractive tool;
- an array element or instance;
- a free-form source geometry;
- an explicitly unresolved part.

#### Geometry basis

The schema must be geometry-independent without pretending to be a complete CAD
kernel. It uses a small constructive basis plus explicit escape hatches:

- primitive 2D profiles;
- primitive 3D solids;
- polygons and profiles made from line or curve segments;
- profiles with holes;
- extrusion;
- revolution;
- path or wire;
- sweep along a path;
- surfaces;
- source-backed mesh geometry;
- referenced instances and patterns;
- unresolved geometry.

The initial discriminated geometry types should cover:

```text
rectangle
circle
ellipse
annulus
polygon
segmented_profile
box
cylinder
cone
sphere
extrusion
revolution
wire_path
sweep
surface
mesh
instance
unresolved
```

Only implement fields whose meaning can be stated and validated. Do not create
a family schema such as `PatchAntenna`, `PIFA`, `Horn`, or `HelixAntenna`.

The `mesh` and `unresolved` forms prevent the schema from lying when a shape
does not fit the initial constructive vocabulary. A mesh must be source-backed
or explicitly identified as an external referenced asset. The model must not
fabricate mesh vertices from a low-resolution figure.

#### Placement and frames

The document declares one global coordinate system. Blocks may use a local
frame referenced to the global frame or another declared frame.

Placement must make translation and orientation unambiguous. The first version
should use one fixed rotation convention and document it. Do not accept several
equivalent rotation representations unless a real case requires them.

Positions and dimensions may be literal quantities or parameter expressions.
All symbols must resolve.

#### Relationships

Relationships connect declared blocks. The initial set may include:

- `subtract`;
- `unite`;
- `intersect`;
- `contact`;
- `aligned_with`;
- `contained_in`;
- `pattern_instance`.

Only relationships needed by benchmark evidence should become executable
schema variants. Boolean relationships identify target, tool, and result
references unambiguously.

Translation, rotation, material assignment, and port creation are not history
commands. They belong to placement, material references, and port declarations.

#### Ports and excitations

A port or excitation records:

- stable ID and reported type;
- referenced blocks, faces, points, paths, or frames;
- placement and orientation;
- impedance when reported;
- evidence IDs;
- unresolved requirements.

The contract describes the physical excitation without CST-specific commands.

### 8.4 Derivations

A derivation is source-grounded when:

- all input values are reported or already validly derived;
- the expression is explicit;
- units are compatible;
- the explanation states why the expression follows from the evidence;
- every source input and relevant visual relationship has evidence.

Example:

```json
{
  "derivation_id": "derive_patch_base",
  "target_parameter_id": "patch_base",
  "expression": "2 * x",
  "input_parameter_ids": ["x"],
  "explanation": "The source figure labels x as one symmetric half of the base.",
  "evidence_ids": ["ev_final_geometry"]
}
```

Use a deliberately small safe expression grammar. Never use Python `eval`.
Support only operators and functions demonstrated by benchmark cases.

### 8.5 Proposed completions

Example:

```json
{
  "completion_id": "propose_conductor_thickness",
  "addresses_unresolved_item_ids": ["missing_conductor_thickness"],
  "proposal": "Choose a conductor thickness before solver construction.",
  "rationale": "The paper identifies copper but does not report thickness.",
  "affected_element_ids": ["radiator", "ground"],
  "requires_confirmation": true,
  "applied": false
}
```

The proposal does not contain an apparently exact default unless a user or
downstream engineering process supplies one. The normal extraction run leaves
`applied` false.

### 8.6 Validation states

Do not compress different kinds of certainty into one label.

`antenna_architecture.json` reports:

- `structural_status`: `valid | invalid`;
- `reconstruction_status`: `complete | incomplete`;
- `scientific_review_status`: `not_reviewed | passed | failed`.

`complete` requires:

- structural validity;
- an unambiguous selected design;
- no unresolved reconstruction-critical geometry, material, placement, port,
  or parameter;
- no proposed completion required by the construction.

`incomplete` is a valid, inspectable output. It must list precise unresolved
items.

`antenna_results.json` reports:

- `structural_status`: `valid | invalid`;
- `publication_status`: `complete_from_extraction | blocked`;
- `scientific_review_status`: `not_reviewed | passed | failed`.

`complete_from_extraction` means every result present in the validated
extraction was published. It does not claim that the extractor found every
result in the paper.

## 9. Branch cleanup strategy

Cleanup happens before new contracts or model code.

The user has confirmed that the old pipeline is preserved on another branch.
Therefore, do not create another `-minimal` branch by default. Clean
`feat/antenna-pipeline-v2` directly after verifying the historical branch and a
clean working tree.

### 9.1 Mandatory preflight

Before any cleanup edit:

1. Run `git status --short --branch`.
2. Record `git rev-parse HEAD`.
3. Record the remote head for `feat/antenna-pipeline-v2`.
4. Confirm the name and reachable commit of the branch preserving the old
   pipeline.
5. Confirm there are no uncommitted or untracked user files that overlap the
   cleanup.
6. Run the current local test and lint baseline.
7. Produce a deletion and retention inventory from the actual tree.

If the working tree is dirty, stop. Do not use `git reset`, `git restore`,
`git checkout --`, or `git clean` to make it clean.

The cleanup base reviewed for this document is `7aefac9`, but the implementation
chat must not assume that SHA is still current.

### 9.2 Preserve and generalise

Preserve the useful behaviour, not necessarily the current file location:

| Current capability | Cleanup decision |
| --- | --- |
| PDF copy, checksum, and document ID | Keep |
| Run ID and manifest | Keep, simplify |
| Repository and environment fingerprint | Keep |
| Failure records and secret redaction | Keep |
| Atomic JSON read/write | Keep |
| Ordered PyMuPDF page rendering | Keep |
| Image-to-data-URL utility | Keep |
| OpenAI-compatible client | Keep, make model-role neutral |
| Environment settings | Keep, rename by model role |
| Injected clients in tests | Keep |
| Five PDF fixtures | Keep as regression inputs |

The cleaned settings should use clear role names, for example:

```text
SKYNET_BASE_URL
SKYNET_API_KEY
DOCUMENT_EXTRACTOR_MODEL
ARCHITECTURE_AUTHOR_MODEL
DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS
ARCHITECTURE_AUTHOR_TIMEOUT_SECONDS
```

Do not add YAML runtime loading merely because unused YAML examples exist.

### 9.3 Remove

Remove from the active branch:

- page-by-page NuExtract Markdown conversion;
- Markdown as a central contract;
- deterministic evidence-block parsing;
- deterministic HTML table parsing;
- lexical evidence indexing and search;
- retrieval traces and RRF logic;
- the canonicalization tool adapter and tool loop;
- canonicalization prompts, doctors, probes, schemas, and validators;
- the legacy `AntennaDesignCandidate` schema and template;
- the legacy full-document candidate runner tied to that schema;
- `canonical_design_record_v1`;
- the 20-phase `pipeline_spec.py`;
- per-design phase scope and prerequisite machinery;
- legacy CLI commands;
- tests that protect only removed behaviour;
- the v1 benchmark freeze script and manifest, since the old pipeline is
  preserved on another branch;
- unused YAML examples;
- placeholder or contradictory schema documents;
- empty package directories with no planned immediate owner;
- `test_localsystem.txt`;
- other dead imports or files proven unused by search and tests.

Do not remove the five source PDFs merely because their old outputs are being
removed.

### 9.4 Minimal phase state

Replace the 20-phase graph with a simple ordered phase record. One paper has one
execution per phase. No design-scoped executions are required.

Each phase record needs only:

- status;
- attempt;
- started and completed timestamps;
- duration;
- model role when applicable;
- input and output artefact names;
- failure reference;
- prompt and schema hashes when applicable.

The runner controls order directly. A generic workflow engine is not required.

### 9.5 Target source tree after cleanup

The exact file split may follow the code, but the cleaned foundation should be
approximately:

```text
src/antenna_ingest/
  __init__.py
  cli.py
  settings.py
  rendering.py
  models/
    __init__.py
    client.py
    doctor.py
  orchestration/
    __init__.py
    failures.py
    fingerprints.py
    phases.py
    runs.py
    schemas.py
  utils/
    __init__.py
    images.py
    json_io.py
```

Do not create empty `extraction`, `results`, or `architecture` packages during
cleanup. Add them only in the commit that implements their first real contract.

### 9.6 Cleanup verification

The cleanup is accepted only when:

- the retained tests pass;
- lint passes;
- CLI help imports without legacy packages;
- page rendering still works on a fixture;
- run manifests contain only the minimal phase set;
- no live import references removed modules;
- searches for legacy path names match only historical documentation when
  appropriate;
- the repository contains no duplicate implementation-plan location;
- the resulting tree is visibly and conceptually smaller;
- no new extraction or architecture behaviour has been implemented early.

The number of tests will intentionally fall when legacy-only tests are deleted.
Do not preserve meaningless tests to retain the number `247`.

## 10. Roadmap summary

| Phase | Commit | Outcome |
| --- | ---: | --- |
| Cleanup | 1 | One documented source of truth |
| Cleanup | 2 | Minimal reusable branch foundation |
| Contracts | 3 | Extraction and results schemas |
| Contracts | 4 | Geometry-independent architecture schema |
| Benchmark | 5 | Scientifically reviewed acceptance suite |
| Extraction | 6 | NuExtract3 full-document call |
| Results | 7 | Final `antenna_results.json` |
| Architecture | 8 | Final `antenna_architecture.json` and author selection |
| Validation | 9 | Objective integrity gates |
| Orchestration | 10 | Sequential two-call runner and final baseline |

Each commit must leave the repository in a coherent state and keep all tests
relevant to retained behaviour green.

## 11. Phase 0: documentation and cleanup

### Commit 1: adopt the new source of truth

Proposed commit message:

```text
docs(plan): adopt minimal two-output pipeline
```

Objective:

- replace the previous plan with this plan;
- make documentation describe one architecture before code is removed.

Required changes:

- place this file at `docs/implementation_plan.md`;
- remove the root-level duplicate;
- update `AGENTS.md` to reference the real path;
- rewrite `docs/architecture.md` as a concise description of the two-output
  flow;
- update `README.md` to state what is implemented now and what is planned;
- remove or consolidate contradictory `claim_schema`, `evidence_schema`,
  `model_assignment`, and `testing_strategy` documents when their useful
  content is already captured here;
- mark all future artefact names as planned until their implementation commit.

Tests:

- existing code tests remain unchanged and pass;
- lint passes;
- Markdown links and referenced paths resolve;
- one search confirms no document still promises `antenna_design.json` as the
  target output.

Completion gate:

- one plan location;
- one final-output definition;
- cleanup is explicitly the next phase;
- documentation does not claim that v2 is already implemented.

Out of scope:

- runtime changes;
- schema code;
- model calls;
- deletion of legacy Python.

### Commit 2: reduce the branch to the minimal foundation

Proposed commit message:

```text
refactor(repo): remove legacy paths and keep minimal foundation
```

Objective:

- perform the branch cleanup in one controlled commit before new functional
  work.

Required changes:

- execute the preflight in Section 9.1;
- simplify the run manifest and phases;
- simplify run directories;
- generalise the endpoint client and settings by model role;
- move rendering and image utilities out of misleading legacy ownership when
  useful;
- reduce the CLI to commands backed by retained foundation behaviour;
- remove all modules, scripts, tests, configurations, and documents listed in
  Section 9.3;
- retain and adapt only tests for run creation, fingerprints, failures, atomic
  JSON, settings, client injection, and ordered rendering;
- update imports and package exports;
- do not leave compatibility wrappers for code with no consumer.

Tests:

- directly affected orchestration, rendering, settings, client, failure, and
  CLI tests;
- complete retained test suite;
- `ruff check .`;
- package build or import;
- one real fixture rendering integration test;
- import search for removed modules.

Completion gate:

- the source tree matches the minimal foundation in purpose;
- the old pipeline remains recoverable from the verified historical branch and
  Git history;
- no Markdown, retrieval, candidate, canonicalization, or 20-phase path
  remains active;
- no empty future packages are added;
- no new scientific extraction logic appears in the cleanup diff.

Stop conditions:

- the historical branch cannot be verified;
- the working tree contains overlapping user changes;
- a supposedly removed module has an active consumer not covered by this plan;
- retained rendering or run creation cannot be made green without unrelated
  refactoring.

## 12. Phase 1: contracts

### Commit 3: define paper extraction and results contracts

Proposed commit message:

```text
feat(contracts): define paper extraction and results schemas
```

Objective:

- define the internal source-oriented contract and the first final output
  contract without calling a model.

Required changes:

- add strict Pydantic models for `paper_extraction`;
- add strict Pydantic models for `antenna_results`;
- generate JSON Schema from those models;
- implement cross-reference validation for designs, evidence, setups, and
  results;
- represent exact source values separately from optional normalised values;
- support all result representation types in Section 8.2;
- distinguish simulated, measured, and analytical origins;
- define deterministic result-projection invariants;
- add small synthetic fixtures, not full model outputs.

Required schema tests:

- duplicate IDs fail;
- unknown design, setup, or evidence references fail;
- one design can have several source-distinct results;
- simulated and measured results coexist without conflict;
- a variant retains its own results;
- exact decimals and units survive round-trip serialisation;
- scalar, interval, series, angular, matrix, field-map, and image-only results
  validate;
- missing or illegible source data can be represented honestly;
- extra fields fail;
- no CST field or geometry construction operation exists in extraction or
  results.

Completion gate:

- every known result case from the five runs is representable;
- result publication can be lossless relative to extraction;
- the contracts remain readable without a generic ontology or property bag;
- no model call or prompt is added.

Open decisions for the commit chat:

- the smallest useful exact-value representation;
- whether normalised values are included in v1 or deferred;
- the exact setup model shared by simulation, measurement, and analytical
  results;
- whether explicit graph points use one general point-series type or a
  specialised angular-pattern type.

### Commit 4: define the architecture contract

Proposed commit message:

```text
feat(architecture): define geometry-independent block schema
```

Objective:

- implement the smallest solver-neutral block representation that can describe
  diverse antennas without antenna-family recipes.

Required changes:

- add strict Pydantic models for `antenna_architecture`;
- implement the geometry basis in Section 8.3 as discriminated types;
- define quantities, parameter references, and safe expressions;
- define one coordinate and rotation convention;
- define materials, blocks, placement, relationships, ports, derivations,
  unresolved items, and proposed completions;
- generate JSON Schema;
- implement only schema and graph invariants needed to validate the contract;
- keep scientific and geometric correctness outside deterministic claims.

Required synthetic coverage:

- rectangular planar stack;
- polygonal radiator with circular subtraction;
- inset or notch;
- multilayer or stacked structure;
- via or shorting element;
- wire or meander path;
- helix or sweep path;
- repeated array instances;
- horn-like or tapered volumetric profile;
- dielectric resonator volume;
- conformal or free-form surface/mesh reference;
- implantable antenna with surrounding material blocks;
- incomplete geometry with proposed completion kept unapplied.

Required validation tests:

- unique IDs and known references;
- parameter expression symbols resolve;
- dependency cycles fail;
- incompatible units fail where objectively detectable;
- invalid polygon or path cardinality fails;
- boolean target, tool, and result references resolve;
- no engineering inference is accepted as an applied parameter origin;
- unresolved geometry remains schema-valid but reconstruction-incomplete;
- no class such as `PatchAntenna` or family-specific recipe exists.

Completion gate:

- the schema is independent of antenna family;
- every construction-critical value is source-grounded, derived, or unresolved;
- the architecture cannot become complete through an unconfirmed proposal;
- no model call is introduced.

Open decisions for the commit chat:

- exact initial curve-segment vocabulary;
- local-frame representation and rotation convention;
- how instances and patterns reference prototype blocks;
- whether `contact`, `aligned_with`, and `contained_in` are needed immediately;
- the minimum mesh reference metadata that avoids embedding large assets.

## 13. Phase 2: scientific benchmark

### Commit 5: define the v2 acceptance suite

Proposed commit message:

```text
test(benchmark): define evidence-grounded v2 acceptance suite
```

Objective:

- prevent schema-valid but scientifically wrong outputs from being accepted.

The current five papers form a patch-heavy regression set. They are not enough
to support the claim that the architecture works for any antenna geometry.

Create two benchmark groups:

```text
benchmarks/v2/
  README.md
  papers.json
  expectations/
    regression/
      001_*.json
      ...
      005_*.json
    geometry_coverage/
      <diverse-paper>.json
  frozen_inputs/
    <optional reviewed paper_extraction fixtures>
```

Do not commit copyrighted PDFs solely for the benchmark. Store filenames,
checksums, and local acquisition instructions when redistribution is not
appropriate.

The geometry-coverage set should include real examples from at least:

- printed planar and slotted antennas;
- wire, loop, meander, or helix antennas;
- multilayer, stacked, via, or shorted antennas;
- arrays or repeated structures;
- horn, waveguide, or tapered volumetric antennas;
- dielectric resonator antennas;
- conformal, implantable, or free-form geometries.

Expectations contain reviewed assertions, not complete hand-authored output
files. Assertion categories include:

- exact value and unit;
- required or forbidden result association;
- required design or variant;
- required material;
- required parameter-symbol mapping;
- required block role;
- required topology or boolean intent;
- required unresolved item;
- prohibited unsupported value;
- primary-design selection;
- evidence page or source label;
- manual visual-review item.

The five current regression papers must include the failures listed in Section
3.4.

Automatic metrics:

- schema validity;
- exact numeric fidelity;
- evidence-reference integrity;
- design and variant association;
- result preservation;
- required parameter coverage;
- prohibited unsupported value count;
- block and relationship graph integrity;
- false `complete` count;
- model-call count and latency.

Manual or expert-reviewed metrics:

- source figure versus declared topology;
- symbol-to-feature mapping;
- selected final or fabricated design;
- whether missing information genuinely blocks reconstruction;
- whether a free-form representation is faithful.

Completion gate:

- all five current papers have reviewed expectations;
- the benchmark explicitly states that five patches do not prove
  generalisation;
- at least the synthetic architecture coverage is complete;
- a concrete plan exists to add the real diverse-paper set before the final
  geometry-independent claim;
- automatic and manual checks are separated;
- remote model calls are not part of default `pytest`.

Stop condition:

- do not freeze a model default from the five patch-heavy papers alone.

## 14. Phase 3: NuExtract3 and the results output

### Commit 6: implement full-document extraction

Proposed commit message:

```text
feat(extraction): add full-document NuExtract3 extraction
```

Objective:

- implement the first normal model call and produce a validated
  `paper_extraction.json`.

Required behaviour:

1. Load the ordered render report.
2. Build one multimodal request containing every page.
3. Include the generated paper-extraction JSON Schema.
4. Persist request metadata before the call.
5. Call NuExtract3 once.
6. Persist the raw response immediately.
7. Parse and strictly validate the response.
8. Validate page, design, evidence, setup, and result references.
9. Persist `paper_extraction.json` and the validation report.
10. Complete or fail the manifest phase without leaving it running.

Prompt requirements:

- treat the images as one ordered scientific paper;
- extract all designs, variants, setups, and results;
- preserve exact symbols, values, units, and source wording;
- use figures, tables, captions, equations, prose, and graphs as evidence;
- distinguish result origins;
- identify likely final or fabricated design candidates without hiding
  ambiguity;
- report missing information;
- forbid solver commands and unsupported engineering assumptions;
- return only the target contract.

Tests with an injected fake client:

- all pages are sent once and in order;
- page labels are globally one-based;
- the effective schema and prompt hashes are recorded;
- raw response survives malformed JSON;
- schema errors create inspectable failure reports;
- invalid page or evidence references fail;
- successful forced rerun does not duplicate artefacts;
- no removed Markdown, table, evidence, retrieval, or canonicalization function
  is called;
- the normal call count is one.

Remote acceptance work:

- probe image count, payload, context, timeout, finish reason, and structured
  output behaviour;
- compare thinking enabled and disabled on fixed inputs;
- record latency and output truncation;
- run the five regression papers;
- inspect exact result, variant, evidence, and symbol coverage.

Completion gate:

- the five regression papers produce inspectable valid extractions or a
  documented technical limit;
- no semantic preselection occurs;
- one call is the normal case;
- every failure preserves enough information to diagnose without repeating the
  call;
- scientific assertions pass at the extraction boundary, not merely the schema
  tests.

### Commit 7: publish `antenna_results.json`

Proposed commit message:

```text
feat(results): publish lossless antenna results
```

Objective:

- complete the first consumer-facing output without another model call.

Required behaviour:

- load only a validated `paper_extraction.json`;
- copy the document reference, complete design registry, setups, results,
  result evidence, result conflicts, and result missing information;
- preserve exact source values and result origins;
- compute provenance and checksums;
- prove one-to-one result publication;
- write `outputs/antenna_results.json` atomically;
- write a validation report;
- fail rather than silently drop an unrepresentable result.

Tests:

- every extraction result appears exactly once;
- every referenced design, setup, and evidence record is retained;
- measured and simulated results remain separate;
- variant results remain attached to the correct design;
- exact decimal strings and units do not change;
- image-only graphs remain visible as result records;
- output ordering is deterministic;
- rerun policy is explicit;
- no model client is invoked.

Benchmark gate:

- the output preserves the `47.98 ohm` case;
- Paper 004 variant results remain present;
- Paper 005 simulated and measured results remain separate;
- all result expectations pass or produce explicit extraction failures.

Completion gate:

- `antenna_results.json` is a stable final contract;
- publication is lossless relative to extraction;
- the results output remains available even if the later architecture phase
  fails.

## 15. Phase 4: architecture author

### Commit 8: generate `antenna_architecture.json`

Proposed commit message:

```text
feat(architecture): add single-call visual architecture author
```

Objective:

- implement the second normal model call, compare the two candidate author
  models, select one default, and produce the final architecture directly.

Required deterministic preparation:

- validate the paper-extraction checksum;
- assemble the complete extraction;
- assemble all ordered pages for the initial highest-recall benchmark;
- implement exact evidence-reference closure as the approved technical-limit
  fallback;
- generate the architecture JSON Schema;
- record an author-input manifest with every included page and reason;
- never use semantic search or a page-importance classifier.

Required model behaviour:

- select the final or fabricated design with evidence;
- map all relevant symbols to geometry or unresolved items;
- produce blocks, geometry, placement, materials, relationships, ports, and
  derivations;
- preserve ambiguity;
- keep unsupported completions unapplied;
- write only the architecture contract;
- make one call.

Required traces:

- exact author model;
- extraction checksum;
- included page list and checksums;
- prompt and schema hashes;
- model settings;
- raw response;
- finish reason and usage when available;
- latency;
- parse and validation result.

Model-selection experiment:

1. Freeze identical extraction and page inputs.
2. Run Gemma4 and Qwen 3.6 sequentially.
3. Do not allow either output to influence the other.
4. Score both with the benchmark in Section 13.
5. Have the same expert review the manual items blind to model identity where
   practical.
6. Select one default only if it meets the minimum correctness gate.
7. Record the decision, exact model identifiers, prompt hash, schema hash, and
   benchmark date.

Minimum author-selection gate:

- no unsupported numeric mutation on the regression set;
- correct final-design selection for Paper 004;
- correct circular-slot subtraction and `2 * x` derivation for Paper 002;
- correct inset or explicit unresolved inset for Paper 003;
- Paper 005 maps the required symbols or remains precisely incomplete;
- no false `complete` on a reconstruction-critical omission;
- architecture schema valid for the diverse synthetic fixtures;
- acceptable expert review on the available real geometry-coverage papers.

Tests with fake clients:

- identical ordered input is reproducible;
- all-pages and reference-closure policies are deterministic;
- invalid references fail before the call;
- raw response survives parse failure;
- explicit extraction values cannot be mutated without a validation issue;
- an engineering inference cannot enter applied parameters;
- forced rerun replaces artefacts without duplication;
- the normal call count is one;
- the selected runtime path calls only the configured winning model.

Completion gate:

- `antenna_architecture.json` is written directly by one selected author;
- there is no deterministic geometry composition phase;
- the chosen author is justified by evidence, not assumed in advance;
- no third model call is introduced;
- incomplete source papers produce honest incomplete architectures.

## 16. Phase 5: validation and orchestration

### Commit 9: add objective output-integrity gates

Proposed commit message:

```text
feat(validation): add architecture and results integrity gates
```

Objective:

- prevent internally inconsistent or unsupported outputs from being consumed
  while keeping deterministic code outside scientific interpretation.

Results checks:

- schema and ID integrity;
- complete publication from extraction;
- exact source-value preservation;
- known design, setup, and evidence references;
- result-source preservation;
- no accidental simulated-versus-measured conflict;
- provenance checksum consistency.

Architecture checks:

- schema and ID integrity;
- known parameter, material, block, frame, relationship, port, and evidence
  references;
- safe expression parsing;
- no unknown symbols or dependency cycles;
- objective unit compatibility;
- geometry-type required fields;
- valid minimal polygon, path, and profile structure;
- acyclic block and boolean dependencies;
- source-backed explicit and derived values;
- no applied proposed completion;
- precise unresolved reconstruction-critical items;
- selected-design reference and evidence.

Validators must not decide:

- which topology is correct;
- whether a figure shows a subtraction or addition;
- which antenna-family components are expected;
- whether a missing material should be copper;
- how to repair geometry;
- whether the antenna will simulate or fabricate correctly.

Tests:

- valid complete architecture;
- valid incomplete architecture;
- invalid schema;
- unknown references;
- expression and block cycles;
- incompatible units;
- unsupported explicit-value mutation;
- applied proposed completion;
- missing critical port or placement declared unresolved;
- loss of a result during publication;
- deterministic status calculation.

Completion gate:

- structural validity, reconstruction completeness, and scientific review are
  separate;
- `complete` cannot be produced when a critical unresolved item or required
  proposal remains;
- tests never encode patch, PIFA, horn, helix, array, implantable, or other
  family recipes;
- validation uses no model call.

### Commit 10: add the sequential two-call runner

Proposed commit message:

```text
feat(cli): add sequential two-call pipeline runner
```

Objective:

- expose one clear end-to-end command and freeze the first reliable baseline.

Target command:

```text
uv run antenna-ingest run <paper.pdf>
```

Normal order:

1. create run;
2. render pages;
3. call NuExtract3;
4. validate extraction;
5. publish and validate results;
6. prepare author input;
7. call the selected architecture author;
8. validate architecture;
9. print run path, output paths, call count, and final statuses.

Failure policy:

- stop at the first failed required phase;
- preserve every completed artefact;
- never delete the valid results output because architecture failed;
- mark later phases pending or skipped under one documented rule;
- return a non-zero status for request failure, parse failure, or structurally
  invalid final output;
- report incomplete architecture clearly without presenting it as CST-ready;
- do not retry automatically.

Resume and force:

- prefer a new run for a new end-to-end attempt;
- allow a phase to be replaced only through an explicit, safe force policy;
- add resume only after remote-call cost demonstrates a need and input, prompt,
  schema, and model hashes make reuse safe;
- do not build a workflow engine.

End-to-end tests with fake clients:

- exact phase order;
- exact normal model-call count of two;
- no concurrent calls;
- results remain after author failure;
- failures never leave a phase running;
- both final outputs and reports are registered;
- CLI status and printed paths are correct;
- all run metadata and checksums resolve.

Final benchmark:

- run the five regression papers;
- run the available diverse geometry set;
- record model calls, page count, page policy, latency, statuses, unsupported
  value count, result assertions, architecture assertions, and manual review;
- do not call the baseline complete while a required benchmark item is
  unexplained.

Final documentation:

- concise README quick start;
- environment-variable example;
- output examples generated from synthetic or distributable inputs;
- instructions for adding a reviewed benchmark paper;
- exact statement of what `complete` does and does not mean;
- recommendation for a baseline tag, created manually only after acceptance.

Completion gate:

- one command produces the two final documents;
- the normal path makes exactly two sequential model calls;
- no legacy path is imported;
- all local tests and lint pass;
- remote benchmark results are recorded;
- the repository contains one implemented architecture and one documented
  architecture;
- a future CST consumer can reject invalid or incomplete architecture without
  guessing.

## 17. Testing strategy

### 17.1 Local unit tests

Use local tests for:

- strict schema behaviour;
- references and IDs;
- values, expressions, and units;
- deterministic projection;
- manifest transitions;
- paths and checksums;
- request construction with fake clients;
- raw-response preservation;
- failure redaction;
- output validators;
- CLI order and call budget.

Default local tests never contact the remote endpoint.

### 17.2 Integration tests

Use integration tests for:

- PDF-to-page rendering;
- run creation and artefact registration;
- fake-client extraction;
- fake-client architecture generation;
- result publication;
- complete sequential orchestration;
- failure preservation.

Use compact synthetic JSON whenever a PDF is not necessary.

### 17.3 Remote capability checks

Remote checks are opt-in and versioned by:

- endpoint;
- exact model identifier;
- prompt hash;
- schema hash;
- settings;
- date.

They test only observed needs:

- multimodal support;
- multiple-image limits;
- structured-output behaviour;
- thinking-mode behaviour;
- timeout and finish reasons;
- numeric fidelity;
- latency.

Do not create a general model-evaluation platform.

### 17.4 Scientific benchmark

Scientific benchmark results are not part of default `pytest`. They combine:

- deterministic assertions;
- model-call metadata;
- expert visual review;
- explicit failed and unresolved cases.

An output that passes Pydantic but fails a scientific assertion is not accepted.

### 17.5 Test order for every commit

1. Directly affected tests.
2. Relevant unit or integration subset.
3. Complete local suite.
4. Lint.
5. Remote or scientific benchmark only when the commit changes model-facing
   behaviour.

## 18. Risks and controls

| Risk | Consequence | Control |
| --- | --- | --- |
| Cleanup deletes the only useful implementation | Lost reference and unnecessary rework | Verify the historical branch and Git state before deletion |
| Cleanup preserves compatibility wrappers | Visual and conceptual legacy remains | Keep only code with a current consumer |
| NuExtract3 misses a small result or symbol | Incomplete outputs look plausible | Reviewed assertions, exact evidence, second-stage full-page baseline |
| Full-document request exceeds endpoint limit | Extraction cannot run in one call | Measure first, then sequential technical batching only |
| Architecture author relies on a bad page list | Missing topology | Benchmark all pages first; use exact reference closure only as a measured fallback |
| Model invents a typical material or dimension | False reconstruction | Raw value preservation, unsupported-value checks, unresolved items |
| Model chooses the wrong design | Wrong antenna architecture | Selection evidence and Paper 004 benchmark |
| Variant results are attached to the primary design | Invalid scientific comparison | Flat design registry and exact result-to-design references |
| Results are lost during geometry work | Incomplete comparison dataset | Results bypass the architecture author |
| Simulated and measured values become conflicts | False contradiction | Source and setup identity in the result contract |
| Initial geometry vocabulary is too narrow | Forced approximation | Surface, mesh reference, and unresolved escape hatches |
| Schema becomes a universal CAD project | Slow and brittle implementation | Implement only meaningful validated geometry forms |
| Five patch papers create false confidence | Poor generalisation | Separate diverse geometry-coverage benchmark |
| A third model call hides systematic errors | Latency and unpredictable behaviour | Stop and fix prompt, schema, or evidence before adding a reviewer |
| Structural validation is presented as scientific proof | Unsafe CST handoff | Separate structural, reconstruction, and review states |

## 19. Deferred decisions and escalation gates

Do not implement the following during the ten planned commits:

- reviewer model;
- automatic repair;
- RAG;
- graph digitisation;
- preview engine;
- CST adapter;
- optimisation;
- multi-paper execution;
- caching;
- automatic retry;
- asynchronous execution.

A deferred feature may be proposed only with:

1. a reproducible failing paper or endpoint condition;
2. evidence that the existing architecture cannot address it;
3. the smallest proposed change;
4. expected call, latency, and maintenance cost;
5. an acceptance test;
6. an explicit decision about whether it changes the normal two-call claim.

Examples:

- Add a reviewer only if benchmarked false-complete or topology errors remain
  after prompt and schema fixes.
- Add repair only if one bounded correction reliably fixes a documented class
  of structural failures.
- Add RAG only for corpus-scale retrieval or demonstrated context limits, not
  because retrieval is familiar.
- Add graph digitisation only when the downstream comparison agent requires
  numeric curves unavailable as explicit points.

## 20. Definition of done

The initial NewPipeline implementation is done only when all of the following
are true.

### Repository

- `feat/antenna-pipeline-v2` contains no active legacy pipeline.
- The historical pipeline is recoverable from its verified branch and Git
  history.
- One plan path, one README path, and one architecture description agree.
- The source tree contains no empty speculative packages.

### Architecture

- The implemented path matches Section 5.
- Normal execution is sequential and makes two model calls.
- No semantic deterministic detector precedes NuExtract3.
- No RAG or tool loop exists in the single-paper path.
- No deterministic geometry assembler exists.

### Outputs

- `antenna_results.json` preserves all validated extraction results and their
  associations.
- `antenna_architecture.json` describes the selected design through generic
  blocks and relationships.
- Exact source values remain unchanged.
- Derivations are reproducible.
- Unsupported completions remain unapplied.
- Missing information is explicit.

### Scientific integrity

- Current five-paper regression assertions pass or have an approved explicit
  unresolved outcome.
- Diverse geometry coverage exists before claiming broad
  geometry-independence.
- No unsupported numeric mutation is accepted.
- No false `complete` result is accepted for a critical omission.
- Scientific review status is not inferred from structural validity.

### Reliability

- model requests and raw responses are traceable;
- failures are redacted and inspectable;
- no handled failure leaves a phase running;
- local tests and lint pass;
- remote checks are opt-in;
- result output survives architecture failure.

### Handoff

- a future CST agent can consume only structurally valid and reconstruction-
  complete architecture;
- the CST agent does not need to recover missing result associations;
- the CST agent does not need to interpret unconfirmed proposals as facts;
- solver-specific planning remains outside these two documents.

## 21. New-chat template

Use this template at the start of a commit chat:

```text
We are implementing Commit <N> from docs/implementation_plan.md in
GoncaGomes/antenna_extraction on branch feat/antenna-pipeline-v2.

First read the complete plan and inspect the actual branch, current HEAD, working
tree, relevant files, imports, and tests. Confirm which earlier planned commits
are already present. Do not assume the commit hashes or test counts in the plan
are still current.

Before editing, explain:
1. what the branch currently does in this area;
2. the smallest coherent change for Commit <N>;
3. any contradiction or missing decision;
4. the exact tests and acceptance evidence.

Keep the pipeline sequential. Do not add RAG, parallelism, retries, fallback
models, agent tool loops, CST commands, antenna-family recipes, or work from a
later commit.

Preserve user changes. Do not commit. Stop if the working tree is unsafe or if
the requested change requires a material scope expansion.

After implementation, report changed files, tests, observed outputs,
limitations, and whether every completion gate for Commit <N> is satisfied.
```

## 22. Handoff record between chats

At the end of every accepted commit, record:

```text
Commit number:
Commit SHA:
Branch:
Files changed:
Tests:
Lint:
Remote checks:
Benchmark cases:
Generated schema versions:
Prompt hashes:
Model identifiers:
Decisions made:
Known limitations:
Deferred work:
Next commit:
```

The next chat should receive this record together with the repository. Passing
tests alone is not a substitute for the completion gate or scientific review.
