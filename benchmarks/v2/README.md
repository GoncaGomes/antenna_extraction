# V2 Evidence-Grounded Acceptance Suite

This directory defines the declarative acceptance evidence for the v2 pipeline.
It validates benchmark structure and provenance; valid JSON does not prove
scientific fidelity.

The `regression` group contains five historical papers that expose known loss
modes. `geometry_coverage` adds three papers with helix, horn, and conformal
geometries. `synthetic_coverage.json` links every required Commit 4 geometry
category to an existing contract test instead of copying ideal outputs. Eight
papers do not establish universal generalisation, and the patch-heavy
regression set alone must not determine a default model.

Each expectation distinguishes automatic checks from manual scientific review.
Automatic assertions require a machine-verifiable condition. Manual assertions
require source evidence and an explicit review instruction. A failed critical,
blocking assertion remains visible; there is no aggregate score. Reviewers must
record identity, role, version, status, and a date when confirming a human
review. Disagreement, illegibility, and inability to conclude are recorded as
source issues. Codex-prepared expectations remain `needs_review` until Gonçalo
Gomes or another identified scientific reviewer confirms them.

Scientific review consists of checking every cited one-based page and source
label against the PDF, recording disagreements or illegibility, completing each
manual instruction, and changing the status to `reviewed` only with the human
reviewer's identity, role, ISO date, and confirmation. Any inability to decide a
critical topology or placement remains explicit and reconstruction-blocking.

PDFs may be stored only when redistribution is licensed. For an article that
cannot be redistributed, acquire it from the recorded publisher URL, keep it
locally at the manifest path, and do not add the PDF to version control. Verify
a file with `Get-FileHash <path> -Algorithm SHA256` and compare the lowercase
digest and page count with `papers.json`.

To add a paper, assign a stable ID, verify title and DOI from the source, record
acquisition and licence evidence, calculate its checksum and page count, add one
strict expectation file, and extend `papers.json`. Cite real one-based pages and
figure, table, or equation labels. Do not use historical runs as ground truth or
handwrite complete ideal outputs.

Run structural validation with:

```powershell
uv run pytest tests/benchmark -q
```

Normal pytest execution performs no network or remote-model calls. Model runs
and scientific output evaluation belong to later commits and must remain
explicit, opt-in activities.

Before any geometry-independent claim, the real-paper set must be expanded with
licence-verified, human-reviewed examples for multilayer/via or shorted designs,
arrays, dielectric resonators, and any other geometry family represented only
synthetically. These additions require their own source-grounded expectations;
the current synthetic links are contract coverage, not scientific substitutes.
