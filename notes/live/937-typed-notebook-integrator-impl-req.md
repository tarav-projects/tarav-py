# Typed Notebook integration

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
-->

## Impl.Abstract

Make Notebook a typed recursive Block and the integration point for capture,
support, review and checks. A global Tarav Notebook can contain Project
Notebooks and further typed notebooks. The User selected Develop after
recapping this direction. Keep Lines minimal and evidence workflows separate.
<!-- tarav.breadcrumb 629c049d1585 -->
<!-- tarav.breadcrumb 9d013b776695 -->

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: executing

Scope: typed Notebook objects, standard bounded operation methods, recursive
checks, Project/default-layout integration, Context consumers, tests, and
documentation. Preserve existing stored Ships, concrete Type identities and
record shapes for Project/Discussion/Model/Archive blocks. Reads do not create
or migrate records. No semantic scoring, general LineTrace/lineage engine,
automatic approval, retrospective support invention, or unrelated Chatlas work.

## Design

Storage remains the existing l1.notebook.Notebook transport. Its qualified
role is a shared Record Registry partition, distinct from the new l2.notebook
Notebook Block. A small l1 NotebookBlock base carries transient storage binding;
loading binds that interface without importing integration code into storage.
The featured Notebook in l2 composes capture/evidence and CheckProvider.

Move the four current semantic block classes into l2 as Notebook subtypes,
retaining their existing TypeShips and serialized Type names. This changes
where behavior is implemented, not the identity of those persisted blocks.
Remove the old duplicate definitions. Move Context selection/resolution to
l2.notebook_context and migrate active consumers; no compatibility aliases.
Existing generic Lines/Blocks and evidence records remain readable unchanged.

The featured Project returns its actual ProjectBlock Notebook, rather than
the old ProjectNotebook association wrapper. Default creation retains the
Discussion, Model and Archive sibling layout and its explicit explanatory
Lines. New Project notebooks attach under a deterministic TaravNotebook root.
Opening existing notebooks preserves parent links and edited layouts; do not
silently change their authoring context to force a new global hierarchy.

Notebook methods coordinate bounded capture, support attachment, review
proposal/record/completion and inspection through NotebookCapture. Standard
capture/support accepts one root Reference plus contextual neighborhood and
producer; construct one existing SupportMember per SupportSet. Root validation
still reports wrong-role/missing evidence after capture. Multiple calls retain
multiple independent sets. Keep the general Grounding schema extensible and
reuse existing token review/state-snapshot mechanics. Requirements continue
to come from Types and ancestry; do not impose new retrospective requirements
on existing seed/archive Lines. Reviewed content remains an independent axis.

Notebook CheckProvider composes its local evidence suite and each nearest
nested Notebook's suite, including subtype extensions. Each Line is checked
once; parent requirements still apply to children. Project access checks only
load existing storage, then compose the Notebook's own suite. Projects keep
action/status ownership. Current normalizer/lineage work is outside this scope.

## Impl.Req.Wiki

Product tarav-py; Wiki owner tarav-md, notes/wiki/line-notebook.md and daily
2026-10-20.md. Current evidence APIs are in l2/notebook_capture.py and
l2/notebook_checks.py; storage and semantic classes are in l1/notebook;
Project association is l2/project/notebook.py. Review tests/test_notebook*,
tests/test_project_notebook.py and tests/test_architecture.py. Current
architecture must remain acyclic with no l1 imports of l2.

The read-only extension imports the moved block classes. Its adapter and
fixture imports need alignment under its own request
../../../vscode-tarav-center/notes/live/014-typed-notebook-api-impl-req.md.
No UI writes or JSON shape change. Its local instructions require tests,
version bump, package and installation after modification.

## Execution.Plan

1. **Verified — Refactor/feature.** Implement storage binding and typed
   Notebook roots; remove the old association wrapper; move Context code and
   migrate source/test imports. Verify record identity/round trips, nested
   root creation, preservation of existing parents/layout, scoped operations,
   and read-only absent-storage behavior.
2. **Verified — Feature.** Route capture/evidence and recursive checks through
   Notebook; compose Project access checks. Verify one-root support sets,
   multiple sets, independent review, inherited policy, subtype checks,
   no duplicate checking and Project action lifecycle. Update maintained
   architecture guidance and explicit testpaths, capture code/test evidence,
   then commit verified work.
3. **Pending — Consumer alignment and closure.** Update extension imports,
   verify actual read-only adapter/tests, package/install it. Refresh installed
   Tarav, run Project checks including tests, and prove existing live records
   open with the richer Notebook Types without modifying their bytes.
   Capture topical/daily Wiki, audit Breadcrumbs, and close evidence commits.

Subtract before adding: remove the old ProjectNotebook wrapper and old block
definitions; migrate all active callers. Data shape: existing Block record,
ProjectBlock adds project_ship; runtime storage/policy services are not data.
Boundary discipline: the integrator rejects operations outside its subtree,
while evidence validity remains a nonblocking check. Material deviations
require explicit alignment before expanding scope.

## Impl.Log

- Inspected storage, blocks, Project association, Context, capture, checks,
  runtime registration, extension consumption and current tests. No nested
  source instructions were found. Session capture refreshed once for this pass.
- Start checkpoints are recorded below. The extension checkpoint preserves
  pre-existing work, including unrelated UI edits, as found; its evidence gap
  is marked unknown-session. Product changes stay scoped after that snapshot.
- Cold-read the complete request and checked its source/API premises before
  implementation. No material scope ambiguity was found. Python checkpoint
  db37ea5b813fa35157e830bed30300d965661dae; Markdown checkpoint
  379e2f6c118e43fda2efdb3748bebe15f7ba9636; extension checkpoint
  e36744e9e48c827de1b1e123bf665a8fc0e82b66.
- Another concurrent task allocated note 936. This request moved to 937 to
  keep numeric lookup unambiguous; the temporary operational files still use
  the 936 prefix. Preserve the other task's action edits and documentation.
- Implemented steps 1–2 together as one verified slice: the featured Notebook
  and Project suite must use the same API to keep imports and callers coherent.
  Existing record TypeShips/names are retained, the old wrapper is removed,
  and active Context, CLI, runtime, importer and tests use the new locations.
- Verification: 94 focused Notebook, evidence, Context, architecture and Record
  contract tests passed; 3 recovery tests also passed. New integration tests
  exercise global roots, old parent/layout preservation, one-root support sets,
  multiple sets, token review, state staleness, bounded operations, inherited
  requirements and subtype checks without duplicate Line evaluation. Initial
  failures exposed test-fixture mistakes in CheckPOI/CheckResult construction;
  those fixtures were corrected to the actual contracts. Architecture graph
  enumeration now separates Notebook modules across layers, as it already does
  for Project/Lines, and a Project base import avoids a package-root cycle.
- The recovery importer was an additional existing caller of the removed
  wrapper. It now uses the ProjectBlock's storage and project_ship. Its current
  import/retention tests pass; no live import was rerun. Five relevant Notebook
  test files are now included in the Project's explicit testpaths.
- Inline capture covers Python/Markdown surfaces. pyproject.toml and extension
  JSON manifests have no registered native Breadcrumb convention; their scope
  and authorization are retained by the request and evidence commits.
- New inline references resolve. Audits preserve pre-existing missing-User-Turn
  findings on older labels in checks, Project/runtime registration, importer,
  recovery/evidence/architecture tests and ARCHITECTURE.md. Position observations
  were refreshed for moved labels. No attachment was retargeted to conceal an
  unavailable earlier Turn. The already-registered request needed only position
  refresh at its renamed path, not another submission.
- Installed Tarav refreshed through uv. The existing live Project Notebook
  loads as the richer ProjectBlock and its Archive has 2,143 members. All 5,126
  files under its storage kept identical hashes; parent=None remains intact
  and no TaravNotebook record was created for this existing root.
- A final extension-point check verifies review operations requested through a
  parent use the destination Notebook's specialized evidence service. All five
  integration tests passed after that adjustment. Non-Block review destinations
  are rejected before evidence storage is created. Ruff and diff checks pass.
