# Attic workflow and System Project maintenance

Knowledge.Surface: wiki

<!-- tarav.sessions
7c51c146 = codex:01a15606-58f7-77a0-9600-8d0b0bf63a82 @7c51c146657d59fa35293ab3b44b6be3b0e38654e1dfd05d83fa752a7bd0f4c4
-->

## Impl.Abstract

Implement a real Python AtticWorkflow for cheap conservation of displaced
material, with a small manifest model and metadata-only checks composed into
the Tarav System Project. Refresh its owning skill in the companion
[documentation request](../../../tarav-md/notes/live/867-attic-semantics-impl-req.md).
Status: implemented; verification and capture closure in progress.
<!-- tarav.breadcrumb 09669f665e26 -->

Contents remain opaque. A manifest is a depositor's self-declaration: checks
cannot establish that its description, former locations, completeness,
recoverability, or disconnected status are true. They must not open, traverse,
hash, index, interpret, or even require existence of its declared payload path.
No automatic movement, recovery, deletion, normalization, payload audit,
retention policy, migration, or dedicated CLI is in scope.
<!-- tarav.breadcrumb fbc662cec7f5 -->

## Design narrative

The User wants material moved aside from active development without losing it,
until deliberate investigation, extraction, or removal. Lightweight maintenance
belongs to the System Project, while the Attic workflow owns its semantics.
<!-- tarav.breadcrumb 06b69a96da15 -->

Inspection: `src/tarav/l2/project/system.py` currently composes active-Project
and unowned-gitleaks checks. `l3/runtime.py` registers workflow and Record
Types. `l1/checks` and `l1/checks/chains.py` supply the existing situation,
atomic POI, action, and detector machinery. There is no Attic implementation.
`tarav-md/skills/tarav-pkg/references/attic.md` owns the existing convention.

Data shape first: keep the current `deposit.json` convention: `class` =
`tarav.attic.deposit`, integer `schema_version` = 1, UUID string, UTC
`deposited_at`, nonempty `sources` list, local relative `material`, nonempty
`reason`, and `dependency_status` = `disconnected`. Extra depositor hints remain
allowed. These are format requirements, never verified claims. `reason` should
orient an investigator to what was stored and why. Old shapes produce findings
without fallback readers or implicit edits; investigation remains possible.

Attic and Deposit are path-backed TaravObjects, not registered Archive
Artifacts or Entity promises. Their ordinary Tarav Records represent the
handlers; the existing deposit manifest is a separate lightweight data format.
AtticWorkflow is an explicit Archive child with its own identity. Discovery
reads only immediate deposit directories and `deposit.json`. No payload
existence check is added: opacity overrides earlier assistant suggestions.

Boundary discipline: one Pydantic manifest model owns format validation.
Manifest checks report missing, unreadable, and invalid metadata separately;
a UUID check reports duplicate valid declarations. Listing errors are surfaced
without claiming an empty, healthy depot. Missing, unused depots are empty and
are not created. Situation identities use the depot path and directory name
for metadata problems, and depot plus UUID for collisions. Details may change
without multiplying actions. Use Situation Chains and the existing resolution
action behavior, with Attic-owned action Types. Check code never repairs data.

Subtract before adding: remove obsolete Diagram.Attic/Diagram.Model progression
from the documentation rather than adding another migration or promotion stack.
The companion documentation request handles that surface.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/` by umbrella routing.
Relevant context: `record-archive.md`, `projects.md`, and this session's exact
User Turns `7e5cab371f946325` and `952e05cea4612df7`.
Capture destinations: `attic.md` and `daily/2026-10-19.md`. Status: pending.
No Diagram Models, Drafts, or authorization Gates are needed.

## Execution.Plan

1. **Feature — workflow and metadata checks.** Add `l1/attic` with workflow,
   path handlers, manifest format, identified suite and situation chains.
   Register workflow, POIs, handlers, and actions in runtime; compose its suite
   into TaravSystemProject. Observable: library and System checks report
   malformed manifests without touching payloads. Verify focused Attic tests,
   System Project tests, action resolution tests, and architecture tests.
   Status: verified.
2. **Feature — operational guidance.** Execute the companion documentation
   request, update architecture and authoritative agents-file source, compile,
   and verify documentation and real metadata inspection. Status: pending.
3. **Validation and closure.** Run project checks including non-routine suites,
   distinguish unrelated concurrent findings, capture implemented surfaces and
   Wiki discussion, and commit under the Hugentics evidence workflow.
   Status: pending.

Risks: other agents are developing in these same repositories. Preserve their
changes and use scoped product commits. Some retained manifests predate the
documented schema; report those rather than silently migrating them. A need
for payload inspection, a new retention policy, or a broader storage migration
is a design deviation and requires alignment before expanding scope.

## Impl.Log

- Design inspected the current depot's nine manifests without opening material.
- Execute start checkpoint: `ac420cd88e099c3b9ac4e9a52da5529a28da11f1`;
  pre-existing concurrent work preserved as found, evidence marked unknown-session.
- Documentation repository start: `1d085d57b61b3d9100279e2c6d9ac1a9e9aeaeff`.
- Current session resolved once and refreshed through Chatlas; selected User
  Turns queried and reference markers rendered through the public commands.
- Cold-reloaded both complete requests before product edits. Implemented
  metadata-only discovery and strict declaration parsing, workflow registration,
  Situation Chains, and Attic-owned resolution actions in the System suite.
- Feature checks: 40 focused Attic/System/action/chain tests passed; the expanded
  selection with architecture passed 88 tests. After final changes, the
  Attic/System/architecture selection passed 75 tests. Ruff passed over all
  `src`, `tests`, and `scripts`.
- Corrected initial test assumptions about tuple results and POI `.identity`;
  these were test API errors, not product-format changes.
- `tarav status --project . --all --json`: 1,175 checks completed, no incomplete
  checks; all 48 configured pytest file suites had zero test findings. The
  broader 78 findings concern existing hooks, bootstrap, action fixtures,
  gitleaks, and other Skillware surfaces; no automatic repairs were attempted.
- Real Attic metadata check: nine deposits, two invalid older manifest shapes
  (`20260826T030536Z-chatlas`, `20260826T213706Z-tarav-skills-reboot`). No
  manifests or opaque material were changed. The first diagnostic script
  wrongly called a LiteRecord method on a POI's dict; corrected the observation
  and reran it successfully.
- Live System status initially failed because its harness lacked rdflib.
  Refreshed its existing environment through `tarav project harness sync` after
  start checkpoint `e7e1c3d198a231567cca56cf1418852c2f58dc23`. Status then ran
  and opened the two Attic actions, alongside ten unrelated bootstrap findings.
  The harness dependency lock changed; no System Project code was changed.
- Refreshed the depot's unversioned `~/Documents/tarav/attic/AGENTS.md` to
  permit bounded metadata maintenance and retain payload opacity; its older
  blanket no-scanning wording conflicted with this explicit User request.
- Product capture ran on all modified Python/Markdown surfaces. No semantic
  annotation was justified in the package re-export file; TOML and JSON have
  no native Inlined Capture convention. SKW's authoritative Markdown content
  was captured through temporary working projections, persisted back to source,
  and compiled; after removing those projections, product position observations
  were refreshed and audited successfully. No payload-derived claims were made.
- Skill build and check: zero findings. Installed skill paths already resolve
  to the maintained product. Agents source compilation: zero findings. The
  installed editable Tarav tool was refreshed through uv.
