# The chatlas-context audit reads cached Turns — implementation request

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

## Impl.Abstract

Status: ready, 2026-10-18.
Knowledge.Surface: wiki.
Alignment.Mode: autonomous.

Make `tarav breadcrumbs audit chatlas-context` resolve each Breadcrumb's Turn
from the cached Normal Model Turns, fresh or stale, and rebuild a session's
model from raw only when its cached Turns do not confirm the Turn or no cache
exists. The rebuild stays in memory; the audit writes nothing.

Non-goals: changing what the audit reports, the submit path, or the cache
policy of other consumers.
<!-- tarav.breadcrumb 3841677415d2 -->

## Design

### Why

Profiled 2026-10-18 on `tarav-py/ARCHITECTURE.md` (79 Breadcrumbs, 10
sessions): 66.5 s under the profiler, 65.5 s of it in `compute_normal_model`,
which rebuilds the whole Normal Model from raw for every referenced session
(about 6.5 s each) and never reads the cache. The audit only needs Turns.
<!-- tarav.breadcrumb 6d2395da62a1 -->

### Decisions (User)

- Connect the audit with the cached paths. A fresh cache is not needed: refresh
  only when the Turn is not found.
  <!-- tarav.breadcrumb b22dcd0733e6 -->
- Accepted gap: a Turn edited or removed after its cache was built still
  matches a stale cache. The audit does not need to be perfect; this happens
  rarely.
  <!-- tarav.breadcrumb cbd15d749fe9 -->
- Its own small request before finishing request 921, and tested while
  finishing 921 (its capture audits).
  <!-- tarav.breadcrumb 52a4f3d36a24 -->

### Agent decisions

- Per session, once per audit: read `turns` from `NormalModelCache` when the
  `main` and `turns` parts are present, whatever their standing. A Turn that
  does not resolve as MATCHED there, an unreadable cache, or a missing one
  leads to one in-memory `compute_normal_model` for that session, whose answer
  is final.
- The lookup is a small function beside the audit, so it can be tested
  without a Breadcrumb store.

## Current implementation observations

- `src/tarav/l2/breadcrumb_workflows/chatlas_context/workflow.py`,
  `ChatlasContextWorkflow.audit`: `models[identity] = compute_normal_model(...)`
  then `resolve_chat_turn_ref(turns, locator)`; standings MATCHED, MISSING,
  AMENDED (`normal_model/turn_ref.py`).
- `NormalModelCache` and `resolve_session_index_row` exist (request 919).

## Impl.Req.Wiki

- Product project: `tarav-py`. Wiki owner: `tarav-md`; note
  `notes/wiki/chatlas-normal-model.md`.
- Capture status: with request 921's completion.

## Execution.Plan

1. Performance — cached Turns first, rebuild only when needed. Check:
   `tests/chatlas/test_context_audit_turns.py` (stale match, stale miss
   rebuilds, no cache computes without writing); the ARCHITECTURE.md audit
   timed before (34 s) and after. Status: pending.

## Impl.Log

- 2026-10-18: request written in the session above. Baseline: 33.78 s for
  `tarav breadcrumbs audit chatlas-context --surface ARCHITECTURE.md --json`.
