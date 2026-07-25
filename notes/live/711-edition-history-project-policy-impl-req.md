# Edition history project policy - impl-req

## Impl.Abstract

- **scope:** give edition-history commands a project-local default depot and make project-scope `agentos skw check` enforce configured edition-history target selectors
- **status:** designed; execution authorized
- **source:** accepted edition-history configuration discussion followed by autonomous develop invocation
- **support set:** design and execution authorization ^c20260725-25u
- **target projects:** `agentos-py` owns policy parsing, target expansion, service composition, and command behavior; `agentos-cli` owns umbrella integration coverage

## Impl.Agendix

- **touched:** `<Agentos.Project>/.agentos/state/bloberia/edition-history` is the canonical default depot for the edition-history command family
- **touched:** project-level `.skw/skw.json` may declare one `edition_history` object with `targets`, optional `exclude`, and optional `depot`
- **touched:** project-scope `agentos skw check` runs the configured edition-history policy once and reports its findings as project POIs
- **structural:** absence of `edition_history` disables the integrated check; package-level checks do not independently run project policy
- **structural:** Chatlas support resolution remains injected at command registration, preserving the foundation/feature dependency split
- **open space:** helper decomposition and exact diagnostic text remain implementation-owned within these contracts

## Impl.Index

### Current.State

- every `agentos skw edition-history` subcommand requires an explicit `--depot`
- `agentos skw check` only checks discovered Skillware packages and never calls `EditionHistoryService`
- `SkwConfig` warns that `edition_history` is unknown and has no file-selector model
- the existing project-local depot already contains the first real edition-history association

### Default.Depot

- derive the default from the Agentos project owning `--file` or `--target`, never from the process working directory
- use `.agentos/state/bloberia/edition-history` below that project root
- retain optional `--depot` as an explicit lifecycle/testing override
- an explicit multi-target check without `--depot` requires every target to belong to the same Agentos project

### Policy.Schema

- extend the project-level `.skw/skw.json` schema with:

```json
{
  "edition_history": {
    "targets": ["src/**/*.py"],
    "exclude": ["tests/**", "src/**/__init__.py"],
    "depot": ".agentos/state/bloberia/edition-history"
  }
}
```

- `targets` is required and is a nonempty list of project-relative glob strings
- `exclude` is an optional list of project-relative glob strings
- `depot` is optional; when absent, use the canonical project-local default
- reject unknown policy keys and invalid field shapes
- expand target globs against files under the project, then subtract files expanded by exclude globs; deduplicate and sort deterministically
- a configured policy that resolves no files is a configuration failure rather than a silent pass

### Check.Integration

- only project-scope `agentos skw check` reads and runs the project policy
- call `EditionHistoryService.check` once with the expanded targets and the injected Chatlas resolver
- expose edition-history findings as top-level project POIs in text and JSON output
- include those POIs in the summary count and exit status
- support normal `--check`/`--skip` selection for known edition-history finding kinds
- resolver failures stay `unresolvable-edition-support`; the current resolver contract does not reliably classify infrastructure outage separately from missing evidence

### Adoption

- configure `agentos-py` initially for `src/agentos/skillware/edition_history.py`, the one file with an established history record
- do not broadly select all Python files before their histories exist
- update `AGENTS.md` and command help to describe the default and integrated policy

### Scope.Boundary

- no change to Bloberia storage semantics or edition/session record schema
- no automatic Git/Chatlas history discovery or maintenance workflow in this slice
- no package-scope edition-history policy execution
- no backward-compatible configuration aliases
- no claim that the local operational check is portable CI state

## Execution.Plan

### Slice 1 - Policy and depot primitives

- add RED tests for default depot derivation, optional CLI override, strict policy parsing, deterministic include/exclude expansion, and empty matches
- add the typed `edition_history` project policy to `SkwConfig`
- expose project-root/default-depot and target-expansion helpers without importing Chatlas
- observable: normal commands work without `--depot`, while overrides remain exact
- check: `uv run pytest tests/test_edition_history.py tests/test_skillware.py`

### Slice 2 - Project linter integration

- add RED command tests for configured project POIs, disabled-when-absent behavior, successful configured history, selector filtering, JSON shape, and exit status
- merge one service check into `_cmd_skillware_project_check`
- register known edition-history POI kinds and keep service-produced unknown corruption kinds visible
- add the narrow real `agentos-py` policy
- observable: `agentos skw check` enforces the configured file set exactly once
- checks: focused `agentos-py` tests and installed CLI smoke

### Slice 3 - Umbrella and regression

- update umbrella CLI tests for project-default command behavior and configured project checking with injected support resolution
- update required documentation
- run full tests and maintained Ruff scopes in both target projects
- refresh the editable umbrella executable and smoke the real project check
- observable: library, thin registrar, and composition root agree on the policy

## Risks And Deviation Triggers

- stop rather than add an `agentos-py` import of `agentos-chatlas-py`
- do not hide a configured policy when no target files match
- keep unrelated dirty `agentos-md` work outside this implementation and its checkpoints
- if the existing POI selector/report model cannot represent project POIs without breaking package output, extend the report additively rather than assigning them to a fake package

## Acceptance Signals

- record/list/check use the owning project depot without `--depot`
- explicit `--depot` still selects exactly that depot
- strict project policy expands and excludes files deterministically
- no policy means no integrated edition-history work
- configured missing, invalid, duplicate, and unresolved histories affect normal check output and exit status
- the real `agentos-py` configured check passes against its existing association
- focused/full tests, maintained Ruff checks, and installed CLI smoke pass

## Impl.Log

- 2026-07-25: autonomous design selected project-level `.skw/skw.json` as the existing configuration extension point
- 2026-07-25: project POIs selected over fake package attribution
- 2026-07-25: separate blocked-versus-unresolvable status deferred because the resolver boundary currently exposes one undifferentiated failure channel
- 2026-07-25: execution gate anchored at `^c20260725-25u`
