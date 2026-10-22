# Review batches reuse class identities and stay small

<!-- tarav.sessions
ec6cf584 = codex:01a1563b-2992-7c62-8a38-05c1cc75b1fe @ec6cf5849bb6c4e66f011b015415da94eeb1a17634872aa4fb9e25d8e065ab53
-->

## Impl.Abstract

Knowledge.Surface: wiki. Status: ready. Develop the existing Review Tracker:
every batch attaches to an existing subject UUID; Tarav's selected specialization
links that UUID to a class's Type identity. Keep the base batch product agnostic.
Do not construct another semantic organization or require every class to have a
batch. The User explicitly selects implementation through Hugentics Develop.
<!-- tarav.breadcrumb 9361654601b1 -->
<!-- tarav.breadcrumb fd42f233ba6f -->

Also bound the number of chunks per batch. The User delegates the default choice;
Agent policy chooses eight chunks, roughly 32 KB at the default 4 KB map target.
It is a chunk-count bound, not a byte limit, because chunks can grow. Put the
control in Project product_review.max_chunks and the generic tracker constructor.
<!-- tarav.breadcrumb 6dca509a41fe -->

## Design and current mechanics

Inspected l1.product_review.model, l2.product_review.tracker/commands/checks,
l2.project.product_review, runtime registration, Ship/TypeShip, TypeRegistry,
TaravClass.bases and existing review/Record tests. Batch currently has an ID,
repository and revision history but no subject. Revisions pin map/chunk states.
TaravClass already supplies class identity, bases, Workflow and Context. Reuse it.
The production Review partition is absent; no batches/completions need migration.
Existing generic tests pass (15 tests). Never repair old records during reads.

Data shape first: Batch.subject is a required generic Ship UUID. BatchRevision
also pins that subject so presentation and past evidence cannot be reinterpreted.
Batch.subject remains fixed for that batch; changing its organizing subject means
retiring it and creating another. Revisions update content/membership, not subject.
ClassBatch specializes Batch.subject to TypeShip. ClassReviewTracker selects it
and resolves new attachments through the existing Type graph rooted in the
supplied trusted Record Type registry (including bases and Workflow classes).
ClassBatch.subject_entity() returns the existing TaravClass, retaining its bases
and Workflow. Do not persist duplicate class names, parents or source paths.

Keep registry resolution out of the generic model/loader. Generic batches can
name UUIDs owned by other consumers. The caller owns proving such a subject exists;
Tarav's specialization performs that proof against its registered class identities.
Only class identities are accepted there, not an object instance's UUID or a
Workflow entity UUID. There is no one-batch-per-class requirement.

Class subjects are visible in create/list/show/history/inspect and the token frame.
The installed CLI requires --subject on create and uses the Project-selected
ClassReviewTracker; the generic Python ReviewTracker accepts arbitrary subject
UUIDs. Existing batch reads preserve their concrete subtype, including retirement.

max_chunks must be a positive integer; default eight. Create/revise/complete reject
current batches above the bound before writing review Records or retaining chat
evidence. Lowering the control reports existing oversized batches through the
normal per-batch Review Action. Records and old completions remain readable;
checks never split batches automatically. Empty and duplicate memberships remain
invalid. Multiple small batches may attach to the same class.

Subtract before adding: replace the anonymous creation path rather than add a
second API/compatibility route. No production migration is necessary. No recursive
batch graph, class inventory copy, semantic grouping algorithm, Notebook creation,
mapping rebuild, or actual User review is part of this bounded implementation.
The existing type graph is navigated through the class attachment.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki. Update product-review-tracker.md
and daily/2026-10-22.md, grounding the generic UUID boundary, class specialization
and size requirement. Companion request: ../../../tarav-md/notes/live/876-review-batch-class-subjects-impl-req.md.

## Execution.Plan

- [x] Feature: required subject on batches/revisions; ClassBatch and class tracker
  resolve trusted Type identities; preserve subjects across revisions/retirement,
  expose exact subjects in Python and CLI. Verify generic UUIDs, class versus
  Workflow/instance IDs, unknown classes, presentation, history and Record roundtrip.
- [x] Feature: max_chunks=8 generic/Project controls, bounded writes and oversized
  batch Action on config reduction. Verify exact boundary, over-limit creation,
  revision/completion, no partial writes and stable Action closure after regrouping.
- [ ] Verify existing mapping/review/architecture/Record behavior, reinstall CLI,
  run Project --all, submit/audit implemented surfaces, capture Wiki and commit.

## Impl.Log

- Develop / Wiki / Interactive. Todo list above; required interfaces inspected,
  checks runnable, no unresolved User decision. Cold-reload before product edits.
- Evidence start checkpoints: Python 6692a0ee; Markdown ff6bd9dc. Other sessions
  checkpointed most initial PathNotebook changes before this checkpoint; preserve
  their ongoing work. No subagents used or requested.
- Implemented subject/size controls together in one coherent feature slice;
  data-shape and CLI changes share the creation boundary. Existing Type graph
  traversal includes registered classes, their bases and Workflow classes; the
  class registry alone omits some foundational and Workflow implementation Types.
- Measured: 40 review/Record/architecture checks passed. Public Python and CLI
  paths prove generic subjects, class and Workflow-class attachments, rejection
  of instance/Workflow-entity/unknown UUIDs, subject-preserving revisions and
  retirement, multiple batches per class, exact size boundary and rejection
  without partial writes. Lowering max_chunks reopens the same review Action;
  regrouping and a fresh User token close it while old reviews remain.
- Test-fixture corrections: Project metadata was unintentionally included in
  synthetic maps, producing 28 tiny chunks; fixtures now explicitly exclude their
  .tarav controls or select the intended product files. An Action assertion used
  obsolete event.source instead of event.poi; corrected against current code.
  No limit or behavioral requirement was weakened to pass those assertions.
- Shared storage review found a class specialization must filter by repository
  before enforcing its own subtype. Added a real public regression with generic
  and class-bound batches in the same workflow partition under different products.
- Reinstalled the editable CLI; create requires --subject and list can filter it.
  Ruff across src/tests/tooling and scoped diff validation passed. Full Python
  Project status --all is running at /tmp/review-subject-full-status.json.
