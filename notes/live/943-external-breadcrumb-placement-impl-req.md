# Embedded and external Breadcrumb placement

<!-- tarav.sessions
ec6cf584 = codex:01a1563b-2992-7c62-8a38-05c1cc75b1fe @ec6cf5849bb6c4e66f011b015415da94eeb1a17634872aa4fb9e25d8e065ab53
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: ready.
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
- Subtract before adding: remove the JSON renderer/write path first; retain
  read-only inspection of existing labels and TOML support.
