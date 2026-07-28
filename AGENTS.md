# AGENTS.md

## Project overview

This repository implements a sequential, VLM-first pipeline for extracting
evidence-grounded antenna designs from scientific PDF papers.

The final output must be a solver-neutral structured representation that can
later be consumed by a separate CST integration.

Read `docs/implementation_plan.md` before implementing any planned pipeline
phase or commit.

## Working principles

- Implement only the scope explicitly requested by the user.
- Work on one agreed implementation change at a time.
- Inspect the current repository state before editing.
- Do not assume that branch names, commit hashes, test counts, file paths, or
  implementation details recorded in planning documents are still current.
- Prefer the smallest direct change that satisfies the requested scope.
- Do not introduce speculative abstractions, frameworks, compatibility layers,
  fallbacks, caches, retries, or configuration systems.
- Do not refactor unrelated code.
- Do not implement future phases early.
- Ask for clarification when a missing decision would materially affect the
  implementation.

## Git safety

Before editing, inspect:

- the current branch;
- the working-tree status;
- the latest commit.

Preserve all existing user changes.

Do not use destructive Git commands such as:

- `git reset`;
- `git restore`;
- `git checkout --`;
- `git clean`.

Do not switch branches unless explicitly requested.

Do not create commits, amend commits, push branches, or open pull requests
unless explicitly requested.

If a file required by the task already contains unrelated user changes, stop
and report the conflict instead of overwriting them.

## Pipeline architecture

The intended normal path is:

1. Mechanically render all PDF pages in order.
2. Use NuExtract3 for full-document multimodal extraction.
3. Structurally validate the document extraction.
4. Build an auditable evidence packet deterministically from extracted
   references.
5. Use Gemma4 for design selection and solver-neutral geometric compilation.
6. Compose the final output without information loss.
7. Perform objective structural and evidence-integrity validation.
8. Generate a preview from the same canonical representation.

The normal single-paper path is sequential and uses:

- one NuExtract3 call;
- one Gemma4 call;
- `parallelism=1`.

Sequential batching is allowed only when required by a verified endpoint or
context limit. Batching must not perform semantic page selection.

## Responsibility boundaries

### Deterministic code may

- render pages;
- validate schemas;
- resolve references;
- collect, deduplicate, and order evidence pages;
- persist artefacts;
- compose outputs without semantic reinterpretation;
- check identifiers, units, expressions, dependencies, and evidence links.

### Deterministic code must not

- classify antenna families;
- decide which geometric blocks describe an antenna;
- contain construction recipes for patches, PIFAs, monopoles, arrays, or other
  antenna families;
- infer missing geometry;
- turn engineering assumptions into extracted facts;
- claim scientific or electromagnetic correctness from structural validity.

### NuExtract3

NuExtract3 extracts what the paper contains and reports. It must not produce
CST commands or silently invent missing information.

### Gemma4

Gemma4 selects the relevant design and compiles its evidence into a
block-oriented, solver-neutral geometric representation. It must not emit CST
commands or discard variants, results, conflicts, or unresolved information.

## Scientific integrity

- Preserve exact reported values, symbols, units, and evidence.
- Keep simulated, measured, and analytical results distinct.
- Preserve design variants and their result associations.
- Record reproducible derivations explicitly.
- Keep source-grounded construction separate from proposed engineering
  completions.
- Never apply proposed completions automatically.
- Represent missing and ambiguous information explicitly.
- Do not claim exact reconstruction when the paper lacks sufficient evidence.
- Keep structural validity, reconstruction readiness, and scientific review as
  separate concepts.

## Scope boundaries

Unless explicitly requested:

- do not add RAG, embeddings, or vector retrieval to the single-paper path;
- do not add parallel processing;
- do not add model repair calls;
- do not implement CST-specific commands in the canonical representation;
- do not remove the v1 pipeline before the agreed cutover;
- do not add dependencies;
- do not add runtime configuration loaders solely for example files.

## Code and tests

- Follow the existing repository structure and coding style.
- Use Python 3.12 or newer.
- Keep unit tests independent of remote model endpoints.
- Remote capability tests must remain opt-in.
- Add or update tests only when required by the implemented behaviour.
- Do not weaken tests merely to make them pass.
- Run directly affected tests first, followed by the complete local suite.

The current default local test command is:

```text
uv run pytest -q