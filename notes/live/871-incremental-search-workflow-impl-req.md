# Impl.Req 871 — Incremental Search workflow

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

**Knowledge.Surface:** wiki. **Alignment.Mode:** Interactive. **Status:** complete. **Phase:** Develop (Execute).

Introduce a general `SearchWorkflow` with a typed query, a `SearchEngine` capability exposed as `obj.search`, and a registry-backed meta engine. An engine may accept or decline a query; several engines may answer the same query. The primary result path yields hits incrementally so query flow controls can stop after the first or Nth hit. This request establishes the common contract and a small in-memory demonstration, without migrating Records or other domain-specific search code.
<!-- tarav.breadcrumb df6f421109ab4cb7d2c423e340eb68785f31bc73ae5547c4a8d7b97d25304359 -->
<!-- tarav.breadcrumb 73bfd4c5b9ab6be99bfb6d211faa5a5ff9518c53fecca604a328bb65fe6d3170 -->
<!-- tarav.breadcrumb 4ac8e74d31110cdf57282cfb32c027f93111544583d6dcc9f96243afde74b18b -->

## Design

`SearchEngine` follows the existing bound namespace convention used by Checks. A concrete engine implements `Search.accepts(query)` and its incremental hit producer. The public `Search.iter_hits(query)` checks `accepts()` and exposes a declined status separately from an accepted search that found zero hits. `Search.run(query)` uses the same gate and collects up to the query's limit. Failure after acceptance remains an error, not a decline.
<!-- tarav.breadcrumb 630b172b05320f3a43f887f3542602d466eefc00b28d096f9c5eb62c22f52b56 -->

`SearchQuery` is a typed TaravObject whose ordinary Record projection remains optional for persistence. It carries a positive `max_hits` or no limit and an optional selected set of engine names. The meta engine registers engines by name, retains registration order, dispatches only to selected engines, and tags yielded hits with their engine path. The limit counts individual hits globally and closes an active iterator when reached. Unknown selected engine names are errors; multiple accepting engines can each contribute hits. There is no cross-engine ranking.
<!-- tarav.breadcrumb e0bdd3c28c109403bc63087e724d1ccd5525d10b1d68df693f7719541d184ea2 -->

The current code has `NamespaceBase` and `CheckProvider.Checks` but no Search workflow. `TaravRecords` already has a runtime-specific provider map; Search should use a parallel engine registry without coupling to Records. This first slice provides manual engine registration and a reusable meta engine. The installed runtime composes one SearchService and registers SearchWorkflow. Domain adapters may follow when their query and result semantics are selected.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Topical destination: `search-workflow.md`; daily: `daily/2026-10-08.md`. Supporting Chatlas session declared above. Capture status: daily and topical Wiki Notes committed and audited.

## Execution.Plan

1. Capture this design evidence, cold-read the request, and checkpoint the declared clean product scope.
2. Add Search workflow, query, engine namespace, incremental stream/result, and registry-backed meta engine.
3. Test acceptance versus empty results, multiple engines, selection, first/N hit limits, iterator closure, and failure propagation; check style and architecture boundaries.
4. Capture justified Product.Surface Breadcrumbs, commit scoped product work, and update the Wiki daily and topical notes with evidence.

## Impl.Log

- Design: existing `NamespaceBase`, Checks capability, and Records service inspected; unrelated worktree edits are outside this request.

- Execution: added `tarav.l1.search` with typed query controls, bound engine namespace, accepted/declined streams, global hit limiting, engine provenance, and a registry-backed SearchService. `create_runtime()` now composes an independent SearchService and registers SearchWorkflow and SearchQuery.
- Verification: shared-worktree `uv run pytest -q` passed 182 tests. Post-capture focused plus architecture tests passed 51, and Ruff passed. A clean-checkout preview of the exact scoped product diff passed 49 focused and architecture tests plus Ruff.
- Product.Surface capture: four source Breadcrumbs, one runtime Breadcrumb, one test Breadcrumb, and one architecture Breadcrumb were submitted. The new labels resolve. Older runtime and architecture labels have preexisting `breadcrumb-position-missing` POIs.
- Product completion commit: `4846ea5d2b9d5e1e633127f387c21b507183e9a3` contains only the Search package, tests, and the Search additions to runtime and architecture guidance. Its five commit-message Breadcrumbs audited clean. Unrelated shared-worktree edits were restored.
- Wiki capture: `tarav-md/notes/wiki/daily/2026-10-08.md` and `search-workflow.md` committed in `8e6d7d00651146649de7bd4da8acd22c916b39b6`; two commit-message Breadcrumbs audited clean. The new Note labels resolve; older daily labels retain position POIs.
