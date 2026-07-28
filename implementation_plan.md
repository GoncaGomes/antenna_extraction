# NewPipeline Implementation Plan

## 1. Purpose of this document

This document is the implementation roadmap for the sequential, VLM-first
antenna extraction pipeline developed in this repository.

Its purpose is to make each implementation phase discussable and executable in
an independent chat without losing the architectural decisions made in earlier
phases. It is intentionally more detailed than a normal issue list. It records:

- the target behaviour of the pipeline;
- the boundaries between model responsibilities and deterministic code;
- the expected artefacts and data contracts;
- the proposed implementation phases and commit boundaries;
- the questions that must be discussed before each phase;
- the minimum tests and acceptance criteria for each phase;
- the work that is explicitly outside the current scope;
- the conditions under which implementation should stop and be reconsidered.

The plan is not an instruction to implement every item automatically. Each
phase begins with analysis and discussion. The proposed design should be
checked against the code and outputs produced by all previous phases before a
local implementation prompt is prepared.

The preferred working loop is:

1. Open a dedicated chat for the phase.
2. Review the current repository state and the relevant section of this plan.
3. Discuss the smallest coherent change that should be made next.
4. Resolve decisions that materially affect that change.
5. Produce one specific prompt for the local Codex implementation.
6. Run that prompt locally without creating a commit.
7. Bring the implementation report, diff, tests, and representative outputs
   back to the phase chat.
8. Review the actual result before preparing another implementation prompt.
9. Create the commit manually only after the change is accepted.

One chat per phase is recommended. One implementation prompt does not
necessarily have to cover the entire phase.

---

## 2. Project objective

The current project must transform a scientific antenna paper in PDF format
into a structured, evidence-grounded, validated JSON document containing enough
information for a later agent to reconstruct the reported antenna.

The eventual consumer is expected to translate the JSON into calls to an API or
MCP interface controlling CST Studio Suite. That CST agent is not part of the
current implementation. The current pipeline must therefore produce a
solver-neutral construction description rather than CST-specific commands.

The final output should represent, as far as the paper permits:

- document and run metadata;
- the final fabricated or otherwise primary antenna design;
- alternative, intermediate, and parametric design variants;
- parameters, values, units, and expressions;
- materials and stackup;
- a coordinate system;
- geometry blocks, dimensions, materials, and placement;
- profiles, extrusions, transformations, and boolean operations;
- ports, feeds, and excitations;
- relevant simulation settings;
- simulated, measured, and analytical results;
- textual, tabular, mathematical, and visual evidence;
- explicit derivations;
- clearly labelled engineering inferences;
- missing information and unresolved ambiguity;
- a final reconstruction-readiness status.

The output must not claim exact reconstruction when the source paper does not
contain enough information.

---

## 3. Agreed architectural direction

The intended critical path is:

```text
PDF
  |
  v
Mechanical page rendering
  |
  v
NuExtract3 full-document multimodal extraction
  |
  v
Gemma4 targeted visual geometry compilation
  |
  v
Lossless final document composition
  |
  v
Deterministic structural and evidence-integrity validation
  |
  v
outputs/antenna_design.json
```

The normal path should require two model calls:

1. One NuExtract3 call containing the complete ordered set of rendered pages.
2. One Gemma4 call containing the structured document extraction and only the
   pages needed to compile the geometry.

A directed repair call may be added later, but it must be disabled by default
and must only receive the invalid geometry, the validator errors, and the
minimum relevant evidence. It must not restart the complete document analysis.

If a paper exceeds a verified endpoint limit, page batches may be used. Batches
must be sequential and defined by transport limits such as image count or
payload size. There must be no deterministic semantic pre-classification of
tables, figures, captions, or page importance before NuExtract3.

### 3.1 Responsibility boundaries

| Component | Responsibility | Must not do |
|---|---|---|
| Page renderer | Convert every PDF page to an ordered image and record rendering metadata | Interpret document content |
| NuExtract3 | Read the full multimodal document and extract evidence, designs, parameters, variants, results, and geometry-relevant pages | Produce solver commands or silently invent missing dimensions |
| Gemma4 | Select the primary design and compile relevant evidence into a block-oriented construction description | Re-extract the entire paper, discard results and variants, or emit CST commands |
| Final document composer | Copy and link model outputs without information loss and serialise the final schema | Decide which blocks exist, interpret geometry, apply antenna-type rules, or resolve scientific ambiguity |
| Deterministic validators | Check schema, identifiers, references, expressions, units, dependency integrity, evidence links, result coverage, and declared completeness | Infer geometry, decide how an antenna type should be built, repair model output, or convert assumptions into facts |
| Future CST agent | Translate a validated solver-neutral design into CST operations | Influence the extraction schema with CST-only concepts |

### 3.2 Non-negotiable technical principles

- The pipeline is sequential. `parallelism` is one.
- NuExtract3 performs the initial semantic and multimodal interpretation.
- There is no preliminary deterministic detection of tables, figures, or
  captions.
- Deterministic code is used for rendering, persistence, lossless document
  composition, structural validation, and other operations with objective
  rules.
- The final construction representation is block-oriented. Gemma4 decides which
  blocks, geometries, placements, and relationships describe the antenna.
- Deterministic code must not contain construction recipes for antenna families
  such as patches, PIFAs, monopoles, arrays, or implantable antennas.
- Structural validation may enforce the declared schema and graph integrity,
  but it must not encode semantic geometry rules that attempt to recognise or
  reconstruct antenna types.
- Visual evidence is valid evidence for topology, shape, and placement.
- Explicit text, table, equation, and figure values must be preserved.
- Normalisation must never overwrite the exact reported value.
- Simulated and measured observations are distinct results, not conflicts.
- Design variants and their results must remain distinguishable.
- A derivation must record its expression, explanation, and evidence.
- An engineering inference must be labelled as an inference, justified, assigned
  confidence, and marked for confirmation.
- Missing information is represented explicitly.
- Failure and incomplete reconstruction are valid, inspectable outcomes.
- No model call is allowed merely because it might improve the output.
- No retry, cache, fallback, generic rule framework, or abstraction is added
  until a concrete requirement demonstrates its necessity.

---

## 4. Current repository baseline

At the time this plan was written:

- active branch: `feat/antenna-pipeline-v2`;
- current implementation commit: `a3e4bff`;
- tags available: `stage0-complete` and `pre-architecture-v2`;
- test baseline: `229 passed`;
- package version: `0.1.0`;
- Python requirement: 3.12 or newer.

The repository currently has a complete Stage 0 foundation:

- run creation;
- input checksums and document identity;
- environment and repository fingerprints;
- phase status and attempt tracking;
- artefact registration;
- atomic JSON writes;
- structured failure reports;
- secret redaction;
- PDF page rendering;
- NuExtract3 and canonicalizer endpoint doctors;
- a frozen manifest for five reference papers.

The existing v1 critical path is:

```text
PDF
  -> page images
  -> per-page NuExtract Markdown
  -> deterministic evidence blocks and HTML tables
  -> lexical evidence index and search
  -> NuExtract antenna candidate
  -> tool-using canonicalization agent
  -> canonical_design_record_v1
```

The following existing modules are expected to remain useful:

- `src/antenna_ingest/nuextract/pdf_rendering.py`
- `src/antenna_ingest/nuextract/client.py`
- `src/antenna_ingest/nuextract/images.py`
- `src/antenna_ingest/nuextract/settings.py`, after role names are clarified
- `src/antenna_ingest/orchestration/runs.py`
- `src/antenna_ingest/orchestration/phases.py`
- `src/antenna_ingest/orchestration/schemas.py`
- `src/antenna_ingest/orchestration/failures.py`
- `src/antenna_ingest/orchestration/fingerprints.py`
- `src/antenna_ingest/utils/json_io.py`
- relevant doctor and capability-probe infrastructure

The following modules belong to the v1 path and are expected to leave the
critical path:

- `src/antenna_ingest/nuextract/markdown_conversion.py`
- `src/antenna_ingest/evidence/blocks.py`
- `src/antenna_ingest/evidence/tables.py`
- `src/antenna_ingest/retrieval/index.py`
- `src/antenna_ingest/retrieval/search.py`
- the tool loop in `src/antenna_ingest/canonicalization/agent.py`
- the existing canonicalization prompt and tools;
- `canonical_design_record_v1`.

These modules should not be deleted while v2 is still being developed. Keeping
the v1 path temporarily allows output comparison and prevents a premature,
irreversible cutover. They should not, however, constrain the v2 schemas.

---

## 5. Target run layout and artefact flow

The exact names should be confirmed while implementing the relevant phase. The
following layout is the current target:

```text
runs/<run_id>/
├── manifest.json
├── input/
│   └── <source>.pdf
├── parsed/
│   ├── pages/
│   │   ├── page_0001.png
│   │   └── ...
│   └── page_render_report.json
├── extraction/
│   ├── document_extraction.json
│   ├── nuextract3_raw_response.txt
│   ├── nuextract3_request_metadata.json
│   └── nuextract3_extraction_report.json
├── compilation/
│   ├── geometry_compilation.json
│   ├── gemma4_raw_response.txt
│   ├── gemma4_request_metadata.json
│   └── gemma4_compilation_report.json
├── outputs/
│   └── antenna_design.json
└── reports/
    ├── validation_report.json
    ├── previews/
    │   ├── geometry_top.svg
    │   └── geometry_3d.<format-to-be-decided>
    └── failures/
        └── <phase>_attempt_<n>.json
```

The manifest should expose the following v2 phases:

```text
run_infrastructure
page_rendering
document_extraction
geometry_compilation
final_composition
structural_validation
optional_repair
```

The output of each phase is the input contract of the next phase:

| Phase | Primary input | Primary output |
|---|---|---|
| Run infrastructure | Source PDF | Run directory and manifest |
| Page rendering | Copied PDF | Ordered page images and render report |
| Document extraction | Ordered page images | `document_extraction.json` |
| Geometry compilation | Extraction plus selected page images | `geometry_compilation.json` |
| Final composition | Extraction plus compilation | `antenna_design.json` |
| Structural validation | Final design | Validation report and previews |
| Optional repair | Invalid compilation plus concrete errors | Revised compilation |

Raw responses and request metadata are first-class diagnostic artefacts. They
must be written as soon as the corresponding data exists, including on parsing
or validation failure.

---

## 6. Data model boundaries

Two different model-generated contracts are required. They should not be
collapsed into one prompt or one schema.

### 6.1 Document extraction contract

`document_extraction.json` represents what the paper contains. It is
descriptive and evidence-oriented. It does not prescribe how CST or another
solver should create the antenna.

The minimal conceptual sections are:

```json
{
  "schema_name": "document_extraction_v1",
  "document": {},
  "pages": [],
  "designs": [],
  "materials": [],
  "parameter_observations": [],
  "geometry_observations": [],
  "result_observations": [],
  "simulation_observations": [],
  "evidence_catalog": [],
  "conflicts": [],
  "missing_information": [],
  "geometry_relevant_pages": []
}
```

This is a conceptual shape, not a final schema declaration. During Phase 2 it
should be reduced to the smallest set of fields that still preserves all
information required by the benchmark.

Important rules:

- evidence IDs must be unique and stable within one extraction;
- every factual observation must reference one or more evidence IDs;
- page numbers are one-based and refer to rendered source pages;
- verbatim or source-faithful values must be kept separately from normalised
  values;
- a source figure, table, equation, paragraph, or caption can have one evidence
  record and support several observations;
- the NuExtract output may identify candidate designs but must not be forced to
  decide the final primary design when the document is ambiguous;
- all reported results must be kept, even when they belong to a rejected or
  intermediate variant;
- result provenance must distinguish `simulated`, `measured`, `analytical`, and
  any other explicitly required category;
- geometry-relevant page selection is an extraction result, not deterministic
  page classification.

### 6.2 Geometry compilation contract

`geometry_compilation.json` represents the selected design as a declarative set
of solver-neutral geometry blocks and relationships. It is prescriptive enough
for a later construction agent, but it is not a sequence of solver commands.

Its minimal conceptual shape is:

```json
{
  "schema_name": "geometry_compilation_v1",
  "selected_design_id": "design_final",
  "coordinate_system": {},
  "parameters": [],
  "materials": [],
  "blocks": [],
  "operations": [],
  "ports": [],
  "simulation_setup": {},
  "derivations": [],
  "engineering_inferences": [],
  "unresolved_geometry": [],
  "evidence_ids": []
}
```

The geometry compiler must not repeat the complete result inventory. Results
are preserved by the document extraction and linked by final document
composition.

Each physical or geometric part should normally be represented as one block.
A block answers:

- what the part is and its semantic role;
- which material it uses, when material is applicable;
- which basic geometry describes it;
- which parameters or literal values define its dimensions;
- where it is placed and relative to which reference;
- which evidence supports it;
- whether any value was derived or inferred.

The block model is declarative. A substrate, radiator, ground plane, feed,
shorting element, via, wire, dielectric volume, or subtractive feature can all
be blocks. It must not require a separate schema for each antenna family.

Illustrative block:

```json
{
  "block_id": "substrate",
  "name": "Dielectric substrate",
  "role": "substrate",
  "material_id": "rogers_5880",
  "geometry": {
    "type": "brick",
    "dimensions": {
      "width": "substrate_width",
      "length": "substrate_length",
      "height": "substrate_height"
    }
  },
  "placement": {
    "reference": "global",
    "anchor": "center_xy_bottom_z",
    "position": {
      "x": 0,
      "y": 0,
      "z": 0
    },
    "rotation": {
      "x": 0,
      "y": 0,
      "z": 0
    }
  },
  "evidence_ids": ["ev_table_dimensions"]
}
```

Geometry fields depend on the primitive rather than being forced into
`x × y × z`. For example:

| Geometry | Minimum descriptive fields |
|---|---|
| `brick` | width, length, height |
| `sheet_rectangle` | width, length |
| `circle` or `disk` | radius |
| `ring` | inner radius, outer radius |
| `cylinder` | radius, height |
| `polygon` | ordered points and optional thickness or extrusion |
| `path` or `wire` | ordered points, width or radius as applicable |

This table is an initial vocabulary, not a closed universal CAD catalogue.
Only geometries demonstrated by the benchmark should be implemented in v1.
Unknown geometry must remain explicit in `unresolved_geometry`; it must not be
silently approximated by a familiar primitive.

Operations exist only when the relationship cannot be expressed by the blocks
themselves. Typical examples are `subtract`, `unite`, and, if required by a
benchmark paper, `intersect`. Placement contains translation and rotation.
Symmetry may be expressed as an explicit block or a small declarative mirror
relationship when that is clearer and evidence-grounded.

Illustrative subtractive feature and relationship:

```json
{
  "block_id": "circular_slot",
  "name": "Circular radiator slot",
  "role": "subtractive_feature",
  "material_id": null,
  "geometry": {
    "type": "circle",
    "dimensions": {
      "radius": "slot_radius"
    }
  },
  "placement": {
    "reference": "radiator",
    "anchor": "profile_center",
    "position": {
      "x": "slot_offset_x",
      "y": "slot_offset_y",
      "z": 0
    },
    "rotation": {
      "x": 0,
      "y": 0,
      "z": 0
    }
  },
  "evidence_ids": ["ev_final_geometry"]
}
```

```json
{
  "operation_id": "cut_circular_slot",
  "type": "subtract",
  "target_block_id": "radiator",
  "tool_block_ids": ["circular_slot"],
  "result_block_id": "radiator_with_slot",
  "evidence_ids": ["ev_final_geometry"]
}
```

Gemma4, not deterministic code, decides that these blocks and this subtraction
represent the evidence in the paper.

### 6.3 Final antenna design contract

`antenna_design.json` is the lossless, consumer-facing composition of document
knowledge and the compiled block-oriented construction.

Its conceptual top-level shape is:

```json
{
  "schema_name": "antenna_design_v1",
  "document": {},
  "primary_design": {},
  "construction": {
    "coordinate_system": {},
    "parameters": [],
    "materials": [],
    "blocks": [],
    "operations": [],
    "ports": [],
    "simulation_setup": {}
  },
  "design_variants": [],
  "results": [],
  "evidence_catalog": [],
  "derivations": [],
  "engineering_inferences": [],
  "missing_information": [],
  "validation": {}
}
```

Final composition should copy and link information. It should not ask a model
to summarise the inputs, determine block geometry, or translate the description
into an ordered solver procedure.

### 6.4 Value origin

Every construction-critical value should expose its origin:

| Origin | Meaning | Confirmation |
|---|---|---|
| `explicit_text` | Directly reported in prose or caption | Not normally required |
| `explicit_table` | Directly reported in a table | Not normally required |
| `explicit_equation` | Directly reported through an equation | Not normally required |
| `explicit_visual` | Directly labelled or dimensioned in a figure | Not normally required |
| `derived` | Deterministically calculated from explicit evidence | Requires expression and explanation |
| `engineering_inference` | Introduced to make an under-specified design buildable | Must require confirmation |

Example derived parameter:

```json
{
  "parameter_id": "patch_base_width",
  "value": null,
  "unit": "mm",
  "expression": "2 * x",
  "origin": "derived",
  "derivation": "The labelled x dimension represents half of the symmetric base.",
  "evidence_ids": ["ev_figure_geometry", "ev_table_dimensions"],
  "requires_confirmation": false
}
```

Example engineering inference:

```json
{
  "parameter_id": "copper_thickness",
  "value": 0.035,
  "unit": "mm",
  "expression": null,
  "origin": "engineering_inference",
  "justification": "The paper identifies copper but does not report conductor thickness.",
  "confidence": 0.5,
  "evidence_ids": ["ev_material_statement"],
  "requires_confirmation": true
}
```

The second example must never be presented as an exact property of the original
antenna.

### 6.5 Blocks and relationships

The first ACIR version should support only block geometries and relationships
required by the reference papers and the immediate reconstruction objective.
It must not be organised around `create_*` commands or an ordered history list.

The future CST agent will decide how to translate a valid block into API calls.
For example, a `brick` block may later become one CST brick creation call, but
that translation does not belong in NewPipeline.

The distinction is:

| Concept | Responsibility |
|---|---|
| Block | Declares a geometric or physical part, its material, dimensions, placement, evidence, and value origins |
| Operation | Declares a relationship between existing block definitions, normally a boolean relationship |
| Port | Declares the physical excitation and the blocks, faces, points, or references it uses |
| Future CST plan | Chooses API calls and execution order from the validated declarative representation |

Block IDs and operation outputs form a dependency graph. The JSON may preserve
a stable list order for readability, but semantic correctness must not depend
on a composer inventing construction order. Deterministic code may verify
that references resolve and that dependencies are acyclic. It must not choose
missing operations or reorder geometry to make an invalid model output appear
constructible.

---

## 7. Model routing and capability verification

The initial routing is:

| Function | Model |
|---|---|
| Deterministic orchestration and state | Python |
| Full-document multimodal extraction | NuExtract3 |
| Primary design selection and geometry compilation | Gemma4 26B |
| Fast textual consistency audit | Deferred until needed |
| Difficult ambiguity escalation | Deferred until needed |
| Embedding retrieval | Deferred; not part of the normal path |
| CST construction agent | Outside current scope |

Before model-dependent code is fixed around assumed behaviour, the endpoint
must be probed for:

- image input support;
- multiple images in one request;
- maximum accepted image count;
- practical payload size;
- effective context length;
- JSON Schema or structured-output support;
- finish reason reporting;
- timeout behaviour;
- response format when thinking is enabled or disabled;
- deterministic behaviour at temperature zero;
- numeric fidelity;
- end-to-end latency;
- behaviour on malformed or schema-invalid model output.

Only capabilities required by the next implementation phase should be probed.
The project must not add a general benchmarking framework.

Configuration examples should document model roles. Runtime configuration
should continue to use the simplest mechanism already present unless a concrete
need justifies another configuration loader.

---

## 8. Implementation phases and proposed commits

The implementation is divided into five active phases after the completed Stage
0. Ten proposed commits provide review boundaries. A phase chat may use several
local Codex prompts before one commit is accepted.

```text
Stage 0  Existing reproducibility foundation                 COMPLETE
Phase 1  Contracts and scientific benchmark                  Commits 1-2
Phase 2  Unified NuExtract3 document extraction               Commits 3-4
Phase 3  Block-oriented construction and visual compilation  Commits 5-6
Phase 4  Composition, validation, preview, and runner         Commits 7-9
Phase 5  Cutover and legacy cleanup                           Commit 10
```

Dependencies:

```text
Phase 1
  |
  v
Phase 2
  |
  v
Phase 3
  |
  v
Phase 4
  |
  v
Phase 5
```

Phase 1 contracts may be revised when a later phase reveals a real mismatch,
but changes must be deliberate and accompanied by updated tests and
documentation.

---

# Phase 1: Fix the contracts and benchmark

## 9. Phase 1 objective

Before changing runtime behaviour, define what the v2 pipeline promises to
produce and what scientific facts the five reference papers require it to
preserve.

This phase prevents later work from being judged only by whether a model
returned schema-valid JSON. It establishes scientific acceptance criteria and
the boundary between extraction, block-oriented geometry compilation, final
document composition, and validation.

## 9.1 Questions for the Phase 1 chat

The chat should resolve or explicitly defer:

1. Which fields are indispensable in `document_extraction_v1`?
2. Which fields belong only in `geometry_compilation_v1`?
3. Which information must be copied into `antenna_design_v1`, and which should
   be referenced?
4. Are figures authoritative for topology and placement when they do not
   conflict with explicit text or tables?
5. When a visual dimension is only approximately readable, should it be stored
   as an observation, an inference, or missing information?
6. Should graph curves be digitised into numeric series in v1, or preserved as
   image evidence plus axes, legends, and explicitly labelled points?
7. What exact minimum semantic assertions can be reviewed confidently for each
   of the five papers?
8. Which acceptance checks can run automatically and which require manual
   scientific review?
9. Are previews mandatory for the first complete v2 baseline, even if their
   first format is deliberately simple?

Recommended initial position for graph data: preserve graph identity, axes,
legend, trace labels, source page, and all explicitly reported or annotated
numeric points. Do not implement general curve digitisation until a concrete
downstream comparison requires it.

## 9.2 Commit 1

Proposed commit message:

```text
docs(architecture): define sequential VLM-first pipeline v2
```

### Intended changes

- Replace placeholders in:
  - `docs/architecture.md`;
  - `docs/model_assignment.md`;
  - `docs/evidence_schema.md`;
  - `docs/claim_schema.md`, either with its real v2 purpose or a clear decision
    that a separate claim layer is unnecessary;
  - `docs/testing_strategy.md`.
- Document the pipeline stages and responsibility boundaries.
- Document the expected run artefact layout.
- Document normal two-call execution.
- Document the policy for technically oversized documents.
- State explicitly that no deterministic table, figure, or caption detection
  precedes NuExtract3.
- Document the solver-neutral final objective and the exclusion of CST control.
- Fill `config/models.example.yaml` and `config/pipeline.example.yaml` as
  examples only.
- Decide whether the v2 schema descriptions live entirely in code-generated
  JSON Schema plus short documentation, avoiding duplicated hand-maintained
  specifications.

### Configuration target

The conceptual configuration is:

```yaml
pipeline:
  extraction_mode: full_document
  parallelism: 1
  repair_enabled: false
  max_repair_attempts: 1

models:
  document_extractor: nuextract3
  geometry_compiler: gemma4:26b
```

Do not add YAML runtime parsing merely to support these example files if
environment-based settings remain sufficient.

### Tests

This is primarily a documentation commit. Existing tests must remain green. If
configuration code changes, add only direct parsing or settings tests required
by that behaviour.

### Acceptance criteria

- The documents describe one consistent architecture.
- The same artefact is not assigned incompatible roles in different documents.
- The two model calls have distinct input and output contracts.
- Oversized-document handling is transport-driven.
- CST is explicitly outside the implementation.
- Existing 229 tests still pass, adjusted only if an intentionally changed
  contract requires it.

### Out of scope

- Implementing new schemas.
- Calling either model.
- Changing the CLI critical path.
- Removing v1 code.
- Adding embeddings or graph digitisation.

## 9.3 Commit 2

Proposed commit message:

```text
test(benchmark): define v2 acceptance contract for reference papers
```

### Intended changes

- Retain `benchmarks/v1/benchmark_manifest.json` as a historical baseline.
- Create a separate v2 benchmark specification, for example:

```text
benchmarks/v2/
├── README.md
├── papers.json
└── expectations/
    ├── 001_rectangular_patch_coaxial.json
    ├── 002_circular_slotted_triangular_patch.json
    ├── 003_5g_microstrip_patch_28ghz.json
    ├── 004_microstrip_patch.json
    └── 005_cp_patch.json
```

- Store paper identity by filename and SHA-256.
- Store reviewed semantic assertions, not complete model-generated gold JSON.
- Add a small benchmark assertion runner only when the expectation format has
  stabilised enough to justify it.
- Distinguish automatic assertions from manual visual review items.

### Required reference-paper expectations

The minimum known expectations are:

#### Paper 001: rectangular patch with coaxial feed

- Preserve the reported `47.98 Ω` value with its exact meaning and evidence.
- Preserve the feed position or coordinate information.
- Represent the principal rectangular patch, substrate, and ground topology.
- Associate the feed with the correct design and geometric location.

#### Paper 002: circular-slotted triangular patch

- Represent the circular slot as a void or subtraction, not as added metal.
- Preserve the triangular radiator topology.
- Preserve the relationship `base = 2 * x` as a derivation when the figure
  defines `x` as the symmetric half-base.
- Link the derivation to the figure and any supporting table evidence.

#### Paper 003: 28 GHz microstrip patch

- Include the inset or notch features that materially define the geometry.
- Preserve feed placement relative to the radiator.
- Preserve the relevant dimensions without collapsing distinct features.
- Represent cut-outs as explicit subtractive blocks and relationships whose
  references resolve.

#### Paper 004: microstrip patch with design evolution

- Select the paper's final or fabricated design as the primary design.
- Preserve intermediate or alternative designs as variants.
- Preserve results belonging to those variants.
- Do not mix variant results into the primary design.

#### Paper 005: circularly polarised patch

- Preserve and geometrically map `S1`, `S2`, `L1`, `L2`, `L3`, `L4`, `b`, `t`,
  and `d`, subject to confirmation from the paper annotations.
- Preserve the topology shown in the final antenna figure.
- Keep simulated and measured results as distinct observations.
- Do not classify normal simulation-versus-measurement differences as
  extraction conflicts.
- Fail as `incomplete` rather than inventing geometry if any symbol cannot be
  mapped.

These expectations must be checked against the source papers during the Phase 1
chat. The plan records prior findings but does not replace scientific review.

### Benchmark dimensions

The v2 benchmark should measure:

- explicit dimension coverage;
- parameter-symbol coverage;
- result coverage;
- evidence reference integrity;
- evidence-to-value semantic compatibility;
- primary-design selection;
- design-variant separation;
- block and relationship graph validity;
- unsupported numeric mutation count;
- derivation and inference labelling;
- reconstruction-readiness status;
- preview similarity through manual or later model-assisted review.

Not every metric needs an aggregate score. Clear pass/fail assertions are
preferred when possible.

### Tests

- Expectation files validate against a small strict schema.
- Every expected paper checksum matches the existing fixture or is clearly
  reported as unavailable.
- Unknown assertion types fail clearly.
- Numeric assertions define an explicit comparison rule and tolerance when
  tolerance is scientifically appropriate.
- Exact reported values default to exact string/value preservation tests.
- The v1 manifest remains unchanged.

### Acceptance criteria

- All five papers have reviewed minimum expectations.
- Paper 005 is represented as a required v2 recovery case rather than an
  accepted failure.
- Expectations test scientific content, not model phrasing or array order.
- The benchmark does not require complete hand-authored final JSON files.
- Automatic and manual checks are clearly distinguished.
- The test suite remains green.

### Out of scope

- Running remote models as part of normal unit tests.
- Building a benchmark dashboard.
- Defining a universal antenna ontology.
- Rewriting the v1 output.

## 9.4 Phase 1 completion gate

Phase 1 is complete when:

- the architecture documents are no longer placeholders;
- all three v2 data-contract boundaries are understood;
- the five benchmark expectation files have been scientifically reviewed;
- unresolved decisions that affect Phase 2 are recorded explicitly;
- existing code behaviour is otherwise unchanged;
- the complete test suite passes.

Do not begin schema implementation if the distinction between document
observations and construction instructions is still unclear.

---

# Phase 2: Unified NuExtract3 document extraction

## 10. Phase 2 objective

Replace the v1 Markdown, deterministic block/table parsing, and early candidate
path with one full-document multimodal NuExtract3 extraction that writes a
strict, evidence-grounded `document_extraction.json`.

The implementation should initially optimise for one complete request. Batching
is added only if the actual endpoint or benchmark papers require it.

## 10.1 Questions for the Phase 2 chat

1. What information in the current `AntennaDesignCandidate` is reusable?
2. Which existing fields caused information loss or ambiguity in the five runs?
3. Does NuExtract3 reliably accept all rendered pages in one request?
4. What structured-output mechanism does the endpoint actually honour?
5. Does thinking need to be disabled for strict JSON?
6. What image resolution gives enough figure legibility without exceeding the
   endpoint payload?
7. How should exact source values and optional normalised values coexist?
8. What minimum evidence record is sufficient to audit a fact?
9. Should the first implementation support only full-document mode and fail
   clearly on endpoint limits, or is size batching immediately demonstrated as
   necessary?
10. If batching is necessary, what deterministic merge rules preserve all
    observations without pretending to semantically reconcile them?

## 10.2 Commit 3

Proposed commit message:

```text
feat(extraction): add unified multimodal document schema
```

### Intended code structure

A minimal structure could be:

```text
src/antenna_ingest/nuextract/
├── document_schema.py
├── document_prompt.py
└── document_extraction.py   # added in Commit 4
```

Do not split models across several files unless `document_schema.py` becomes
genuinely difficult to navigate.

### Schema responsibilities

The schema must support:

- document identity and title metadata;
- ordered page inventory;
- evidence catalogue;
- candidate designs and variant relationships;
- material observations;
- parameter observations;
- geometry and topology observations;
- result observations;
- simulation-setting observations;
- conflicts and missing information;
- geometry-relevant page references.

### Evidence record

The minimum evidence record should contain:

- `evidence_id`;
- source kind such as text, caption, figure, table, or equation;
- one-based page number;
- source label when available, such as `Figure 4` or `Table II`;
- source-faithful excerpt or concise visual description;
- optional bounding region only if NuExtract3 reliably supplies one;
- optional confidence;
- optional notes about legibility or ambiguity.

Bounding boxes should not be mandatory unless they are required by an immediate
consumer and the model can produce them consistently.

### Observation design

An observation should separate:

- semantic identity, for example `substrate_width`;
- reported symbol, for example `Ws`;
- exact reported value;
- exact reported unit;
- optional normalised numeric value;
- optional normalised unit;
- design association;
- evidence IDs;
- ambiguity or conflict state.

The implementation must not convert all values to strings merely to avoid
modelling them. It also must not force every observation into a numeric value:
materials, shapes, qualitative relationships, and unresolved symbols are valid
observations.

### Schema simplicity rules

- Prefer explicit small Pydantic models over generic `dict[str, Any]`.
- Avoid inheritance hierarchies for evidence and observations unless they remove
  real duplication without making parsing harder.
- Use strict schemas with `extra="forbid"` at model boundaries.
- Avoid a generic property bag.
- Avoid a complete SI unit system in this commit.
- Avoid geometry construction operations in this schema.
- Avoid storing the same observation in several nested locations.

### Tests

At minimum:

- minimal valid document extraction;
- evidence page number must be positive;
- duplicate evidence IDs fail;
- duplicate design IDs fail;
- unknown design references fail;
- unknown evidence references fail;
- result source accepts the reviewed categories;
- a measured and simulated value for the same metric can coexist;
- exact reported values survive serialisation;
- a design variant can reference its parent or predecessor;
- geometry-relevant page references must exist;
- extra fields fail;
- the schema supports each of the five benchmark paper requirements with small
  synthetic examples.

### Acceptance criteria

- The schema can represent all reviewed Phase 1 expectations.
- It contains no CST-specific field.
- It describes the document rather than a build sequence.
- Evidence references have enforced integrity.
- Results are not optional side notes that can be dropped later.
- The schema remains understandable without a separate ontology engine.
- No model call is introduced in this commit.

### Out of scope

- Full prompt engineering.
- Geometry compilation.
- Expression evaluation.
- Composition of the final document.
- Automated repair.

## 10.3 Commit 4

Proposed commit message:

```text
refactor(nuextract): implement full-document multimodal extraction
```

### Intended behaviour

The default run path becomes:

```text
rendered pages
  -> ordered image payload
  -> one NuExtract3 request
  -> raw response persisted
  -> strict parsing
  -> document_extraction.json
  -> extraction report and manifest update
```

### Reuse from the current implementation

The current `raw_extraction.py` already demonstrates useful behaviour:

- all rendered pages can be sent in one request;
- page order is recorded;
- raw and cleaned responses are persisted;
- request metadata is written;
- parsing failures leave traces;
- source page references are checked;
- manifest phases and artefacts are updated;
- existing outputs require `--force`;
- model clients and settings are injectable in tests.

The new implementation should reuse or adapt this behaviour instead of
rewriting the same infrastructure. The current candidate schema and prompt
should not constrain the new output.

### Prompt requirements

The NuExtract3 prompt should:

- state that the ordered images form one scientific paper;
- ask for complete multimodal interpretation;
- require all final and intermediate antenna designs;
- require figures, captions, tables, equations, prose, and graphs to be treated
  as evidence;
- require all parameters and reported results;
- distinguish measured, simulated, and analytical results;
- identify geometry-relevant pages;
- record uncertainty and missing information;
- avoid solver operations;
- forbid unlabelled engineering assumptions;
- return only the target schema.

The target JSON Schema should be generated from the Pydantic model at runtime or
kept from one source of truth. Do not manually maintain a second full schema in
the prompt.

### Request and trace metadata

Persist at least:

- invocation or request ID when available;
- hash of the effective request payload without secrets;
- model name;
- temperature and thinking setting;
- page numbers and image paths included;
- image count;
- rendered image checksums where practical;
- request start and finish time;
- latency;
- finish reason;
- raw response path;
- parsing status;
- schema validation status;
- exception type and failure reference.

Token counts should be stored when supplied by the endpoint. Their absence must
not fail the phase.

### Full-document policy

The initial attempt must send the full document. It must not preselect pages.

If endpoint capability tests show that a benchmark paper cannot fit, introduce
the smallest necessary batching:

- fixed sequential batches based on verified image-count or payload limits;
- preserved global one-based page numbers;
- no page-content classifier;
- no parallel requests;
- unique batch-local evidence IDs prefixed or remapped during merge;
- deterministic concatenation of observations and evidence;
- exact duplicate removal only when identity is objective;
- cross-batch ambiguity preserved for Gemma4 or later validation rather than
  silently resolved.

Do not add batching speculatively.

### CLI

Add a clear command for the v2 extraction, for example:

```text
uv run antenna-ingest nuextract extract-document <run_dir>
```

The exact CLI nesting can follow existing conventions. Existing v1 commands
remain available during migration but should be clearly distinguished.

### Phase and artefact changes

- Add or activate `document_extraction`.
- Register the structured output, raw response, request metadata, and report.
- On request failure, record the request substage.
- On parsing failure, keep the raw response.
- On schema failure, keep both the raw response and the validation error.
- Never leave the phase marked `running` after a handled failure.

### Tests

Unit tests with an injected fake client must cover:

- all pages are sent once and in order;
- the correct model and structured-output schema are sent;
- exact source values survive parsing;
- raw response and metadata are written before final parsing success;
- valid response writes all artefacts and completes the phase;
- request error creates a redacted failure report;
- malformed JSON preserves the raw response and marks the phase failed;
- schema-invalid JSON preserves diagnostics and fails clearly;
- invalid evidence page references are rejected or explicitly reported
  according to the approved contract;
- `--force` controls replacement;
- artefact registration does not create duplicates after forced rerun;
- no Markdown, evidence-block, table-extraction, or retrieval function is called
  by the v2 path.

Integration tests should cover:

- rendered fixture pages to fake or controlled extraction response;
- CLI invocation;
- manifest phase transition;
- path and checksum consistency.

Remote-model tests should be explicitly marked and excluded from the default
unit suite.

### Benchmark evaluation

Run the five papers manually or through an opt-in script. Inspect:

- whether every expected result is present;
- whether the final design and variants are all represented;
- whether evidence pages are correct;
- whether geometry-relevant pages are sufficient;
- whether exact symbols and values are preserved;
- whether Paper 005 now reaches a valid extraction even before geometry
  compilation.

The phase should not be accepted based only on JSON validity.

### Acceptance criteria

- One command produces `document_extraction.json` from rendered pages.
- The default implementation uses one NuExtract3 call per paper.
- No deterministic content detection is used.
- All five reference papers produce schema-valid extractions or reveal a
  documented endpoint limitation requiring an approved batching change.
- Benchmark extraction assertions pass.
- Paper 005 no longer fails opaquely.
- Raw response, request metadata, and failures are sufficient to diagnose a
  future run without repeating it.
- Default tests pass.

### Out of scope

- Gemma4.
- Construction operations.
- Final document composition.
- Embedding retrieval.
- General curve digitisation.
- Automatic model retries.
- Semantic page chunking.

## 10.4 Phase 2 completion gate

Do not begin geometry compilation until:

- the extraction contract has survived all five papers;
- geometry-relevant page references are credible;
- results and variants are demonstrably preserved;
- request failures and parse failures are inspectable;
- the number of model calls is measured and documented;
- any batching is justified by an observed endpoint limit.

---

# Phase 3: Block-oriented construction and visual compilation

## 11. Phase 3 objective

Define the smallest solver-neutral Antenna Construction Intermediate
Representation (ACIR v1) required by the reference papers, then implement one
Gemma4 call that converts the document extraction and selected visual evidence
into a declarative, block-oriented construction representation.

The ACIR is not a universal CAD language. It is a precise handoff contract
between extraction and a future antenna-building agent. Its centre is the set
of geometry blocks, not an ordered list of solver commands.

## 11.1 Questions for the Phase 3 chat

1. What block geometry types are actually required by the five papers?
2. Which parts should be final physical blocks and which should be auxiliary
   blocks used by boolean relationships?
3. What coordinate convention is easiest to validate and consume?
4. How are sheet conductors represented when thickness is unknown?
5. Which anchors are necessary for placement?
6. Which expression operators and functions are immediately required?
7. What unit families are needed by the benchmark?
8. When should symmetry be expanded into explicit blocks, and when is a mirror
   relationship clearer?
9. How are design variants represented without duplicating the entire primary
   construction?
10. Which simulation settings are reconstruction-critical now?
11. How should incomplete geometry remain useful without becoming buildable by
    accident?
12. Can Gemma4 reliably produce the strict schema with the available image
    count and context?
13. Which relationships genuinely need `operations`, rather than being
    expressed directly through block geometry and placement?

## 11.2 Commit 5

Proposed commit message:

```text
feat(acir): define block-oriented antenna construction schema
```

### Intended code structure

```text
src/antenna_ingest/acir/
├── __init__.py
├── schemas.py
├── expressions.py
└── validation.py
```

If expression parsing and validation remain short, they may initially share one
module. File structure should follow actual complexity, not the diagram.

### Required ACIR concepts

#### Coordinate system

- length unit;
- axis orientation;
- origin description;
- optional reference plane;
- explicit convention for planar antennas.

There should be one document-level coordinate system unless a benchmark paper
demonstrates the need for local coordinate systems.

#### Parameters

- unique ID;
- optional source symbol;
- reported or computed value;
- unit;
- optional expression;
- value origin;
- explanation for derived or inferred values;
- evidence IDs;
- confirmation requirement.

#### Materials

- unique ID;
- reported name;
- electromagnetic properties when reported;
- frequency dependence only when reported and immediately needed;
- evidence IDs.

Do not attempt to reproduce the complete CST material model.

#### Geometry blocks

Support the minimum shapes demonstrated by the benchmark, likely including:

- brick or rectangular volume;
- rectangular sheet/profile;
- circle or disk;
- polygon;
- possibly cylinder;
- path or wire only if required by a reference paper.

Each block needs:

- stable block ID;
- human-readable name;
- semantic role such as substrate, ground, radiator, slot tool, feed, or port
  support;
- material when applicable;
- shape definition;
- dimensions;
- placement with an explicit reference, anchor, position, and rotation;
- evidence IDs.

Block dimensions may reference parameters or contain explicit values with their
origin. Primitive-specific geometry fields should be represented by a small
discriminated schema. Do not require every block to use `x`, `y`, and `z`
dimensions when those fields do not fit its geometry.

A block may represent:

- a final physical part;
- an auxiliary additive or subtractive feature;
- a dielectric or environmental volume;
- a path, wire, via, or other benchmark-demonstrated geometry;
- an unresolved part whose missing description is explicit.

Do not create Python rules such as "a patch antenna must contain these blocks"
or "a PIFA must be assembled in this way". Gemma4 interprets the paper and
declares the blocks.

#### Relationships and boolean operations

Use operations only for relationships that cannot be represented directly by a
block and its placement. The expected initial set is:

- `subtract`;
- `unite`;
- `intersect`, only if required by a benchmark paper;
- `mirror`, only if keeping the relationship is clearer than emitting the
  mirrored blocks explicitly.

Every operation needs:

- stable operation ID;
- operation type;
- target and tool block IDs, or other operation-specific block references;
- result block ID where applicable;
- evidence IDs;
- optional derivation or inference reference.

Boolean operations must make void-versus-material intent unambiguous. Placement
contains position and rotation, so `translate` and `rotate` are not separate
history-list commands. Material belongs to the block, so `assign_material` is
not a construction step. Ports are separate declarations, not `create_port`
steps.

Operations form a dependency graph rather than a solver history. A stable list
order may be used for serialisation, but semantic validity depends on resolved,
acyclic references, not on a composer selecting an execution order.

#### Ports and excitations

Represent:

- port ID;
- type when reported or required;
- target blocks, faces, points, or other explicit geometric references;
- placement and orientation;
- impedance when reported;
- evidence IDs;
- unresolved fields.

The schema should describe the physical excitation without using CST history
list commands.

#### Simulation setup

Initially preserve only what is explicitly needed:

- frequency range;
- boundary or environment statements;
- substrate and conductor assumptions already represented elsewhere;
- solver or analysis type if reported;
- result quantities requested.

Do not model every CST setting.

#### Derivations and engineering inferences

These remain separate:

- a derivation follows a reproducible expression from evidence;
- an engineering inference supplies absent design information using domain
  judgement.

Both must be traceable. Only engineering inferences force
`requires_confirmation: true`.

### Expressions

Use a small, safe expression grammar. Do not call Python `eval`.

The first version should support only demonstrated needs:

- numeric literals;
- parameter identifiers;
- parentheses;
- addition, subtraction, multiplication, and division;
- unary plus and minus;
- possibly a small reviewed set of functions such as `sqrt` if required.

Expression validation must:

- reject unknown symbols;
- detect dependency cycles;
- resolve dependencies in order;
- reject division by zero;
- enforce compatible units for addition and subtraction;
- derive predictable units for simple multiplication and division, or reject
  unsupported compound dimensions clearly.

A small explicit conversion table for required unit families is preferable to a
new dependency if it covers the benchmark correctly. If unit requirements
become broader, revisit this decision rather than growing an ad hoc unit engine.

### Structural validation in this commit

Schema-level and reference-level checks should include:

- unique parameter, material, block, operation, port, and inference IDs;
- known material references;
- known block and operation references;
- known parameter references in expressions;
- known evidence references when the evidence catalogue is provided to the
  validation boundary;
- acyclic operation dependencies;
- no duplicate block or result ID;
- valid polygon point count;
- no empty placement.

These checks must remain generic to the declared data contract. They must not
attempt to infer missing blocks, decide whether a particular antenna topology
is scientifically correct, or encode construction recipes. Broader readiness
and preview checks remain in Phase 4.

### Tests

Synthetic schema tests should cover:

- rectangular patch stackup;
- coaxial or point feed placement;
- triangular polygon;
- circular slot subtraction;
- inset or notch subtraction;
- mirrored or symmetric feature;
- derived `2 * x` dimension;
- engineering inference with confirmation;
- unknown block in boolean operation;
- cyclic operation dependency;
- expression cycle;
- incompatible units;
- duplicate IDs;
- invalid polygon;
- strict extra-field rejection;
- incomplete construction represented without schema corruption.

At least one compact fixture should model the core construction needs of each
benchmark paper.

### Acceptance criteria

- ACIR represents all reviewed benchmark geometries.
- ACIR is solver-neutral.
- Every construction-critical value is traceable to evidence, derivation, or
  inference.
- Unsupported operations fail clearly.
- The expression evaluator is safe and deliberately small.
- The schema is understandable as a list of blocks and relationships without a
  generic CAD framework.
- The schema does not duplicate block definitions in an ordered
  `construction_steps` history.
- No deterministic antenna-family construction rule is introduced.
- No model calls are introduced in this commit.
- Tests pass.

### Out of scope

- Meshing.
- Solver-specific boundary defaults.
- Optimisation variables.
- Parametric sweeps.
- CST API calls.
- General solid-modelling kernels.
- Geometry repair.

## 11.3 Commit 6

Proposed commit message:

```text
feat(compiler): add targeted visual geometry compiler
```

### Intended code structure

```text
src/antenna_ingest/compilation/
├── __init__.py
├── geometry_compiler.py
├── prompt.py
└── page_selection.py
```

`page_selection.py` should remain a small resolver from extraction page
references to rendered image paths. It must not classify page content.

### Compiler inputs

- validated `document_extraction.json`;
- ACIR JSON Schema;
- images listed in `geometry_relevant_pages`;
- adjacent pages only under an explicit, simple policy when captions or tables
  cross page boundaries;
- model settings;
- run metadata required for tracing.

### Compiler responsibilities

- choose the primary or final fabricated design;
- explain or encode that selection;
- preserve links to related design variants;
- map symbols and observations to construction parameters;
- choose a coordinate system;
- define blocks, primitive-specific geometry, materials, and placement;
- define only the boolean or symmetry relationships required between blocks;
- represent slots and notches with correct boolean intent;
- represent feeds and ports;
- create only defensible derivations;
- mark missing dimensions;
- introduce engineering inferences only under the approved policy;
- return strict `geometry_compilation_v1`.

### Compiler non-responsibilities

- repeat full-document extraction;
- search a lexical evidence index;
- use tools in a model loop;
- decide that measured and simulated values conflict;
- discard variant results;
- generate CST commands;
- emit an ordered solver history or rely on deterministic code to invent one;
- repair its own output through unbounded retries.

### Primary design selection

Selection should use explicit document evidence such as:

- language identifying the proposed, optimised, final, fabricated, or measured
  antenna;
- design-evolution sequence;
- figure and table labels;
- association with measured results;
- conclusions describing the selected design.

The output should retain:

- selected design ID;
- selection rationale;
- selection evidence IDs;
- unresolved ambiguity when the paper does not support a unique choice.

If selection remains ambiguous, the output may be incomplete. The compiler must
not choose silently.

### Page resolution

The extraction supplies semantic page references. Deterministic code:

1. validates that page numbers exist;
2. maps them to rendered image paths;
3. preserves order;
4. removes exact duplicate page references;
5. optionally includes a one-page neighbour only under the approved policy.

It does not inspect the image to decide relevance.

### Prompt design

The Gemma4 prompt should be shorter and narrower than the NuExtract3 prompt. It
should contain:

- the construction objective;
- the validated document extraction;
- selected page images;
- the ACIR schema;
- origin and evidence rules;
- the requirement to preserve uncertainty;
- the prohibition against inventing exact dimensions;
- the requirement to map every construction-critical symbol or mark it
  unresolved.

The prompt should state that the extraction is authoritative for the complete
result inventory and that Gemma4 is compiling geometry, not rewriting the
paper.

### Tracing and failure behaviour

Persist:

- request metadata;
- selected page list;
- extraction checksum;
- model and parameters;
- raw response;
- finish reason and usage when available;
- parsed compilation;
- validation errors;
- latency;
- structured failure record.

Failure in geometry compilation must not destroy the valid document extraction.

### Tests

With an injected fake client:

- only extraction-selected pages are sent;
- page order is deterministic;
- invalid page references fail before the request;
- adjacent-page policy behaves exactly as configured;
- the correct schema and model are sent;
- valid response writes the compilation and report;
- malformed and schema-invalid responses preserve diagnostics;
- primary-design selection evidence is required;
- unknown extraction evidence IDs fail;
- inferred values require confirmation;
- explicit values do not silently change;
- no retrieval tool loop is invoked;
- forced replacement does not duplicate manifest artefacts.

Remote benchmark review:

- Paper 001 feed location and impedance context compile correctly.
- Paper 002 circular subtraction and `2 * x` derivation compile correctly.
- Paper 003 inset/notch and feed placement compile correctly.
- Paper 004 final design is selected while variants remain linked.
- Paper 005 maps all required symbols or reports specific unresolved geometry.

### Acceptance criteria

- One Gemma4 call normally produces schema-valid geometry.
- Only extraction-selected visual pages are sent.
- The primary design choice is evidence-grounded.
- Every explicit construction value remains unchanged.
- Every derived value has an expression and explanation.
- Every engineering inference requires confirmation.
- All benchmark block representations pass ACIR schema and reference validation or
  report precise missing information.
- No autonomous tool loop exists in the v2 compiler.
- Tests pass.

### Out of scope

- Final document composition.
- Preview generation.
- CST execution.
- Model-based visual comparison.
- Automatic repair.
- Embedding retrieval.

## 11.4 Phase 3 completion gate

Do not proceed to final document composition until:

- all five papers produce inspectable geometry compilations;
- Paper 004 primary-design selection is correct;
- Paper 005 either compiles fully or identifies exact unresolved symbols;
- explicit, derived, and inferred values are visibly distinct;
- the block and relationship graph is solver-neutral and structurally valid;
- the compiler normally makes one model call;
- no result inventory has been moved into the geometry prompt unnecessarily.

---

# Phase 4: Final composition, validation, preview, and runner

## 12. Phase 4 objective

Compose document extraction and geometry compilation without information loss,
validate the structural readiness of the resulting block description, generate
a preview from that same representation, and expose one sequential pipeline
command.

This phase determines whether the pipeline can honestly deliver a design to a
future CST agent. It does not prove electromagnetic correctness or use
deterministic rules to decide whether the model chose the right topology.

## 12.1 Questions for the Phase 4 chat

1. Which fields are copied into the final document and which remain referenced?
2. How should one result be associated with a design and variant?
3. What exact conditions distinguish `complete`,
   `complete_with_inferences`, `incomplete`, and `invalid`?
4. Which validators are blocking and which produce warnings?
5. What is the smallest useful 2D/3D preview format?
6. Can preview generation be implemented from the ACIR without adding a heavy
   geometry dependency?
7. How should visual similarity be reviewed in the first baseline?
8. Is optional repair needed immediately, based on observed benchmark failures?
9. Which phases should be resumable, and what does `--force` mean for the
   end-to-end runner?
10. Should v2 reuse the current run directory names while leaving unused legacy
    directories temporarily present?
11. Which checks are genuinely structural, and which require scientific or
    visual review rather than another deterministic rule?

## 12.2 Commit 7

Proposed commit message:

```text
feat(composition): build lossless final antenna document
```

### Intended code structure

```text
src/antenna_ingest/composition/
├── __init__.py
└── final_document.py
```

One module is sufficient unless composition becomes genuinely complex.

### Composition responsibilities

- load validated document extraction;
- load validated geometry compilation;
- verify both refer to the same run and extraction;
- copy document metadata;
- materialise the selected primary design;
- retain all non-primary variants;
- attach the compiled blocks, relationships, ports, and simulation description
  to the primary design without reinterpretation;
- preserve every result observation;
- preserve the evidence catalogue;
- preserve derivations, inferences, conflicts, and missing information;
- link result and construction records by stable IDs;
- write `outputs/antenna_design.json`;
- update the manifest and composition report if one is needed.

### Losslessness requirements

The composer must prove or report:

- every extraction evidence ID is retained or intentionally excluded with a
  documented reason;
- every result observation is present in the final output;
- every design and variant is present;
- every compilation evidence reference resolves;
- every engineering inference remains labelled;
- no exact reported numeric value changes;
- no result source changes from measured to simulated or vice versa.

The composer should not use an LLM.

The composer must not:

- decide which geometric blocks should exist;
- turn a semantic role into a shape;
- generate boolean operations;
- infer placement, dimensions, material, or port geometry;
- apply antenna-family templates;
- repair or reorder the block graph;
- choose between conflicting scientific observations.

### Conflict handling

The composer does not resolve scientific conflicts. It carries them into the
final document.

Normal differences between:

- simulated and measured results;
- different design variants;
- different frequency conditions;
- analytical and simulated calculations

must not be collapsed into conflicts merely because their numeric values differ.

### Tests

- all results survive composition;
- all designs and variants survive composition;
- primary construction attaches to the selected design;
- measured and simulated results remain distinct;
- unknown design links fail;
- unknown evidence links fail;
- mismatched extraction checksum fails;
- exact values remain exact;
- inference flags remain unchanged;
- composition is deterministic for the same inputs;
- existing output replacement follows the approved `--force` policy.

### Acceptance criteria

- `antenna_design.json` is produced without a model call.
- It contains complete result and variant inventories.
- It contains one selected construction or records why selection is incomplete.
- All references resolve.
- Re-running composition on the same inputs produces equivalent JSON.
- Tests pass.

### Out of scope

- Structural validation details.
- Preview rendering.
- Repair.
- CST adapter.

## 12.3 Commit 8

Proposed commit message:

```text
feat(validation): add evidence and structural readiness gates
```

### Validator categories

#### Schema and identity

- final Pydantic/JSON Schema validation;
- unique IDs;
- valid cross-references;
- extraction and compilation identity consistency.

#### Values, expressions, and units

- every construction expression resolves;
- no unknown symbol;
- no dependency cycle;
- compatible units;
- no silent explicit-value mutation;
- derived value matches its expression within an explicit tolerance;
- engineering inference contains justification, confidence, and confirmation.

#### Block and relationship integrity

- every block conforms to one supported primitive schema or is explicitly
  unresolved;
- fields required by the declared primitive type are present;
- placement contains the references required by the schema;
- referenced materials, parameters, blocks, and operation results exist;
- operation dependencies are acyclic;
- boolean target, tool, and result IDs are coherent;
- a block requiring material has a known material reference;
- polygons meet basic schema constraints such as minimum point count;
- operation outputs do not silently overwrite unrelated block IDs.

These are contract checks, not antenna-design rules. Deterministic validators
must not decide:

- which blocks a patch, PIFA, helix, array, implantable antenna, or any other
  antenna family should contain;
- whether a shape seen in a figure ought to be a subtraction or an addition;
- whether Gemma4 selected the scientifically correct topology;
- how missing geometry should be repaired;
- which CST operation sequence should implement the description.

Those semantic decisions belong to Gemma4 and to benchmark or manual review.
The deterministic boundary only verifies that the declared block description
is internally coherent and honest about unresolved information.

#### Ports and simulation

- port block or geometric references exist;
- placement and orientation are sufficient for the declared port type;
- reported impedance is preserved;
- frequency range endpoints and units are valid;
- missing reconstruction-critical setup is reported.

#### Evidence

- every explicit fact has semantically compatible evidence;
- visual-origin dimensions reference visual evidence;
- table-origin dimensions reference table evidence;
- derivations reference their source values;
- selection rationale references evidence;
- every geometry-relevant symbol reported by the compiler as mapped or
  unresolved has a valid evidence reference.

Semantic compatibility should begin with explicit origin/source rules, not a
new general-purpose natural-language inference system. Whether Gemma4 missed a
symbol in the source figure is a benchmark or manual-review question; Python
cannot discover that omission without reinterpreting the document.

#### Results and variants

- every extraction result appears in the final output;
- every result links to a known design;
- variant results remain attached to their variant;
- measured and simulated observations remain separate;
- metric, value, unit, source, and evidence are present when reported.

### Reconstruction-readiness states

The final state should be computed from declared missing information,
inferences, and structural validation. It describes whether the JSON is safe to
hand to a future construction agent. It is not a claim that the antenna will
simulate correctly.

#### `complete`

- all blocking structural validators pass;
- no reconstruction-critical information is missing;
- no engineering inference is required;
- primary design is unambiguous.

#### `complete_with_inferences`

- all blocking structural validators pass;
- the block description is structurally consumable;
- one or more engineering inferences are present and require confirmation;
- no unresolved item prevents a build.

#### `incomplete`

- schema and references are valid enough to inspect;
- one or more declared missing or ambiguous items prevent reliable
  reconstruction;
- the pipeline identifies those items precisely.

#### `invalid`

- schema, reference integrity, expressions, units, or block dependencies are
  internally inconsistent;
- the output must not be sent to a CST agent.

Blocking versus warning rules must be encoded explicitly and tested.

### Preview generation

A preview must be derived from the same block-oriented ACIR used by future
reconstruction. It
must not be generated independently from the paper image.

The first implementation should favour a minimal deterministic preview:

- top-view SVG for planar geometry;
- layer or material colour legend;
- block IDs optionally available for debugging;
- representation of additions and subtractions;
- a simple three-dimensional preview only if it can be produced without a
  disproportionate dependency or geometry engine.

If robust 3D preview requires materially more work, the Phase 4 chat should
split it into a separate approved change rather than hiding the complexity.
However, a visual geometry comparison must exist before declaring the full v2
baseline complete.

The comparison may initially be a documented manual benchmark review:

- source final-geometry figure;
- generated preview;
- reviewer decision;
- noted mismatch;
- affected block or parameter IDs.

A later model-assisted visual comparison should be added only after deterministic
validation and manual review expose a concrete need.

### Validation report

The report should contain:

- overall reconstruction-readiness state;
- blocking errors;
- warnings;
- check IDs and human-readable messages;
- affected block, parameter, result, or evidence IDs;
- counts by category;
- preview paths;
- validation timestamp and schema version.

Avoid building a generic validation plugin framework. Plain validator functions
returning a small common issue model are sufficient.

### Tests

Cover at least:

- a complete explicit design;
- a complete design with one engineering inference;
- an incomplete design;
- a cyclic or invalid block dependency;
- unresolved parameter expression;
- unit mismatch;
- polygon self-intersection;
- subtraction from an unknown block;
- unresolved symbol with a valid evidence link;
- lost result;
- result attached to unknown variant;
- measured/simulated coexistence;
- preview generation from a simple patch;
- deterministic state calculation;
- validation report persistence and manifest update.

Each reference-paper fixture should exercise its specific benchmark gates.

### Acceptance criteria

- The state is determined by code.
- Invalid or incomplete outputs cannot be mistaken for safe build inputs.
- Every required benchmark assertion is represented by an objective validator
  or a documented scientific or visual review.
- Preview comes from ACIR.
- Paper 005 failures identify exact missing or inconsistent elements.
- Validation does not call a model.
- Tests pass.

### Out of scope

- Automatic correction.
- Full electromagnetic simulation.
- Geometric tolerance optimisation.
- Universal CAD rendering.
- Visual similarity scoring unless separately justified.

## 12.4 Commit 9

Proposed commit message:

```text
feat(orchestration): add sequential v2 pipeline runner
```

### End-to-end command

Target user experience:

```text
uv run antenna-ingest run <paper.pdf>
```

Optional arguments should remain limited to demonstrated needs, likely:

- runs root;
- paper ID;
- pipeline version;
- render DPI;
- force or resume behaviour;
- repair enablement only if repair is implemented.

### Sequential execution

The runner executes:

1. create the run;
2. render pages;
3. extract the document with NuExtract3;
4. compile geometry with Gemma4;
5. compose the final document;
6. validate and generate previews;
7. stop with the final state;
8. optionally perform one directed repair and repeat steps 5-6.

There must be no task pool, asynchronous fan-out, concurrent page request, or
parallel model call.

### Failure behaviour

- Stop at the first failed required phase.
- Preserve all completed artefacts.
- Leave later phases pending or skipped according to one consistent policy.
- Return a non-zero CLI status for failed or invalid runs.
- Decide explicitly whether `incomplete` returns zero with a reported status or
  non-zero; document the choice.
- Print the run directory and decisive report path.
- Do not automatically retry transient failures unless that behaviour is later
  approved.

### Resume and force

The simplest correct policy is preferred:

- a new source PDF creates a new run;
- individual phase commands can be rerun with `--force`;
- end-to-end resume should be added only if repeated remote calls make it
  concretely valuable and phase fingerprints make reuse safe.

Do not implement a complex workflow engine.

### Optional repair

Repair should be implemented only if benchmark evidence shows that one directed
retry fixes common schema or construction errors at acceptable cost.

If implemented:

- disabled by default;
- maximum one attempt initially;
- runs only after deterministic validation;
- receives the invalid geometry compilation;
- receives concrete validator issues;
- receives only relevant extraction evidence and pages;
- writes a separate repair request, raw response, and report;
- never changes explicit source values;
- re-runs composition and validation;
- preserves both original and repaired compilations.

Do not add repair merely to make failing tests pass.

### Tests

- phases run in exact order;
- no later phase runs after failure;
- each successful phase updates the manifest;
- complete run writes the final output and report;
- incomplete and invalid outcomes map to documented CLI statuses;
- exceptions create structured failure artefacts;
- injected clients make end-to-end tests network-free;
- `parallelism` cannot silently exceed one;
- optional repair is not called by default;
- one repair attempt is enforced if enabled;
- command output identifies the run and final status.

### Benchmark run

Execute the end-to-end pipeline on all five papers and record:

- model call count;
- page count;
- selected geometry pages;
- latency per model call and phase;
- final status;
- benchmark assertions passed and failed;
- inference count;
- missing-information count;
- preview review outcome.

The normal target is two model calls per paper. Any extra call must have a
recorded reason.

### Acceptance criteria

- One command runs the complete v2 pipeline sequentially.
- Normal papers use one NuExtract3 and one Gemma4 call.
- All artefacts and failures are inspectable.
- All five papers reach the scientifically correct status.
- A `complete` or `complete_with_inferences` output satisfies every blocking
  validator.
- Paper 005 no longer ends in an unexplained running or failed state.
- Tests pass.

### Out of scope

- Scheduling several papers.
- Parallel execution.
- Web UI.
- Job queues.
- Database-backed run tracking.
- Automatic remote retries.
- CST execution.

## 12.5 Phase 4 completion gate

Phase 4 is complete when:

- the final output is lossless relative to extraction;
- structural validation is deterministic and contains no antenna-family
  construction rules;
- reconstruction-readiness states are tested;
- a preview derived from ACIR supports geometry review;
- all five benchmark papers have reviewed end-to-end results;
- model call counts and latency are known;
- the end-to-end CLI is simple and sequential.

Do not cut over from v1 until these conditions are met.

---

# Phase 5: Cutover and legacy cleanup

## 13. Phase 5 objective

Make v2 the only supported critical path after it passes the benchmark, then
remove or archive legacy components that no longer serve a concrete purpose.

Cleanup is last because deleting v1 earlier would remove the easiest comparison
point and increase migration risk.

## 13.1 Questions for the Phase 5 chat

1. Has every v2 benchmark expectation passed or been consciously revised?
2. Is any v1 module still used by v2?
3. Is lexical retrieval needed for any observed document, or only hypothetical?
4. Should old commands be removed immediately or retained for one deprecated
   version?
5. Which old tests still protect reusable infrastructure?
6. Do stored v1 runs need read compatibility?
7. Is package version `0.2.0` appropriate for the cutover?
8. What exact example output can be committed without copyright or repository
   size concerns?

## 13.2 Commit 10

Proposed commit message:

```text
refactor(legacy): retire v1 critical path and finalize documentation
```

### Intended changes

- Make `antenna-ingest run` the documented primary command.
- Remove legacy commands from the main CLI or mark them clearly unsupported
  according to the approved migration decision.
- Remove code that is both unused and replaced:
  - Markdown conversion;
  - deterministic evidence block parsing;
  - deterministic HTML table extraction;
  - lexical evidence indexing and search;
  - canonicalization tool adapter;
  - canonicalization agent tool loop;
  - v1 prompts and schemas.
- Preserve reusable low-level code and tests.
- Update:
  - `README.md`;
  - architecture documents;
  - model assignment;
  - schema documentation;
  - testing strategy;
  - example configuration.
- Add a small representative `antenna_design.json` example.
- Document how to add a paper and reviewed expectations to the benchmark.
- Update package version to `0.2.0` if approved.
- Record the final baseline tag recommendation, for example
  `pipeline-v2-baseline`, without creating it automatically.

### Cleanup rules

- Use import searches and tests before deleting a module.
- Do not delete v1 benchmark metadata.
- Do not preserve dead compatibility code without a consumer.
- Do not refactor unrelated infrastructure during cleanup.
- Do not rename working v2 modules solely for aesthetic consistency.
- Keep the diff reviewable.

### Tests

- no remaining imports of removed modules;
- CLI help lists only supported commands;
- documentation commands parse;
- example output validates;
- benchmark specification remains valid;
- all unit and integration tests pass;
- an opt-in end-to-end run still succeeds.

### Acceptance criteria

- v2 is the documented and executable default.
- No legacy module remains on the critical path.
- Removed code has no live imports.
- The repository documentation reflects actual behaviour.
- A new developer can run one reference paper and interpret the output.
- Tests pass.

### Out of scope

- Future CST agent.
- General multi-paper retrieval.
- Optimisation agents.
- Production deployment.
- User interface.

## 13.3 Phase 5 completion gate

The refactor is complete when the repository contains one clear pipeline,
documents one clear contract, and produces one validated solver-neutral output
without relying on legacy extraction or canonicalization behaviour.

---

## 14. Testing strategy across all phases

Tests should remain proportional to the change being implemented.

### 14.1 Unit tests

Use unit tests for:

- Pydantic schema constraints;
- reference integrity;
- expression and unit evaluation;
- manifest transitions;
- artefact paths and checksums;
- request construction with fake clients;
- response parsing;
- deterministic final composition;
- validators;
- CLI parsing and status mapping.

Unit tests must not depend on the remote endpoint.

### 14.2 Integration tests

Use integration tests for:

- PDF-to-page rendering;
- phase-to-phase artefact handoff;
- fake-client extraction and compilation;
- complete sequential orchestration;
- failure preservation;
- preview generation.

Use the existing fixture PDFs only when the test genuinely requires a PDF.
Prefer compact synthetic JSON fixtures for schema and validator tests.

### 14.3 Remote capability tests

Remote tests are opt-in and used for:

- endpoint capability probes;
- real structured output;
- maximum image count;
- context and timeout behaviour;
- representative full-document calls;
- latency measurement.

They should not run under the default `pytest` command.

### 14.4 Scientific benchmark tests

Benchmark checks validate content rather than implementation details:

- exact values and symbols;
- topology;
- design selection;
- variant/result association;
- evidence;
- derivation and inference treatment;
- preview agreement.

Model output ordering and prose wording should not be asserted.

### 14.5 Test execution order for each implementation change

1. Run the directly affected test file.
2. Run the relevant unit or integration subset.
3. Run the complete local suite.
4. Run remote or benchmark checks only when the change requires them.

The current baseline command is:

```text
uv run pytest -q
```

---

## 15. Observability requirements

The existing failure and manifest infrastructure should be extended rather than
replaced.

For every model call, preserve:

- phase and attempt;
- invocation ID;
- request payload hash;
- model role and model name;
- effective model parameters;
- page/image references;
- input artefact checksums;
- start time and end time;
- latency;
- raw response;
- finish reason when available;
- token usage when available;
- parsing outcome;
- schema validation outcome;
- failure record and stack-relevant exception information.

Writes should be incremental:

1. request metadata before the request where possible;
2. raw response immediately after receipt;
3. parsed structured artefact after validation;
4. final report and manifest state at phase completion.

Secrets must never be written. Existing failure-message redaction remains part
of the required foundation.

Observability should use JSON and text files in the run directory. A database,
telemetry server, or tracing platform is not required.

---

## 16. Migration policy

### During Phases 1-4

- Keep v1 modules and tests.
- Add v2 beside v1.
- Give v2 phases and artefacts distinct names.
- Do not make v2 schemas backward-compatible with
  `canonical_design_record_v1` merely to reduce diff size.
- Use output comparisons to find regressions.
- Document which CLI path is experimental.

### At Phase 5

- Confirm v2 benchmark completion.
- Search all live imports and commands.
- Remove only demonstrably unused v1 code.
- Keep historical benchmark metadata.
- Update documentation and version together.

Run-directory migration should remain simple. Existing v1 manifests may remain
readable if the current loader already supports them, but the project should not
build a general manifest-migration framework without a consumer.

---

## 17. Decisions deliberately deferred

The following are not required to start the refactor:

- exact CST version;
- CST Python API versus VBA/COM versus MCP command translation;
- optimisation-agent design;
- CST model validation;
- general graph curve digitisation;
- hybrid retrieval and embeddings;
- difficult-document escalation models;
- automatic repair;
- multi-paper or corpus processing;
- parallelism;
- web or desktop interface;
- production persistence.

These topics should be revisited only when the validated
`antenna_design.json` exists and a downstream consumer demonstrates a concrete
requirement.

---

## 18. Risks and controls

| Risk | Consequence | Control |
|---|---|---|
| NuExtract3 cannot accept all pages | More calls and possible cross-page loss | Probe real limit; add sequential size batching only if observed |
| Structured output is unreliable | Invalid JSON or hidden truncation | Persist raw response; strict parsing; inspect finish reason |
| Extraction schema becomes a CAD schema | Model prompt becomes confused and brittle | Keep observations separate from construction |
| ACIR becomes a universal framework | Slow implementation and hard maintenance | Support only benchmark-demonstrated block geometries and relationships |
| Deterministic code accumulates antenna recipes | Brittle rules fail on unfamiliar antennas | Keep topology and block selection in Gemma4; validate only declared contract integrity |
| Gemma4 invents missing dimensions | False exact reconstruction | Origin field, evidence checks, confirmation requirement |
| Primary design is selected incorrectly | Wrong antenna is reconstructed | Selection rationale, evidence, Paper 004 benchmark |
| Results disappear during compilation | Scientifically incomplete final JSON | Results bypass compiler and are checked by lossless composition |
| Measured and simulated data are treated as conflicts | Incorrect scientific interpretation | Explicit result source and variant association |
| Paper 005 fails without diagnostics | Regression remains opaque | Incremental traces and precise validation issues |
| Legacy code constrains v2 | New architecture inherits old limitations | Separate v2 contracts; remove legacy only after validation |
| Too many model calls | Unacceptable latency | Normal two-call budget; log and justify every extra call |
| Tests validate schemas but not science | Plausible but wrong output | Five-paper semantic benchmark and preview review |
| Preview diverges from build representation | False validation confidence | Generate preview from the same ACIR |
| Optional repair hides systemic errors | Cost and unpredictable behaviour | Disabled by default; one directed attempt only if justified |

---

## 19. Definition of done for the complete project

The current NewPipeline refactor is done when all of the following are true:

### Architecture

- The documented critical path is the implemented critical path.
- The normal pipeline is sequential.
- No deterministic content detector precedes NuExtract3.
- Extraction and construction responsibilities are separate.
- The output is solver-neutral.

### Functionality

- A user can provide one PDF to one CLI command.
- Every page is mechanically rendered.
- NuExtract3 produces a validated full-document extraction.
- Gemma4 produces a validated geometry compilation.
- Deterministic final composition produces `outputs/antenna_design.json`
  without interpreting geometry.
- Deterministic structural validation assigns the final status.
- A preview can be compared with the source geometry.

### Scientific integrity

- Explicit values are preserved.
- Evidence is traceable.
- Variants are retained.
- All reported results are retained.
- Simulated and measured results remain distinct.
- Derivations and engineering inferences are distinguishable.
- Missing information is explicit.
- The pipeline does not claim exactness unsupported by the paper.

### Benchmark

- All five reference papers have reviewed expectations.
- All automatic assertions pass or have a documented, approved reason not to.
- Manual preview checks are recorded.
- Paper 005 has an explainable final state.

### Reliability

- Every model call is traceable.
- Failures preserve raw evidence and do not leave phases running.
- Normal execution uses two model calls.
- Unit and integration tests pass.
- Remote tests are opt-in.

### Maintainability

- The code is direct and comprehensible.
- No unused v1 critical path remains.
- No speculative parallelism, caching, fallback, or generic framework exists.
- Documentation and CLI examples match actual behaviour.

The future CST agent may then consume only designs whose state is `complete` or
`complete_with_inferences`, with the latter requiring explicit confirmation of
the recorded inferences.

---

## 20. Recommended phase-chat briefs

These briefs are conversation starters, not local implementation prompts. Each
phase chat should inspect current results and discuss the change before
generating any prompt for Codex.

### Phase 1 chat

```text
We are defining the contracts and scientific benchmark for NewPipeline v2.
Review Phase 1 of docs/implementation_plan.md and the current placeholder
documentation and benchmark manifest. Before proposing code changes, help me
decide the minimum boundaries between document extraction, block-oriented
geometry compilation, and final composition, then review the five
paper-specific
expectations. Do not implement anything. After we agree on one coherent change,
prepare one local Codex prompt for that change only.
```

### Phase 2 chat

```text
We are replacing the Markdown/evidence/retrieval ingestion path with one
full-document NuExtract3 extraction. Review Phase 2 of
docs/implementation_plan.md, the approved schemas, and the current
raw_extraction implementation. First analyse what can be reused and what must
change. Keep the normal path to one model call and do not add batching unless an
observed endpoint limit requires it. Do not implement anything. After we agree
on the next minimal change, prepare one local Codex prompt.
```

### Phase 3 chat

```text
We are defining the block-oriented ACIR v1 and the targeted Gemma4 geometry
compiler. Review Phase 3 of docs/implementation_plan.md, the current extraction
outputs, and the five benchmark geometries. First determine the smallest
solver-neutral set of blocks, primitive geometries, placements, and
relationships actually required. The representation must centre on blocks, not
an ordered command history. Avoid a universal CAD framework and deterministic
antenna-family rules. Do not implement anything. After we agree on one schema
or compiler change, prepare one local Codex prompt for that change only.
```

### Phase 4 chat

```text
We are implementing lossless final composition, deterministic structural and
evidence-integrity validation, a block-derived preview, and the sequential
runner. Review Phase 4 of docs/implementation_plan.md and the real outputs
produced by Phases 2 and 3. Keep deterministic code limited to copying, linking,
schema/reference checks, and other objective invariants. Do not introduce
antenna-family construction recipes. First identify the smallest next change
and its acceptance evidence. Do not implement anything. After discussion and
approval, prepare one local Codex prompt only for that change.
```

### Phase 5 chat

```text
We are preparing the v2 cutover and legacy cleanup. Review Phase 5 of
docs/implementation_plan.md, the final benchmark results, live imports, CLI, and
documentation. First determine exactly which legacy code is unused and whether
any compatibility is still required. Do not implement anything. After we agree
on a bounded cleanup, prepare one local Codex prompt.
```

---

## 21. Local Codex handoff requirements

After a phase-chat decision is approved, the generated local prompt should:

- state one concrete objective;
- ask Codex to inspect only relevant code before editing;
- provide the approved behaviour and acceptance criteria;
- identify explicit exclusions;
- request the smallest correct implementation;
- avoid prescribing unnecessary abstractions or file names;
- request proportionate tests;
- prohibit unrelated refactoring;
- prohibit commits;
- require Codex to stop if the repository contradicts an important assumption
  or requires a material scope increase;
- request a final report containing changed files, tests, results, decisions,
  and limitations.

The local implementation report should then be reviewed against this plan and
the approved phase-chat decision. Passing tests alone does not establish
scientific correctness.
