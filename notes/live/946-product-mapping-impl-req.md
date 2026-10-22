# Product Mapping

<!-- tarav.sessions
ec6cf584 = codex:01a1563b-2992-7c62-8a38-05c1cc75b1fe @ec6cf5849bb6c4e66f011b015415da94eeb1a17634872aa4fb9e25d8e065ab53
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: completed.
Implement Product Mapping and exercise it on tarav-py, from the first commit
through pinned target 04981e436403e158559c9c40be1a5cd8255f2262, every ten
first-parent commits and at the final target. The chain has 1,257 commits.
The User authorized implementation and this historical run. Review batches,
review tokens and the Product Review Tracker are separate, future consumers.
<!-- tarav.breadcrumb 4b319be9965a -->

## Design

A confirmed map names one exact Git commit/tree. Each chunk has a persistent
UUID and a version naming a regular file's Git blob, half-open byte range and
SHA-256 content fingerprint. Mapping works on committed bytes only, without
language parsers. A target size (initially 4096 bytes) and boundary flexibility
(256 bytes) guide initial partitioning; maintained chunks can grow or shrink.
All regular tracked files are covered by default. Symlinks and submodules are
listed explicitly as unsupported surfaces, never followed. Empty files receive
an empty chunk. Scope filters, if supplied, are retained with the map stream.
<!-- tarav.breadcrumb 7263a4da5337 -->
<!-- tarav.breadcrumb aeb63d7c2588 -->

The simple mechanics propose candidates from exact blobs, exact content and
line alignment between endpoint states. Maintainers explicitly confirm the
transition: keep an ID, create IDs, retire IDs, or express splits/merges through
parent IDs. A proposal is not a confirmed map. Confirmed records retain actor,
reason and per-change decisions; exact byte checks establish state, not meaning.
Git supplies evidence. Neither similarity nor a fingerprint establishes identity.
Unchanged chunks can be carried forward mechanically within an explicitly
accepted transition. Changed candidates require a decision. Ambiguity must not
silently transfer an ID or delete its history.
<!-- tarav.breadcrumb d501ed77221f -->

Maps advance between selected checkpoints; intermediate commits are optional
investigation evidence. Routine maintenance is a freshness policy, not a delay
on mappable commits: if newer commits exist and the latest confirmed map is
older than the configured interval, raise one update POI/action per tracked
repository. Explicit updates can map any committed target. Checks only read;
they do not provision storage, generate proposals or confirm transitions.
Project integration composes this through its selected managers in l2, leaving
the core workflow independent of Projects and review semantics.
<!-- tarav.breadcrumb 6eda671b8224 -->
<!-- tarav.breadcrumb 4de7cef76bf3 -->

## Current state and implementation choices

Inspected: l1.git.repository supplies exact revisions and Git bytes; l1.records
supplies workflow-owned RecordMap partitions; l2.project.Checks composes featured
integrations; l3.runtime owns registration and CLI composition. No Product
Mapping workflow exists. No legacy path needs replacement. The independent
workflow will live at l1.product_mapping; Project integration at l2.project.
Use typed Records for confirmed maps and their tracker; proposals are editable
typed Records too. Keep immutable map history in the standard Record Registry.
Keep repository identity explicit, using tarav-py's existing Repository DOI.
Use conservative alignment as a candidate generator, with explicit decisions
for edited, removed and new chunks. A run must report unresolved work honestly.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner/root: tarav-md/notes/wiki. Related context:
project-integration-managers.md and breadcrumbs.md; neither defines mapping.
Capture this discussion in product-mapping.md and daily/2026-10-22.md.
Companion: ../../../tarav-md/notes/live/873-product-mapping-guidance-impl-req.md.

## Execution.Plan

- [x] Feature slice 1: typed maps, byte chunking, committed snapshots,
  endpoint proposals and explicit confirmation. Check real temporary Git repos:
  initial coverage, insertions, moves, changes, retirement, split/merge,
  ambiguous candidates, immutability and working-directory independence.
- [x] Feature slice 2: installed CLI, Record Registry persistence, Project
  freshness check and update action. Check actual CLI proposal/confirm/inspect,
  stable action identity, closed/reopened update and no writes during checks.
- [x] Operational slice 3: map the complete pinned first-parent history at
  ten-commit checkpoints. Inspect transitions, record agent decisions, audit
  exact byte coverage, and retain a reproducible report and unresolved cases.
- [x] Completion: code and Wiki capture, architecture contract, Ruff, focused
  tests and full root status --all; evidence commits and compact report.

## Impl.Log

- Initial worktrees clean. Pinned endpoint above prevents implementation commits
  from creating a moving completion target. No product code edited yet.
- Data shape first: identity, exact state and continuity decisions are distinct.
  Boundary discipline: Git reads and Record/CLI input validate at the boundary.
- Todo list is Execution.Plan. Cold reload follows before the first code edit.
- Cold reload completed. Start checkpoints: Python 98b88dff; Markdown d74445e9.
- Slice 1 measured: 74 focused mapping/runtime/architecture/Record tests passed;
  Ruff passed. Initial seven failures exposed a missing explicit Type discriminator
  in strict new Record interfaces, fixed at the data boundary. One test's byte
  offsets were corrected after inspecting the literal input's positions.
- Slice 1 Product.Surface capture submitted and audited every changed surface.
  Export-only __init__.py and the test-suite list have no additional supported
  annotation position. Older audit positions on shared runtime/pyproject need
  position refresh; no new mapping support was fabricated.
- Slice 1 commit: 23141237. Refreshed earlier positions; all audited surfaces
  then clean. Slice 2 measured: 73 mapping, architecture, manager and action
  tests passed, including actual CLI rejection/confirmation and one-action
  close/reopen. Disabled scans preserve open actions through a scan checkpoint.
- Installed editable CLI refreshed. Freshness measures time since confirmation;
  mapping old history on demand is permitted. README exposes this policy choice.
- Operational choice for the authorized historical run: actor is this Agent,
  never the User. Exact states carry forward; edited candidates require retained
  decisions. A conservative, inspectable replay policy may replace weak candidates
  with fresh IDs rather than pretend semantic certainty. User review remains out
  of scope. Report the policy, decisions and exact coverage separately.
- Slice 2 commit: 13920481. A next-slice driver's literal byte-count assertion
  was included too early; corrected its expected 35 to the measured 36 before
  proceeding. The real script process exposed a missing runtime bootstrap,
  fixed explicitly and covered by a subprocess regression.
- Historical run completed: 127 checkpoints, from 7abab7a4 through pinned
  04981e43. Final historical map 4082e071-903d-42a7-84d0-67ba97183da4 covers
  1,157 regular files, 4,584 chunks and 16,161,833 bytes; two symlinks are listed
  as skipped. Independent installed `product-map audit --all` verified all 127.
- Retained 30,935 explicit Agent decisions; 2,344 edited candidate ranges got
  fresh IDs under the conservative evidence policy. No User review is claimed.
  Full report: product-mapping-history-2026-10-22.json. Record partition:
  /Users/pereiro/Documents/tarav/records/ef1dc42a-fd98-43b8-a30d-e68bf742de34.
- Performance evidence: profiling one early transition found 173M calls / 26.7s
  dominated by character alignment. Switched operational evidence to exact
  matching line/block bytes; a later sampled transition took 0.048s. Samples
  differ, so these are diagnostic observations, not a controlled speedup claim.
  Paused during candidate calculation; confirmed maps remained intact. Resumed
  with explicit report recovery support, preserving earlier decisions.
- Code review found contradictory retire/create decisions could reuse an ID
  within one transition. Reproduced with a failing public confirmation test;
  now retained IDs must be on both sides of the same continuity decision.
- Enabled five-day freshness policy in tarav-py's config. JSON config and run
  report captured externally (c9ada48176b1, a8d7afb1f253), without metadata edits.
- Full root status --all is running. Final catch-up map will target the completed
  implementation commit, beyond the fixed historical report's endpoint.
- Full root status --all completed 1,345 checks without incomplete checks. Its
  66 pytest file suites exposed two failures in the one generic Record contract
  file: new Types lacked complete schema examples. Reproduced that failure,
  supplied examples, and made Mapper loading detached/lazy so unavailable
  repository locations can still round-trip. The generic and mapping files then
  passed 24 tests; latest mapping/architecture checks passed 68 tests.
- Added direct chunk lookup, fingerprint-checked committed reads and recorded
  chunk history, including retirement. Consumers can pin a map ID rather than
  receiving a silently substituted version. A public test verifies old/new
  exact bytes and retired standing.
- Rerunning all affected file suites through the actual Project harness and
  ActionManager, with exact file-suite identities, to clear the two own failures
  without asserting anything about unrelated findings or unrun suites.
- Affected harness rerun completed with zero POIs; both own test-failure actions
  closed as gone. This follows the broad run and targeted fixes, rather than
  claiming the original broad run passed. New/changed mapping tests: 15 passed;
  mapping plus architecture: 68 passed; generic Record plus mapping: 24 passed.
  Ruff across src/tests/tooling passed. The verification wrapper initially
  failed to serialize typed action signals after its successful run; corrected
  its report serialization and retained the focused harness result separately.
- Slice 3 commit: 0bd9564c. All changed Product.Surfaces were submitted where
  supported and audited clean, including external JSON observations. Pure
  mechanical exports/examples have no additional invented User-Turn support.
- Wiki captures: tarav-md/notes/wiki/product-mapping.md and
  daily/2026-10-22.md. The companion request records that repository's closure.
- Final catch-up runs after this completion commit. Its exact commit/map ID is
  retained in the Product Mapping registry, avoiding a self-referential tracked
  report that changes the product after mapping it. The historical JSON report
  intentionally retains its fixed 04981e43 endpoint. Product Review Tracker and
  review approval remain unimplemented, as explicitly scoped out.
