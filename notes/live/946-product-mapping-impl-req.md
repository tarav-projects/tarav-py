# Product Mapping

<!-- tarav.sessions
ec6cf584 = codex:01a1563b-2992-7c62-8a38-05c1cc75b1fe @ec6cf5849bb6c4e66f011b015415da94eeb1a17634872aa4fb9e25d8e065ab53
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: executing.
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
- [ ] Feature slice 2: installed CLI, Record Registry persistence, Project
  freshness check and update action. Check actual CLI proposal/confirm/inspect,
  stable action identity, closed/reopened update and no writes during checks.
- [ ] Operational slice 3: map the complete pinned first-parent history at
  ten-commit checkpoints. Inspect transitions, record agent decisions, audit
  exact byte coverage, and retain a reproducible report and unresolved cases.
- [ ] Completion: code and Wiki capture, architecture contract, Ruff, focused
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
