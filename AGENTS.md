# AGENTS.md

## Scope

These instructions apply to the entire repository.

The target branch for the NewPipeline work is:

```text
feat/antenna-pipeline-v2
```

Do not assume that the active branch, local HEAD, remote HEAD, working tree, or
test baseline still matches a previous report. Verify them at the start of each
task.

## Sources of truth

Use the following authority order:

1. The repository is authoritative for behaviour that is currently
   implemented.
2. `docs/implementation_plan.md` is authoritative for the intended
   architecture, roadmap, commit boundaries, acceptance criteria, and deferred
   work.
3. The current user-approved task or commit decisions refine the work within
   that plan.

Read `docs/implementation_plan.md` in full before making changes for any
planned NewPipeline commit.

Do not treat planned files, commands, outputs, schemas, or model behaviour as
already implemented. Documentation must distinguish clearly between the current
state and the planned state.

If the repository, plan, and task disagree materially, stop and report the
contradiction. Do not silently choose one interpretation or implement around
the conflict.

Do not create another implementation plan or duplicate the executable
contracts in documentation. Pydantic models and their generated JSON Schemas
are the executable contract source of truth once implemented.

## Fixed architectural constraints

The initial target is a small, sequential, VLM-first, single-paper pipeline:

```text
PDF
-> ordered page rendering
-> NuExtract3 full-document extraction
-> paper_extraction.json
-> deterministic antenna_results.json publication
-> one selected multimodal architecture author
-> antenna_architecture.json
-> objective structural validation
```

The normal path has exactly two synchronous, sequential model calls:

1. NuExtract3 produces the internal `paper_extraction.json`.
2. One benchmark-selected architecture author produces
   `antenna_architecture.json`.

`antenna_results.json` is a deterministic, lossless projection of the validated
extraction and requires no model call.

The only consumer-facing outputs are:

```text
outputs/antenna_results.json
outputs/antenna_architecture.json
```

Unless the implementation plan is deliberately revised and approved, do not
introduce:

- RAG, embeddings, semantic or lexical retrieval, reranking, or vector stores;
- parallel processing, asynchronous model execution, or subagents;
- retries, fallback models, ensembles, reviewer calls, repair calls, or agent
  tool loops;
- deterministic semantic geometry assembly or antenna-family recipes;
- unsupported default dimensions, materials, solver settings, or engineering
  assumptions;
- CST integration, solver commands, simulation, optimisation, or construction
  planning;
- graph digitisation, caching, multi-paper orchestration, a web interface, or a
  general workflow framework.

Python may perform objective operations such as rendering, copying, linking,
reference resolution, checksums, persistence, projection, schema validation,
safe expression validation, and structural integrity checks. It must not make
scientific or geometric decisions assigned to a model or expert review.

Unsupported engineering proposals must remain explicit, unapplied, and
reconstruction-blocking. Structural validity, reconstruction completeness, and
scientific review are separate states.

## Work unit and scope control

Implement one planned commit at a time.

Before editing:

1. Read this file and the complete implementation plan.
2. Run read-only Git checks for the branch, HEAD, remote relationship, and
   working tree.
3. Confirm which earlier planned commits are actually present.
4. Inspect the relevant files, imports, consumers, tests, and documentation.
5. State the current behaviour, the smallest coherent change, material
   contradictions or open decisions, and the evidence required for acceptance.

Keep every change inside the current commit's required scope and completion
gate. Do not implement later commits early, even if doing so appears convenient.
Do not combine planned commits into one implementation.

Prefer the smallest coherent implementation. Avoid unrelated refactors,
speculative abstractions, generic frameworks, compatibility wrappers without a
current consumer, empty future packages, and manually duplicated schemas.

Do not spawn subagents or delegate work. Keep inspection, implementation, and
verification in one traceable line of work.

Do not create commits, push branches, open pull requests, or modify remote
resources unless the user explicitly asks. The normal handoff is an uncommitted,
tested diff for user review.

## Repository safety

Preserve all user changes and unrelated work.

If the working tree contains changes, determine whether they overlap the task.
Stop when overlap makes the requested edit unsafe. Never use `git reset`,
`git restore`, `git checkout --`, `git clean`, or another destructive command
to manufacture a clean tree.

Before deleting or moving code:

- verify the exact targets;
- search for live imports and consumers;
- confirm that the retained behaviour has another owner;
- respect the historical-branch checks required by the implementation plan;
- remove obsolete tests only with the behaviour they exclusively protect.

Do not preserve legacy code merely to retain the previous test count. Do not
remove the five scientific PDF regression inputs during cleanup.

Do not expose credentials, API keys, complete base64 image payloads, or other
secrets in traces, reports, fixtures, or documentation.

## Implementation rules

Follow the existing project configuration and established style. Inspect
`pyproject.toml` and the current package structure before choosing commands,
dependencies, or module locations.

Project-wide requirements include:

- strict boundary validation and rejection of unknown fields unless explicitly
  designed otherwise;
- stable IDs and explicit, validated cross-references;
- preservation of exact source values and units separately from any optional
  normalised representation;
- deterministic ordering where output order is not semantic;
- atomic JSON writes for completed structured artefacts;
- immediate persistence of raw model responses before strict parsing;
- inspectable, redacted failure records;
- dependency injection for model clients in tests;
- globally one-based source page references;
- no Python `eval`; use a deliberately bounded safe expression grammar;
- no antenna-family-specific schema classes or validation recipes.

An incomplete but honest output is preferable to a plausible invented one.
Never turn a schema-valid result into a claim of scientific correctness.

## Testing and verification

Run verification in this order:

1. directly affected tests;
2. the relevant unit or integration subset;
3. the complete retained local test suite;
4. lint;
5. package build, import, CLI, rendering, remote checks, or scientific
   benchmark only when required by the current commit.

Use the commands declared by the repository. Do not contact remote model
endpoints from default tests. Remote checks are opt-in, must be relevant to the
current model-facing commit, and must record the endpoint, exact model, prompt
hash, schema hash, settings, and date.

Passing tests and valid JSON are necessary but not sufficient when the plan
requires a completion gate, benchmark assertion, artefact inspection, or expert
review.

Do not weaken, delete, or rewrite an acceptance test merely to make an incorrect
implementation pass.

## Documentation rules

Keep one implementation-plan location:

```text
docs/implementation_plan.md
```

Keep the README, architecture description, implementation plan, schemas, and
actual behaviour consistent. Future artefact names and commands must be marked
as planned until their implementation commit is accepted.

Do not reintroduce `antenna_design.json`, `geometry_compilation.json`, the
legacy Markdown/retrieval/canonicalization path, or the 20-phase orchestration
as target architecture.

Use concise English for code, schemas, comments, and technical documentation
unless an existing file clearly follows another convention. User-facing
discussion and handoffs may be in Portuguese from Portugal.

## Stop conditions

Stop before editing or continuing when:

- the active branch or task target is ambiguous;
- overlapping user changes make the work unsafe;
- a material plan/repository contradiction is unresolved;
- a required earlier commit is absent or only partially implemented;
- the requested work needs a material decision that the user has not approved;
- a supposedly obsolete module has an active consumer not covered by the plan;
- the change requires work from a later commit or a deferred capability;
- a remote capability, credential, or model behaviour is being assumed rather
  than verified;
- the current commit's completion gate cannot be satisfied without unrelated
  scope expansion.

Report the evidence, impact, and smallest available options. Do not hide a stop
condition with a workaround.

## Required final report

After implementation, report:

- branch and inspected HEAD;
- concise summary of the implemented behaviour;
- files added, changed, moved, or removed;
- tests and lint commands with results;
- remote checks or benchmark cases, if any;
- generated or inspected artefacts;
- completion-gate results, item by item;
- unresolved decisions, known limitations, and deferred work;
- confirmation that no commit or push was performed.

Do not declare the planned commit complete unless every applicable completion
gate in `docs/implementation_plan.md` has been checked explicitly.
