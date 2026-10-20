# 938 — Named CheckSuite checkpoints

<!-- tarav.sessions
396354ec = codex:01a1563f-0d2c-77f1-8402-cdef13fb5025 @396354ecc7d3ed791eb669fa240045c4303adf3e1c5d55d7002f018a4502ac58
-->

## Impl.Abstract

Knowledge.Surface: wiki  
Alignment.Mode: Interactive  
Status: complete.

Let a CheckSuite record named checkpoints reached during its run. A checkpoint certifies that a particular dynamic Check producer finished scanning. When an earlier POI is absent, its Action may take its existing `gone` exit only when the relevant checkpoint was reached and the detector's Checks completed conclusively. Use this in md-library's paragraph alignment suite through [request 631](/Users/pereiro/projects/md-library-project/md-library-py/notes/live/631-alignment-checkpoint-impl-req.md). No generic redesign of Action exits or Check identity.
<!-- tarav.breadcrumb 2e55d97404c4 -->
<!-- tarav.breadcrumb 6e00d01ea782 -->

## Design narrative

A suite is the Integration.Object and authority for the Checks it discovers. A suite that reaches its end can still have skipped one dynamic producer. The observed failure is md-library: a Markdown floor violation suppresses alignment Checks, but an earlier alignment Action closes because an exhausted suite reports no matching POI. The correction is a checkpoint at the end of the alignment scan, absent on the gated path. Checkpoint reach is run-local, reset on rerun, and belongs to the suite that emits it. Associate each checkpoint with the Check types it certifies; persist that association with the POI Action event, so a later run that emits zero of that type can still test its checkpoint. A marker reached after failed or refused Checks is not conclusive; those Checks retain their existing failure semantics.
<!-- tarav.breadcrumb 639214076a72 -->
<!-- tarav.breadcrumb c543137cba89 -->

Declare a suite's checkpoint-to-Check-Type relation at construction and yield a named checkpoint marker in its production stream after the scan. This lets the current suite govern already-open Actions even if their saved event predates the checkpoint feature. A branch that returns before the marker does not reach it. The declaration also attaches the checkpoint to Checks produced before the marker, including partial scans. Preserve existing behavior for unrelated suites that make no checkpoint declaration; this is an explicit authority refinement for a producer, not a reader or data compatibility path. Checkpoint names are local to a suite. Reject duplicate certification of a Check type, rather than silently choosing one.

## Impl.Req.Wiki

Product Project: tarav-py. Wiki owner: tarav-md; captured `notes/wiki/checks-workflow.md` and `notes/wiki/daily/2026-10-20.md`. Source evidence is the above User Turns; behavior evidence is the focused CheckSuite and Action tests. New Breadcrumb labels resolve; older unrelated labels retain existing audit POIs.

## Execution.Plan

1. **Feature — suite run.** Add declaration, marker, reached-set and certified Check-type relation. Verify reset and local filtering/failure behavior. Status: verified.
2. **Integration — POI Action.** Record the checkpoint on events and use the current suite declaration for earlier events. Verify skipped dynamic producer stays open, completed producer closes, and suite scoping remains correct. Status: verified.
3. **Guidance and integration.** Update maintained architecture and md-library consumer. Capture inline evidence, Wiki, focused/full checks, and commits. Status: verified.

## Impl.Log

- Before implementation, inspected CheckSuite run/conclusion and POI Action event/scope code and reproduced the md-library floor-gated false closure in an isolated project.
- Start checkpoint `04dffc0`. A concurrent workflow's checkpoint `ca3cb1a` included the verified Tarav code, tests, architecture, compiled AGENTS source, and this note's design refinement alongside its separate Notebook work. No unrelated Notebook files were edited by this workflow.
- `SuiteCheckpoint(name)` is emitted after a declared scan; `CheckSuite.checkpoints` and `summary()["checkpoints"]` report names reached. Check-type certification is declared at suite construction. The Action's `gone` path requires the current detector's checkpoint and conclusive same-type results; a skipped path remains `not run`.
- Focused Checks/Actions tests: 49 passed. Architecture tests: 100 passed in the combined run. Full Tarav suite: 496 passed. Ruff passed. Real DeMonte read-only suite reached `reading-alignment.scan` and retained 159 alignment POIs across 416 results.
- Product and Wiki Breadcrumb labels submitted and audited; this pass's labels resolve. The broader audit still reports older unrelated unresolvable labels. `tarav skw document produce` found no producer for the ProjectSystemPrompt block; `compile` succeeded from its maintained JSON source.
