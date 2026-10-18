# 867 — Record namespace class loading — Impl.Req

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: Complete. Phase: Develop (Execute).

Complete the shared Record namespace boundary: `obj.records.to_record()` projects an instance and `SomeType.records.from_record(record)` loads that concrete Type. Keep the established validation, exact-Type checks, `_from_record()` hook, and `_record` retention behavior. Migrate the kernel's dynamic loading call to the new path and exercise both paths through public tests. Broad call-site migration across every domain remains a later slice; this request does not change storage or TaravRecords navigation.
<!-- tarav.breadcrumb 1288ecfac949 -->
<!-- tarav.breadcrumb 36b96153a663 -->

## Design narrative

The User wants Record behavior under an object namespace without changing its behavior. The first namespace slice introduced `TaravObject.Records` and `obj.records.to_record()`, but class loading still has only `Type.from_record()`. The current instance `records` property cannot bind a class. The simplest class-side spelling consistent with the object path is `Type.records.from_record()`: one descriptor binds the selected `Records` class to either the object or its Python class. `Type.Records` remains the class-level namespace definition and composition point. The class-side view holds the same base loading implementation; the established top-level method delegates during the broader caller migration.
<!-- tarav.breadcrumb 2f462a2a5a01 -->

The kernel's `TypeRegistry.from_record()` is a first-class dynamic loading consumer and should use the new concrete class path. Preserve rejection of an abstract `TaravObject`, exact Type mismatch, strict Record validation, exact constructed class, and retention of the supplied Record. Avoid a new registry, reflection-based owner lookup, or per-subclass generated namespace classes. Tests should show inherited `Records` binds to the actual subclass and that a class view cannot project an absent instance.
<!-- tarav.breadcrumb 57dbb943c98c -->

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant Notes: `record-framework.md` and daily `2026-10-07.md`. Supporting session: `codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8`. Capture status: complete; new daily and topical Breadcrumbs resolve.

## Execution.Plan

1. Cold-read this request, the kernel Record implementation, TypeRegistry, and relevant tests. Check the shared dirty worktree before product edits.
2. Bind lowercase `records` to an instance or its concrete class. Move the base class-loading body into the Record namespace; keep the established direct call as a delegating entry during caller migration.
3. Change the kernel's dynamic loading call to the namespaced path. Test class/instance binding, round trips, and existing validation failure cases. Update architecture guidance.
4. Capture Product.Surface Breadcrumbs on each changed surface, run focused and proportionate full checks, make scoped evidence commits, and capture Wiki daily/topical context.

## Impl.Log

- Design inspection: `TaravObject.Records` already implements the projection; `TaravObject.from_record()` owns the class-loading body. `TypeRegistry.from_record()` calls the selected concrete class's direct method. The worktree has extensive unrelated edits, including `records.py`, `ARCHITECTURE.md`, and several tests; preserve them during scoped commits.
- Design note Breadcrumb audit passed with four resolved labels. Design commit: `a08a375a476722b62c894d817119aa5806b1d7a2`. The Design note was written before its own start checkpoint; Execute used a separate scoped start checkpoint `782744e5a29e9ab23151c56361a3c244b97341d5` on clean product paths. Dirty shared files were excluded from the start checkpoint to avoid committing unrelated edits.
- Added a Record namespace descriptor that binds `Type.records` to the concrete class and `obj.records` to the instance. Moved the base class loading body into `Records.from_record()`; the prior direct method delegates. `TypeRegistry` uses the class path. Tests cover inherited binding, class-side misuse of projection, abstract base rejection, and dynamic loading.
- Focused Kernel and architecture tests: 66 passed. Full Python suite: 179 passed. Ruff across `src` and `tests` and scoped diff whitespace checks passed. The installed editable Tarav tool was refreshed. Product completion commit `c70a0ee7fa1c78287da1694f9d0c8598887635af` contains only this slice's changes; pre-existing worktree edits remain. Commit Breadcrumb audit passed without POIs.
- Product.Surface capture: seven new labels across six code, test, and architecture surfaces resolve. Full audits of `records.py`, `tests/test_architecture.py`, and `ARCHITECTURE.md` retain respectively 3, 10, and 29 older position POIs; none points to a new label. Other changed surfaces audited cleanly.
- Wiki start checkpoint `9a906f7ad89f0a94bd4d2cbbe9f877f5cc3dc0e9`; daily and `record-framework.md` capture committed as `8741982585c12b889221a25f65dfd31f66f1fc7b`. The four new Wiki labels resolve and the commit evidence audit passed. The topical note's full audit retains 144 older position POIs.
