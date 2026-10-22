# Shared Label formats and consumer adoption

## Impl.Abstract

Status: complete. Knowledge.Surface: wiki. Alignment.Mode: Interactive.

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
<!-- tarav.breadcrumb 71f8d1ea2295 -->
<!-- tarav.breadcrumb 9bf9928bdc58 -->
<!-- tarav.breadcrumb 1296bf2be560 -->

Data shape first: Label is an immutable string value with construction and
Pydantic validation/JSON Schema. Format implementations own their matching
rules; Label accepts their union. Dotted format preserves the existing rule of
at least two capitalized alphanumeric segments. JSON Pointer accepts the empty
root and slash-prefixed tokens with only ~0/~1 escapes, without normalization.
Consumers can select a format explicitly (PathEntry requires JSON Pointer),
while later Label subclasses can narrow the supported format tuple.

The dependency-clean value belongs to l0.label_formats. Its identified Workflow
belongs to l1.label_formats and depends on Kernel, while Kernel imports only the value module; no upward import
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

- [x] Feature/refactor: implement Label/format rules, Workflow, Pydantic contract
  and consumers. Verify dotted and pointer construction/edit/load/schema, Type
  names, restricted Label subtype, stable Notebook review state, path checks and
  architecture. Run focused tests, Ruff and full Project status.
- [x] Consumer adoption: execute extension request 016, test actual Python
  reader and Node surface, package/install under its project guidance.
- [x] Capture/closure: source Breadcrumbs, API and architecture guidance, scoped
  Wiki capture, evidence audits and commits. Keep known unrelated findings clear.

## Impl.Log

- Inspected Lines, Notebook evidence/review, Type identity, PathRegistry and
  extension title selection. Existing path/Notebook tests provide baseline.
- Exact session refreshed once; supporting User Turns resolved. Plan above is
  the todo list. Concurrent Product Review request 949 remains separate.
- Start checkpoints: Python `996d19d76d53b922a97b8c8a005310b1e46144ff`,
  Markdown `d40407427f7c968421ce3eb5b38e0b71f2166fd5`, extension
  `b258a2eacae20a03065c0c0eb4bfb0db5f89a47a`. Cold-read request before edits.
- Focused values/Notebook/path/Record tests passed 62 cases. Initial failures
  exposed Label subclasses at the strict JSON boundary; explicitly project
  Labels to plain strings without accepting arbitrary non-JSON objects.
- Evidence/architecture run: 81 passed, three architecture failures from the
  initial Workflow/value aggregate dependency. Moved identified Workflow to l1
  and retained dependency-free values at l0; corrected architecture rerun passed
  all 56 tests. No higher-layer Kernel dependency or runtime callback added.
- Both live reviewed title Lines load as ReviewedLabel with zero support/review
  problems. Type Ships and wire names preserve exact historical reconstruction.
- Full status (87 completed checks, none incomplete) reported four test failures:
  the three earlier architecture failures and generated System Project Type
  naming. A targeted run reproduced the latter: scaffold embedded a raw Python
  package slug in a semantic label. Update that producer to capitalized dotted
  words, keeping Python identifiers unchanged. Adopt the corrected label in this
  machine's System Project too (separate request there). Do not expand Label to
  accept arbitrary slugs merely to conceal the generator mismatch.
- The generator/system/tree rerun passed 13 tests. Final focused values run
  passed 62; corrected architecture passed 56; all 28 Notebook evidence tests in
  the original 84-test run passed. Ruff passed. Full status was run before these
  last fixes; its four failures were resolved by the targeted reruns, not a new
  full-run claim.
- Extension tests: 8 Python tests passed, including pointer-title search through
  the actual worker; Node: 29 passed, three browser-only skips. Version 0.1.25
  packaged and installed successfully. Earlier fixture assertions were updated
  to account for the newly added pointer title (117 records and nonempty Model).
- Final combined run: 131 tests passed (Label, Notebook, path registry, Record
  contract, Project generators/tree and architecture), and Ruff passed. Final
  routine status completed 21 checks, none incomplete; remaining findings are
  Gitleaks, two synthetic markers and Product Review coverage. The previous full
  run's four failures were corrected and verified by this combined run; no claim
  that a second full run was performed. Existing persisted test Actions from that
  full run remain until the next matching Project test-suite status.
- Source audit covered 25 surfaces: all new Breadcrumbs resolved; five older
  TurnUnavailable findings remain (Lines init, extension reader/test/README).
  Other findings were position updates. Guidance and System marker JSON use
  external capture. Final Markdown status completed 1,215 checks, none incomplete;
  existing harness, Git, SKW and two unrelated Wiki provisional-marker findings
  remain. Capture destinations: label-formats.md, path-registry.md cross-link,
  daily/2026-10-22.md.
- Concurrent task 952 checkpoint `7595c061` captured the verified Python product
  files before our slice commit. Preserve that commit; completion here records
  their provenance and verification. No history rewrite or duplicate code edit.
- System Project adoption ran through its own environment with runtime assembly;
  Project/Type UUIDs and active list verified unchanged. It has its own bounded
  request at ~/Documents/tarav/system/notes/live/001-shared-label-adoption-impl-req.md.
- Completion commits: Python `9c5a6afa`, extension `09d3869b`, Wiki `2526b6cf`,
  System Project `688e6512`; all commit Breadcrumb audits passed. Extension
  version 0.1.25 was repackaged after source capture and force-installed.
- Final schema boundary check tightened exported pattern end anchors: bare `$`
  can accept a trailing newline in JSON Schema regex search, unlike Label's
  fullmatch. The schema test now checks accepted/rejected literal examples,
  including a trailing newline, instead of mirroring implementation constants.
  Label/path/Record rerun passed 40 tests. This is the only change after the
  131-test combined run; it does not change accepted Python Label values.
