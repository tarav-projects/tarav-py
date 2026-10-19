# 929 — Recursive Lines Blocks

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
-->

## Impl.Abstract

Status: implemented. Knowledge.Surface: wiki. Alignment.Mode: Interactive.
Product: tarav-py. Wiki owner: tarav-md.

Redesign the active Lines foundation around two small identified entities:
Line and recursive Block. A Line has one authoring Block; that Block and its
ancestors form the bounded context needed to interpret the Line. Blocks are
typed through Tarav's existing class identity and may contain ordered Lines
and child Blocks. Retain Line Ship identity across wording edits. The old
Diagram Model is not a required Lines container.

Retire the disconnected Models workflow, Project.models facade, and the entire
legacy Diagram application. The user clarified that Git history is sufficient
retention for that code. Do not delete unrelated data models (including Chatlas
Normal Models) or the new l1 Lines core.

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

At the start of the request, `l1.lines.Line` accepted any TaravEntity as
scope, including another Line. Its Block ordered Lines but did not nest.
`l2.models` was disconnected, while `l2.unsorted` still imported Model
records and handlers. That baseline motivated the coordinated retirement.

## Execution.Plan

1. Feature: reshape Line and Block records and APIs so Line scope is exactly
   one Block; a Block has one optional parent Block and one ordered contents
   collection of Lines or Blocks. Reject duplicate members, mismatched scope, parent conflicts,
   and cycles. Check: focused construction, binding, and record round-trip tests.
2. Removal: retire old l2 Lines, Models, Unsorted Diagram, Project.models,
   Diagram CLI/config wiring, and adapters dependent only on that application.
   Keep independent Scoring and Skillware behavior. Check: import sweep, CLI
   help, runtime composition, architecture, and focused Scoring/SKW tests.
3. Documentation: update the Lines Wiki and architecture boundaries; run
   focused tests, Ruff, and project validation. Capture exact User Turns and
   audit the resulting Breadcrumbs.

## Impl.Req.Wiki

Wiki root: `tarav-md/notes/wiki`. Relevant topical note:
`lines-workflow.md`; daily capture: `daily/2026-10-19.md`.
The current Chatlas session and exact User Turns were recovered after the
write restriction lifted. The Lines topical note and 2026-10-19 daily note
capture the design and implementation decisions.

## Impl.Log

### 2026-10-19 — Design

Inspected active Lines primitives, disconnected Models facade, runtime wiring,
legacy Diagram imports, project guidance, Constitution, and Wiki. The current
repository was clean before this request. Chatlas update failed because its
cache lies outside the writable sandbox; no Turn hash was guessed.

### Slice 1 — Recursive authoring context

Start checkpoint: `e6d45001`. The focused tests first failed for missing
parentage, unrestricted Line scope, and unrestricted Block membership. Line
scope now requires a Block. Blocks retain parent and ordered child identities,
support detached record binding, and reject membership mismatches and known
parent cycles. Block subtypes use ordinary Tarav class identity; there is no
closed role enumeration. The synthetic scoring corpus was updated to describe
the new scope rule.

Focused tests: `tests/test_scoped_lines.py` and
`tests/scoring/test_line_support_scenario.py` passed (18 tests before the final
binding-order case). Ruff and `git diff --check` passed. Product Breadcrumb
capture is pending because Chatlas refresh cannot write its cache.
Final focused run: 19 passed. Slice commit: `222cfb65`.

### Legacy Model dependency found

The active Model constructor is disabled, but `l2.unsorted` still uses the
Model handler and Model record types across storage, CLI, View, projection,
rendering, and retained type registration. Deleting `l2.models` alone breaks
those imports and historical record reading. Two coherent retirement scopes
remain: remove only the active Model workflow/Project facade while retaining
the historical Diagram application, or retire that entire application and its
CLI/records together. This is a material scope decision in Interactive mode.

Architecture contract updated for the new l1 core. Focused architecture,
Project, scoring, and Lines suites passed (72 tests). The broader Model
retirement and Wiki capture remain pending.

### User clarification — retirement scope

The user explicitly chose retirement of all old code except the new
implementation, relying on Git to retain history. This resolves the prior
choice: old Diagram CLI/storage/record readers are no longer compatibility
requirements. Keep unrelated Chatlas Normal Models and generic Scoring/SKW
mechanics.
<!-- tarav.breadcrumb 7debcc61fe46 -->

Read-only `tarav check --project . --all` completed 63 checks with three
pre-existing POIs unrelated to this slice (one gitleaks finding and two test
fixture markers). `tarav status --project . --all` could not finish because
its Actions registry is outside the writable sandbox; the Project index and
usage traces likewise could not be updated. No POI was treated as an
instruction to change unrelated code.

### Slice 2 — Legacy Diagram retirement

Removed the entire l2 Diagram application (Models, Lines, Unsorted), its
Project facade, runtime and CLI composition, Diagram-specific Skillware
publication checks, and the Line-grounding Scoring adapter. Generic Scoring,
Skillware, Chatlas Normal Models, and the new l1 Lines core remain. Updated
architecture and package documentation. The retirement followed the user's
explicit clarification; Git retains the old implementation.

The focused Lines, architecture, Project, Scoring, and Skillware suite passed
(95 tests). The full Python suite passed (405 tests). Ruff passed on changed
source and tests. Chatlas refresh subsequently succeeded; exact User Turns
were captured in the Lines Wiki, daily note, and selected product surfaces.
Breadcrumb submission succeeded for those surfaces. Audits of the new
placements found no failures; existing positions shifted in runtime.py and
ARCHITECTURE.md and were refreshed. Removed the retired `diagram.main_model`
configuration from the root, tarav-py, and tarav-md Projects. The Project
status check completed 63 checks; its new UnknownConfigSection action closed
after the config removal. Three unrelated pre-existing actions remain (two
fixture marker POIs and one gitleaks finding). The tarav-md check completed
1,099 checks and reported 68 existing POIs in other surfaces. After the final
test fixture and CLI boundary adjustments, the focused suite passed
(98 tests); Ruff and Git whitespace checks passed.

### Completion verification

The umbrella Project status ran 1,173 checks, all completed. The retired
`diagram` config actions for the root and tarav-md Projects closed as gone.
Its 75 remaining open actions predate this change or concern other surfaces:
68 in tarav-md, four in the root, and three in tarav-py. All three repository
worktrees were clean after the implementation commits. The old code remains
available in Git history; there is no active legacy Diagram CLI or Model
workflow.

### Amendment — meaning through Lines and one ordered contents collection

The user removed the base Block's predefined topic: its Lines confer its
meaning. Replace separate Lines and child Blocks collections with one ordered
`contents` collection of Line or Block objects, retained as `content_ships`.
Keep one parent Block and each Line's authoring Block. Filtering by Python
type is sufficient; do not retain aliases for the split collections.
<!-- tarav.breadcrumb ef1a144918fb -->
<!-- tarav.breadcrumb 7f99331894ef -->

Todo:
- [x] Replace the Block fields and collection API; retain parent/scope checks.
- [x] Update the synthetic scoring consumer and mixed-order/binding tests.
- [x] Update the Wiki and architecture, capture this decision, and verify.

Start checkpoints: tarav-py `5b8ccf73` (existing Skillware changes retained
as found) and tarav-md `089b4bd6` (clean).

The focused Lines, scoring-scenario, and architecture suites passed (62 tests).
Ruff and whitespace checks passed. The synthetic fixture now writes its subject
as an ordinary context Line, retaining 50 scoring candidates plus 10 context
Lines. Mixed membership, ordering after Record binding, empty Blocks, duplicate
Ships, and parent/scope conflicts are covered. Fourteen new Breadcrumbs across
eight changed surfaces were submitted and audited with no failures; moved
positions were refreshed. The umbrella Project status is running for closure.
