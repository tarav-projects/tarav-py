# Path Notebook with schema and path context

## Impl.Abstract

Status: complete. Knowledge.Surface: wiki. Alignment.Mode: Interactive.

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
<!-- tarav.breadcrumb aa4e87b3cfc3 -->
<!-- tarav.breadcrumb 29908b3ac04b -->
<!-- tarav.breadcrumb 1aa901496934 -->

Inspected state: `l2.notebook.Notebook` is already a typed Block with storage,
capture and nested checks; `l1.notebook.Notebook` is its shared persistence service.
JSONView already has an identity and PathEntry declares its owning View and exact
RFC 6901 pointer. Registry enrollment normally registers every parent position.
The implementation needs an integration above those independent workflows.

Data shape first: `l2.notebook.PathNotebook(Notebook)` retains registry_ship;
SchemaBlock retains schema_ship; PathBlock retains path_ship. Each Block has its
own stable identity and inherited authoring semantics. A PathNotebook contains
Lines and SchemaBlocks; schema/path Blocks contain Lines and PathBlocks. Typed
Record projection/loading and ships() retain the registry links. These Types
belong to NotebookWorkflow; no separate workflow or storage partition is needed.

`project.paths.notebook()` and `project.notebook().paths` select its PathNotebook
inside the already existing Project Notebook without writing. Explicit Project
Notebook create adds the Path Notebook child, including on an existing edited
layout, while preserving all its prior content and identity. Explicit Path
Notebook create uses the same parent and normal Notebook operations.
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

- [x] Feature: three typed Blocks, explicit schema/path add/read operations and
  Project selection. Test persistent round trips, root/escaped/numeric pointers,
  inherited context and ordinary capture, missing/duplicate/retired links,
  rename continuity, ancestry drift and read-only selection.
- [x] Integration/closure: runtime registration, architecture/guidance, source
  capture, focused and full Project checks, bounded Wiki capture and scoped
  evidence commits. Show a real Line schema in isolated Notebook data.

## Impl.Log

- Read Project instructions and current Notebook/registry/Project code before
  changes. Plan above is the todo list. Exact Chatlas session refreshed once;
  latest User design and Develop Turns resolved.
- Concurrent configuration/Agent work is present. Start checkpoint preserves
  pre-existing work; scoped implementation commits do not include unrelated
  files except any shared mixed surfaces, recorded explicitly.
- Cold-read request before product edits. Checkpoints: Python
  `247f77bd98b6f70c06f30dc1d8e5428404bf9b98`, Markdown
  `4c74b707fd1a6eeaedff278f77df84a2d3e1b3e9`.
- User clarified during execution that the default Path Notebook belongs inside
  already existing Project Notebooks and describes their Types. Implemented
  ProjectBlock.paths and explicit ProjectBlock.create adoption without replacing
  the parent or existing layout. This steering arrived after the pass's single
  Chatlas freshness boundary; its exact new Turn remains to be indexed separately.
- Core link Types live at l1.notebook.paths; PathNotebook integration lives with
  other typed Notebooks in l2.notebook to avoid a reverse module dependency.
- Focused run passed 86 tests, with one unrelated global architecture failure
  reporting the concurrent actions/agent/operator_context cycle. No Path Notebook
  dependency cycle was reported. All path behavior and Record examples passed.
  Initial tests corrected an incorrect SubjectState attribute and ensured moves
  with missing parent notes report ancestry drift rather than ordinary absence.
- Corrected integrator run passed 14 tests; final local path/Record/new
  architecture contract run passed 19. Ruff passed. The old edited-layout test
  now verifies the requested addition while preserving every earlier child and
  the byte content of the existing Line.
- Live adoption: existing Tarav Project Notebook f6c673d6-88e7-5071-8533-ab0a6450c6e6
  gained PathNotebook aab88039-65ca-5411-8f8f-372111a384f8. Exactly one membership
  Record changed and one empty child was added; the other 2,165 Records remained
  byte-for-byte unchanged. Shared Notebook data was clean before its checkpoint
  and scoped adoption commit. No schema enrollment or generated note text.
- A final create-path inspection found that preparing notes before creating an
  unpersisted parent could let parent default construction replace the pending
  child with an empty one. The explicit create now attaches that pending child
  before persisting the parent; a new test verifies the prepared Line survives.
  Final local run passed 20 tests; Ruff passed. Capture audit resolved all 12
  surfaces with zero errors; its 26 findings were position updates only.
- Markdown full status completed 1,215 checks, none incomplete. Existing harness,
  Git, SKW and two other Wiki provisional-marker findings remain. Source capture
  reused the exact original design Turns; the post-refresh default-placement
  steering is retained verbatim in this conversation and summarized above, with
  exact newer Chatlas-turn indexing still pending rather than fabricated.
- Python full status completed 87 checks, including 66 pytest suites, with no
  incomplete checks. Two tests still expected the former three-branch Project
  layout; updated those expectations for the default Path Notebook while
  preserving custom layouts and existing notes. The focused Project Notebook
  and Path Notebook rerun passed all 13 tests; Ruff passed. The concurrent
  Agent architecture cycle was fixed by its owner, and its exact architecture
  check now passes. Remaining full-run POIs concern existing Gitleaks, Product
  Review coverage and synthetic test markers. The full run preceded these final
  expectation corrections; it was not repeated in full.
- Committed product implementation in
  `2e52b1a322eec472c2313b4bdb03b4b657eca786`, shared Notebook adoption in
  `1324ff0c9db0cfe8b8b767b141d3d236d6433e9f`, and Wiki capture in
  `851fcfdb8817dd77c75d3374d8802b492708ab85`. Evidence audits passed for
  all three commits. Wiki destinations: path-notebook.md, path-registry.md,
  daily/2026-10-22.md. Completion records these results and the final layout test
  correction; unrelated concurrent Product Review work remains untouched.
