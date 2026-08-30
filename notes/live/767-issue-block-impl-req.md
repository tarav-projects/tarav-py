# Issue.Block Implementation

## Impl.Abstract

- **Status:** Implemented; Diagram capture reconciliation remains
- **Source session:** `01a02f8b-8c36-7123-ba70-1a217b776e28`
- **Objective:** Implement `Issue.Block` as a Tarav2 Diagram Object.Type so the
  Hugentics Parking and Issue-maintenance workflows operate over one
  addressable object.
- **Boundary:** Parking remains a workflow, not a `Parking.Note` Object.Type or
  separate store.
- **State rule:** An Issue is open until an `Issue.Line.Resolve` ship contains a
  Line Annotation with a passing `Verbatim.Gate`. Later Lines do not stale the
  resolution.
- **Validation rule:** Open Issues remain writable and surface a POI.

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index`
- **Model:** Tarav Project Model; resolution currently unavailable
- **Impl.Req.Block:** not landed
- **Capture POI:** the running process cannot read
  `~/Documents/tarav/diagram/user-touched-chatlas-index/namespace.json`
  (`Operation not permitted`). Product implementation proceeds without
  inventing Diagram identities or evidence.

## Execution.Plan

1. **Object.Type registration** — add `Issue.Block` and
   `Issue.Line.Resolve`, their projected Python classes, namespace allowlists,
   and public exports. **Complete.**
2. **Issue state and POI** — derive open/closed standing from the centralized
   Assertion.Engine and surface `issue-open` without blocking capture. Check
   open, unassessable, and passing Gate cases. **Complete.** Existing Gate
   tests cover failed mechanical standing; Issue state closes only on Passed.
3. **Rendering** — expose the projected Issue state through the existing Block
   renderer and retain ordinary Lines, support, Assertions, and POIs. Check
   focused renderer tests. **Complete.**
4. **Regression validation** — run Tarav2 Diagram tests, lint the changed
   surfaces, and inspect the final diff. **Complete:** the focused 41-test
   Diagram suite, 85-test Tarav2/architecture suite, and full 1,615-test
   repository suite passed; Ruff and diff checks passed.

## Impl.Log

- The execution invocation selected Autonomous alignment.
- The workflow checkpoint commits are `966e755` in `tarav-py` and `9d77c2c`
  in `tarav-md`.
- Definition Blocks for the new Object.Types are not manufactured by product
  code. Missing definitions remain ordinary Object.Type definition POIs until
  grounded capture creates them.
- `Issue.Block` reuses the Design-family Line.Types and adds
  `Issue.Line.Resolve` with rendering code `RESOLVE`.
- `IssueBlock.assess(AssertionEngine)` is the single state projection. Only a
  passing reviewed Resolve closes the Issue; later ordinary Lines preserve
  that standing.
- Capture checks and Block rendering ask the projected Block.Type for its
  mechanical findings. Open Issues therefore surface `issue-open` without
  blocking writes.
- The maintained Tarav Diagram design reference now records the implemented
  `Issue.Block`/Parking boundary and state rule.
- Existing live Namespace configuration may still need `Issue.Block` added to
  its allowlist. The current process cannot inspect or amend that depot because
  of the recorded filesystem permission failure.
