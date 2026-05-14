# Agent Account Registry Consolidation - impl-req

## Impl.Abstract

- **scope:** replace the current intermediate account registry storage with provider-scoped `Account.Registry`, `Artifact.Registry`, and `Link.Registry` files, then update register/link/status behavior around that model
- **status:** implemented
- **source:** `notes/live/588-agent-account-registry-consolidated-design-session.md`
- **primary paths:** `src/agentos/agent/commands.py`, `src/agentos/agent/account_registry.py`, `src/agentos/codex/account_registry.py`, `src/agentos/claude/account_registry.py`, `tests/test_agent_account_registry_commands.py`

## Impl.Index

### Registry.Storage.Model

- account state is provider-scoped under `~/.agentos/accounts/<provider>/`
- the target storage shape is:

```text
~/.agentos/accounts/<provider>/
  accounts.json
  artifacts.jsonl
  links.json
  artifacts/
    <sha256>.auth.json
```

- `accounts.json` is current account metadata and owns `active_artifact_id`
- `artifacts.jsonl` records known artifacts idempotently
- `artifacts/` stores durable artifact files
- `links.json` stores current account-to-home links keyed by home
- do not preserve the current `accounts/<account>/manifest.json`, `files/`, or `registry.jsonl` shape in new code paths

### Register.Semantics

- `register` creates or updates account metadata
- artifact-backed providers also store/register artifacts and set `active_artifact_id`
- metadata-only providers leave `active_artifact_id` as `null`
- `register` must not create home links; home association belongs to `link`
- duplicate artifact registration is a noop
- registering a new artifact for the same known account updates the account's `active_artifact_id`

### Link.Semantics

- `link` owns account-to-home association for all account types
- for artifact-backed accounts, `link` installs the account's active artifact into the target home and updates `links.json`
- for claimed/browser-login accounts, `link` asks the provider engine to perform the claimed-link path, then records `kind: "claimed"` in `links.json`
- no `--kind claimed` flag is needed; the registered account and provider engine decide the path
- normal valid re-linking does not require `--force`
- `--force` is the caller-responsibility path for overwriting unknown or broken target-home state

### Target.Home.Preservation

- normal artifact linking inspects the target `home/auth.json` before replacement
- valid auth from a known account but new hash is registered for that known account before switching
- valid auth from an unknown account fails non-interactively with registration guidance unless `--force` is used
- broken or unreadable auth fails and is not touched unless `--force` is used
- no auth means install the active artifact normally
- existing home auth files are never deleted by normal link behavior

### Status.Consistency

- general `agentos agent accounts status` reconciles accounts, artifacts, and links
- home-specific status answers what AgentOS can determine about that home
- artifact links should report verified, stale, missing, broken, or mismatched state
- claimed links should report as claimed/unverified, not as artifact-verified
- registry corruption should fail clearly with the file path and problem

### Event.Logging

- account register and link operations should write command log events through the generalized command logger when available
- link events should include provider, account, home, resulting link kind, force flag, previous link context, and relevant artifact ids
- command logging is observability, not registry source of truth

### No.Legacy.Allowed

- do not add compatibility branches that keep writing old registry layouts
- if migration support is needed, make it a narrow read/migrate boundary that writes the new layout and then all normal behavior uses the new model
- tests should assert the new files exist and old per-account manifests are not created

## Execution.Plan

### Slice 1 - Add registry IO primitives

- create provider-scoped helpers for `accounts.json`, `artifacts.jsonl`, `links.json`, and `artifacts/`
- use atomic writes for `accounts.json` and `links.json`
- keep JSONL append/idempotency for artifact records
- path: registry IO helpers -> provider account registry modules
- observable: unit tests can create/read/update all three registries without provider CLI behavior
- check: focused tests for file shape, idempotent artifact append, active artifact update, and malformed JSON errors
- status: completed

### Slice 2 - Move Codex register to the consolidated registries

- update Codex `register --auth-file` to write `accounts.json`, `artifacts.jsonl`, and `artifacts/<sha>.auth.json`
- remove new writes to `accounts/<account>/manifest.json`, duplicated per-account `auth.json`, `files/`, and `registry.jsonl`
- preserve account-id mismatch protections
- preserve manual email fallback behavior
- path: CLI register -> Codex auth parser -> Account.Registry + Artifact.Registry
- observable: registering `jp/br/mm/tk` creates account entries and artifact files in the new layout
- check: update existing register tests to assert the new layout and no old layout creation
- status: completed

### Slice 3 - Move metadata-only register to Account.Registry

- update Claude Code registration to write only account metadata into `accounts.json`
- set `auth_kinds` to include `ambient-browser-login`
- set `active_artifact_id` to `null`
- do not write a home link during register
- path: CLI register -> Claude account registry -> Account.Registry
- observable: `claude-code/jp-browser` exists as account metadata with no artifact and no link
- check: tests for required email, metadata persistence, and no `links.json` mutation during register
- status: completed

### Slice 4 - Implement artifact-backed link semantics

- update Codex `link` to resolve account metadata and `active_artifact_id`
- inspect target `home/auth.json` before replacing it
- register valid target auth for a known account when the artifact hash is new
- fail non-interactively for valid auth from an unknown account unless `--force`
- fail for broken/unreadable target auth unless `--force`
- copy the active artifact into the target home when allowed
- update `links.json`
- path: CLI link -> Codex link engine -> target home -> Link.Registry
- observable: changing `~/.codex` to another registered account preserves/registers current known auth and records the new home link
- check: tests for known-new-hash preservation, unknown-account guidance, broken-auth blocking, force overwrite, and resulting `links.json`
- status: completed

### Slice 5 - Implement claimed link semantics

- route metadata-only/no-active-artifact accounts through provider engine claimed-link behavior
- implement Claude Code claimed-home link path by writing `links.json` after provider validation
- make unsupported provider claimed-link paths fail from provider code with a clear message
- no `--kind` flag
- path: CLI link -> provider account engine -> Link.Registry
- observable: `agentos agent accounts link --provider claude-code --account jp-browser --home ~/.claude` records a claimed link
- check: tests for successful claimed link, re-linking without force, suspicious conflict with force, and unsupported provider failure
- status: completed

### Slice 6 - Rework status around registry reconciliation

- update general status to read the new provider registry files
- update home-specific status to combine target home inspection with `links.json`
- display artifact-backed links as verified/stale/missing/broken/mismatched where applicable
- display claimed links as claimed/unverified
- keep `--json` machine output complete enough for tests and future monitor use
- path: CLI status -> registry reconciliation -> formatter
- observable: status reports accounts, artifacts, links, and home consistency from the new layout
- check: tests for human output, JSON output, claimed link output, and artifact inconsistency output
- status: completed

### Slice 7 - Add event logging for register/link

- connect account register/link operations to the generalized command logger if that infrastructure exists
- record link events with previous-link context and `force` usage
- do not make command logs required for registry correctness
- path: account commands -> command logger -> event sink
- observable: after register/link, debug logs can answer the last linked account for a home
- check: focused tests around emitted event payloads, or guarded tests if logger infrastructure is not ready
- status: completed

### Slice 8 - Migrate and clean old tests

- migrate current test fixtures from old layout to new layout
- add narrow compatibility/migration tests only where implementation reads old state
- assert new command paths do not create old registry shapes
- remove obsolete expectations around per-account manifests and `registry.jsonl`
- path: tests -> fixtures -> command coverage
- observable: `tests/test_agent_account_registry_commands.py` describes the consolidated model
- check: `uv run pytest tests/test_agent_account_registry_commands.py -q`
- status: completed

## Risks And Deviation Triggers

- If the generalized command logger is not ready, do not block registry consolidation; add a clear deferred test or stub boundary.
- If old live user registry data exists, prefer explicit migration code over silent partial reads from both shapes.
- If provider claimed-link behavior becomes ambiguous, keep the provider error explicit instead of introducing a generic capabilities registry.
- If status output gets too broad, preserve stable JSON first and keep human output concise.

## Acceptance.Signals

- `~/.agentos/accounts/<provider>/accounts.json` is the account metadata source of truth.
- `~/.agentos/accounts/<provider>/artifacts.jsonl` and `artifacts/` are the artifact registry/storage.
- `~/.agentos/accounts/<provider>/links.json` is the account-to-home link registry.
- `agentos agent accounts register --provider codex --account jp --auth-file ...` writes the new account/artifact layout.
- `agentos agent accounts register --provider claude-code --account jp-browser --email ...` writes account metadata only.
- `agentos agent accounts link --provider codex --account jp --home ~/.codex` installs the active artifact and updates `links.json`.
- `agentos agent accounts link --provider claude-code --account jp-browser --home ~/.claude` records a claimed link without `--kind`.
- known target-home auth with a new artifact hash is registered before switching.
- unknown-account target-home auth fails non-interactively without `--force`.
- `--force` can overwrite unknown or broken target-home auth state.
- normal link does not delete existing auth files.
- status reconciles account, artifact, and link registries.
- old per-account manifest/auth duplication is not recreated by new code paths.
- focused account registry tests pass.

## Impl.Log

- 2026-05-14: Created implementation request from `588-agent-account-registry-consolidated-design-session.md`.
- 2026-05-14: Implemented consolidated provider registries: `accounts.json`, `artifacts.jsonl`, `links.json`, and `artifacts/`.
- 2026-05-14: Moved Codex register/link/status to Account.Registry, Artifact.Registry, and Link.Registry semantics, including known-account preservation, unknown/broken target-home refusal, and `--force` overwrite path.
- 2026-05-14: Moved Claude Code registration to metadata-only `accounts.json` and added claimed-home linking through `links.json`.
- 2026-05-14: Replaced focused account registry command tests with consolidated-layout expectations and verified `uv run pytest tests/test_agent_account_registry_commands.py -q`.
