# 868 — Record namespace validation and examples — Impl.Req

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: Ready. Phase: Develop (Design).

Expose `Type.records.validate_record(value)` and `Type.records.record_example()` on the same class-bound Record namespace as loading. Preserve existing class-specific validation and example behavior, including `super().validate_record()` and inherited overrides. Use the new validation path inside Record projection and loading. This is a bounded API path change; it does not rewrite the dozens of concrete classmethod overrides or every caller across workflows.
<!-- tarav.breadcrumb b79db67bea92c077dabb630f02194a27d1596fd0a5693b696f81f63b50d93feb -->
<!-- tarav.breadcrumb 41b7c43b0e15fa25793d24623f69ba151378a28b0a02674642693cb9f58c5b75 -->

## Design narrative

The User accepted the next Record namespace slice after the class loading path landed. Inspection found many `record_example()` overrides and several `validate_record()` overrides that call `super()`. Moving all implementations into `Records` would touch dozens of domain Types and break the current Python override chain unless those Types migrated together. Therefore, the concrete classmethods remain the dispatch points for this slice, and the bound namespace exposes them without changing their behavior. The shared Record projection and loading logic calls the namespaced validation path, making it the common API boundary. This revises the earlier proposed source-code move while preserving the requested qualified paths.
<!-- tarav.breadcrumb 4917943a770b1dfb7a3062ac3052de29a014564f92f84f265b382a7f823f46c3 -->

`TaravObject.Records` can derive the bound Python Type from its class or instance binding. Its new methods delegate to that Type's existing classmethods; no reflection, generated namespace classes, storage migration, or new registry is needed. Direct classmethods remain for existing callers and subclass extension. A later decision can consider migrating the override mechanism itself if the qualified API proves valuable enough to justify that larger change. This request makes no claim that all Record functionality now lives under the namespace.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant Note: `record-framework.md`; daily `2026-10-07.md`. Supporting session: `codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8`. Capture status: pending Execute.

## Execution.Plan

1. Cold-read this request and current Kernel Record code, then checkpoint the clean product scope while preserving unrelated dirty files.
2. Add class-bound `validate_record()` and `record_example()` methods to `Records`; use namespaced validation inside `to_record()` and `from_record()`.
3. Test base and specialized validation, inherited subclass example dispatch, and unchanged round trips. Update architecture guidance and its maintained test.
4. Capture changed Product Surfaces, run focused and full checks, commit only this slice, capture daily/topical Wiki notes, and close this request.

## Impl.Log

- Design inspection: `record_example()` has dozens of concrete overrides; `validate_record()` has several overrides using `super()`. The shared worktree still has many unrelated edits, including `records.py` and `ARCHITECTURE.md`. An empty design start checkpoint was made as `b13f423ee4362a5271edd8097d5a7671509e6cb8`; its first attempted manifest named the absent note path and failed without a commit, then the empty scope succeeded.
