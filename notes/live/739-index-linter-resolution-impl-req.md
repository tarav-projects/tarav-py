# 739 — Deterministic Index linter project resolution

## Impl.Abstract

Replace the Index linter's implicit cwd-local evaluator with one explicit project target and
a minimal structural default configuration. Delete the HEAD and touch-authority manifests as
inputs to evaluation. Preserve the shared record depot and the concurrent report-model work.

Configurable Index composition, record-level project ownership, and a richer structural HEAD
model remain later design work. This slice establishes the deterministic default they can extend.

**Parked follow-up.** [CT] Every Tarav linter `POI.Class` requires an individual semantic
review; corpus counts prove execution, not correctness. ^c20260821-6u

## Impl.Index

- [CT] `tarav index linter` requires `--project`; a bare flag selects the current directory and
  an omitted flag is an error. ^c20260821-0u
- [DC] The default Index evaluator derives project identity from `.tarav/project.json` and
  resolves evidence and surfaces structurally, without evaluator manifests. ^c20260821-1u
- [RJ] `head-surfaces.json` and project touch-authority manifests are removed rather than
  retained as compatibility inputs. ^c20260821-2u
- [CT] Chat evidence resolves directly from its typed support reference; archive availability
  affects verification standing, never whether the selected project enables resolution. ^c20260821-3u
- [PR] Implementation leaves sparse grounded Index annotations at the durable project, surface,
  and evidence-resolution boundaries. ^c20260821-4u

## Execution.Plan

### Slice 1 — one explicit project boundary

- Put the required optional-value `--project` option on `index linter`.
- Resolve it through the canonical Agentos project model and carry project id/root in the run.
- Include the selected project in the single report model used by text and JSON renderers.
- Prove that the same explicit project produces the same normalized result from different cwds.

### Slice 2 — structural defaults, no evaluator manifests

- Remove `HeadSurfaces`, `head-surfaces.json`, manifest loading, manifest initialization, and
  their compatibility branches.
- Resolve Chatlas support directly by typed reference.
- Discover native Index depots and SKW annotations from project structure. Treat the discovered
  live surface cut as the minimal default HEAD until the richer structural model is designed.
- Make unverifiable blessing evidence unable to silence a finding.

### Slice 3 — close the visited surfaces

- Update tests, CLI help, architecture guidance, and project guidance affected by the contract.
- Add grounded code annotations only at stable decision boundaries.
- Run focused tests, then the Index and full suites as proportionate.
- Audit the working tree without rewriting concurrent edits.

### Slice 4 — capture hosted lines through one record model

- Treat grounded SKW notes and native Markdown lines as the same `SurfaceLine` input.
- Add `index capture preview|land --project [PATH] [--label ...]` to verify each Anchory
  dossier's exact typed attachment and user-message support before constructing a record.
- Make an explicitly selected capture batch write nothing when any selected line is
  unresolved or contradictory; never partially land a requested batch.
- Reconcile the grounded implementation annotations created by this requirement and resolve
  their resulting records back through the CLI.

## Impl.Log

- [TS] Execution of Impl.Req 739 is authorized by the tarav-hugentics implementation invocation.
  ^c20260821-5u
- [OBS] The target worktree already contained concurrent Index report, CLI, linter, surface, and
  test edits before this requirement was created; they are shared state and must be preserved.
- [OBS] The first real run exposed a stored canonical typed scope
  (`Natural.Placement::Skills`) that the legacy `LineScope` regex rejected. The scope grammar
  now accepts canonical double-colon type parameters.
- [TS] Focused Index/CLI suite: 196 passed. Full suite: 2,159 passed. Ruff: clean.
- [TS] Real `tarav-md` targeted runs from `tarav-py` and `tarav-md` resolved the same project,
  3,998 records, 92 surfaces, 3,195 surface lines, checks, classes, and POI instances; only
  elapsed time varied. Full corpus execution completed in 122.956 seconds.
- [TS] The capture audit initially found grounded code annotations without records. The new
  bounded capture path landed five records (`^c20260821-0u`, `-1u`, `-3u`, `-6u`, `-7u`);
  a selected preview now reports all five existing with zero unresolved items or conflicts.
- [TS] Post-capture focused Index/CLI suite: 200 passed. Ruff: clean. Hugentics Skillware
  build regenerated `references/capture.md`; its own target is current, while eight unrelated
  pre-existing package POIs remain visible.
