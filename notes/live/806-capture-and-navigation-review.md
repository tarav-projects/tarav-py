# Capture and navigation: findings and proposed solutions

Date: 2026-09-25. Status: open review; proposals have not been implemented or
approved as an implementation contract.

Source session: `codex:01a0d86c-9538-7be1-af96-014cd4203d61`.
This note records the Agent's code review and proposed responses requested by
the User. It does not promote the proposals into accepted design.

## Scope and design constraints

The review inspected the current working tree, including in-progress changes,
in Kernel, Context, Record Archive, and Breadcrumb capture. It is not a review
of the whole distribution. The relevant existing suite passed 52 tests:

```sh
uv run pytest -q tests/kernel/test_context.py \
  tests/kernel/test_context_workflow.py tests/record_archive tests/breadcrumbs
```

Additional disposable probes reproduced the findings below. Their original
script is `/tmp/tarav-review.vu5OJY/probe.py`; that temporary path is not durable
evidence. Reproduction steps and observed results are retained here instead.

The proposals preserve Tarav's deliberate choices: capture before integration,
evolving code as semantic authority, evidence-driven manual recovery, and
human-paced workflows. They do not require automatic semantic repair, stable
schemas, universal integration, or a drift-free system.

## 1. Submission can overwrite intervening edits

**Priority: high — possible loss of user work.**

[`submit_annotations()`](../../src/tarav/breadcrumbs/surfaces.py) reads the
surface once, prepares and stores Breadcrumbs and attachments, then atomically
replaces the surface from that original snapshot. It neither checks whether
the source changed nor coordinates competing writers. Atomic replacement
prevents a partial file, but does not prevent lost updates.

Reproduction: submit a two-line Markdown fixture containing `EXAMPLE` as its
provisional marker. In a custom workflow's attachment callback, replace the
first line with an intervening human edit. Submission reports `ok`, but the
result contains the original first line. The callback deterministically
simulates a write between the initial read and final replacement.

### Proposed response

Use explicit conflict detection at the publication boundary. Retain the
original content fingerprint, prepare the intended replacement, and refuse to
replace a changed surface. Return a conflict with enough evidence to inspect
the original, current, and proposed versions; let the agent decide how to
reconcile them. Preserve the current file and do not silently retry or merge.

Coordinate cooperating Tarav writers with a per-surface lock covering the
read/check/write operation. A fingerprint check followed by replacement still
has a race against editors that ignore that lock; document that limitation
rather than presenting the check as a universal compare-and-swap guarantee.
Preserving the proposal and conflict evidence gives a recovery path.

Submission also writes attachments before publishing the surface. Define how
a conflict or interruption reports that partial state, and make a deliberate
retry able to identify prior work without silently multiplying Breadcrumbs.
A small submission receipt or journal is a candidate if required; full
cross-store transaction machinery is not a prerequisite.

Acceptance: an intervening edit survives and submission reports a conflict;
cooperating concurrent submissions cannot silently overwrite each other;
interruption after attachment creation leaves inspectable evidence and a
defined retry path.

## 2. One damaged or colliding entry disables context listing

**Priority: high — blocks the ordinary evidence-discovery path.**

[`ContextWorkflow._populate()`](../../src/tarav/context_workflow.py) calls
`archive.get()` for every placement. [`RecordArchive._entry()`](../../src/tarav/record_archive/__init__.py)
raises for a missing artifact, and the exception aborts the whole listing.
[`ContextBuilder.add()`](../../src/tarav/kernel/context.py) similarly aborts on
duplicate names, including collisions between runtime and retained entries.

Reproductions:

- Create a subject archive with eight valid entries, then move one artifact
  aside. `runtime.context(subject).ls()` raises `FileNotFoundError`; another
  entry remains directly readable through the archive.
- Store a valid retained entry named `class`. The write succeeds, but context
  listing raises `Duplicate Context entry: class` because the runtime already
  contributes that name.

### Proposed response

Separate discovering a placement from opening and validating its target.
Return healthy entries together with inspectable findings for broken ones;
failure to open one entry should remain local to that entry. Preserve its
name, retained locator, and specific failure so an agent can investigate.
Handle known data/lookup failures explicitly; do not hide arbitrary programming
errors behind a broad exception handler.

For collisions, preserve both contributions and report their origins. A
source-qualified inspection path could expose them without silently choosing
a winner. Ordinary ambiguous lookup should report the ambiguity. The exact
qualification interface remains a design choice; the minimum requirement is
that unrelated entries and both conflicting contributions remain inspectable.
Rejecting collisions only on write would not handle a later code change that
introduces a new runtime entry.

Acceptance: a missing artifact leaves healthy siblings listable/openable;
collisions expose both sources without shadowing; opening a damaged or
ambiguous entry reports its own problem; reads do not repair retained state.

## 3. Ordinary edits invalidate Breadcrumb position observations

**Priority: medium — repeated capture friction and avoidable recovery work.**

[`BreadcrumbStore.resolve()`](../../src/tarav/breadcrumbs/store.py) checks
recorded file/line observations for the canonical label. An intact label moved
to an unrecorded line is reported as missing. Submission records positions for
new labels but does not refresh existing labels shifted by the edit.

Observed during the preceding wiki capture: after adding prose and session
declarations, 167 older labels required new position observations (120 in
`record-framework.md`, 43 in `context-graph.md`, and four in the daily note).
Explicitly recording their current positions restored passing audits. This
does not imply every old position was valid before the capture.

### Proposed response

Provide an explicit, bounded observation operation for one selected surface.
Use the existing surface parser to enumerate exact canonical labels outside
literal examples. For each unique label with a retained Breadcrumb, append a
new observation when its current position is not already recorded. Preserve
old observations and all attachments.

Missing, duplicated, or unknown labels remain findings; do not infer a match
from neighboring prose, mint replacement identities, or change semantic
attachments. Audit and resolution remain read-only. The mutating capture
workflow can explicitly invoke observation after its final surface edit.

Acceptance: inserting text above a label can be handled by one explicit
observation pass; old observations remain; duplicates are reported rather than
chosen; repeating observation on unchanged content adds no redundant entries;
code examples containing labels are not treated as active anchors.

## 4. Listing repeatedly reads and validates the entire index

**Priority: medium — avoidable cost before an agent selects any material.**

[`ContextWorkflow._populate()`](../../src/tarav/context_workflow.py) lists
placements, then calls `get()` for each one. Each Dictionary Archive `get()`
accesses `entries`, rereading and validating all of `entries.json`.
[`ArchiveCursor.ls()`](../../src/tarav/record_archive/navigation.py) uses the
same list-then-get pattern for typed archives.

Reproduction: instrument `Path.read_text` for `entries.json`, then list a fresh
context with eight retained entries. The probe observed nine complete index
reads. For N entries, validating N items on each of N lookups creates quadratic
index-processing work, in addition to per-entry work.

### Proposed response

Read and validate one index snapshot per listing. Build lazy entry handles
from that snapshot, loading selected entry Records and artifacts only when
needed. Keep single-name lookup and mutation semantics separate; mutations
should continue rereading the current index under their existing lock.

Decide which cheap placement metadata listing needs, such as directory kind.
Do not add a second authoritative index just to avoid a file read. A first
improvement can retain per-entry metadata reads while eliminating repeated
full-index reads; deeper laziness can follow the failure-isolation work above.

Acceptance: cold listing reads the full index once, does not deserialize cargo,
and performs linear index work. A selected open still uses trusted Type
dispatch. Tests specify whether an existing view is a snapshot and confirm
that a fresh view sees later changes.

## Suggested order

1. Protect submission against lost edits and make partial outcomes inspectable.
2. Isolate navigation failures and name collisions.
3. Add explicit exact-label observation to the capture workflow.
4. Reuse listing snapshots; coordinate lazy handles with item 2.

Implementations should add focused regression tests for the reproductions
above. The existing 52 passing tests establish a baseline, not coverage of
these failure modes. No implementation or Git commit is authorized by this
note alone.
