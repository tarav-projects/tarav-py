# Shared Label formats and consumer adoption

## Impl.Abstract

Status: ready. Knowledge.Surface: wiki. Alignment.Mode: Interactive.

Create the LabelFormats Workflow and a shared Label value accepting the current
dotted Block format and RFC 6901 JSON Pointers. Replace the BlockTitle Python
API and update all maintained consumers: Lines, Notebook review, Type names,
PathRegistry pointer validation and the extension reader. This does not build
the PathSchema viewer, Path Notebook or a generic annotation workflow.

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
-->

## Design

The User selected Label as the shared abstraction. It accepts any supported
format; later specializations may restrict formats. Initial formats are citable
dotted words and paths. The User requested LabelFormats and updating all
consumers through Develop.
<!-- tarav.context 0f5bad01:894fe2cbf2c3c3b5 -->
<!-- tarav.context 0f5bad01:67e0fcc7bda286d7 -->
<!-- tarav.context 0f5bad01:825b33d4f96b76f2 -->

Data shape first: Label is an immutable string value with construction and
Pydantic validation/JSON Schema. Format implementations own their matching
rules; Label accepts their union. Dotted format preserves the existing rule of
at least two capitalized alphanumeric segments. JSON Pointer accepts the empty
root and slash-prefixed tokens with only ~0/~1 escapes, without normalization.
Consumers can select a format explicitly (PathEntry requires JSON Pointer),
while later Label subclasses can narrow the supported format tuple.

The dependency-clean value belongs to l0.label_formats. Its Workflow module
depends on Kernel, while Kernel imports only the value module; no upward import
or new runtime callback is required. Runtime registers the identified Workflow.
Label is a value primitive like Ship, not a Line or an independently stored
Entity. LabelLine is its Lines consumer, retaining normal authoring context;
ReviewedLabel composes Notebook support and review. Type names validate through
Label at TaravClass construction and Record loading. PathEntry reuses the JSON
Pointer format instead of keeping a separate regex. Arbitrary strings such as
file names, UI captions and SKW local slugs are not automatically semantic Labels.

Subtract before adding: remove BlockTitle/ReviewedBlockTitle Python classes,
imports and duplicated validators; update their callers and documentation.
Preserve their existing Type Ships and wire Record Type names: two live reviewed
title records and their Git-pinned snapshots name those Types. These retained
wire names are not old Python API aliases or a fallback reader. Keeping them
unchanged preserves review state digests and exact historical reconstruction.
No live data rewrite is required. All live registered Type names satisfy the
existing dotted rule (verified before edits).

## Impl.Req.Wiki

Product: tarav-py; Wiki owner tarav-md/notes/wiki. Read existing path-registry
and line-notebook notes. Capture the shared syntax decision and implemented
consumer boundaries in label-formats.md and the daily Note, with source links.
Extension adoption is request 016 in that repository; execute after Python.

## Execution.Plan

- [ ] Feature/refactor: implement Label/format rules, Workflow, Pydantic contract
  and consumers. Verify dotted and pointer construction/edit/load/schema, Type
  names, restricted Label subtype, stable Notebook review state, path checks and
  architecture. Run focused tests, Ruff and full Project status.
- [ ] Consumer adoption: execute extension request 016, test actual Python
  reader and Node surface, package/install under its project guidance.
- [ ] Capture/closure: source Breadcrumbs, API and architecture guidance, scoped
  Wiki capture, evidence audits and commits. Keep known unrelated findings clear.

## Impl.Log

- Inspected Lines, Notebook evidence/review, Type identity, PathRegistry and
  extension title selection. Existing path/Notebook tests provide baseline.
- Exact session refreshed once; supporting User Turns resolved. Plan above is
  the todo list. Concurrent Product Review request 949 remains separate.
