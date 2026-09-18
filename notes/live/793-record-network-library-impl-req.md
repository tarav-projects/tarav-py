# 793 — Record network library

## Impl.Abstract

Status: Complete, with capture POIs recorded below. Alignment.Mode: Autonomous.

Reimplement the shared Record-network contracts as a Python library: FileRecord
and DirectoryRecord loading, typed locator/check/hints references, Workflow
registration, provider navigation, and Archive participation. Consumers use
the library directly; no explicit action graph is required. Existing native
agent and domain workflows remain consumers. No legacy adapters or runtime
schema repair. Code and affected retained data migrate together.

Source: current session `01a0af61-72e2-7bd2-94a3-26529d6914ec` and
`../..` sibling tarav-md Wiki Record framework/reference/Archive notes.
The inspected bases are harness/types.py, archive/__init__.py,
wayfinder/{model,resolver,registry}.py, poi/runtime.py, runtime.py, and Diagram's
registered interpreters. Existing uncommitted 791 work is the starting state.

## Impl.Req.Diagram

- Namespace: `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Collection: `7cd0633b-edf9-4bc1-b95f-b145cc309245` (`793.Impl.Req`)
- Draft: `ffb803f9-d018-44b4-8ef5-274960b0bef4`
- Draft path: `/Users/pereiro/Documents/tarav/diagram/drafts/ffb803f9-d018-44b4-8ef5-274960b0bef4.json`
- Authorization Gate: `a880a375-d1f2-4245-9e09-7ef460944cf5`
- Grounding: View `3f54d0ca-8506-4978-a9b8-d51260310226`, retained at
  commit `6a3b6346826d67762aa261b2eea0437f51fbe678`; inspected existing Record,
  Record/Artifact, resolution, identity, context and recoverability Blocks.

## Execution.Plan

- [x] Checkpoint current product and complete cold reload.
- [x] Record foundation: classification, entry PATH, source context, exact
  registered dispatch. Test malformed preferred entries and class authority.
- [x] Typed references: explicit locator/check/hints, filesystem implementation,
  reported failures; test mismatches, unchanged hints behavior, and no repair.
- [x] Workflow registration and navigation: Python/file entry points, typed
  providers, bounded browsing, library runtime. Test an external workflow and
  real Record collection, including provider failures.
- [x] Adopt foundations in Archive and Diagram; migrate affected retained
  data explicitly with recoverable history. Preserve stable Artifact identity.
- [x] Reconcile existing reference consumers with the new contract; run
  affected suites, full tests, Ruff, architectural checks, installed script smoke.
- [x] Capture audit, Draft check/apply, completion report.

Risks: authoritative data cannot be silently retargeted; migration must preserve
identity, payload and Git evidence. Unknown Records remain errors/POIs rather
than guessed types. External Python registration is explicit trusted code, not
code selected from untrusted Record payloads. No semantic Model repartitioning
is inferred from the framework migration. Domain-specific unrelated features
are outside this reimplementation.

## Impl.Log

- This is a library implementation, not a new workflow execution engine.
- Use existing shared check runner; keep domain assertions owned by domains.
- Directory entry PATH initially uses `__tarav.json`, `main.json`, `type.json`.
  First present wins, including invalid entries; no fallback repair.
- Registration must be usable explicitly from scripts before convenience
  configuration expands. Source paths provide primary code discoverability.
- Product.Surface production-context annotation is unavailable in the current
  capture primitive; exact changed paths and Git diff remain recovery evidence.
- Product checkpoint: `9ad2e03`. Implementation changes after it remain
  uncommitted; no legacy serialization adapters were added.
- Directory entry PATH also admits `archive.json` and `registration.json`
  after the three general names. These are Archive's current concrete entry
  conventions, with the same first-present/error behavior.
- Built-in Workflow registration now composes Archive, Diagram and Navigation;
  external Python registration uses a trial registry so failed registration
  does not leave partially registered classes or workflows. Explicit provider
  configuration mounts local roots; there is no implicit whole-disk scan.
- Archive and Wayfinder references use locator/check/hints. Archive locators
  require a complete DOI; name and prefix selectors remain operation inputs,
  never stable references. Hints do not supply fallback resolution.
- Migrated `/Users/pereiro/Documents/tarav/archive/records/archive.json` from
  schema 1 to 2 with explicit tooling. Previous bytes remain at checkpoint
  `8931ddd9755ea25571d233d9f02cd9011ce51411`. That default corpus contained only
  the Archive definition, so no retained Artifact IDs needed rewriting.
  The data migration is uncommitted. Tests cover a populated previous-schema
  Archive, JSONL observations, DOI/payload preservation and dirty-tree refusal.
- Inspected maintained local Diagram/Scoring and `~/.tarav` retained JSON/JSONL
  for the old Wayfinder reference schema; no retained instances were found.
  Existing Diagram Record serialization already follows registered dispatch.
- Verified full suite: **1,363 passed**. Ruff and architecture checks pass.
  Reinstalled the editable tool and used `tarav python run --file` to mount
  the live Archive and Diagram and load a typed Model with its Namespace binding.
  Follow-up Archive/Harness checks cover structural Type authority.
- Product paths: `src/tarav/harness/{types,records,references,workflows}.py`,
  `src/tarav/navigation/__init__.py`, `src/tarav/runtime.py`,
  `src/tarav/archive/{__init__,records,references,workflow}.py`,
  `src/tarav/diagram/{__init__,workflow}.py`,
  `src/tarav/wayfinder/{model,resolver}.py`, corresponding tests,
  `tooling/migrate_793_archive_records.py`, `ARCHITECTURE.md`, and `AGENTS.md`.
- Capture audit retains eleven supported implementation constraints in the
  existing semantic Blocks, hosted by this one Impl.Req Collection. No
  fabricated Verbatim review or Assertion score was introduced.
- Current capture POIs: unscored semantic records, mechanically unassessable
  Chatlas-to-Archive grounding, and Model projection findings for missing
  legacy Block/Line types, closed-collection writes and staleness. The missing
  Product.Surface Production.Context primitive remains a separate follow-up.
- Scope boundary: this establishes and adopts the shared library contracts.
  Additional domain workflows/providers and custom DOI contract/check types
  can register through those contracts; no universal action executor, schema
  adapter engine, Model repartitioning or automatic migration was introduced.
- Final Draft applied once; receipt is retained in the Draft above. Diagram
  commit: `904197e3944ccfd5f2ea72a35ecd94c5eace4e1f`. It created twelve Ships
  (Collection plus eleven Lines), thirteen editions (including Open/Closed
  Collection editions), and the authorization Gate. Exact identities are in
  the retained receipt; the Collection re-renders as **Closed**.
- Capture receipt POI counts: 11 `archive-grounding-unassessable`,
  14 `semantic-record-unasserted`, 24 `block-type-missing`,
  205 `line-type-missing`, 72 `model-staleness`, and
  42 `impl-req-closed-write` in the checked Model overlay. After landing,
  the Collection renderer flags its eleven hosted editions as
  `impl-req-closed-write`; that closure/order finding remains visible for
  follow-up. It was not suppressed or marked as passed.
- Final Model re-render recomputed standing: 1 `block-has-no-lines`,
  24 `block-type-missing`, 53 `impl-req-closed-write`,
  205 `line-type-missing`, 76 `line-unreviewed`, 72 `model-staleness`,
  6 `verbatim-gate-approval-unresolved`, and
  6 `verbatim-gate-proposal-unresolved`. These aggregate Model findings include
  earlier material; this automatic capture makes no claim of wording review.
