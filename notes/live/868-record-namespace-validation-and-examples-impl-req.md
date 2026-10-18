# 868 — Record namespace validation and examples — Impl.Req

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: Complete. Phase: Develop (Execute).

Expose `Type.records.validate_record(value)` and `Type.records.record_example()` on the same class-bound Record namespace as loading. Preserve existing class-specific validation and example behavior, including `super().validate_record()` and inherited overrides. Use the new validation path inside Record projection and loading. This is a bounded API path change; it does not rewrite the dozens of concrete classmethod overrides or every caller across workflows.
<!-- tarav.breadcrumb b79db67bea92 -->
<!-- tarav.breadcrumb 41b7c43b0e15 -->

## Design narrative

The User accepted the next Record namespace slice after the class loading path landed. Inspection found many `record_example()` overrides and several `validate_record()` overrides that call `super()`. Moving all implementations into `Records` would touch dozens of domain Types and break the current Python override chain unless those Types migrated together. Therefore, the concrete classmethods remain the dispatch points for this slice, and the bound namespace exposes them without changing their behavior. The shared Record projection and loading logic calls the namespaced validation path, making it the common API boundary. This revises the earlier proposed source-code move while preserving the requested qualified paths.
<!-- tarav.breadcrumb 4917943a770b -->

`TaravObject.Records` can derive the bound Python Type from its class or instance binding. Its new methods delegate to that Type's existing classmethods; no reflection, generated namespace classes, storage migration, or new registry is needed. Direct classmethods remain for existing callers and subclass extension. A later decision can consider migrating the override mechanism itself if the qualified API proves valuable enough to justify that larger change. This request makes no claim that all Record functionality now lives under the namespace.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant Note: `record-framework.md`; daily `2026-10-08.md`. Supporting session: `codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8`. Capture status: complete; the new Wiki Breadcrumbs resolve.

## Execution.Plan

1. Cold-read this request and current Kernel Record code, then checkpoint the clean product scope while preserving unrelated dirty files.
2. Add class-bound `validate_record()` and `record_example()` methods to `Records`; use namespaced validation inside `to_record()` and `from_record()`.
3. Test base and specialized validation, inherited subclass example dispatch, and unchanged round trips. Update architecture guidance and its maintained test.
4. Capture changed Product Surfaces, run focused and full checks, commit only this slice, capture daily/topical Wiki notes, and close this request.

## Impl.Log

- Design inspection: `record_example()` has dozens of concrete overrides; `validate_record()` has several overrides using `super()`. The shared worktree still has many unrelated edits, including `records.py` and `ARCHITECTURE.md`. An empty design start checkpoint was made as `b13f423ee4362a5271edd8097d5a7671509e6cb8`; its first attempted manifest named the absent note path and failed without a commit, then the empty scope succeeded.
- The Design note's three Breadcrumbs passed audit; Design commit `bb719d503398464cb1abfc05576f9ce6b4915f13`. Execute start checkpoint `2392ad33964307adbc2a270f1c3ff03606178813` selected the clean focused test file. Dirty shared files were excluded from the start checkpoint.
- `TaravObject.Records` now exposes validation and example methods through the bound Type. Loading and projection call namespaced validation, which dispatches to existing concrete classmethod overrides. Focused tests cover base behavior, a Decision validator using `super()`, rejection of a missing timezone, a specialized Blessing example, and loading. The maintained architecture check and guide describe the boundary.
- Focused tests passed (56). The full Python suite passed (179), Ruff passed across `src` and `tests`, and the scoped diff passed whitespace checks. The editable Tarav tool was reinstalled. Product commit `763a1139840bb8d658a0eefd10fe7e5c197dc12d` includes only this slice's hunks; unrelated worktree edits remain. Its commit Breadcrumb audit passed.
- Product.Surface capture added five labels across Kernel, focused tests, architecture tests, and guide. The new labels resolve by audit or direct resolution. Larger file audits retain older position POIs; they do not concern the new labels.
- Wiki start checkpoint `cb38f0266bb63e63aa8d257c557eca6697db4503`; October 8 daily and `record-framework.md` capture committed as `cd10ad553cecfc38e3b4d7c2224b8ce52233c06f`. Both new Wiki labels resolve and the commit evidence audit passed. The topical note still has 144 older position POIs.
