# Skillware edition-history service - impl-req

## Impl.Abstract

- **scope:** implement the first `Skw.Edition.History.Service` vertical slice as an importable Skillware library, thin `agentos skw edition-history ...` CLI, explicit-target linter, and specialized developer module
- **status:** implementation-ready
- **source:** autonomous develop request for the accepted Skillware/Chatlas/Git/Bloberia responsibility split
- **support set:** implementation and execution authorization ^c20260725-7u
- **target projects:** `agentos-py` owns the service and command domain; `agentos-cli` owns end-to-end umbrella coverage; `agentos-md` owns the Skillware developer module and accepted ontology

## Impl.Agendix

- **touched (index):** `Skw.Edition.History.Service` and its appendix children define the service, edition, session association, and history concepts ^c20260725-5u
- **touched (index):** `Agentos.Bloberia` defines the explicit-depot query:value substrate and application-owned payload boundary ^c20260724-31u
- **touched (chat):** the service/API, developer skill, linter, and generic-storage responsibility split ^c20260725-7u
- **structural:** the umbrella CLI already consumes `register_skillware_commands` from `agentos-py`; no second command implementation belongs in `agentos-cli`
- **open space:** exact Python helper decomposition, diagnostic wording, and JSON presentation remain implementation-owned within the public contracts below

## Impl.Index

### Current.Implementation

- `agentos.bloberia.BloberiaDepot` already provides explicit-depot create, query, and structural checking over application-owned JSON values
- `agentos.skillware.commands.register_skillware_commands` already owns the `skw` command namespace and its deprecated `skillware` alias
- `.agentos/project.json` provides a stable `project_id`; `AgentosProjectHandler` exposes it with project-root discovery
- the Skillware package skill is generated from `skills/agentos-skillware/.skw/src/`; its compiled files must not be edited directly
- `agentos-py` and `agentos-cli` begin clean; `agentos-md` contains approved edition-history index edits plus unrelated concurrent work that execution must preserve

### Edition.File.Identity

- a file identity is `{project_id, path}`
- `project_id` comes from the nearest containing `.agentos/project.json`
- `path` is normalized POSIX text relative to that project root
- CLI file and target arguments must resolve to existing regular files inside an Agentos project
- the identity does not depend on a workstation-specific absolute project path

### Edition.Session.Record

- one Bloberia application value represents one edition/session association
- schema discriminator: `kind = "skw.edition-session"` and `schema_version = 1`
- `file` carries `project_id` and project-relative `path`
- `edition` carries full commit identity and Git commit time
- `session` carries provider-native session identity and optional Chatlas start time
- `evidence` is an optional JSON object supplied by the maintaining workflow
- record input rejects empty identities, malformed timestamps, non-object evidence, and unknown or missing schema fields
- equivalent `{file, commit, session.id}` requests are idempotent: repeated recording returns the existing association rather than adding another record
- v1 idempotency covers repeated serialized calls; adding a cross-process unique constraint to generic Bloberia is out of scope

### Edition.History.Projection

- listing selects associations by file identity through Bloberia structural queries
- records are validated before becoming service objects
- the history groups sessions by edition commit
- editions sort by commit time and commit identity; sessions sort by start time when present and then session identity
- invalid matching application records fail through the service boundary rather than being silently omitted

### Edition.History.Check

- checking receives one or more explicit target files and the exact Bloberia depot
- each target with no valid edition/session association emits `missing-edition-history`
- malformed matching records emit deterministic schema findings
- duplicate association records emit `duplicate-edition-session`
- Bloberia structural corruption is surfaced as an edition-history check finding
- success means no findings; this is the minimal linter contract, not proof that every historical session was recovered

### Library.Surface

- public module: `agentos.skillware.edition_history`
- primary service: `EditionHistoryService`
- public value objects cover file identity, edition, session association, grouped history, record outcome, finding, and check result
- the service accepts an explicit `BloberiaDepot`
- file resolution and Git commit dating are reusable library operations, not CLI-only behavior

### CLI.Surface

- `agentos skw edition-history list --file <path> --depot <path>`
- `agentos skw edition-history record --file <path> --commit <sha> --session <id> --depot <path> [--session-started-at <ISO>] [--evidence-json <object> | --evidence-file <path>]`
- `agentos skw edition-history check --target <path> [--target <path> ...] --depot <path>`
- all commands emit deterministic JSON and require an explicit depot
- `record` derives the full commit identity and commit time from the file's Git repository
- the `skillware` alias receives the same nested command through the existing parser registration

### Developer.Module

- add `references/edition-history-developer.skw.md` under the Skillware package source
- route edition-history recovery and maintenance situations from `agentos-skillware`
- the module inspects full Git file history, queries Chatlas for candidate editing sessions, evaluates evidence, records accepted associations through the service CLI, and closes with list/check
- the module never writes raw Bloberia records and never treats temporal overlap alone as proof
- build and check the Skillware package after editing its source

### Scope.Boundary

- no `skw.json` schema expansion or automatic target discovery
- no integration into the existing generic `agentos skw check`
- no automatic claim of complete historical recovery
- no deletion, amendment, or migration command
- no Chatlas import into the `agentos-py` foundation package
- no Bloberia API or storage-format change
- no legacy edition-history format or compatibility path

## Execution.Plan

### Slice 1 - Association service and history projection

- add boundary tests for file identity, record validation, idempotent recording, Bloberia persistence, deterministic grouping, and malformed matching records
- implement the public `EditionHistoryService` and immutable value objects over `BloberiaDepot`
- derive canonical commit identity and commit time from Git for record inputs
- observable: a caller can record one file/commit/session association twice and list one grouped edition
- check: `cd agentos-py && uv run pytest tests/test_edition_history.py`
- status: pending

### Slice 2 - Explicit-target linter

- add boundary tests for targets with and without history, duplicate associations, malformed records, and corrupt Bloberia storage
- implement deterministic findings and an `ok` result over explicit target files
- observable: configured targets without any association fail with `missing-edition-history`
- check: `cd agentos-py && uv run pytest tests/test_edition_history.py`
- status: pending

### Slice 3 - Thin Skillware CLI

- extend the existing Skillware registrar with the nested `edition-history` command family
- add command-domain and umbrella end-to-end tests for record/list/check, optional metadata, explicit depot enforcement, idempotency, and nonzero checks
- update `agentos-py/AGENTS.md` for the new service and CLI surface
- observable: both `agentos skw edition-history ...` and the existing `skillware` alias reach the same library behavior
- checks: `cd agentos-py && uv run pytest tests/test_edition_history.py tests/test_skillware.py`; `cd agentos-cli && uv run pytest tests/test_e2e_edition_history.py`
- status: pending

### Slice 4 - Specialized developer module

- author the new module in `agentos-skillware/.skw/src/references/`
- extend the source router and `--dev` guidance without editing compiled targets
- build and check the package
- observable: an agent loading `agentos-skillware` is routed to a concrete Git/Chatlas/service maintenance workflow
- checks: `agentos skw build --skill skills/agentos-skillware`; `agentos skw check --skill skills/agentos-skillware`
- status: pending

### Slice 5 - Full verification and installed CLI

- run full tests and Ruff in `agentos-py` and `agentos-cli`
- reinstall the editable umbrella executable from `agentos-cli`
- smoke record/list/check against a scratch initialized Git/Agentos project and explicit Bloberia depot
- run the full `agentos-pkg` index linter to preserve the accepted ontology relocation
- observable: library, CLI, developer module, and ontology operate together without regressions
- status: pending

## Risks And Deviation Triggers

- stop rather than introduce a dependency from `agentos-py` to Chatlas
- stop rather than alter Bloberia persistence semantics to enforce concurrent uniqueness
- preserve unrelated `agentos-md` changes when checkpointing and editing generated Skillware sources
- record any parser-shape drift if nesting `edition-history` under the existing `skw` registrar requires a different command arrangement

## Acceptance Signals

- `EditionHistoryService` is importable and stores only schema-valid application values
- repeated equivalent record calls produce one association
- listing returns deterministic editions grouped with their sessions
- explicit targets lacking history produce `missing-edition-history`
- CLI record/list/check all require one explicit depot and emit deterministic JSON
- the Skillware developer module uses Git and Chatlas for discovery and the service for persistence
- focused and full tests, Ruff, Skillware check, and index lint all pass

## Impl.Log

- 2026-07-25: autonomous design resolved file identity to stable Agentos `project_id` plus project-relative path
- 2026-07-25: automatic target discovery and generic `skw check` integration deferred; v1 check takes explicit repeatable targets
- 2026-07-25: session start time and evidence are optional record metadata supplied by the Chatlas-aware developer workflow, avoiding a foundation-to-Chatlas dependency
- 2026-07-25: execution gate anchored at `^c20260725-7u`
