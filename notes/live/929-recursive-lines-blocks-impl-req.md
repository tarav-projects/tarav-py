# 929 — Recursive Lines Blocks

## Impl.Abstract

Status: developing. Knowledge.Surface: wiki. Alignment.Mode: Interactive.
Product: tarav-py. Wiki owner: tarav-md.

Redesign the active Lines foundation around two small identified entities:
Line and recursive Block. A Line has one authoring Block; that Block and its
ancestors form the bounded context needed to interpret the Line. Blocks are
typed through Tarav's existing class identity and may contain ordered Lines
and child Blocks. Retain Line Ship identity across wording edits. The old
Diagram Model is not a required Lines container.

Remove the disconnected Models workflow and Project.models facade from active
composition. Do not delete unrelated data models (including Chatlas Normal
Models) or silently migrate historical Diagram records. Legacy Diagram storage
still needs an explicit retirement path where it imports Model records.

## Design narrative

The user chose a bounded writer-reader contract: before adding a Line, select
or create an identified Block. A Line must make sufficient sense from its direct
Block and parent chain. Other graph relationships can discover or apply that
Block, such as a typed spec-of relation, but do not enlarge the Line's default
interpretive scope. A specification is a typed Block related to its subject;
the relation, rather than the core Lines workflow, may impose alignment review.

The Line Ship continues one semantic point through Git changes. A different
point gets a new Ship; an independently evolving branch may record a fork
relationship elsewhere. Git records editions; the Ship supplies semantic
continuity across file movement.

Current `l1.lines.Line` accepts any TaravEntity as scope, including another
Line. Current `l1.lines.Block` orders Lines but does not nest and deliberately
does not own their scope. `l2.models` is a disconnected handler; Project.models
only lists aliases. Older `l2.unsorted` Diagram code still imports those Model
records and handler, so its removal requires coordinated changes.

## Execution.Plan

1. Feature: reshape Line and Block records and APIs so Line scope is exactly
   one Block; a Block has one optional parent Block, ordered direct Lines and
   child Blocks. Reject duplicate members, mismatched scope, parent conflicts,
   and cycles. Check: focused construction, binding, and record round-trip tests.
2. Refactor: remove the disconnected active Models workflow and Project.models
   facade; keep historical Diagram data readable without restoring it to the
   new Lines core. Check: runtime composition, architecture, and focused legacy
   checks. If legacy consumers require more than a bounded removal, record the
   dependency and keep their historical paths until separately retired.
3. Documentation: update the Lines Wiki and architecture boundaries; run
   focused tests, Ruff, and project validation. Capture exact User Turns where
   accessible; retain a truthful gap if Chatlas storage is sandbox blocked.

## Impl.Req.Wiki

Wiki root: `tarav-md/notes/wiki`. Relevant topical note:
`lines-workflow.md`; daily capture: `daily/2026-10-19.md`.
Current Chatlas session resolves, but refreshing its cache is sandbox blocked;
exact Turn Breadcrumbs are pending. Earlier conversation in this same session
remains the user decision source, not an agent-approved design.

## Impl.Log

### 2026-10-19 — Design

Inspected active Lines primitives, disconnected Models facade, runtime wiring,
legacy Diagram imports, project guidance, Constitution, and Wiki. The current
repository was clean before this request. Chatlas update failed because its
cache lies outside the writable sandbox; no Turn hash was guessed.
