# Path Notebook with schema and path context

## Impl.Abstract

Status: ready. Knowledge.Surface: wiki. Alignment.Mode: Interactive.

Implement a typed PathNotebook under the existing Notebook, with SchemaBlocks
linked to registered schema Ships and PathBlocks linked to registered Path Ships.
Lines use ordinary Block ancestry for interpretation. Keep associations out of
PathRegistry. Reuse Notebook storage and capture; no new database, extension UI,
general annotation engine, lineage or review policy.

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
-->

## Design

The User requested a simple Notebook specialization whose Blocks reference
registered paths. They clarified that schemas have Ships too and can have Lines;
a subpath note's interpretive context includes all parent notes up to the schema,
using the same ancestry semantics as other Notebook Lines. Develop is authorized.
<!-- tarav.context 0f5bad01:1447ec75ae51ec24 -->
<!-- tarav.context 0f5bad01:a3d0027b7576ede9 -->
<!-- tarav.context 0f5bad01:f2ce9196bf104645 -->

Inspected state: `l2.notebook.Notebook` is already a typed Block with storage,
capture and nested checks; `l1.notebook.Notebook` is its shared persistence service.
JSONView already has an identity and PathEntry declares its owning View and exact
RFC 6901 pointer. Registry enrollment normally registers every parent position.
The implementation needs an integration above those independent workflows.

Data shape first: `l2.path_notebook.PathNotebook(Notebook)` retains registry_ship;
SchemaBlock retains schema_ship; PathBlock retains path_ship. Each Block has its
own stable identity and inherited authoring semantics. A PathNotebook contains
Lines and SchemaBlocks; schema/path Blocks contain Lines and PathBlocks. Typed
Record projection/loading and ships() retain the registry links. These Types
belong to NotebookWorkflow; no separate workflow or storage partition is needed.

`project.paths.notebook()` selects its PathNotebook under the Project Notebook
without writing. Explicit create provisions via normal Notebook operations.
Schema/path add operations work in memory; ordinary save persists the tree.
Adding a path materializes only its registered parent chain, including the empty
root position. JSON Pointer token boundaries, not decoded slash characters or
text prefixes, determine parents. Missing/retired/ambiguous links fail explicitly.
Schema and path reads never create records or mutate PathRegistry.

A current path label is computed from its Path Ship through Label. Reassigning
that Ship within the same parent retains its note; changing its parent must not
silently change a reader's interpretive context. The current-path accessor detects
an ancestry mismatch and asks for explicit Notebook maintenance. Ordinary stored
Blocks remain readable for historical inspection. No automatic reparenting,
deletion or title Line rewriting is part of this request.

Subtract before adding: inherit capture, scopes, mixed-order storage and checks;
do not build another annotation store or duplicate Line text in PathRegistry.
Note Lines do not automatically become supported/reviewed; existing concrete
Line/Block policies remain responsible for that behavior.

## Impl.Req.Wiki

Product tarav-py; Wiki owner tarav-md/notes/wiki. Relevant Notes: path-registry.md,
line-notebook.md and label-formats.md. Capture typed note links and schema/path
ancestry into path-notebook.md and daily/2026-10-22.md. Use the refreshed exact
session above for request/source/Wiki evidence. Preserve older evidence gaps.

## Execution.Plan

- [ ] Feature: three typed Blocks, explicit schema/path add/read operations and
  Project selection. Test persistent round trips, root/escaped/numeric pointers,
  inherited context and ordinary capture, missing/duplicate/retired links,
  rename continuity, ancestry drift and read-only selection.
- [ ] Integration/closure: runtime registration, architecture/guidance, source
  capture, focused and full Project checks, bounded Wiki capture and scoped
  evidence commits. Show a real Line schema in isolated Notebook data.

## Impl.Log

- Read Project instructions and current Notebook/registry/Project code before
  changes. Plan above is the todo list. Exact Chatlas session refreshed once;
  latest User design and Develop Turns resolved.
- Concurrent configuration/Agent work is present. Start checkpoint preserves
  pre-existing work; scoped implementation commits do not include unrelated
  files except any shared mixed surfaces, recorded explicitly.
