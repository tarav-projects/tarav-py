# 729 — Chatlas scannable sources

## Impl.Abstract

- **Scope:** add explicit `chatlas.sources[].scannable` policy and configure only the canonical Codex home for native scanning.
- **Status:** complete and verified.
- **Source:** autonomous `$agentos-hugentics --dev --AUTO` request; accepted source-selection semantics are grounded by ^c20260813-0u.
- **Out of scope:** deleting or rewriting existing Chatlas raw archives and indexes, ingesting satellite Codex archives, or removing the per-session symlink-source defense.

## Impl.Index

### Source.Configuration

- `chatlas.sources` remains the authority for native provider-home selection.
- `scannable` is a boolean source policy with a default of `true`.
- A non-boolean configured value is rejected at the configuration boundary.
- Non-scannable sources remain valid configuration entries but never become live `ChatlasProviderInstance`s.

### Codex.Topology

- `~/.codex` is the sole scannable Codex source.
- Satellite Codex homes remain configured with `scannable: false`; their symlinked sessions, residual indexes, and real archives are ignored by native Chatlas scanning.
- Existing Chatlas-owned raw data is untouched.

### Symlink.Defense

- The existing per-session backing-artifact symlink check remains intact.
- No second root-filtering mechanism is added; explicit source selection prevents redundant satellite discovery.

## Impl.Agendix

- **Touched:** `Provider.Instance` — live instances are projected only from scannable configured sources.
- **Touched:** `Provider.Home.Adapter` — retains its per-session source-path defense unchanged.
- **Execution authority:** implement the accepted `scannable` policy without raw-archive mutation. ^c20260813-0u

## Execution.Plan

### Vertical.Slice 1 — Configuration model and selection

- **Status:** complete.
- **RED:** prove `scannable: false` excludes a source while omitted/true sources remain selected, and invalid values fail clearly.
- **GREEN:** extend `ChatlasSource` parsing and filter before provider-instance construction.
- **Check:** focused source-selection tests.

### Vertical.Slice 2 — Live configuration

- **Status:** complete.
- Mark canonical Codex scannable and every satellite Codex source non-scannable.
- Verify selected live Codex instances contain only `~/.codex`.
- Confirm raw archive state is not mutated.

### Vertical.Slice 3 — Regression verification

- **Status:** complete.
- Run focused Chatlas selection, provider-query, delta-scan, and hook-consumer tests plus Ruff and `git diff --check`.
- Update this artifact and the repository guidance if its source-selection description changes.

## Impl.Log

- **Checkpoint:** pre-existing repository work was checkpointed as `e35493d` before implementation edits.
- **Decision:** `scannable` controls future native scanning only; historical raw/index cleanup is explicitly deferred.
- **Implemented:** source parsing accepts only a JSON boolean for `scannable`, defaults omitted values to `true`, and projects only enabled sources into live provider instances.
- **Configured:** Claude Code, canonical `~/.codex`, and Copilot remain scannable; `.codex-br`, `.codex-jp`, `.codex-mm`, and `.codex-tk` are explicitly non-scannable.
- **Preserved:** `ProviderHomeAdapter` still rejects every discovered session carrying a symlinked source path; no additional root-filter mechanism was introduced.
- **Verification:** all 491 Chatlas tests and 6 architecture tests pass; touched Python files pass Ruff; `git diff --check` passes; live instance selection returns only `/Users/pereiro/.codex` for Codex.
