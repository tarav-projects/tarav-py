# Embedded and external Breadcrumb placement

<!-- tarav.sessions
ec6cf584 = codex:01a1563b-2992-7c62-8a38-05c1cc75b1fe @ec6cf5849bb6c4e66f011b015415da94eeb1a17634872aa4fb9e25d8e065ab53
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: developing.
The User selected two placement modes of the same registered Breadcrumb.
Embedded placement writes its opaque label into a writable surface. External
placement records a file, observed line and exact single-line fragment in the
registry without writing the surface. JSON is read-only for this workflow.
The User rejected the proposed general Record metadata namespace as unnecessary.
<!-- tarav.breadcrumb 833dba6e4d5e -->
<!-- tarav.breadcrumb cb73b70fd88a -->

## Design

BreadcrumbStore already separates identity, append-only LocatorObservations and
typed workflow attachments. Add an optional placement field (embedded by default)
to Breadcrumb and a fragment field to external file observations. Maintain a
single identity/attachment system. Existing embedded records remain valid.

External resolution checks the latest recorded line, then searches the same
file by exact fragment. One matching line resolves; several are ambiguous;
none reports ExternalAnchorMissing. A missing file or line never deletes the
Breadcrumb or its attachments. Maintainers explicitly append a new location
and fragment; reads never rewrite observations. Previous observations remain.

The generic submission library and chatlas-context CLI expose external placement
with explicit line, fragment and User-Turn prefix. Existing Chatlas Query,
snapshot retention and typed attachments are reused. File audits discover external
Breadcrumbs through the registry and validate the same attachments. The existing
position-refresh option may append a uniquely resolved external line observation.

Embedded submission rejects JSON before workflow preparation or registry writes,
including attempts to override its language. JSON label inspection remains
read-only so existing evidence is not discarded. Existing JSON source metadata
is not automatically removed or migrated. No Record-system namespace or fuzzy
matching is introduced. External text placement is usable beyond JSON.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki. Relevant note: breadcrumbs.md
and daily/2026-10-22.md. Guidance companion:
../../../tarav-md/notes/live/871-external-breadcrumb-guidance-impl-req.md.

## Execution.Plan

1. Feature: external observations, exact resolution, ambiguity/missing findings
   and explicit relocation. Verify no source mutation, movement, duplicate
   fragments, missing content/file, retained attachments and append-only repair.
2. Feature/removal: disable embedded JSON writes; expose external submission
   through chatlas-context and include external positions in file audits.
   Verify real CLI registration/audit and rejected JSON writes before effects;
   preserve Markdown/Python/TypeScript/TOML behavior and old JSON inspection.
3. Documentation/integration: update capture guidance at its SKW source and
   compile; exercise external capture on the changed JSON source, capture code
   and Wiki evidence, run focused tests/Ruff and full Project status, then commit.

## Impl.Log

- Cold review: inspected Store, LocatorObservation, submission/audit protocols,
  Chatlas integration, CLI and file-position Reference. No new workflow identity
  is needed. Data shape first keeps placement and observations in Breadcrumbs.
- Subtract before adding: remove the JSON renderer/write path during integration; retain
  read-only inspection of existing labels and TOML support.
- Start checkpoints: Python df267e3761e5bc1261180a0f797ae00a8a3c8174;
  Markdown 83c455ae41bb62bf1942de028c42535566e47f16. Trees were clean apart
  from the new requests. Cold execution reload confirms the selected design.
- Slice 1: eleven new tests first failed because external creation did not
  exist. After implementing observations and resolution, 24 tests pass,
  including existing prefix and short-label behavior. External reads do not
  mutate observations, and missing/ambiguous selections retain their identity.
- Slice 1 committed as 7588afbdb2bfa9cadc8e7ffe572745e21ed70fc5.
- Slice 2: embedded JSON writes are rejected before workflow preparation,
  regardless of language override. Chatlas external submission reuses Query,
  exact Turn snapshots and typed attachments; relocation is explicit. File
  audit discovers external anchors from their latest registered location and
  supports read-only inspection or opt-in observation refresh.
- Verification: 115 focused tests pass across Breadcrumbs, Chatlas, Normal
  Model and the runtime Record contract; Ruff passes. The broader architecture
  test currently fails on an independent archive_git/git import cycle in
  concurrent DOI/Change-ID work. Those files are outside this implementation.
- The JSON source for capture guidance was edited as its owner's product
  work, then four blocks were prepared/recorded and compiled with no findings.
  Its Breadcrumb capture uses external placement only; registration checks its
  exact source bytes remain unchanged. Existing JSON labels remain inspection
  history; no source metadata is added or removed by this workflow.
- The transient independent import cycle and runtime move have settled; the
  architecture acyclicity test now passes and the installed CLI is usable.
  Concurrent commit 5932b1aa retained the shared ARCHITECTURE.md updates,
  including this request's placement paragraph; no external changes were removed.
- Product capture: eleven embedded submissions plus four external anchors on
  the guidance source. The source SHA-256 stayed
  b34c832fece5e9f34fbf36eb760feb689c840acb9747a5a5f759dd5d3b7341ed.
  Slice 1 and both requests were already captured separately. The final read-only
  batch audit covers nineteen implemented/request/Wiki surfaces: all OK, zero
  POIs and zero errors. Position refresh only appended registry observations.
- Slice 2 committed as 430fff7c3cc3cfade9d7d07411ab8838d65db36e.
- Full root verification completed all 1,338 checks with no incomplete checks;
  all 64 pytest file suites passed. It found two new external audit POI Types
  missing their required rendered summaries. Opened their action context and
  added explicit descriptions; the final routine recheck verifies that fix.
