# Archive package organization

## Scope and checklist

- [x] Move artifact-registration Record authorities from `archive.records` to
  `archive.artifact_records`.
- [x] Move Record Archive implementation to the `archive.records` package.
- [x] Update maintained source, tooling, examples, and tests without aliases.
- [x] Preserve Type and Workflow Ships, Record schemas, and storage paths.
- [x] Complete validation: 212 focused tests and the new package-boundary
  test passed; full suite passed all 1,296 tests. Ruff and diff whitespace
  checks pass.

The previous `tarav.record_archive` public import is removed. External callers
and explicitly configured Python class-path bindings must use the new package.
No external environments or retained data are rewritten. Historical notes keep
their original paths as evidence. Context and other package moves are deferred.

## Capture status

Coordination note only. No Diagram Collection, Draft, or capture receipt has
been produced for this change; Diagram capture remains unreconciled.
