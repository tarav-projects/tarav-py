# Breadcrumb data surfaces and exact Chatlas reference recovery

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: developing.
The User requested fixes for the investigated provenance gaps, explicitly
including native JSON and TOML Breadcrumb support. Preserve unrelated Notebook
work and existing evidence targets. No heuristic retargeting of old references.

## Design and measured evidence

The investigation found twelve broken Breadcrumbs naming nine User Turns in
session 01a15483-94e8-7fe0-86ad-ddd83e2bae52 (identity 0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a).
Seven Turns (eight labels) resolve exactly from the original rollout alone;
later rollout files reuse native session and record indexes and replace those
events in the aggregate. Two Turns (four labels) resolve exactly with the
pre-voice normalizer on the retained later rollout; their messages still exist,
but newly recognized voice events change their Turn boundaries. See request
935 for the earlier measured collision and raw-retention context. Raw evidence
for all nine targets is retained. Temporary reproduction and reconstruction:
/tmp/investigate-project-manager-references.py and
/tmp/breadcrumb-investigation-reconstruction.json.

JSON uses an explicit `tarav.breadcrumbs` array of strings at a schema-permitted
object position. Marker strings become Breadcrumb label strings without
changing application fields. Ordinary JSON strings remain inactive. TOML uses
native # comments; all basic/literal and multiline strings are skipped. Both
use normal submit/resolve/audit, validate native syntax, and preserve formatting.

Fix cross-rollout collisions in the aggregate by retaining distinct event
variants and remapping their dependent Messages and Context memberships, while
identical observations still merge. Preserve all retained signal rather than
letting record position silently select another event. Keep current aggregate
schema and source navigation. Make collision selection deterministic.

For exact references, retain the addressed Turn, Messages and supporting Events
as a validated immutable snapshot in the Chatlas Record Registry partition.
The existing three-coordinate locator still pins the same exact Turn; resolution
can explicitly report its retained representation. Capture snapshots before
creating new Breadcrumb attachments. Restore the nine historical snapshots
once from exact reproductions; do not ship an old normalizer or guess a new
target. Current Turn lookup and snapshots stay distinct and inspectable.

## Impl.Req.Wiki

Product: tarav-py. Documentation owner: tarav-md/notes/wiki.
Relevant notes: chatlas-normal-model.md, breadcrumbs.md (if present), and
daily/2026-10-22.md. The User's direct fix request and explicit JSON/TOML
instruction supply scope. Implementation observations are not User decisions.
Exact current-session evidence will be attached during closure.

## Execution.Plan

1. Feature: JSON/TOML marker spans, rendering, submit/resolve/audit and native
   validation. Existing unsupported-language failure was measured in request
   940. Verify real CLI round trips, malformed markers, ordinary strings,
   nested JSON metadata and all TOML string forms. Prototype: 29 focused tests
   pass. Add both formats to the public capture guidance and use them on the
   formerly unsupported manager sources.
2. Bug fix: write a failing two-rollout collision regression first, retaining
   both user messages and exact source observations. Remap events and dependent
   messages/contexts with stable conflict identities; shared prefixes dedupe.
   Rerun Normal Model, Query, raw-version, cache and architecture tests.
3. Feature/recovery: validate and retain exact Turn snapshots, resolve references
   and audit them through that path, capture future attachments before loss,
   and restore nine exact historical targets from retained raw. Verify tamper
   detection, immutable writes, current-model loss and all twelve real labels.
   Refresh the affected derived session, run focused and full Project checks,
   inline/Wiki capture, evidence audits, and completion closure.

## Impl.Log

- Start checkpoint e34051b9149285206c667a0682c6ccf809b3ab45 retains existing
  independent Notebook work as found; no changes were discarded.
- JSON/TOML native support and tests are in progress. Existing Markdown,
  Python and TypeScript contracts remain supported. No fake JSON comments.
