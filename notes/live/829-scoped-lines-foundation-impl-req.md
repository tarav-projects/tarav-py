# 829 — Scoped Lines foundation

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
-->

## Impl.Abstract

Status: ready for implementation.
Knowledge.Surface: wiki. Alignment.Mode: Interactive.
Product: tarav-py. Wiki owner: tarav-md.

Build a storage-independent Lines foundation around `Line(TaravEntity)` with
identity, natural-language text and required interpretive scope. Scope accepts
`TaravEntity`, including another Line. Deliver construction, explicit scope
navigation and record round-tripping without a required Model.
<!-- tarav.breadcrumb 4572a6ed3c84 -->

This first slice establishes Line and the foundational workflow declaration.
The earlier Block proposal remains relevant, but a new Block container,
BlockLine specialization, Models redesign, automatic extraction, semantic
checks, scoring, evidence, approval and editions are not prerequisites or
deliverables of this slice. Do not change request 828 or absorb its concurrent
implementation. No code is implemented by this Design pass.

## Design narrative — accepted semantics

A Line is an identifiable, typed natural-language statement expressing one
semantic contribution within an explicit scope. It decomposes larger material
into minimally complex statements; it is not designed to stand alone. Scope
is constitutive of interpretation, not merely optional background evidence.
Lines can scope other Lines and participate in a larger semantic graph.
<!-- tarav.breadcrumb 814dd69b014d -->

For example, “it is red” can contribute a color statement within a scope
describing the exterior of a particular car. The scope supplies what the
statement need not repeat. Changing scope can change meaning without changing
text. Do not conflate scope with the places where the statement is displayed.
<!-- tarav.breadcrumb 606d568377f5 -->

Lines model no authority. One fact is an authoring aim, not a truth guarantee.
They are a modeling tool for decomposition, encapsulation and maximal practical
orthogonality. They need not be completely independent: the aim is local edits,
so a changed car color affects one or a few statements rather than the entire
account. Do not reject a Line because it is false, uncertain, compound, or
overlapping with another Line.
<!-- tarav.breadcrumb 3332aaae4b19 -->

Evidence, editions, approval and scoring stay optional. Interpretive scope is
basic, while Block-specific interpretation could later be expressed by a
BlockLine subtype. A Line can attach semantically to other kinds of subjects;
neither scope nor orthogonality requires a mandatory Block container.
<!-- tarav.breadcrumb 275643b37079 -->

The user selected `TaravEntity` as the current scope boundary. Do not widen it
to arbitrary strings/dictionaries or require a new Scope-specific entity type.
<!-- tarav.breadcrumb 02cee6edca44 -->

## Current implementation observed

- `src/tarav/l2/lines/line.py`: `DiagramLineShip` is a frozen projection with
  mandatory `block_ship`, annotations, editions, type IDs and legacy findings.
  `DiagramLineEdition` supplies text through its retained annotation.
- `src/tarav/l2/lines/records.py`: `LineShipRecord` requires `model_ship` and
  `block_ship`; `BlockShipRecord` requires `model_ship`. Their base `TypedShip`
  comes from `l2.unsorted.records` and is a FileRecord, not TaravEntity.
- `src/tarav/l2/lines/block.py`: `DiagramBlock` is another Model-bound projection.
- `src/tarav/l2/lines/workflow.py` and `identity.py` own the existing workflow
  declaration. Workflow Ship is `9409e0c4-a058-4a68-abca-daaac011ce31`;
  workflow class TypeShip is `25a55b5b-6aa3-485e-a4cd-3c309a2a67fa`.
- `src/tarav/l3/runtime.py` imports the l2 workflow declaration. Runtime is
  concurrently edited by request 828; coordinate any later wiring changes.
- `src/tarav/l0/kernel/records.py`: TaravEntity provides a stable Ship identity,
  RecordInterface, `_to_record` / `_from_record`, `ships()` and `obj_context`.
  New classes need class-local `class_entity()` declarations.
- `src/tarav/l1/references` provides typed locator-based resolution; an arbitrary
  Ship alone is not a universal entity loader. Do not invent such a guarantee.

There is no `tarav.l1.lines` package at inspection time. Existing projection
subtypes such as DesignLineDefinition do not supply the proposed new base.

## Proposed implementation shape

These mechanics are agent proposals implementing the accepted semantics; exact
helper names may change to match inspected conventions without changing scope.

```python
from tarav.l0.kernel import Ship
from tarav.l1.lines import Line

line = Line(id=Ship("4c40f26f-0c1a-481b-884b-072076318ad1"),
            text="The exterior is red.", scope=vehicle)
detail = Line(id=Ship("624667cc-b72e-455f-b37b-4dd2e50a2791"),
              text="The finish is matte.", scope=line)

assert detail.scope is line
assert line.scope is vehicle
```

Use keyword-oriented construction. `vehicle` is any supplied TaravEntity, not
a class or record invented by Lines. Identity follows the existing Ship
contract. Text is a string; do not parse it into facts or normalize its meaning.
The Python subtype supplies typing; no parallel mandatory statement-kind field.

### Packages and workflow ownership

Introduce `tarav.l1.lines` for Line and LinesWorkflow. Move the existing
workflow declaration/identity to this lower layer, preserving both established
UUIDs. Update maintained imports to the canonical path; do not create another
Lines workflow or a new root re-export. Existing l2 consumers can depend on l1.

Keep legacy projection/record mechanics in l2 until their consumers are
deliberately migrated. The new primitive must not import Models, unsorted,
runtime, CLI, legacy scoring, or the concurrent SKW implementation. Register
Line through ordinary trusted runtime composition and give it a fresh TypeShip,
not the identity of a legacy class with a different record contract.

### Scope and retained representation

In-memory `.scope` returns the supplied TaravEntity. Preserve a stable scope
Ship in the record rather than recursively serializing its object graph.
Include that edge in `ships()` and expose a `scope` route through the ordinary
context hook. Context expansion should be lazy/one-hop, not recursively flatten
an entire scope chain or include a higher-layer context runtime in l1.

Preferred minimal detached-record behavior: retain `scope_ship`, then allow
explicit binding to the corresponding entity (or a caller-provided resolver).
Validate both TaravEntity type and matching identity before binding. Reading
`.scope` on an unbound record reports that it is unresolved; it must not return
None, substitute a fake entity, or pretend a Ship is the resolved scope.
Use existing binding/resolution mechanics if they already meet this contract;
otherwise a small Line-local helper suffices, not a new global resolver.

Record round-trip must preserve identity, text, scope identity and concrete
type without needing the target to be available. Resolution is separately
tested against actual entities. Missing scope fields and malformed identities
are structural errors; an unavailable target is an explicit resolution state.
Do not infer scope from storage location, Block membership or text.

No scope-cycle policy was selected by the user. Do not silently impose a tree
or claim recursive scopes terminate. One-hop access and serialization must
remain bounded even if supplied objects form a cycle; any future whole-graph
walk must handle revisits explicitly.

### Editing and interpretation

Permit ordinary explicit text updates using a small property/setter or method
consistent with nearby entities. They preserve the Line's identity; do not
create editions, claim approval or run semantic checks automatically. Preserve
the declared scope unless explicitly changed. Scope rebinding used for loading
must not accidentally become an operation that changes semantic scope.

### Migration boundary

Moving workflow Python paths needs a search of imports, runtime wiring, tests
and retained class descriptors. Preserve UUIDs and report any external retained
metadata requiring an explicitly scoped path migration; never repair on load.

Do not reinterpret legacy LineShipRecord as Line. Old Block attachment may
suggest a scope, but does not establish it. Legacy records, evidence and Models
remain readable through their existing types. This is a distinct primitive
alongside the old application, not an alias or fallback. A later conversion
must explicitly select text/edition and scope; wholesale data migration and
retirement of legacy application types are deferred.

## Execution.Plan

1. Recheck current worktree, relevant guidance and imports. Coordinate runtime
   and ARCHITECTURE edits with the agents implementing 828; preserve their work.
2. Add focused tests for construction, required entity scope, Line-to-Line
   scope and the absence of Model/Block prerequisites.
3. Introduce l1 Line and relocate the workflow declaration, preserving workflow
   and class identities. Add records, explicit binding and context exposure.
4. Update trusted registration/imports and architecture documentation. Do not
   add a CLI, extraction engine, Block API or checks framework for this slice.
5. Verify record round-trips before/after scope binding, wrong-type and wrong-ID
   rejection, unavailable targets, lazy scope expansion, and text edits that
   preserve identity. Test supplied cycles do not recurse during serialization.
6. Test class entities, owning workflow, import direction and legacy record
   readability. Run focused tests and `tests/test_architecture.py`, then broader
   verification proportional to affected imports. Use uv and inspect the diff.
7. Apply product-surface Breadcrumb capture to actual implementation changes,
   log checks and migration gaps here, then complete bounded Wiki capture and
   scoped evidence commits. Do not commit unrelated concurrent changes.

## Impl.Req.Wiki

Wiki root: `/Users/pereiro/projects/taravangian-project/tarav-md/notes/wiki`.
Create `lines-workflow.md` for this accepted scoped-statement model and update
`daily/2026-09-30.md`. `kernel-writting.md` remains a principles-only writing
note: do not reintroduce architecture, SKW relationships or implementation
history there. Original design User Turns are attached in this request so
another session can implement it without reconstructing the conversation.

## Impl.Log

### 2026-09-30 — Design

Inspected existing l2 Lines, kernel entity records, references and runtime
wiring. New Line semantics are defined independently of legacy Models.
No product code changed or product tests run during Design. Other agents'
uncommitted SKW/Checks/POI changes and skill-source migrations remain untouched.
Scoped start checkpoints: tarav-py `50961d1a`, tarav-md `927fbae4`.

Design capture: the request's six Breadcrumbs and the topical note's five
Breadcrumbs submitted and audited successfully, with no findings. Daily capture
is pending: another agent concurrently inserted markers for session alias
`1f561f5d` without its declaration, and shifted existing label positions.
The daily submission failed; our appended section remains alongside their
work. Do not commit or repair their edits as part of this request. Completion
scope excludes the shared daily file; its submission/audit/closure must be
reconciled after the concurrent writer finishes. No product tests were run.

### 2026-09-30 — Develop extension and implementation

The user requested Lines, typed Context and Models disconnection together.
This extends the original scope: default context remains the general explorer;
explicit `type` selects a read-only specialized Context. Unsupported types
fail. `LineScope` exposes the single interpretive dependency, not placement.
Models execution is disabled in place, not removed; guidance and retained
data remain unchanged. This supersedes the earlier legacy-callability promise.

Implemented:
- `tarav.l1.lines.Line`: identity, text, one TaravEntity scope, scope Ship
  record projection, explicit identity-checked binding, and lazy scope context.
- LinesWorkflow moved to l1 with established identities preserved; maintained
  imports updated. Legacy l2 projection/record implementations remain present.
- Typed context selection in standalone and runtime interfaces; object
  `.context(type=...)` delegates through a host-configured Kernel hook.
- `LineScope` ContextFolder specialization; default ContextExplorer unchanged.
- Models construction/resolution/creation/projection/application and Project
  integration entry points raise `ToImplementError` before their old work.
- Explicit SKW ModelPublication access raises the same error; package checks
  and builds no longer execute model publications automatically, reporting
  `model-publication-disconnected` instead. Other document builds still run.

Start checkpoint: `0a6692d3`. No retained Model data was migrated or touched.
External class metadata referring to the old workflow Python path has not
been migrated; no compatibility alias or runtime repair was added.

Verification uses the existing `.venv/bin/python`: uv command startup and
editable reinstall both panic in system-configuration (NULL dynamic-store
object). The focused Ruff selection and `git diff --check` passed.
Product Breadcrumb capture remains pending across changed source/test/docs:
Chatlas cannot create its Normal Model lock under the filesystem permissions.
No substitute Turn evidence was invented. Completion evidence commit remains
pending with that capture; the start checkpoint had an explicit evidence gap.

Combined verification: 128 tests passed across scoped Lines, architecture,
Context, runtime, object records, Type declarations, SKW skills/loading,
workflow identity and Assertion objects. These are targeted suites, not a
claim that legacy Models behavior tests remain valid after disconnection.
The Wiki daily entry records implementation facts with source/test pointers;
its conversational Breadcrumbs and closure remain pending too.
