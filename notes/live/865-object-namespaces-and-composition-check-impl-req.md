# 865 — Object namespaces and composition check — Impl.Req

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: Ready. Phase: Develop.

Introduce a small object-level namespace mechanism in Kernel, demonstrate it through `obj.records`, and reject class compositions that silently lose an independent parent's contribution to the same namespace. Keep storage/navigation in TaravRecords and retain existing Record call sites for a later, explicit migration.
<!-- tarav.breadcrumb 7b15a924a199091347afff993b692c68102388494355bd821aae360aafb88cf0 -->

## Design narrative

The User wants explicit `obj.<namespace>.<member>` paths without creating a separate workflow for every method family. Multiple independent workflow bases may contribute to one namespace. A common `NamespaceBase` binds the object; namespace classes can be defined outside their host classes. The composed host chooses the combined namespace class explicitly, as in `ClassB.P = PXY`; Python MRO must not silently choose only one independent contribution.
<!-- tarav.breadcrumb 1604651a6b406b44f313216d5957e69502e18e5dd710cf5f365cc24bfc5e76f8 -->
<!-- tarav.breadcrumb 9fd8c3e9beb5373acb4e504621919baf1da8925e58b1deba4668d0740b87c95e -->
<!-- tarav.breadcrumb 99f5970e7988de7e759753123c8da440d2553b6d20a74d82a8e3a57d63e96a1c -->

The User prefers the simplest workable pattern and asked for automatic checks. The check should validate the selected namespace class against every direct parent contribution, without automatic namespace merging. A regular property binds `obj.records`; the class holds `Records`. Namespaces are stateless views of the object for this slice.
<!-- tarav.breadcrumb 10d0bb650a80c17fec9b5e916c507ada5a960f6864a4b52156dfee33b16ba637 -->
<!-- tarav.breadcrumb 8c90e5f4972e0cd5336072a25bb94b689899e54f6e824b6846d1d51ba6e32895 -->

Current code: `TaravObject` in `tarav.l0.kernel.records` owns `_record`, `to_record`, `from_record`, hooks, and validation; many existing classes override its hooks and many callers use its root API. The user's preference is to move this family under `records` while keeping behavior the same. This slice establishes a real namespaced instance path and retains the root API; a wholesale migration of class-level loading and all call sites is separate because it affects a large established contract. The storage workflow `tarav.l1.records` remains independent.
<!-- tarav.breadcrumb 1c8778f2834a77b6645155ef10b0e7750017d49af413606f296b600f8cbd017b -->
<!-- tarav.breadcrumb eee02ba305940cb42678d46b19a1055bbc565bf638a8b46e4ca63986ba2d7c5d -->

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`; topical candidate `tarav-records.md`; daily `2026-10-07.md`. Supporting session: `codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8`. Capture status: pending submission and audit.

## Execution.Plan

1. Add a reusable bound `NamespaceBase` and class-composition validation in Kernel. Independent host bases can contribute the same namespace and a concrete class explicitly composes them.
2. Add `TaravObject.Records` and `obj.records` with an initial Record projection, retaining existing methods for current callers.
3. Test bound access, independent composition, rejection of a dropped contribution, inherited namespace behavior, and Record output parity. Update architecture guidance.
4. Capture Product.Surface Breadcrumbs, run focused checks, make scoped evidence commits, and capture daily/topical Wiki notes.

## Impl.Log

- Design: reviewed Constitution, project routing, Record source and callers, and current worktree. The worktree contains unrelated edits, including `ARCHITECTURE.md` and architecture tests; preserve them.
