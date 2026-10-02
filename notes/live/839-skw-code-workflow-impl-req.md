# 839 — SKW Code base workflow

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: implemented and verified.

Introduce `skw.code` as the base workflow for developing instruction surfaces
as typed, inspectable source. It owns the common SKW source and reading
declarations from which specialized workflows such as `skw.skills` can build.
The compiled product remains ordinary content for its reader; the reader does
not execute the SKW source model itself.

Non-goals: a separate compiler workflow, a new block hierarchy, project
onboarding, a generalized agent runtime, or redesigning retained SKW schemas.

## Design narrative

The motivating use case is to reuse the content/generated-block and reading
path primitives outside deployable skills, first for project-agent onboarding.
The shared mechanics therefore cannot remain semantically owned by
`skw.skills`.
<!-- tarav.breadcrumb ba1abfd8abb917b189f7b82e5524b37de4ccf558f570856f98efb32b82b55dd5 -->

The selected name is `skw.code`: SKW is already the family for developing
generated surfaces with software-like structure, and this workflow is the
common base rather than another top-level “agentware” abstraction.
<!-- tarav.breadcrumb 1ce1f8f1a47f4fa65bf3a1dd1f7071519af74d78c78b361d22056843ab4b1aeb -->
<!-- tarav.breadcrumb a5374f6eeb929e7e9b64464e1349398ec5413ee1816a420c1d1415f4b239cb76 -->

“Code” describes the developer-side source and tooling. A reader agent may see
only compiled text or instructions. The conceptual route is therefore
`SKW.Code source → compile/render → ordinary surface → reader`, analogous to
source, compiler, and interpreter without claiming that the product is Python
or that the reader understands SKW Records.
<!-- tarav.breadcrumb b6a33ea553a80b060db5fd854be56aa6568de21ce67b74a4ee51abb7558e5a32 -->
<!-- tarav.breadcrumb 501b543511752be470cbf482fcde441baa8a03f0f1c8ddc15a249f0820d30f93 -->

Compilation remains part of `skw.code`; do not create `skw.compiler`. The
workflow provides a base that later specializations can extend, while
`skw.skills` keeps skill-package layout, deployment, and skill-specific
components.
<!-- tarav.breadcrumb f5a447e306157cda85cb1deb564ae9d0c67eee890bebfbfa25cdf8397c8c78a3 -->

The user explicitly requested implementation through Hugentics Develop.
<!-- tarav.breadcrumb 6b5facfb1957680e8f85db72c942f3844cf2610f32e1da636e714e8b3cc00f7e -->

## Current implementation observations

- `SkillwareWorkflow` owns the neutral document, block, and annotation types.
- Generic reading declarations live in `tarav.l1.skw.reading`, but their class
  entities declare `SkillsWorkflow` ownership.
- `SkillsWorkflow` does not currently declare `SkillwareWorkflow` as its parent;
  it defaults to the Tarav workflow root.
- `LoadingModel`, `SkwSkill`, and `SkillLink` contain genuine skill-specific
  mechanics and should remain in the specialization.

## Bounded contract

Add a singleton `CodeWorkflow` below `SkillwareWorkflow` and make
`SkillsWorkflow` its child. Give the common document/block/annotation and
reading declaration Types `CodeWorkflow` ownership while preserving every
existing Type Ship and retained Record shape.

Expose common authoring imports from `tarav.l1.skw.code`. Put reading contracts
under that namespace and update internal consumers. Keep `SkwBlock` neutral:
typed annotations and workflow placement add semantics; no `CodeBlock` subtype
is required.

Do not generalize the existing skill loading engine in this slice. It may
consume the common declarations, but its package graph, rendering conventions,
and checks remain owned by `skw.skills`. This establishes reusable primitives
without prematurely specifying the project-onboarding workflow.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`.

Integrate the settled ownership distinction into `skillware.md`: SKW Code is
developer-side source and mechanics; Skills is one specialization; the reader
consumes the compiled surface. Record the implementation once verified.

## Execution.Plan

1. Add the `SKW.Code` workflow identity, class, public namespace, and explicit
   workflow-parent relationships.
2. Move generic reading declarations beneath `skw.code` and update active
   imports without retaining a second authoritative module.
3. Reassign common source Types to `CodeWorkflow` while preserving Type Ships
   and Record schemas; keep skill package Types under `SkillsWorkflow`.
4. Register the workflow and add architecture tests for hierarchy, ownership,
   imports, and runtime registration.
5. Run focused tests, the configured suite, lint/diff checks, Product.Surface
   Breadcrumb capture, and bounded Wiki capture.

Acceptance: runtime navigation exposes `skillware → skw.code → skw.skills`;
common source and reading Types resolve to `skw.code`; skill-specific Types
remain owned by `skw.skills`; existing SKW Records and behaviors continue to
work.

## Impl.Log

- Added `CodeWorkflow` with an established Workflow Ship and registered it
  between `SkillwareWorkflow` and `SkillsWorkflow`.
- Added the public `tarav.l1.skw.code` namespace. Generic reading declarations
  now live under `skw.code.reading`; the former parallel module was removed.
- Reassigned common document, block, annotation, generation, and reading Types
  to `CodeWorkflow` without changing their Type Ships or Record schemas.
- Kept `SkwSkill`, `SkillLink`, package loading, reading analysis, deployment,
  and skill Checks owned by `SkillsWorkflow`.
- Updated architecture guidance and added a runtime ownership/hierarchy test.
- Verification: focused architecture/runtime/SKW tests passed (47); the full
  configured suite passed (152); Ruff and `git diff --check` passed.
- Product and Wiki Breadcrumb audits resolve with no outstanding POIs. Position
  refreshes emitted only informational notifications for shifted older labels.
