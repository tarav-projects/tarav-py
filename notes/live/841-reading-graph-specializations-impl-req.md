# 841 — Reading graph specializations

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: implemented and verified.

Introduce a deliberately small `ReadingGraph` Type under `skw.code`. Rename the
existing skill loading graph to `SkillReadingGraph` and make it a subtype, then
introduce an abstract project-bound `ProjectReadingGraph` specialization. This
establishes the executable ontology and common analysis contract before project
onboarding paths acquire their own declarations or retained format.

Non-goals: no project onboarding route yet; no AGENTS.md or project-skill
parser; no generalized graph storage; no movement of skill package binding,
rendering, or checking mechanics into the base merely because they could be
made generic.

## Design narrative

A standard Project should eventually expose a code-controlled onboarding route
from the generic agent, through Tarav's agent context, into the project agent.
AGENTS.md, Tarav's skill, and a project skill are reader-facing entry surfaces
into that route.
<!-- tarav.breadcrumb 9fd16506eef9 -->

The route has the same structural problem as SKW Skills reading paths: authored
content declares what it contains and what a reader needs, while static tooling
analyzes the probable paths designed for that reader.
<!-- tarav.breadcrumb ae3295c1e1b7 -->

The requested bootstrap order is intentionally conservative: first establish a
nearly empty common reading-graph Type, then Skill and Project specializations,
and only then extract mechanics demonstrated by both applications. The base is
an extension point, not an excuse to predict every future graph.
<!-- tarav.breadcrumb 38cee166b5ba -->

`ReadingGraph` is the selected name. Its semantics are static analysis of a
declared probable reading route, not control of the agent's actual runtime
behavior. Agents may deviate; the graph helps authors determine whether the
route they designed supplies the context its blocks declare.
<!-- tarav.breadcrumb c8912cdfa5d8 -->
<!-- tarav.breadcrumb 0bd81c65424a -->

The user authorized this first implementation slice through the Develop path.
<!-- tarav.breadcrumb 9f6129f3b666 -->

## Current implementation observations

- `tarav.l1.skw.loading.LoadingModel` already implements the Skill package
  graph: source binding, declarations, path analysis, rendering, and inspection.
- `tarav.l2.skw.reading_checks.ReadingGraphCheck` already names the general
  concept but accepts an untyped graph and assumes Skill-specific attributes.
- `skw.code` now owns neutral blocks, annotations, and reading declarations;
  it has no reading-graph Type.
- Project has base and featured Types plus explicit attached workflows, but no
  reading-graph specialization or onboarding path declaration.

## Bounded contract

Add an abstract `ReadingGraph(TaravType)` under `tarav.l1.skw.code`. It owns the
shared `analyze()` contract and declares `skw.code` workflow ownership.

Rename `LoadingModel` to `SkillReadingGraph`, preserve its behavior, and give
its Python class entity explicit `skw.skills` ownership. Update active callers
and explanatory strings; do not retain a compatibility alias.

Add abstract `ProjectReadingGraph(ReadingGraph)` under `tarav.l2.project`. It
binds one `TaravProject` and declares Project ownership, while leaving path
declaration and analysis to later concrete Project Types. This is intentionally
not exposed as `project.reading_graph()` yet: there is no honest default graph
to return.

Type the current Skill reading checks against `SkillReadingGraph`, because
their POI evidence and subject construction still depend on Skill package
bindings. The shared base does not falsely claim those checks are already
generic.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`.
Relevant notes: `skillware.md`, `reader-context-path.md`, and today's daily
note. Capture the new Type boundary and the deferred Project-path semantics
after verification.

## Execution.Plan

1. Add and export the abstract `ReadingGraph` Type from `skw.code`.
2. Rename the live Skill implementation to `SkillReadingGraph`, add its Type
   projection, and update Skill callers/check typing without changing behavior.
3. Add and export the project-bound abstract `ProjectReadingGraph` Type.
4. Add focused hierarchy, ownership, constructor, and existing Skill analysis
   tests; update architecture guidance for the new boundary.
5. Run focused tests, the configured suite, Ruff/diff checks, Product.Surface
   Breadcrumb capture, and bounded Wiki capture.

Acceptance: `ReadingGraph` belongs to `skw.code`; `SkillReadingGraph` and
`ProjectReadingGraph` are discoverable subtypes belonging to Skills and Project
respectively; existing Skill reading analysis remains behaviorally unchanged;
Project path/storage semantics remain explicitly deferred.

## Impl.Log

- Added the abstract `tarav.l1.skw.code.ReadingGraph` Type and common
  `analyze()` contract.
- Renamed the existing implementation to `SkillReadingGraph`, retained its
  package binding, rendering, inspection, and analysis behavior, and typed the
  Skill-owned reading checks against that specialization.
- Added abstract `tarav.l2.project.reading.ProjectReadingGraph`, binding one
  `TaravProject` without inventing a default onboarding graph.
- Kept the Project specialization on its explicit qualified import path. An
  attempted package-root re-export exposed an architecture cycle and was
  removed before completion.
- Updated architecture guidance and added focused hierarchy, ownership,
  abstraction, and Project-binding tests.
- Verification: focused reading/SKW/architecture tests passed (40); the full
  configured suite passed (152); Ruff and `git diff --check` passed.
- Product.Surface Breadcrumb capture completed on the new Type boundaries,
  their hierarchy test, and the maintained architecture guidance.
- Wiki capture completed in `daily/2026-10-03.md` and `skillware.md`; both
  audits passed. Position refresh emitted only informational notifications for
  older labels shifted by the appended sections.
