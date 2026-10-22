# Product Review Tracker

Product Mapping supplies persistent chunk coordinates. Product Review Tracker
groups them into meaningful, potentially overlapping review batches. The Agent
chooses those groupings with the User; no language parser or automatic semantic
grouping is required.
<!-- tarav.breadcrumb 627c28d2091a -->

A batch keeps its ID. Each immutable revision pins a confirmed map ID, commit,
title/purpose and exact selected chunk states. Maintaining membership creates a
new revision. It never transfers review completion from an older revision.
Retiring a batch preserves its history and removes it from active coverage.
<!-- tarav.breadcrumb 66309baf6611 -->

Every batch attaches to an existing subject UUID. The generic `Batch.subject`
is a Ship; consumers decide what it identifies. Tarav's `ClassBatch` specializes
it to a class TypeShip. `ClassReviewTracker` resolves attachments through the
existing Type graph rooted in trusted registered classes, including their bases
and Workflow classes. Class identity is distinct from an instance UUID or the
Workflow entity's UUID. `batch.subject_entity()` opens the existing TaravClass
with its bases, Workflow and Context. No class names or hierarchy are copied.
Not every class needs a batch; several batches can share one class subject.
<!-- tarav.breadcrumb 5953feda0ad1 -->
<!-- tarav.breadcrumb 6ce828066883 -->

The subject remains fixed across a batch's revisions and appears in its exact
completion frame. To move a review subject, retire the old batch and create a
replacement under the new UUID. Earlier revisions and reviews stay available.
`batches(subject=...)` finds batches attached to an existing subject.

The default maximum is eight chunks per batch, configurable as `max_chunks`.
Creation, revision and review completion reject larger batches without writing
partial review Records. Eight default-sized chunks are roughly 32 KB, but
this is a count limit, not a byte limit: existing chunks can grow. When a lower
limit makes a saved batch oversized, inspection and its existing review Action
report that state. Maintainers regroup explicitly; historical reviews remain.
<!-- tarav.breadcrumb 7ee4c30897ac -->

Review completion means the User and Agent processed that batch and recorded
the outcomes. Follow-up Actions, design changes and other products can remain
open elsewhere and reference this exact revision. Completion does not endorse
the content. One User token covers both maintained membership and discussion.
<!-- tarav.breadcrumb cca810df9bd2 -->
<!-- tarav.breadcrumb f2d7c26d518f -->

## Python workflow

`tarav.l1.product_review` owns the Records and Workflow. Mapping and Chatlas
integration lives in `tarav.l2.product_review.ReviewTracker`:

1. Open a `ProductMapper` with its repository identity and existing maps.
2. Construct `ReviewTracker(mapper, max_chunks=8)` for generic subjects, or
   `ClassReviewTracker(mapper, max_chunks=8)` for Tarav class subjects;
   reads never provision storage. Explicit
   `create()` initializes its standard Record Registry partition.
3. `select_map()` chooses an ancestor of HEAD whose commit is at least five
   days old. `map_id=` explicitly selects any available confirmed map. No
   qualifying map is reported as unavailable; it never silently falls back to
   fresh material. Confirmation timestamps do not determine commit age.
4. `inspect(map_id=...)` reports uncovered chunk IDs and per-batch currency.
   `create_batch(subject=..., map_id=..., chunk_ids=[...], title=..., purpose=..., actor=...,
   reason=...)` creates a coherent subject. `revise(batch_id, base=...,
   map_id=..., chunk_ids=[...], actor=..., reason=...)` maintains it explicitly.
5. Read `current(batch_id)`, expand `read(revision_id)` for exact committed
   bytes, and discuss with the User. `presentation(revision_id)` produces the
   precise completion frame and `::reviewed review:<revision-id>` token.
6. After the User actually issues that token, pass the exact Agent presentation
   and later User Turn references to `complete(revision_id, presentation=...,
   completion=..., outcomes=[...])`. The cited frame and token are checked and
   both Turns retained as Chatlas snapshots. No synthetic User evidence.
7. Use `history(batch_id)` to recover earlier revisions and their completions.

The completion frame confirms the whole revision. It does not require the User
to review each chunk separately. A new membership or selected-state change
requires maintenance and a fresh review. Unchanged selected chunks retain
currency across unrelated map advances; a blob changing elsewhere in a file
does not itself change a chunk. Location changes are visible and require an
explicit, possibly quick, renewed review.

## Project integration and CLI

Featured Projects select `Project.Review` and expose `project.review.open()`
and `project.review.suite()`. Configure the workflow in `.tarav/config.json`:

```json
"product_review": {"enabled": true, "horizon_days": 5, "max_chunks": 8}
```

The Git repository identity and Product Mapping scope come from the existing
Project configuration. Mapping owns which files exist in the map. The tracker
does not rebuild maps or introduce its own file-selection rules. Routine checks
select existing maps by commit age; `--map` overrides the horizon on demand.

Discover `tarav product-review --help` and each command's help. Commands take
`--repo PATH --repository-id DOI`. `--maps-store` and `--store` explicitly
override their independent standard Record Registry partitions.

`inspect` reports uncovered chunks and batch states. `init` creates storage;
`create` requires `--subject TYPE_UUID` and selects repeated `--chunk ID` values
with a title, purpose, actor and
reason. `revise` also requires the stable `--batch ID` and current `--base
REVISION`. `show`, `list` and `history` expose retained revisions; `list --subject
TYPE_UUID` filters by the attachment. `read`
returns exact committed bytes as base64, including binary material. `present`
prints the completion frame. After the actual in-chat review, `complete`
requires `--revision`, `--presentation` and `--completion` JSON files holding
exact Chatlas Turn Reference Records; `--outcomes` optionally holds an array
of Reference Records. The command never generates a User token or finishes
follow-up work. `retire` explicitly removes an obsolete batch from active use.

`tarav status` integrates the signals into Actions: one aggregate completeness
action and one stable review action per batch. Successful scans close findings
that have disappeared and reopen them on recurrence. Disabled, failed or
unavailable scans do not imply the work has gone away. A missing eligible map
is an incomplete check, not a reason to generate a fresh one during inspection.

Completeness and currency are independent. Every selected-map chunk must belong
to at least one live batch. Every live batch needs its own current review,
regardless of whether another batch overlaps it. Checks emit findings without
repairing membership, writing Records or performing reviews.
<!-- tarav.breadcrumb 57a71fa7da11 -->
