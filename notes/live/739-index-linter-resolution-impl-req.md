# 739 — Deterministic Index linter project resolution

## Impl.Abstract

Replace the Index linter's implicit cwd-local evaluator with one explicit project target and
a minimal structural default configuration. Delete the HEAD and touch-authority manifests as
inputs to evaluation. Preserve the shared record depot and the concurrent report-model work.

Configurable Index composition, record-level project ownership, and a richer structural HEAD
model remain later design work. This slice establishes the deterministic default they can extend.

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

## Impl.Log

- [TS] Execution of Impl.Req 739 is authorized by the tarav-hugentics implementation invocation.
  ^c20260821-5u
- [OBS] The target worktree already contained concurrent Index report, CLI, linter, surface, and
  test edits before this requirement was created; they are shared state and must be preserved.

