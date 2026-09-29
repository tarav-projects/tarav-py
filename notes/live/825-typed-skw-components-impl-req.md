# Typed SKW components and retained output

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
-->

## Impl.Abstract

- Knowledge.Surface: wiki
- Scope: typed SKW blocks and SkillLink; Batchy routing is follow-up work.
- Status: complete.
- Outcome: extensible typed SKW blocks with current output retained in source,
  demonstrated by a code-produced SkillLink in the built-in skill specialization.
- Non-goals: implementing Batchy routing tables, a mechanical agent router,
  restoring Attic systems, automatic agent generation, or deployment.

This implementation request applies the recent typed-block discussion to SKW.
The implementation plan below proposes a bounded first slice; supporting user
decisions and implementation proposals are distinguished in the narrative.
<!-- tarav.breadcrumb ab5c2350050e6246a66eb2076d7836fc79bd7658c6d38df9bd9d98def7b2e0ab -->

## Design narrative and decisions

SKW should model generation of arbitrary surfaces. Skill development is built-in
specialization under `tarav.l<X>.skw.skills`; Batchy is an application/style of
that support and should live directly under `tarav.l<X>.batchy_skills`, not
inside `skw.skills.batchy_skills`. Conceptual specialization does not force
package nesting. Exact layers and workflow-parent declarations were not settled.
<!-- tarav.breadcrumb 0e3b94ff2272fe3e67cb573c5b419f79e6abb1737777f0be82c1cdd5641af793 -->

Skills need reusable typed authoring components, not only opaque generated
prose. A SkillLink directs the consuming agent toward a target. It belongs to
skill support, distinct from the general engine's internal generation-context
and dependency references. Code can produce it through a shared template so
occurrences have homogeneous presentation; agent generation is not required.
<!-- tarav.breadcrumb 3fc21f86b65c03c0712908e92fd74ba79ad2ee8d7e92db326bf16e951a8bd496 -->
<!-- tarav.breadcrumb f9ca82671e9a676a09af88ccb2ff4bf693aa86816ebcd8108b9721c0ef2b9245 -->

Every retained block should declare its concrete type and derive from SkwBlock.
The base should carry minimal common data, suggested as id and output. Use
trusted Tarav type registration rather than expanding a hardcoded kind switch.
Do not infer arbitrary import paths from retained data.
<!-- tarav.breadcrumb 0e612deb8ee8dc600a61f92605c5eb4c7dbfa9bd82fd84f542b1264abd96b602 -->

Crucially, output is retained data in `.skw.json`, not just a method that renders
on demand. Both code-produced and agent-produced blocks keep their current
output there. The user considered `return` and selected `output`. The earlier
assistant suggestion that SkillLink need not store output is rejected by this
clarification. Production and assembly must respect this retained-source model.
<!-- tarav.breadcrumb 00c93d3359caf6107021f354ad6a6f433c57f633cd11156803c02336e1e6eb47 -->
<!-- tarav.breadcrumb 9c4bc7d5bca2aabb0e1f9896a8da932455fa6d616a04ad3b6dd0f87fbb5e2c52 -->

## Impl.Req.Wiki

Product: tarav-py. Documentation owner: tarav-md, `notes/wiki/`.
Read [Skillware](../../../tarav-md/notes/wiki/skillware.md#typed-surface-components-and-retained-output)
and [Batchy skills](../../../tarav-md/notes/wiki/batchy-skills.md#batchy-as-a-skillware-extension)
for wider context. This note carries the bounded rationale and direct evidence
needed for a different execution session; Wiki references supplement it.
Original evidence is session 01a0d86c-9538-7be1-af96-014cd4203d61, not a future
executor's invocation. Preserve these attachments when logging later work.

## Impact assessment

Inspected 2026-09-29; recheck on execution because other agents are active.

| Current implementation | Necessary delta |
| --- | --- |
| [SkwBlock](../../src/tarav/l1/skw/document.py) is a TaravObject with kind restricted to literal/generation; Document calls SkwBlock.from_record directly. | Minimal base plus concrete subtypes; dispatch nested records through the existing trusted registry and check the resulting block family. |
| Literal content lives in lines; generation content in output. Document.text, inputs, lint and loading rendering branch on kind. | Normalize current output storage; make producer-specific behavior subtype-owned without losing generation checks. |
| [LoadingModel](../../src/tarav/l1/skw/loading.py) substitutes links/includes and anchors during compilation. Links are dictionaries in loading.json. | Typed SkillLink declaration and explicit output production; reconcile retained output with existing slot composition and analysis. |
| [SkwSkill](../../src/tarav/l2/skw/skills.py) selects SkillDocument only for packages declaring loading, while navigation constructs generic documents. | All load/read/build/check paths must understand the same registered components. |
| [TypeRegistry.from_record](../../src/tarav/l0/kernel/types.py) already resolves trusted types and constructs Records. | Reuse it, not a new parallel plugin registry. |

Already aligned: source owns generated text; compilation does not accept new
generation baselines; skill loading is separate from generic documents; loading
edges are declared rather than inferred from Markdown. Existing tests in
`test_skw_loading.py` cover relative links, anchors, includes, declared paths,
and stale declarations. Preserve these semantics during the transition.

The migration is broader than adding SkillLink: generation dependency reads,
listing, record roundtrips, locking, checks, CLI factory selection, fixtures,
and maintained `.skw/src/` documents all consume the current block shape.

## Proposed implementation boundary

First land typed blocks and one real SkillLink. Leave Batchy schemas and routing
execution for a later request; demonstrate third-party extension using a test
subtype outside skw instead of introducing unused Batchy classes.

Keep the generic base and producer types under l1.skw. Put skill-specific
components under l1.skw.skills, moving/reusing current skill loading mechanics
as necessary; retain publication and cross-workflow checks in l2.skw.skills.
Do not move the whole skill package into l1 or make generic SKW import Batchy.
Preserve existing TypeShips where their meanings remain the same.

Suggested base output shape is the existing list of strings, with an explicit
missing-output state for unfinished production. This is a proposal, not a
user-selected schema. Literal and agent-generation subtypes own their extra
data and operations. Code production should update retained output explicitly;
compile should assemble current retained content, not silently regenerate it.
Staleness checks report POIs without pretending an agent generation occurred.

SkillLink should have one authoritative target declaration consumed by both its
producer and loading analysis. Preserve inline placement supported by current
slots; do not force every link onto its own paragraph. Resolve the small
composition interface during implementation design before migrating fixtures.
Do not duplicate targets in independent block and loading declarations.

## Execution.Plan

1. Re-read instructions, this note, current code and worktree. Follow the
   applicable implementation checkpoint policy and the scope below;
   preserve concurrent Project harness work rather than editing it incidentally.
2. Inventory in-scope records, generation annotations and locks. Define the
   minimal typed record schema and explicit migration, including literal lines
   to output. No automatic legacy fallback or silent load-time rewrite.
3. Implement trusted block dispatch and subtype-owned production/checks.
   Thread the same block support through document and skill navigation/build.
4. Implement SkillLink production, retained output, inline composition and
   declared loading analysis. Reuse path escaping and anchor mechanics.
5. Migrate fixtures and the explicitly agreed maintained skill sources.
   Preserve block IDs, text, evidence and generation history. Schema conversion
   must not falsely mark stale context as reviewed or generation as performed.
6. Run focused and architecture tests, then broader validation; update maintained
   architecture guidance, whose l1.skw.skills references currently predate the
   actual l1.loading/l2.skills split.
7. Capture justified product Breadcrumbs from these original design turns,
   audit final surfaces, record tests and migration results here, and complete
   selective Wiki capture. Do not deploy or automatically make a final product
   commit without applicable authority.

## Verification

- Existing literal and generation records migrate without content loss.
- A registered external subtype loads, roundtrips and compiles without editing
  generic SKW; unknown types and non-block types produce useful failures.
- Deterministic production persists output; compilation consumes that output
  and does not mutate source or generation baselines.
- Link labels, escaping, relative paths, section anchors and inline placement
  work after production; target changes surface stale output as appropriate.
- Loading analysis distinguishes referenced versus inlined material; output
  scraping never manufactures graph edges.
- Listing, reading, compilation and package checks use the same type dispatch.
- Agent generation preparation/recording and context-staleness checks retain
  their existing behavior; failed production preserves previous retained output.
- Focused suites: test_skillware_document, test_skillware_generation,
  test_skillware_navigation, test_skw_loading, test_skw_skills, test_skw_poi,
  and test_architecture; then broader tests proportionate to changed boundaries.

## Implementation scope and remaining details

The first slice is typed core + SkillLink, with Batchy deferred. The proposed
maintained source migration scope is tarav-md/skills plus fixtures,
excluding deployed depots and Attic). Output shape and inline composition are
implementation proposals to make concrete before changes, not fixed user mandates.

## Impl.Log

- Execute checkpoint: `2db73e8` (the existing Project-harness work and this
  request were checkpointed before SKW edits).
- Implemented typed `LiteralBlock` and `AgentGenerationBlock` records beneath
  `SkwBlock`; Document resolves every block through the trusted Type registry,
  rejects non-block Types, and keeps `output` as the retained source
  representation. Added explicit `Document.produce()` and CLI `produce`; it
  validates and writes producer output, while compilation only assembles
  retained output.
- Added skill-owned `SkillLink` with one target declaration, deterministic
  escaped relative Markdown output, stale-output checks, and loading analysis
  that counts its target as referenced context. Added one code-produced link to
  the Hugentics skill. Migrated 36 maintained `tarav-md/skills` source records
  (15 literal and 97 generation blocks) without changing compiled Markdown;
  Batchy and deployed/Attic surfaces remain out of scope.
- Updated SKW architecture/development guidance and fixtures. Existing
  generation annotations, locks, context observations, and stale findings were
  preserved; the migration did not invent baselines or silently rebase output.
- Verification: focused SKW/architecture suite passed 88 tests, the final
  full suite passed 1,381 tests, and `uv run ruff check src tests tooling` plus
  `git diff --check` passed. Reinstalled the editable CLI; `tarav skw document
  produce --help` is available. Maintained package builds reproduced all
  Markdown with no text drift; pre-existing stale generation/context and
  unannotated-link findings remain surfaced by checks.
- Product Breadcrumbs: `src/tarav/l1/skw/document.py` IDs
  `218840d2e598e238395a44e5e66211f2064dfad13f5f4936839bec2bc3942d13`,
  `e1dbc0ae21389449d35926a5dcf9fe717168db8afacbe4ff94f80ae4009325ce`, and
  `432b274a6a49d11a9a31d381a8bad064b544a44d210397fdec9450d6d9bdea97`; the
  `SkillLink` source ID is
  `b7587610e2af5af9ea51dfbddae8571e0b452713dbb757dac8bf38698f7299f3`.
  Both audits returned `ok` with no findings.
- Wiki capture updated `notes/wiki/skillware.md` and
  `notes/wiki/daily/2026-09-29.md`; Breadcrumb IDs are
  `97dcd940ff0d11c69605334367cb3df25172c3196951cbabcdc3c8f6c2eda593` and
  `d5828faeeb944d0ad620eba2f995c7ebd470d12b449997cd6436d9cfce366abf`.
  Both Wiki audits returned `ok`; scoped Wiki commit is
  `3d8ea13742787b6715b88c5f81c5dd3118c88aaf`.
- The current workspace was not provisioned or deployed. Product and live-note
  changes remain uncommitted by policy.
