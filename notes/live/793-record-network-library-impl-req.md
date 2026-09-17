# 793 — Record network library

## Impl.Abstract

Status: Designing → executing. Alignment.Mode: Autonomous.

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
- Grounding: capture context resolved current Model; View creation requested.

## Execution.Plan

- [ ] Checkpoint current product and complete cold reload.
- [ ] Record foundation: classification, entry PATH, source context, exact
  registered dispatch. Test malformed preferred entries and class authority.
- [ ] Typed references: explicit locator/check/hints, filesystem implementation,
  reported failures; test mismatches, unchanged hints behavior, and no repair.
- [ ] Workflow registration and navigation: Python/file entry points, typed
  providers, bounded browsing, library runtime. Test an external workflow and
  real Record collection, including provider failures.
- [ ] Adopt foundations in Archive and Diagram; migrate affected retained
  data explicitly with recoverable history. Preserve stable Artifact identity.
- [ ] Reconcile existing reference consumers with the new contract; run
  affected suites, full tests, Ruff, architectural checks, installed script smoke.
- [ ] Capture audit, Draft check/apply, completion report.

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
