# 938 — Named CheckSuite checkpoints

<!-- tarav.sessions
396354ec = codex:01a1563f-0d2c-77f1-8402-cdef13fb5025 @396354ecc7d3ed791eb669fa240045c4303adf3e1c5d55d7002f018a4502ac58
-->

## Impl.Abstract

Knowledge.Surface: wiki  
Alignment.Mode: Interactive  
Status: executing.

Let a CheckSuite record named checkpoints reached during its run. A checkpoint certifies that a particular dynamic Check producer finished scanning. When an earlier POI is absent, its Action may take its existing `gone` exit only when the relevant checkpoint was reached and the detector's Checks completed conclusively. Use this in md-library's paragraph alignment suite through [request 631](/Users/pereiro/projects/md-library-project/md-library-py/notes/live/631-alignment-checkpoint-impl-req.md). No generic redesign of Action exits or Check identity.
<!-- tarav.breadcrumb 2e55d97404c4 -->
<!-- tarav.breadcrumb 6e00d01ea782 -->

## Design narrative

A suite is the Integration.Object and authority for the Checks it discovers. A suite that reaches its end can still have skipped one dynamic producer. The observed failure is md-library: a Markdown floor violation suppresses alignment Checks, but an earlier alignment Action closes because an exhausted suite reports no matching POI. The correction is a checkpoint at the end of the alignment scan, absent on the gated path. Checkpoint reach is run-local, reset on rerun, and belongs to the suite that emits it. Associate each checkpoint with the Check types it certifies; persist that association with the POI Action event, so a later run that emits zero of that type can still test its checkpoint. A marker reached after failed or refused Checks is not conclusive; those Checks retain their existing failure semantics.
<!-- tarav.breadcrumb 639214076a72 -->
<!-- tarav.breadcrumb c543137cba89 -->

Declare a suite's checkpoint-to-Check-Type relation at construction and yield a named checkpoint marker in its production stream after the scan. This lets the current suite govern already-open Actions even if their saved event predates the checkpoint feature. A branch that returns before the marker does not reach it. The declaration also attaches the checkpoint to Checks produced before the marker, including partial scans. Preserve existing behavior for unrelated suites that make no checkpoint declaration; this is an explicit authority refinement for a producer, not a reader or data compatibility path. Checkpoint names are local to a suite. Reject duplicate certification of a Check type, rather than silently choosing one.

## Impl.Req.Wiki

Product Project: tarav-py. Wiki owner: tarav-md; relevant `notes/wiki/checks-workflow.md` and daily note. Source evidence is the above User Turns; behavior evidence will be focused CheckSuite and Action tests. Capture status: pending.

## Execution.Plan

1. **Feature — suite run.** Add marker, reached-set and certified Check-type relation. Verify markers only after actual production, run reset, and filtering/failure behavior. Status: pending.
2. **Integration — POI Action.** Record the checkpoint on events and require it for absence conclusion when attached. Verify skipped dynamic producer stays open, completed producer closes, and suite scoping remains correct. Status: pending.
3. **Guidance and integration.** Update maintained architecture and md-library consumer. Capture inline evidence, Wiki, focused/full checks, and commits. Status: pending.

## Impl.Log

- Inspected CheckSuite run/conclusion and POI Action event/scope code. Reproduced md-library floor-gated false closure in prior read-only investigation. No product changes yet.
