# 931 — Line Notebook and first archive recovery

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
-->

## Impl.Abstract

Status: complete. Knowledge.Surface: wiki.
Alignment.Mode: Interactive. Product: tarav-py. Wiki owner: tarav-md.

Implement Notebook storage over the existing Lines primitives, a Project
integration with typed Discussion, Model, and Archive sibling Blocks, and a
first real import of the recent retained legacy Diagram state. Complete the
request, then execute it; the User explicitly authorized both.
<!-- tarav.breadcrumb 9c020280baa3 -->
<!-- tarav.breadcrumb 2869686f13fb -->

Scope is deliberately bounded. Do not add generic Lineage, old-history
reconstruction, semantic alignment checks, mutation approvals/protections,
new CLI commands, searching/index infrastructure, or move/reorder operations.
Existing Block.append and mutable Line.text remain the editing primitives.
<!-- tarav.breadcrumb 8b070a268e44 -->
<!-- tarav.breadcrumb 8cf1e9e4d974 -->

## Design narrative

Lines owns stable natural-language Lines and recursive typed Blocks. Each
Line has one authoring Block; parent Blocks supply inherited context. Blocks
have no topic field and hold one ordered contents sequence. Notebook supplies
the central persistent home. Projects can select their own Block layout;
the first default is Project root → Discussion, Model, Archive as siblings.
Discussion stores reasoning without an implementation obligation. Model aims
to be current. Archive retains historical material without claiming current
applicability. Put these explanations in ordinary Lines.
<!-- tarav.breadcrumb 46cfba6dccb7 -->
<!-- tarav.breadcrumb bb99afaf14a5 -->

General evolution of Ships belongs to a separate future History/Lineage
workflow, potentially with Git-backed and explicitly stored histories. For
this import, choose one recent state per identity and let Git record changes
from here. This is not a reconstruction of all historical editions.
<!-- tarav.breadcrumb 683f9cafc25a -->

### Inspected implementation and proposed mechanics

- `l1.lines.Block` retains parent_ship and ordered content_ships and has
  explicit binding methods; `Line` retains scope_ship.
- `l1.records.registry.RecordMap` already initializes Git-backed keyed
  storage, dispatches registered Record Types, and supports insert/replace.
  Reuse it as the Notebook Workflow partition under the standard Record
  Registry instead of adding another storage engine.
- `l2.project.Project` exposes optional integrations through bound helpers;
  RootProject inherits it, so the Tarav root can use the same notebook.
- `l3.runtime` explicitly registers Types and Workflows. New Notebook
  Types must be registered there; l1 Notebook must not import Project or l3.

Data shape first: Notebook (a TaravObject storage handle), NotebookWorkflow,
ProjectBlock(Block, project_ship), DiscussionBlock, ModelBlock, ArchiveBlock.
The three branch Types have the existing Block schema. A ProjectNotebook
binding lives in l2/project; Project.notebook() returns it and Project's
notebook_layout() supplies the default branch Types. create() provisions an
initial layout once; loading never silently creates or regenerates it.

Notebook.save writes one identified Record; save_tree writes a Block's
contents recursively. load resolves scope, ancestry, and ordered contents
using one identity cache per load. ids lists stored Ships; commit explicitly
records changes. Constructor selection and reads never create storage.
Keep exact registered Type and filename/identity agreement at the boundary.

Recovery observations: the current JSON ship stores under
`~/Documents/tarav/diagram/{attic,user-touched-chatlas-index}` contain 1,581
Lines and 269 Blocks, plus nine former Model groupings. They have no overlapping
Ships and no missing Line→Block links. Latest edition timestamps extend to
2026-09-26. Recover both stores beneath the live Tarav root Project's Archive,
grouping former Models as ordinary Blocks. Keep legacy UUIDs for recovered
Lines/Blocks/groupings; make former labels ordinary Lines. Select the most
recent explicit edition, retain verbatim text, and order by recorded timestamp
then Ship where the source supplies no stronger ordering.

Use a bounded recovery script, not restored legacy readers. Copy the source
JSON and namespace/annotation data into the Notebook repository and keep an
import report mapping selected source editions to the new Records. This
preserves metadata beyond the minimal new schema without adding version Types
or live dependencies on old storage. Repeated import must not overwrite later
notebook edits. Older Markdown indexes, Attic repository histories, and
uncommitted Drafts remain later recovery inputs; this slice imports the
selected committed Diagram corpus, not every historical representation.

## Impl.Req.Wiki

Owner/root: tarav-md/notes/wiki.
Read `line-notebook.md`, `lineage.md`, `lines-workflow.md`, and
`daily/2026-10-19.md`. The first three document the user-agreed boundaries;
the implementation observations and mechanical choices above come from
inspected code. Capture the implementation outcome back to the daily and
Notebook topical notes with exact User-Turn Breadcrumbs.

## Execution.Plan

1. **Feature — storage.** Implement l1/notebook using RecordMap and register
   NotebookWorkflow/Notebook. Prove mixed nested contents and subtype Records
   survive save/load, a Line edit keeps its Ship, missing references fail,
   and readonly selection creates nothing.
2. **Feature — Project layout.** Add typed root and three branches, the bound
   ProjectNotebook, and Project access/layout hooks. Prove idempotent creation,
   Project isolation, custom layout extension, and default sibling order,
   with meaning expressed through Lines. Document ownership boundaries.
3. **Feature — first recovery.** Implement the bounded import script and test
   latest-edition selection, verbatim text, labels-as-Lines, membership,
   source retention, and non-overwriting reruns. Run it against the two
   inspected stores into the real Notebook; reload the Tarav Project Archive
   and compare all selected texts/Ships to source. Commit the data repository.
4. **Closure.** Run focused suites, Ruff, architecture tests, and Project
   status --all. Apply supported Breadcrumb capture per changed surface,
   update Wiki and this log, and make scoped evidence commits.

## Impl.Log

### Design

Read repository routing, Constitution, relevant Wiki, primitive APIs,
RecordMap, GitRepository, Project integrations, runtime wiring, and source
ship records. Data shape first and reuse of RecordMap keep storage minimal.
No obsolete active Notebook implementation needs removal.

Execution completed through slice 3 and closure. Product tree was clean at inspection.
tarav-md has unrelated ongoing Explain Me skill edits; preserve them under
the evidence workflow's checkpoint rules.

### Execute — slice 1

Cold-reloaded this request before execution. Start checkpoints: tarav-py
`cdc0f8d0`, tarav-md `445f1bef` (external Skillware edits retained).
The feature test failed first because Notebook did not exist. Notebook now
uses RecordMap without storage creation on reads, saves exact registered
Records, and rebinds the connected context through one per-load identity map.
Fourteen Notebook/Lines tests pass; Ruff passes. No change to Line/Block schema.

### Execute — slice 2

Typed ProjectBlock, DiscussionBlock, ModelBlock, and ArchiveBlock are registered.
Project.notebook() selects a binding; create() seeds its layout and explanatory
Lines once. Project.notebook_layout() customizes the default Types. Detached
Projects work because association uses identity, not folder location.
The feature test first failed for the absent Types. The focused Notebook,
Project, and architecture run passed (53 tests). An architecture test caught
an unnecessarily broad import of l1.project; importing its base module keeps
the existing module ownership graph acyclic. Ruff passed.

Updated architecture and the authoritative agents-file Skillware source;
produced and compiled AGENTS.md. JSON source has no registered native inline
Breadcrumb convention; supported source-code, test, and Markdown surfaces
carry the selected design Turns instead. No editing policy or check engine
was added. Slice 1 commit: `2dc187fe`.

### Execute — slice 3 and actual recovery

Slice 2 commit: `07815f86`. The bounded recovery script is
`scripts/import_legacy_notebook.py`. Its first tests failed for the absent
script. Tests now cover latest-edition selection independent of array order,
verbatim text, retained Ships, labels-as-Lines, inherited Archive context,
byte-identical raw source retention, rejection of overwriting reruns, and
missing source membership before writes.

The real invocation exposed a missing runtime bootstrap in the standalone
script; fixed main() to initialize get_runtime() and added a fresh-process
regression test. All three recovery tests pass.

Provisioned the live Tarav root Project (85c304e9-a3f9-4093-abc3-ee10a32743bf),
not the retired Tara workspace. Its notebook is the standard Record Registry
partition `~/Documents/tarav/records/92338514-6f87-4dad-8a41-3148020f90d4`.
Data start commit: `4213906a`. Project root:
`f6c673d6-88e7-5071-8533-ab0a6450c6e6`; Archive:
`3ed966a8-aeda-5f14-96df-236590db4958`.

Imported 1,581 legacy Lines, 269 Blocks and nine former Model groupings as
ordinary Blocks. Including generated context/label Lines and the Project's
eight initial Records, the notebook contains 2,149 Records. All 38 legacy
Collection records remain retained as raw source rather than being interpreted
as authoring ancestry. Both source repositories were clean:
Diagram.Attic `1baf6789b23e5621d742a3196d5ad29989e0f6ab` and
User.Touched.Chatlas.Index `caf59454702f65726292d7594a530a91ec561ce9`.
The import report and source copies live under
`imports/ee7c5865-2209-516f-8be2-361eea2d8f18/` in that partition.

Verified by reopening the real notebook through Project.notebook().root:
all 1,581 selected legacy texts and scope Ships match; all 1,859 selected
source records have matching retained hashes; original labels survive as
Lines; every legacy Line inherits Archive context; all 2,149 Records are
reachable from the Project root. The verification initially reloaded the
whole tree repeatedly inside a loop; interrupted that read-only check and
reran it using one loaded tree. The corrected check completed successfully.
Ruff and whitespace checks pass.

### Closure

The umbrella status --all ran 1,175 checks, all completed, with no new actions.
The 78 remaining actions are outside this scope: 71 in tarav-md (Skillware and
harness/Breadcrumb findings), four in the root harness, and three in tarav-py
(two fixture markers and a pre-existing gitleaks report). The run reported no
Notebook or import test failures. Focused tests, source Ruff, the actual reload
comparison, and Wiki parsing all passed.

Slice 3 code commit: `57cf4da0`. Imported data commit: `a14e4955`.
Wiki capture commit: `082750a2`, covering Notebook implementation/usage and
the 2026-10-19 daily narrative. Fifteen new Wiki Breadcrumbs were submitted
and audited without failures. Product Python and Markdown surfaces were
captured and audited per slice; stale positions were refreshed. The Skillware
JSON source has no native Breadcrumb convention, as recorded above. Registry
data and raw retained JSON are contextualized by their evidence-backed commits
and the source-selection report rather than invented inline JSON markers.

Concurrent Attic implementation work appeared during execution, including
request 932 and changes to runtime, agents source, architecture, dependency,
and test surfaces. Those pending external edits remain outside the Notebook
completion scope. Notebook did not restore legacy workflows or implement
general Lineage, semantic alignment, mutation approvals, or new CLI commands.
