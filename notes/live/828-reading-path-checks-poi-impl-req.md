# 828 — Reading paths, shared Checks, and POI providers

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
-->

## Impl.Abstract

Status: ready for implementation. Knowledge.Surface: wiki.
Product: `tarav-py`. Alignment.Mode: Interactive.

Implement the discussed chain as one coherent feature: typed declarations on
SKW blocks → declared reader-context paths → shared executable Checks →
CheckResults providing contextual POIs → explicit POI raising. Include the
necessary block identity migration and integrate the existing skill checker.
<!-- tarav.breadcrumb 5af14522c3cc566d4d60c315b78084b95d70d081d41e88641eafd1424ba63612 -->

Non-goals: semantic scoring of content claims, agent execution, automatic
content collection or repair, Batchy routing-table generation, universal
check discovery/scheduling, or rewriting every existing linter. This request
designs the complete structural slice, not just placeholder classes.

## Design narrative — user decisions

### Expected reader context

Reader.Context.Path belongs to `skw.skills`. It describes context expected
from a declared route, not everything an agent actually knows. A route may
start at Skill.Description, enter SKILL.md, follow a link to file A, and read
preceding blocks before X. Authors can avoid repetition by declaring what X
expects the reader already to have encountered.
<!-- tarav.breadcrumb 31a1db653fa71fc8a236d684a669f563f09b8cc152ffd1d6b37f969a973d8376 -->

Keep per-path availability and expose its intersection and union. A dependency
can hold on one route and fail on another. Report the dependency and a path
that misses it. Typed links distinguish expected traversal from optional
consultation; dependencies distinguish inlined content from referenced
content. Link entry semantics matter: starting a file and jumping to a block
do not supply the same preceding context.
<!-- tarav.breadcrumb 9ec5de7abd593e06ddddc8b18571b76395308a730d6659f9dc59ef86bb63eb6a -->

### Block declarations and identity

Ordinary blocks can declare provided content, embedded typed links, inlined
entities, and required reader context. Specialized link/inline blocks expose
the same declarations; an embedded link need not become a separate block.
Consume explicit declarations uniformly, without inferring semantics from
headings or prose. These declarations are claims, not proof of their truth.
<!-- tarav.breadcrumb 2a3f6927518288b2757755b8893ef91690db16a9c2e2aa8f7c557a26c7087e96 -->

Targets require only `TaravEntity`, including entities from other workflows.
Do not introduce a `SemanticEntity` base. Blocks are themselves TaravEntities:
stable UUID identities, with separate free-text labels. A block reference may
use its Ship for exact identity or a label for scoped, weaker selection;
ambiguous labels must not resolve silently. Prefer base types and semantic
subtypes to a general object with mode strings, so the Type Graph exposes the
distinctions. Reading-path mechanics neither collect nor render the entities'
content.
<!-- tarav.breadcrumb 95f65c1404ad6489ffddfe0b3c9da18891ebb36e8b43dfe49fd1149fc842b253 -->

Structural checks judge whether declarations supply the required entities in
the required form. They do not judge whether output substantiates those
claims. Semantic checks and scoring are separate future consumers.
<!-- tarav.breadcrumb 0fa55e6db86a3355b2e889c4dfdaf6733d91b7f4bbea311be8e7694a9bc1dbfe -->

### Checks are independently usable capabilities

`Check` defines reusable checking behavior and binds its inputs. Optional
`CheckProvider` exposes appropriate instances through `obj.checks`; do not
add this obligation to every TaravObject. Providers can live on objects,
types, or workflows. Their definitions belong where the semantics fit.
<!-- tarav.breadcrumb dce0914ef0f97cbe02966a0c63e967f38949c613f6b07c38fd18edd102538603 -->

Runners and linters select, execute, and aggregate checks. They may collect
object-supplied checks, use explicit pools, and construct cross-subject checks
that do not belong naturally to one object. All share the same Check contract.
<!-- tarav.breadcrumb 34a0fbee1dcf95e248b306db525cab756901398f89acc2a05ba6b61402282827 -->

One check or one object's checks must run without a linter, enabling targeted
experiments. A larger orchestrator is an optional consumer, not a prerequisite.
<!-- tarav.breadcrumb 3929f8aac6db66ef5baa7ff78045feeae20cfdcb443961c2b51966a6121d7352 -->

### Results provide POIs; POIs own raising

`CheckResult` is a POI provider. It retains or can access everything necessary
to produce POI instances, alongside whatever result data the check needs.
Do not introduce another finding model duplicating POIs. “Findings” may name
the POIs, but the objects describing check findings are POIs themselves.
<!-- tarav.breadcrumb a04ae03f10180928f28eac89ebc0d152d3c9795ce3fa1d7940361b7933d14ca7 -->

POIs are an agent-facing communication surface with investigation context,
including the check and occurrence. Producing/inspecting them and raising
them are separate actions. Raising semantics belong to the POI workflow,
not a second mechanism in Checks. A result can be lighter than its POIs.
<!-- tarav.breadcrumb 00bd204c02751fbe691af51198b504a6f1b13cb6c71a30690b14f352b48b0932 -->

## Inspected implementation — 2026-09-30

These observations describe source inspected during Design, not new behavior:

- [`document.py`](../../src/tarav/l1/skw/document.py): `SkwBlock` is currently
  a TaravObject/Mapping with a nonempty string `id` and retained `output`.
  Literal and agent-generation subclasses already exist. IDs participate in
  document selection, generation references and lock baselines.
- [`skills.py`](../../src/tarav/l1/skw/skills.py): typed `SkillLink` already
  produces retained output through the loading model. Its `label` currently
  means rendered link text, and its `target` names a loading node.
- [`loading.py`](../../src/tarav/l1/skw/loading.py): declared `.skw/loading.json`
  nodes bind source blocks; parents, links, includes and requirements feed
  path analysis. Analysis already tracks inlined/referenced sets, path-local
  missing context, cycles, reachability and a traversal limit. It also emits
  finding dictionaries and shares a module with rendering/composition.
  Availability currently centers on loading nodes, not arbitrary entities.
- [`l2/skw/skills.py`](../../src/tarav/l2/skw/skills.py) and
  [`pois.py`](../../src/tarav/l2/skw/pois.py) integrate analysis and map legacy
  dictionaries into typed SKW POIs. Reuse their orchestration, not a second
  competing reading analyzer.
- [`poi/primitives.py`](../../src/tarav/l1/poi/primitives.py): `POICheck` is a
  finding-kind declaration, not the proposed bound executable Check.
  `POIInstance` already provides stable identity/state, retained records,
  check/coordinate/evidence context and `.error()`. `POIFinding` is already a
  POIInstance subtype, not the prohibited parallel finding representation.
  `POICollector.emit()` collects instances. There is no shared CheckProvider /
  CheckResult POIProvider contract yet.

Existing tests to extend: `test_skw_loading.py`, `test_skw_skills.py`,
`test_skw_poi.py`, `test_poi_primitives.py`, `test_poi_workflow.py`, and
`test_architecture.py` under `tests/`.

The required md-library comparison inspected `md_library/lint2/runner.py`:
it separates check execution status from findings and supports node/document
checks. Reuse that distinction, not its separate LinterFinding model or its
domain-specific gating policy. Missing prerequisites must not masquerade as
a successful empty check.

## Proposed MVP — implementation choices, not fixed user schemas

### Ownership and imports

```text
tarav.l1.poi                 POIProvider, POI instances, collector/raising
tarav.l1.checks              ChecksWorkflow, Check, CheckResult,
                            CheckProvider, small runner
tarav.l1.skw.skills          typed reading declarations, paths, availability
tarav.l2.skw.skills.checks   concrete checks and integration providers
tarav.l3.runtime            trusted Type/Workflow composition
```

Convert the two existing `skw/skills.py` modules into packages where needed,
preserving their public module paths and existing Type identities. Keep
rendering with SKW production/composition, not the path evaluator. Lower
layers must not import l2 concrete checks: an l2 subject wrapper/provider or
explicit composition supplies them. Do not add automatic registration hooks
to every object merely to enable `obj.checks`.

Give new semantic types class entities and explicit workflow ownership using
the existing patterns. Use Ships for entity references and the trusted record
registry for dispatch; never import a Python path selected by retained data.

### Small shared interfaces

Proposed usage (names of concrete reading checks remain adjustable):

```python
check = ReadingDependenciesCheck(graph=graph)
result = check.run()
pois = tuple(result.pois())           # No emission or exception.

results = run_checks(checks=subject.checks)
for result in results:
    for poi in result.pois():
        collector.emit(poi)          # Explicit POI-owned emission.
# poi.error() remains explicit Python exception escalation.
```

`CheckProvider.checks` can initially be an iterable of bound Checks; no
collection framework is required. `POIProvider.pois()` returns POIInstances.
Repeated inspection of one result must describe the same execution, not rerun
the check against changed files. Results can hold POIs or sufficient immutable
execution data to construct them, without another public Finding type.

Distinguish completed execution, unavailable prerequisites/incomplete analysis,
and execution failure. A completed result can provide zero or many POIs;
“completed” does not mean “no problems.” Keep exception policy explicit and
do not swallow interrupts. The runner aggregates the same independently usable
checks; it does not introduce a second behavior contract.

Build on POICollector rather than add another event bus. If a default in-memory
collector is exposed, keep explicit injection/isolation available and make
emission opt-in. Do not conflate collection with `.error()`, auto-persistence,
or blessing. Preserve existing POI identity/state and blessing semantics;
execution timestamps or result IDs must not make recurring issues appear new.
Link execution context without replacing the stable check-kind/occurrence
identity. POIs not originating in Checks remain valid.

### Reading declarations and evaluation

Use typed declarations for inline availability, reference availability,
required traversal links, optional consultation links, and corresponding
reading dependencies. Suggested names are implementation choices; subtype
behavior, not string dispatch, must express the distinctions. Store declarations
on blocks, with optional empty declarations for generic non-skill blocks.

A semantic target and a reading destination are different references. A link
may point at an arbitrary entity; traversal additionally needs an explicitly
resolvable block/file-entry destination. No content lookup or rendering is
implied by an entity's presence. Optional consultation makes a reference
available but does not silently add the target's content to every path.

For the first evaluator, check a block's prerequisites against its incoming
context, then add that block's declared contributions for subsequent reading.
This avoids a block satisfying its own prerequisites simply by declaring that
it provides them. A specialized composite can expose an explicit internal
reading sequence if needed; do not infer ordering inside opaque prose.

Keep delivery sets distinct. Define and test whether a particular dependency
accepts inline availability, reference availability, or either. Do not silently
substitute a union of paths for availability on every path. Retain a witness
path and relevant declarations for failures. Starting at a section must not
credit blocks skipped on that route.

Reuse the existing bounded traversal and cycle handling where sound. Analysis
returns path/state/completeness data, not an intermediate findings domain.
Checks interpret that data into POIs. Truncation or unresolved routing prevents
an unconditional all-path success claim; report incomplete coverage. Multiple
entry points and disconnected/cyclic components need explicit checks. This
MVP need not solve arbitrary cyclic instruction programs.

### Required concrete checks

- Declaration/destination consistency: missing or ambiguous traversal targets,
  invalid source bindings, and unsupported required declaration semantics.
- Reading dependencies: target unavailable in the required delivery, with
  consumer block, requirement, available context and witnessing path.
- Coverage/topology: unreachable blocks, cycles that prevent the declared
  evaluation, and incomplete bounded analysis, without claiming every cycle
  in every possible reading model is inherently invalid.

Each result provides actual POIs with inspectable context back to its check,
subject block/graph, requirement/target and occurrence/path. Extend existing
SKW POI types where semantics match. Keep unrelated legacy linter conversion
bounded; do not rebuild all output/generation checks in this request.

### Explicit retained-data migration

Inventory maintained SKW packages and fixtures before migration. Produce an
explicit old-ID → UUID mapping scoped by document/package; equal old labels in
different documents do not establish shared identity. Preserve already-valid
identities. Use TaravEntity/Ship identity conventions, with UUID serialization,
and keep readable labels separate. Labels are not required globally unique;
ambiguous convenience selection reports candidates rather than choosing one.

Update affected block references, loading bindings, dependencies and mutable
indexes together. Inspect generation records and lock hashing before changing
them: preserve historical evidence and existing stale/clean standing, never
refresh baselines merely to hide migration effects. Where immutable historical
references cannot be rewritten, retain an explicit migration mapping consumed
by the appropriate historical resolver, not a permissive live-record fallback.

Preserve the content of retained block outputs, including agent-generated
prose, and the intended reading/navigation meaning through identity migration.
Exact bytes of `output` and compiled text need not remain unchanged: stable
Ships may change generated anchors and link targets. Update those surfaces and
their affected baselines explicitly without rewriting unrelated content.
Resolve SkillLink's existing link-text `label` explicitly (for example, a
separate caption field); do not change the visible link text accidentally.
Translate legacy reading edges into equivalent typed block declarations only
where meaning is known. Report unknown/ambiguous cases; no runtime auto-repair
or speculative claims that text provides new entities. Dry-run the inventory
and mapping before writing; external user depots require explicit selected
scope. Product fixtures and maintained source packages are the initial scope.

## Execution.Plan

1. Recheck source and retained package inventory; fix the MVP names and record
   fields in this note. Add focused failing tests for the end-to-end contract.
2. Add POIProvider and shared Checks/provider/result/runner contracts. Verify
   independent single-check use, multi-subject pools, execution status, stable
   result inspection and explicit emission with existing POI/blessing tests.
3. Migrate SKW blocks to TaravEntity UUID identity plus labels, including
   retained references and regression fixtures. Preserve Type IDs and output.
4. Add typed block declarations and refactor existing reading traversal into
   analysis data separate from rendering/check reporting. Test path-local,
   intersection/union, optional/required traversal, section entry, skipped
   content, cycles, unresolved routing and bounded completeness.
5. Implement reading Checks and providers in l2; adapt current package check /
   evaluate and CLI reporting to consume these same results and POIs. Verify
   context navigation and explicit collection/error escalation end to end.
6. Run focused suites, layer/Type registration tests, then broader tests/Ruff
   proportional to the migration. Update ARCHITECTURE and CLI help where
   changed; reinstall the editable tool if installed command behavior changes.
7. Attach supported Breadcrumbs to changed authoritative product surfaces,
   rerun affected checks, log results here, and complete bounded Wiki capture
   and scoped evidence commits through the Hugentics execution workflow.

Acceptance example: two routes reach X; only A provides entity E inline.
X requires E inline. Analysis exposes both routes, intersection excludes E,
union includes E, and the independently run CheckResult provides a POI with
route B as evidence. Merely inspecting the result emits nothing. Explicit
POI collection records it; `.error()` raises it. Replacing A's declaration
with a consultation link does not satisfy the inline dependency. No semantic
scoring or content generation occurs.

## Impl.Req.Wiki

- Product project: `/Users/pereiro/projects/taravangian-project/tarav-py`.
- Wiki owner: sibling `tarav-md`; root `notes/wiki/`.
- Relevant notes: `reader-context-path.md`, `checks-workflow.md`,
  `poi-system.md`, and `skillware.md`.
- Current-session design evidence is embedded above, preserving exact User
  Turns independently of Wiki summaries. API choices in the proposed MVP
  are agent design work, not additional user decisions.
- Capture: append the implementation-design handoff to `daily/2026-09-30.md`;
  existing topical captures already carry the discussed design.

## Impl.Log

### 2026-09-30 — Design

Inspected SKW loading, typed blocks, package checks and POI mechanics, plus
md-library's check/result separation. Produced the bounded implementation plan;
no product code changed and no product tests claimed as executed.
Start checkpoints: tarav-py `b3374678`, tarav-md `f9c214f3`.
Breadcrumb submission/audit and scoped closure follow after finalizing this note.

Capture verification: 11 new Breadcrumbs in this request and one in the Wiki
daily handoff. Both surface audits returned `ok`, with no findings. Exact
User Turns resolved; local placement was inspected. Existing topical notes
were left unchanged. No unresolved capture gaps were found.
