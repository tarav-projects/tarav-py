# Impl.Req 870 — Record namespace extension migration

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

**Knowledge.Surface:** wiki. **Status:** complete.

Move the Record API and its extension methods into the selected `Records` namespace. Maintained Tarav callers should use `obj.records.to_record()` and `Type.records.from_record()`, `.validate_record()`, and `.record_example()`. Remove the duplicate direct API on `TaravObject`; keep distinct APIs such as `TypeRegistry.from_record()` and storage adapters. Keep `_record`, `_from_record()`, and `_to_record()` as object state and protected construction/projection hooks in this migration.
<!-- tarav.breadcrumb c9021145029cd49a4c173a8569ab93e29309dab1b64c7c4b18179c8b7ad6834d -->

## Design

Today `TaravObject.Records` performs projection and loading, but `validate_record()` and `record_example()` forward to classmethods on the Object Type. Concrete Types override those classmethods; some extend them with `super()`. This creates two public Record paths and leaves the extension mechanism outside the namespace. Move each override into a nested `Records` subclass that inherits its parent Type's `Records` class. The namespace method can use `self._owner` for the concrete Type; `super()` then follows the corresponding namespace inheritance. The user explicitly observed that calling `super()` was already necessary before the migration, so preserving that relationship is the requirement, not a new burden.
<!-- tarav.breadcrumb 8caa4a4d0f61e19bbe076a750fb61b8cf8607d1079398859e413a52bdbb9a9e5 -->

Use the existing `NamespaceBase` selection and composition check. Do not add automatic namespace merging or compatibility wrappers. Keep the exact Record validation, type matching, construction, and copy semantics. A class that specializes a Record example or validator owns that specialization in its `Records` class; inherited behavior should remain bound to the concrete Object Type.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant note: `record-framework.md`; daily capture: `daily/2026-10-08.md`. Supporting Chatlas session is declared above. Capture status: pending.

## Execution.Plan

1. Inventory overrides and direct calls; identify independent `from_record`/`to_record` methods.
2. Move base and concrete Record example/validator overrides into `Records` classes, preserving `super()` chains.
3. Migrate maintained source and tests to qualified Record paths; update architecture documentation and namespace behavior tests.
4. Run focused tests, Ruff, and the full Python suite. Submit and audit Product.Surface Breadcrumbs on materially supported surfaces.
5. Make scoped evidence commits and capture the outcome in the Wiki daily and topical notes.

## Impl.Log

- Design: current code has direct wrapper methods on `TaravObject` and many concrete classmethod overrides. `TypeRegistry.from_record()` and Pydantic draft interfaces are separate APIs.
- Execution: moved Record validation/examples into nested `Records` classes and removed the four direct `TaravObject` APIs. Migrated maintained callers; kept Diagram storage-handle `to_record()` and registry dispatch as distinct APIs. Class creation now rejects misplaced direct Record overrides.
- Verification: focused namespace and Object contract tests passed; full shared-worktree suite passed (182 tests); `uv run ruff check src tests` and `git diff --check` passed. Product Breadcrumbs were submitted on Kernel Records, Blessing Record, namespace tests, and architecture documentation. Their audits resolve new labels; older labels with stale position observations remain nonblocking POIs.
- Scope: five preexisting untracked files were edited to keep the active shared worktree compatible. Their preexisting content and these migration edits remain in the worktree outside the scoped commit. A temporary clean-baseline preview checked the exact committed file set.
- Commit closure: product `b91bbee598182d090fae93e5f903ebf27f05f0ce` contains 102 tracked paths, isolated from unrelated worktree edits. The exact commit preview passed 54 focused and architecture tests plus Ruff. The shared worktree was restored byte for byte after committing. Wiki capture landed in `5a8d74537238f16b7a9700fd5bf8c0784b81616b`, followed by heading correction `8b88686772b07723392d60c12866b5ee9dc29de3`.
- Post-commit check: product commit Breadcrumb audit resolved all three attachments with no POIs; restored-worktree focused tests passed (19 tests). Wiki additions have resolved new Breadcrumbs. Older Breadcrumb labels on the daily and some large product surfaces retain stale position observations and remain nonblocking POIs.
