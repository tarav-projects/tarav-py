# Project-configured Product Mapping scope

<!-- tarav.sessions
ec6cf584 = codex:01a1563b-2992-7c62-8a38-05c1cc75b1fe @ec6cf5849bb6c4e66f011b015415da94eeb1a17634872aa4fb9e25d8e065ab53
-->

## Impl.Abstract

Knowledge.Surface: wiki. Status: completed. Correct the overbroad tarav-py run:
only committed .py files under src/ and tests/ belong in its active map. The
User explicitly puts this scope in Project configuration, not engine defaults.
Keep the generic workflow product-agnostic.
<!-- tarav.breadcrumb bf55eef4fcef -->
<!-- tarav.breadcrumb 53a090edbe4a -->
<!-- tarav.breadcrumb 49304512c08e -->

## Design and Impl.Req.Wiki

Add include/exclude globs to the existing product_mapping config section.
The Project Mapping manager supplies those controls to ProductMapper; the
historical driver reads the same Project config. Scope changes must not silently
reinterpret a confirmed map: retain each map's actual include/exclude selection
and audit against it. Standalone callers retain the existing explicit controls.
An outdated scope triggers an update even at the same commit.

Preserve the rejected broad run through its existing committed Registry data
and a superseded track. Rebuild the active history at the same ten-commit
checkpoints from the configured scope, then map completed HEAD. Keep the report
outside the selected product paths. Migrate existing records explicitly to name
their original scope; do not add read-time repairs or hardcode Python in core.

Wiki owner: tarav-md/notes/wiki; product-mapping.md and daily/2026-10-22.md.
This corrects request 946's operational scope, not the underlying general design.

## Execution.Plan

- [x] Feature: Project config → manager/driver → generic mapper; snapshot scope
  preserves old audits. Verify nested .py inclusion and exclusion of .md, notes,
  retired code and similarly named directories; config changes update selection.
- [x] Data: preserve old run, rebuild scoped history, independently audit each
  snapshot and compare inventory with committed src/tests Python files.
- [x] Capture, checks and commits; final HEAD catch-up without changing scope.

## Impl.Log

- Worktrees initially clean. Product head 1f714d75, original run 128 maps.
- Todo list above. Product Mapping's existing include/exclude mechanics are
  reused. No new file classification, parser or workflow type is needed.
- Readiness checked against the current mapper, Track, Project config, manager,
  commands, driver and tests. No unresolved user decision. Cold-reloaded plan.
- Config controls are shared by Project manager, CLI and replay. Core remains
  generic. Map snapshots record selection; old map audits ignore new controls.
  A changed configuration triggers an update at the same commit and rejects
  confirmation of an obsolete-scope proposal.
- Measured verification: 78 mapping/generic Record/architecture tests passed;
  after scope-staleness coverage, 25 mapping/generic Record tests passed. Ruff
  across src/tests/tooling passed. Nested .py inclusion, other-directory and
  non-Python exclusion, CLI/manager agreement and historical audit are asserted.
- Preserved 128 rejected broad maps in the existing data Git history and the
  superseded-whole-repository Track. Explicit schema migration adds only their
  original include/exclude values, verifying all other fields unchanged. No
  runtime migration or repair was added. The active history is being rebuilt
  from Project configuration through pinned original target 04981e43.
- Start checkpoints: Python 1818f589, Markdown c027fdc9. Rebuilt 127 historical
  checkpoints. At 04981e43: 553 files, 1,184 chunks, 3,454,612 bytes, no skipped
  surfaces. Independent Git inventory enumeration matches exactly: regular
  committed files whose path starts src/ or tests/ and ends .py.
- The installed CLI independently audited every rebuilt historical map. All
  modified product/doc surfaces audited clean; schema/control plumbing had no
  additional invented User-Turn placement. JSON source remains externally
  annotated. The superseded report is retained by the earlier product Git commit.
- Broad root status --all is running. Final catch-up will follow completion
  commit; exact coordinates will be retained in the registry.
- Full root status --all completed 1,346 checks, none incomplete. All 66 pytest
  file suites passed with zero test POIs. The 66 older hook/security/test-marker,
  prompt and SKW/Breadcrumb maintenance findings remain unchanged.
- Slice commit 25c184a2; Wiki closure f3c90012. JSON/config and every changed
  product/Notes surface audited clean. The data baseline 993f5f5b preserves the
  rejected run; no additional data start checkpoint was made before its explicit
  schema migration. Existing records' non-scope fields were verified unchanged.
- Final catch-up is executed after this completion commit using the same Project
  configuration adapter. Current selection: 563 files, 463 src and 100 tests.
  Final commit/map coordinates are retained in the workflow registry so a tracked
  report need not change after mapping HEAD.
