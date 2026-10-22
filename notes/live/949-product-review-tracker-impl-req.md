# Product Review Tracker

<!-- tarav.sessions
ec6cf584 = codex:01a1563b-2992-7c62-8a38-05c1cc75b1fe @ec6cf5849bb6c4e66f011b015415da94eeb1a17634872aa4fb9e25d8e065ab53
-->

## Impl.Abstract

Knowledge.Surface: wiki. Status: completed. Build a product-agnostic
Review Tracker over confirmed Product Maps. Batches are long-lived meaningful
views over potentially overlapping chunk sets; reviews belong to exact batch
revisions. The User requests design and execution together.
<!-- tarav.breadcrumb 6105c6e9e8f9 -->

Review completion means that the User and Agent processed the batch, recorded
outcomes, and can move on. It never certifies correct content or completed
follow-up work. One explicit User token confirms both maintained membership
and the review discussion. Products of review may live elsewhere and reference
the exact batch revision.
<!-- tarav.breadcrumb 87d3b8b9d3a0 -->
<!-- tarav.breadcrumb d012dbc89536 -->

## Design

Two independent checks: every chunk in the selected map belongs to at least
one live batch; every live batch has a completed review of its current revision.
Overlapping batches are independent obligations. No approval or review state
is stored on a chunk. Aggregate uncovered chunks into one completeness signal;
use one stable review signal per batch, rather than one action per chunk.
<!-- tarav.breadcrumb b8bd245604d7 -->
<!-- tarav.breadcrumb 828043d669e8 -->

Choose one confirmed map at a committed review horizon. Routine selection uses
the most recent ancestor map at least five days old, measured by target
commit time, not mapping-record creation time; an explicit map overrides the
horizon. Do not silently use a too-recent map when none qualifies. A map older
than the preferred horizon is still usable and its date is visible. Branches
outside HEAD ancestry and superseded mapping tracks are not routine candidates.
This is implementation policy within the discussed older-map convention.
<!-- tarav.breadcrumb d240980b8b0d -->

Maintaining a batch selects its chunk IDs at that map and creates an immutable
revision with a base revision ID, map ID, commit, title/purpose, actor, reason
and exact selected chunk states. IDs stay stable across revisions. Membership
changes are explicit Agent/User decisions, not inferred semantic regrouping.
A batch becomes stale when membership disappears or a selected chunk's exact
state differs at the chosen horizon. The maintainer reconciles membership,
then discusses and completes that revision with a fresh token. Pure location
moves also request this explicit, potentially quick, review. Unchanged selected
states retain their review across unrelated map advances. Retirement is explicit
and historical records remain available.
<!-- tarav.breadcrumb 97a7aa58f020 -->
<!-- tarav.breadcrumb a110a7493712 -->

Review completion stores a presentation token, exact Agent presentation and
later User completion Turn references, and optional outcome references. The
Agent presentation must include the exact batch revision/map/commit and the
token; the User must issue the displayed completion command in that session.
Retain both cited Turns using Chatlas snapshots. Never synthesize a User token.
Membership maintenance and review completion can happen in one chat and be
covered by that one completion token.
<!-- tarav.breadcrumb ce5e08509d02 -->

### Current code and boundaries

Inspected l1.product_mapping.model/mapper/checks/commands, l2.project.product_mapping,
l2.project.Project, l3.runtime, l1.review.VerbatimReview, l1.chatlas.references
and turn_snapshots, and mapping/Notebook evidence tests. ProductMap pins commit,
tree, chunks and scope; ProductMapper already reads exact bytes and history.
Existing VerbatimReview is for presented wording/Notebook operations, so do not
reinterpret it as product-content approval. Add separate Product Review Records.
No existing path needs deletion or compatibility migration. Existing map IDs
and chunk IDs are reused; no rebuilding of mappings.

Data shape first: l1.product_review owns Workflow, Batch, BatchRevision,
ChunkState and ReviewCompletion Records. l2.product_review owns mapping/evidence
integration, persistent tracker operations and checks; l2.project.product_review
owns Project configuration/manager. Runtime composes registration and the thin
product-review CLI. Standard Record Registry storage; explicit create only.
Boundaries: validate IDs, selected chunks, evidence roles/order/token at writes;
checks read only, preserve pending actions if horizon/config cannot be evaluated.

Non-goals: automatic semantic grouping, performing actual reviews, approving
content, executing follow-up work, general pipelines or map regeneration.
No real review completion is recorded without the User's actual token.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki. Read product-mapping.md;
add product-review-tracker.md and today's daily narrative at completion.
Supporting session is declared above. Product and Wiki keep independent commits.
Companion request: ../../../tarav-md/notes/live/875-product-review-tracker-impl-req.md.

## Execution.Plan

- [x] Feature: immutable batch revisions and explicit retained review completion.
  Python lifecycle: create, maintain/revise, inspect exact committed material,
  present token, complete with validated evidence, retain history. Check real Git
  and public Python API: overlaps, exact states, invalid IDs, stale transitions,
  retirement, proper User/Agent roles, wrong tokens and old reviews preserved.
- [x] Feature: horizon selection, independent completeness/currency checks,
  Project manager/config and installed product-review CLI. Check actual CLI and
  Project status actions across no-map, uncovered, pending, completed and stale
  states; no reads provision storage. Reinstall installed entrypoint.
- [x] Verify, capture supported design into Wiki daily/topical Notes, submit and
  audit changed product surfaces, run required Project --all, close commits.

## Impl.Log

- Develop / Wiki / Interactive. User explicitly requests plan and execution.
- Todo list above. Readiness: targets and patterns verified; no unresolved User
  decision needed. Agent policy choices above remain distinct from User design.
- Initial worktrees clean. Empty evidence start checkpoints created before edits;
  hashes retained in /tmp/product-review-start-{py,md}-result.json.
- Cold-reloaded the complete request before product edits. Start checkpoints:
  Python 85054981, Markdown 93b922c6. Initial baseline command used a nonexistent
  test_records.py; corrected to the actual generic Record test files.
- Slice 1 measured: 24 Product Review/generic Record checks passed, then all
  11 review and new architecture checks passed. Existing mapping/architecture
  run had 79 passes and one fixture assertion error (dict treated as BaseModel),
  corrected and rechecked. Ruff passed. Actual Chatlas reference resolution and
  hash-valid Turn snapshot retention are exercised, not a mock completion result.
- Concurrent PathRegistry work checkpointed some in-progress Review Tracker
  files in f892309d. Preserve it. Shared ARCHITECTURE/tests contain changes from
  both tasks; this workflow commits those files as found and leaves unrelated
  PathRegistry files alone. Capture audits passed except shared ARCHITECTURE
  temporarily carries the other session's undeclared marker; finish after that
  session's capture. Unmarked schema/plumbing surfaces had no justified extra
  placements; submit reports no provisional marker and audit passes.
- Slice 1 commit: 1095b4df. Slice 2 added independent Situation Chains, a guarded
  scan checkpoint, Project.Review manager/config and product-review CLI. All
  12 public lifecycle/CLI/real Project status tests passed before extra retirement
  and unavailable-map cases. Disabled scans and missing horizon maps preserve
  pending Actions. Configuration enabled for tarav-py with horizon_days=5.
- No mapping rebuilt, batch grouping invented, actual User review performed or
  completion token synthesized. Existing maps remain untouched.
- Slice 2 commit: 902147a9. Measured checks: 99 mapping/review/architecture/Record
  tests passed; after enforcing token-to-revision binding and validating retained
  batch states against their pinned map, 29 review/Record tests passed. Ruff over
  src/tests/tooling and git diff --check passed; installed CLI reinstalled.
- Actual CLI inspection selected existing map 31f594b1-6d1d-47bf-8a31-6239c4983e47
  at commit 131b0357a3fbe441c99c8e2931e97833825ca0b7: 1,171 selected chunks,
  none yet assigned to batches. Inspection did not create review storage.
- Capture: all changed Python/Markdown surfaces audited clean, including the
  shared architecture surfaces after concurrent capture resolved. Config JSON
  externally anchored with Breadcrumb b63b5f2538ee; no metadata injected. Product
  source changes after capture were audited with refreshed positions. Wiki daily
  and product-review-tracker.md submitted/audited clean. Full root --all running
  with report /tmp/product-review-full-status.json.
- Full root status --all completed: 1,347 completed checks, zero incomplete;
  all 66 pytest file suites passed without test POIs. The expected single
  completeness Action f30f5bdb-6dbb-81ac-563d-c653416e7202 now reports 1,171 mapped
  chunks lacking batch membership. No batch reviews exist yet. The other 66
  findings are existing hook/security, test-marker, prompt and SKW/Breadcrumb
  maintenance signals. Product Mapping's check has zero findings.
- Wiki closure b6b9f9b0 records the daily and topical capture. Product slice
  commit 902147a9 evidence audit passed with zero POIs. Independent inspection
  verified the selected horizon map contains 526 src/tests .py files and 1,171
  chunks. Read-only inspection left the Product Review Registry unprovisioned.
- Completion: implementation, installed CLI, Project integration, supporting
  evidence and Wiki capture are complete. Existing maps and their IDs were
  reused. Actual batch curation and User-present reviews are future use of the
  workflow, not unfulfilled implementation steps.
- Completion commit 796d29c62437cd1b2138715e8aa8aa428d70b328 exists. Its post-commit
  Breadcrumb observation failed with InvalidRecordJSON: Not a JSON value: Label,
  during concurrent shared LabelFormats/Record edits. Explicit register-commit
  recovery and commit audit hit the same serialization error. Earlier product
  and Wiki captures audited clean; only this final commit observation remains
  pending. Preserve the existing commit and recover its observation after the
  shared Record serialization change is repaired; do not repeat the product
  commit. This gap is reported to the User separately from passed validation.
