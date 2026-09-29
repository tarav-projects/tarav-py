# First shared POI model

## Impl.Abstract

Implement the approved first POI model on the existing collector and
identity/state mechanics. No retired linter runner or Wayfinder dependencies.

## Impl.Req.Diagram

Implementation capture is unreconciled: no current-session Chatlas support,
Collection, Draft, or Product Breadcrumbs have been resolved for this change.
This note is coordination only, not a substitute for those artifacts.

## Execution.Plan

- [x] Add POIWorkflow, check declarations, identified finding Records and Context.
- [x] Promote blessing/assessment Records to extensible Entities.
- [x] Compose runtime-local collector and shared Archive blessing placement.
- [x] Verify focused and broader regression suites.

## Impl.Log

- Prior Python worktree checkpoint: 0369b73.
- Findings preserve existing identity/state hashes and derive a UUID Ship
  from concern identity. Repeated emissions retain the same identity; state
  distinguishes evidence editions, not independently identified events.
- Loaded check metadata remains detached. Explicit trusted registry resolution
  supplies live code; stored Python paths never authorize imports.
- Existing caller-owned blessing paths and stored schema remain supported.
  Typed subclasses provide validation and assessment requirements.
- Full regression suite: 1,318 tests passed. Final Ship-link and typed-append
  additions: 189 focused POI, SKW, Kernel, and architecture tests passed.
  Ruff across src/tests/dev/tooling and git diff whitespace checks passed.
- Code is implemented; implementation capture remains unreconciled as above.
