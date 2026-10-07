# 864 — TaravRecords workflow — Impl.Req

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: Complete. Phase: Develop (Execute).

Introduce `TaravRecords` as the workflow for reusable Record storage primitives and basic discovery and navigation across storage solutions contributed by other workflows. A contributing source must be able to expose its Records without registering every Record in a central index. Tarav should also offer standard Record storage locations, while workflows remain free to use the same primitives in their own storage.
<!-- tarav.breadcrumb 20afcba0227f4eeb35a648765a9dd1172c5cf15d76d1ab9a33b29059fc815fb1 -->
<!-- tarav.breadcrumb 31c9342f314b83fb558f4dd02e53cc05929bc7c8187c0294923723a9dc5da3d1 -->

This request captures the intended architecture and a proposed first implementation boundary. It does not assert that the proposed API, storage layout, or migration order has been approved.

## Design narrative

### User decisions and direction

Archive and Registry have different semantics. Archive identifies Artifacts, retains descriptive Records, and has long-term preservation and DOI-like responsibilities. A Registry stores Records; Archive could use one for its own Records. Whether Records are append-only or have a changing current edition belongs to the storage policy, not to the meaning of Registry. Shared primitives must support both. The existing Record Archive is a candidate source of Registry mechanics, not an automatically approved generic contract.
<!-- tarav.breadcrumb b49f45c1c243c75b9f95aa96041b658fbb29bd2022eb5b46c06f8809334c7e08 -->
<!-- tarav.breadcrumb 973561d7af371d2eab2a0814e84d02564a1b8f38768f9fd68d45cb37595bc8a6 -->

An Entity view should not require a second repository. The desired global workflow lets other workflows hook their storage solutions into a navigable Record graph, potentially using JSON registries, class subtyping, or other discovery mechanisms. There must be no central enumeration of every Record as a prerequisite for reachability. `TaravRecords` is the chosen workflow name and includes both primitives and basic navigation and discovery.
<!-- tarav.breadcrumb 7b3743b705e6bb691763ce2056adcc573680962970d39ebe63353fee204ad12b -->
<!-- tarav.breadcrumb a934e11731cd1dede9643f3b238af28ab54ca4b47c81eddf1515b4fe30751ab1 -->
<!-- tarav.breadcrumb e00200904b1c6fc37f8345f7637a451269576fb31849662e65ef7617e70e7d64 -->

The immediately preceding recovered discussion in `tarav-md/notes/live/864-entity-registry-and-storing-workflow-recovered-discussion.md` additionally distinguishes ordinary file/path references, a Git `HEAD` reference, and an exact edition. Their precise contracts remain to be designed.

### Current implementation observations

- `tarav.l0.kernel` already supplies typed Record interfaces, trusted Type loading, and generic Explorer contracts. `tarav.l1.context` and `tarav.l1.archive.records` specialize navigation independently.
- `tarav.l1.archive.records` provides Dictionary and Vector Archives with `entries.json`, separate entry and artifact files, typed loading, locks, and nested Git repository policy. Its Workflow is currently a child of Archive.
- `tarav.l2.scoring.repository.ScoringRepository` keeps domain Records in its own Git repository with paths, commits, immutable Tribunal Records, and append-only event streams. It does not use Record Archive.
- `tarav.l1.git` and `tarav.l1.references` already own shared Git operations and typed reference mechanics. New Records mechanics should compose these existing surfaces.
- The `tarav-py` worktree contains pre-existing edits in `ARCHITECTURE.md`, `src/tarav/l3/runtime.py`, and `tests/test_architecture.py`, which are likely to be touched by any installed workflow integration. Those edits are outside this request and must be preserved.

### Proposed bounded design

`TaravRecords` owns a source-contribution contract and a lazy root/explorer over contributed sources. A source exposes navigable roots and enough bounded operations to list children and open or resolve Records; its implementation may rely on a directory, JSON index, class behavior, or another store. The workflow composes those source roots rather than storing a row for every Record. Cross-source navigation follows explicit references. Optional derived search indexes may accelerate later queries without becoming Record authority.

Reusable storing primitives should cover typed loading and writing, keyed and ordered placements, append-only or replaceable-current policy, and Git-aware references. A standard RecordRegistry should offer a Tarav-owned location partitioned by owning Workflow. Custom workflow repositories can use the same primitives. A cross-source Entity view locates retained Entity Records by Ship and exposes multiple locations or editions when present instead of silently selecting one canonical Record.

Identity, placement, and edition must remain distinct: an Entity Ship identifies a logical subject; a source path or key locates a retained Record; a Git commit can select an exact edition. Current working-tree, current committed, and exact-edition reads require explicit semantics. The first implementation should reuse existing loading, Git, Reference, and Explorer mechanics rather than introduce parallel versions.

Archive keeps Artifact and preservation semantics. Adopting Registry primitives for Archive's Record storage is a separate migration question; existing Archive Records and layouts remain authoritative until that migration is designed.

### Material alignment question

Choose the first execution boundary: **A.** introduce `TaravRecords` discovery/navigation and generic primitives around current stores, with adapters demonstrating Archive and Scoring reachability, then migrate Record Archive storage in a later request; or **B.** include renaming/refactoring the current Record Archive into the standard RecordRegistry and any required data migration in this request. A is the recommended first slice because it tests the extension contract against distinct real stores before changing retained layouts. This choice affects scope, tests, documentation, and the worktree conflict.

The User selected the incremental first boundary: establish the workflow organization and extract common or easily migrated primitives now; workflows may retain custom storage and further alignment follows later. This authorizes A and a bounded standard Registry without a Record Archive data migration.
<!-- tarav.breadcrumb 8c6ea8fd95ab9394630db8ad490c2ba05a82da870ab504292d45ecdd09fe6111 -->

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant Notes: `record-framework.md`, `record-archive.md`, `context-graph.md`, `references.md`, `archive-doi-registry.md`, and new candidate-design Note `tarav-records.md`. Supporting chat: current Codex Chatlas session `01a1176b-f14c-7fd0-a97c-b22279c3f8c8`, identity `473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f`; exact User Turns are attached beside the decisions above. Capture status: seven Inlined Capture Breadcrumbs submitted and audited. Wiki daily and topical capture completed in `cf8c01147bd51efb743fc5933392f51efa5ddd90`; design alignment pending.

## Execution.Plan

1. Resolve the first execution boundary and cold-read this request. Recheck current project instructions, source, tests, and the shared worktree.
2. Scope evidence checkpoints to only the product paths actually changed. Preserve pre-existing changes, including partially modified architecture and runtime files. Stop if a clean scoped checkpoint cannot be made.
3. Implement one coherent vertical slice of `TaravRecords`: the source hook, lazy root/explorer, standard Registry entry point and Entity view appropriate to the chosen boundary. Adapt at least two unlike existing storage sources so the hook proves useful beyond one layout.
4. Verify reachability, typed loading, entity lookup, repeated editions, missing or invalid Records, and the fact that navigation does not mutate stores or require a per-Record global registry. Run focused tests and architecture checks. Update architecture guidance and runtime registration where the selected boundary requires them.
5. After each product slice, run Product.Surface Inlined Capture; close with scoped evidence commits and selective Wiki daily/topical capture. Record mechanics and any gaps in this log.

Acceptance requires a real workflow with discoverable contributed Records, a standard Tarav-owned storage path or entry point, and at least one custom-storage contribution using the same navigation contract. No source may need to register its Records individually. Archive Artifact semantics remain distinct.

## Impl.Log

- Design investigation: read Tarav Constitution, project guidance, relevant Wiki Notes, Archive/Scoring/Git/Reference/Explorer source, and the current worktree state. No product code changed.
- Status: awaiting the execution-boundary choice above. The original recovered discussion note in `tarav-md` is pre-existing and untracked; leave it untouched.
- Impl.Req Inlined Capture: seven User-Turn Breadcrumbs submitted; audit reported `status: ok` without findings.
- Wiki capture: empty scoped start checkpoint `62be24cf67f8fd7a36223f31197f472371777d7b`; daily `2026-10-07.md` and topical `tarav-records.md` committed as `cf8c01147bd51efb743fc5933392f51efa5ddd90`. Nine Note Breadcrumbs and two commit-message Breadcrumbs audited without findings. The unrelated untracked recovered-discussion note remains untouched.
- Scoped `tarav-py` design start checkpoint: `db063eb3bcd146c45c178768dc94f9d2520a224e`. Its scope is this new Impl.Req only; pre-existing product edits remain outside the checkpoint.
- Execute start checkpoint: `0b37d6306dffe6aec6a989f94fbdebefafb83d26` in `tarav-py`, empty and scoped to this implementation. The pre-existing dirty changes remain outside its scope.
- Implemented `tarav.l1.records` as the TaravRecords workflow, replacing the former Navigation namespace while keeping its Workflow Ship. Runtime composes `RecordsService`; `RecordProvider` contributions remain per source. Archive and Scoring expose existing custom storage; a standard RecordRegistry stores typed Records by Workflow Ship with insert/replace policy and working, committed-head, and exact-edition references. An Entity view scans contributed sources on demand without a per-Record central index.
- Extracted a shared typed atomic write boundary and workflow-neutral Git init/selected-path commit operations. Record Archive uses the typed writer and Git initializer without changing its retained layout or Artifact semantics.
- Verification: focused suite 75 passed; full `uv run pytest -q` 174 passed; Ruff on the changed code passed. Architecture dependency graph passed after moving shared Git mutations into `l0._core`.
- Product.Surface Inlined Capture: new Breadcrumbs submitted for every changed product surface; new labels audited as resolved. Some earlier Breadcrumb observations in `ARCHITECTURE.md`, runtime, Git repository, and tests report `breadcrumb-position-missing` after line shifts from this and other worktree edits; they remain a capture POI, not a test failure. Wiki daily and topical implementation capture submitted and audited with no findings.
- Scoped product completion commit: `b1f8751ee0263b82eeb09f7b610e7a10c949b5e7`; its three commit-message Breadcrumbs audited `ok`. For the three files with pre-existing user edits (`ARCHITECTURE.md`, `src/tarav/l3/runtime.py`, and `tests/test_architecture.py`), the commit contains only this request's hunks; their full working copies were restored afterward and the unrelated edits remain in the worktree.
- Wiki capture start checkpoint: `808bf7b615bf1a15be51a8c8a691af551fa0eb39`. Wiki completion commit: `393a2de986d3272cde95b8ade6a6fd2c2c80901d`; its commit-message Breadcrumb audited `ok`. The unrelated untracked recovered-discussion note remains untouched.
