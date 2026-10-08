# 867 — Record namespace class loading — Impl.Req

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: Ready. Phase: Develop (Design).

Complete the shared Record namespace boundary: `obj.records.to_record()` projects an instance and `SomeType.records.from_record(record)` loads that concrete Type. Keep the established validation, exact-Type checks, `_from_record()` hook, and `_record` retention behavior. Migrate the kernel's dynamic loading call to the new path and exercise both paths through public tests. Broad call-site migration across every domain remains a later slice; this request does not change storage or TaravRecords navigation.
<!-- tarav.breadcrumb 1288ecfac9497d43d48ae24b34ecf98a5a7f3e002fda927285c26c0f1a37146d -->
<!-- tarav.breadcrumb 36b96153a66364ece90f1720da80058059c33e0dac2bc054a29f3865cd149580 -->

## Design narrative

The User wants Record behavior under an object namespace without changing its behavior. The first namespace slice introduced `TaravObject.Records` and `obj.records.to_record()`, but class loading still has only `Type.from_record()`. The current instance `records` property cannot bind a class. The simplest class-side spelling consistent with the object path is `Type.records.from_record()`: one descriptor binds the selected `Records` class to either the object or its Python class. `Type.Records` remains the class-level namespace definition and composition point. The class-side view holds the same base loading implementation; the established top-level method delegates during the broader caller migration.
<!-- tarav.breadcrumb 2f462a2a5a0149e344dbbb0ddeb87d5951893522e4c987be1841b7cf02ef4290 -->

The kernel's `TypeRegistry.from_record()` is a first-class dynamic loading consumer and should use the new concrete class path. Preserve rejection of an abstract `TaravObject`, exact Type mismatch, strict Record validation, exact constructed class, and retention of the supplied Record. Avoid a new registry, reflection-based owner lookup, or per-subclass generated namespace classes. Tests should show inherited `Records` binds to the actual subclass and that a class view cannot project an absent instance.
<!-- tarav.breadcrumb 57dbb943c98c521a9cb6b77ddf250b298474da462189c7772ec86b2bec539715 -->

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant Notes: `record-framework.md` and daily capture. Supporting session: `codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8`. Capture status: pending Execute.

## Execution.Plan

1. Cold-read this request, the kernel Record implementation, TypeRegistry, and relevant tests. Check the shared dirty worktree before product edits.
2. Bind lowercase `records` to an instance or its concrete class. Move the base class-loading body into the Record namespace; keep the established direct call as a delegating entry during caller migration.
3. Change the kernel's dynamic loading call to the namespaced path. Test class/instance binding, round trips, and existing validation failure cases. Update architecture guidance.
4. Capture Product.Surface Breadcrumbs on each changed surface, run focused and proportionate full checks, make scoped evidence commits, and capture Wiki daily/topical context.

## Impl.Log

- Design inspection: `TaravObject.Records` already implements the projection; `TaravObject.from_record()` owns the class-loading body. `TypeRegistry.from_record()` calls the selected concrete class's direct method. The worktree has extensive unrelated edits, including `records.py`, `ARCHITECTURE.md`, and several tests; preserve them during scoped commits.
