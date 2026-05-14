# Agent Account Registry Consolidation - design-session

## Session.Abstract

- intent: design the next `agentos agent accounts` registry model around explicit account, artifact, and link registries.
- active focus: converge the persistent registry shape before implementation.
- references: current implementation under `src/agentos/*/account_registry.py`, `src/agentos/agent/commands.py`, and tests in `tests/test_agent_account_registry_commands.py`.
- state: converging.
- next: decide the command migration path and consistency/reporting details.

## Design.Index

### Account.Registry

`Account.Registry` is the provider-scoped registry of account identity and current account metadata.

It answers: "who is this account?" It does not answer where the account is active.

The active artifact pointer belongs to account metadata when the provider has registered artifacts. A metadata-only account has no active artifact.

#### appendix

Storage:

```text
~/.agentos/accounts/<provider>/accounts.json
```

Codex-shaped account:

```json
{
  "schema_version": 1,
  "provider": "codex",
  "accounts": {
    "jp": {
      "account": "jp",
      "account_id": "3b74c6d3-b4a8-45ea-9d5b-852bdbd92899",
      "email": "jose.pereiro.personal@gmail.com",
      "label": "Codex jp",
      "auth_kinds": ["auth-file"],
      "active_artifact_id": "de129e665404a548731ed860a238a6f17e724311f3b96f6a78ed3284393bd42b",
      "created_at": "2026-05-14T00:00:00Z",
      "updated_at": "2026-05-14T00:00:00Z"
    }
  }
}
```

Metadata-only/browser-login account:

```json
{
  "account": "jp-browser",
  "email": "jose.pereiro.personal@gmail.com",
  "label": "Claude jp browser",
  "auth_kinds": ["ambient-browser-login"],
  "active_artifact_id": null
}
```

#### meta

- status: converging.
- settled: `active_artifact_id` is account metadata, not a separate manifest.

### Artifact.Registry

`Artifact.Registry` is the provider-scoped registry of known auth artifacts.

It records artifact facts and stores durable artifact files. It is append/idempotent for registry entries. Normal registration and linking flows must not delete artifact files.

#### appendix

Storage:

```text
~/.agentos/accounts/<provider>/artifacts.jsonl
~/.agentos/accounts/<provider>/artifacts/<sha256>.auth.json
```

Artifact entry:

```json
{
  "artifact_id": "de129e665404a548731ed860a238a6f17e724311f3b96f6a78ed3284393bd42b",
  "kind": "auth-file",
  "account": "jp",
  "account_id": "3b74c6d3-b4a8-45ea-9d5b-852bdbd92899",
  "path": "artifacts/de129e665404a548731ed860a238a6f17e724311f3b96f6a78ed3284393bd42b.auth.json",
  "registered_at": "2026-05-14T00:00:00Z"
}
```

Codex `auth.json` is the current reference artifact. Browser-login providers may have no artifact registry entries.

#### meta

- status: converging.
- settled: artifacts are durable evidence and backup material, not per-account active files.

### Link.Registry

`Link.Registry` is the provider-scoped registry of current home links.

It answers: "where does AgentOS currently believe this account is active?" There is one current link per provider/home.

Links can be artifact-backed or claimed. Artifact-backed links are verifiable. Claimed links are metadata-only but still useful for status, monitor, consistency checks, and debugging.

#### appendix

Storage:

```text
~/.agentos/accounts/<provider>/links.json
```

Artifact-backed link:

```json
{
  "schema_version": 1,
  "provider": "codex",
  "links": {
    "/Users/pereiro/.codex": {
      "home": "/Users/pereiro/.codex",
      "account": "jp",
      "kind": "artifact",
      "artifact_id": "de129e665404a548731ed860a238a6f17e724311f3b96f6a78ed3284393bd42b",
      "source": "agentos-link",
      "linked_at": "2026-05-14T00:00:00Z",
      "updated_at": "2026-05-14T00:00:00Z"
    }
  }
}
```

Claimed/browser-login link:

```json
{
  "home": "/Users/pereiro/.claude",
  "account": "jp-browser",
  "kind": "claimed",
  "auth_kind": "ambient-browser-login",
  "source": "manual",
  "linked_at": "2026-05-14T00:00:00Z",
  "updated_at": "2026-05-14T00:00:00Z"
}
```

Claimed link meaning: for this metadata-only account, AgentOS currently believes this local home is linked to it.

Claude Code browser login is not special. Codex or another provider can also have browser-login or claimed-home semantics later.

#### meta

- status: converging.
- settled: use `links.json`, not `links.jsonl`, because this registry is current state keyed by home.

### Provider.Storage.Shape

Provider account state is a compact provider-scoped directory containing the three registries and durable artifact storage.

The common model should not create per-account directories or duplicated per-account `auth.json` files.

#### appendix

Target shape:

```text
~/.agentos/accounts/<provider>/
  accounts.json
  artifacts.jsonl
  links.json
  artifacts/
    <sha256>.auth.json
```

Avoid this legacy/intermediate shape in new code:

```text
~/.agentos/accounts/<provider>/accounts/<account>/manifest.json
```

Known current intermediate paths include:

```text
~/.agentos/accounts/codex/accounts/<account>/manifest.json
~/.agentos/accounts/codex/files/<sha>.auth.json
~/.agentos/accounts/codex/registry.jsonl
```

Provider-specific account-local files can be introduced later only when a provider has a real need for them.

#### meta

- status: converging.
- implementation pressure: migration should not preserve legacy slop in new code paths.

### Register.Command

`agentos agent accounts register` feeds `Account.Registry` and, when applicable, `Artifact.Registry`.

For artifact-backed providers, registration validates the incoming artifact, stores it durably, records it idempotently, and updates the account metadata with the active artifact pointer.

For metadata-only providers, registration validates required metadata and writes account metadata. It may also create a claimed link when the command explicitly receives a home to link.

#### appendix

Artifact-backed registration flow:

1. Read and validate the incoming auth file.
2. Compute the artifact hash.
3. Store the artifact under `artifacts/<sha256>.auth.json` if not already present.
4. Append or idempotently recognize the artifact in `artifacts.jsonl`.
5. Create or update the account entry in `accounts.json`.
6. Set `active_artifact_id` on the account metadata when the incoming artifact becomes the active artifact.

Metadata-only registration flow:

1. Validate required provider metadata.
2. Create or update the account entry in `accounts.json`.
3. Leave `active_artifact_id` as `null`.

#### meta

- status: converging.
- settled: `register` does not create home links. Home association belongs to `link`.

### Link.Command

`agentos agent accounts link` owns account-to-home association for all account types and feeds `Link.Registry`.

For artifact-backed providers, `link` also installs the account's active artifact into a target home.

Artifact-backed linking must preserve or register the current home auth file before replacement when possible. Unknown or broken current auth files block the operation with a useful error and must not be deleted.

Metadata-only/browser-login providers use `link` to create a claimed link when the registered account has no active artifact and the provider engine implements claimed-home semantics. The command does not need a `--kind claimed` flag; the provider/account registry feeds the provider engine, and the engine fails clearly if the path is not implemented.

Normal valid re-linking does not require `--force`. Suspicious changes, such as overwriting unknown auth state, replacing broken target-home auth state, or changing link/account kind in a way the provider cannot validate, should require `--force` or fail with clear guidance.

#### appendix

Artifact-backed linking flow:

1. Resolve the account in `accounts.json`.
2. Resolve `active_artifact_id`.
3. Inspect the target home auth file.
4. If the target home has a valid known auth file, register/preserve it, then switch.
5. If the target home has a valid auth file for a known account but an unknown artifact hash, register the new artifact for that known account, then switch.
6. If the target home has a valid auth file for an unknown account, detect the account if possible and fail with registration guidance unless `--force` is used.
7. If the target home has a broken or unreadable auth file, fail and do not touch it unless `--force` is used.
8. If the target home has no auth file, copy the active artifact.
9. Update `links.json` for the target home.

Claimed-link flow:

1. Resolve the account in `accounts.json`.
2. Confirm the account is registered and has provider metadata sufficient for a claimed link.
3. Ask the provider engine to perform the claimed-link path.
4. Inspect the current `links.json` entry for the target home.
5. If the existing link is a valid re-linking case, update it without `--force`.
6. If the existing link has a suspicious kind/account-kind conflict, require `--force` or fail with clear guidance.
7. Update `links.json` for the target home with `kind: "claimed"`.

Example:

```bash
agentos agent accounts link --provider claude-code --account jp-browser --home ~/.claude
```

#### meta

- status: converging.
- settled: `link` owns home association for all account types.
- settled: current home auth files are never deleted as part of link.
- settled: claimed links are created through `link`, not `register --home`, and do not require a `--kind` flag.
- settled: normal valid re-linking does not require `--force`; suspicious overwrites or account-kind changes can require it.
- settled: `--force` can overwrite broken or unreadable target-home auth state; responsibility is on the caller.
- settled: when target-home auth is valid and belongs to a known account, `link` registers the new artifact before switching.
- settled: `--force` can overwrite valid auth from an unknown account; normal link should fail non-interactively with registration guidance.
- settled: link events should be logged, including previous-link context when a home is re-linked.

### Status.Consistency

`agentos agent accounts status` should reconcile all three registries.

General status reports registered accounts and registry health. Home-specific status reports the best answer for that home, using verifiable artifacts first and claimed links where artifacts are not available.

#### appendix

Status inputs:

- account list from `accounts.json`
- artifact availability from `artifacts.jsonl` plus files under `artifacts/`
- home/account belief from `links.json`

Consistency checks:

- artifact link points to matching home artifact: ok
- artifact link points to missing, broken, stale, or mismatched home artifact: report inconsistency
- claimed link duplicates another account claim for the same provider/home: warn
- claimed link cannot prove provider login itself: report as claimed, not verified

#### meta

- status: active design target.
- open pressure: decide default human output phrasing for claimed vs verified links.

### Registry.Invariants

The three registries are logically independent and feed each other during commands and status reconciliation.

Core invariants:

- `accounts.json` owns current account metadata, including `active_artifact_id`.
- `artifacts.jsonl` tracks every registered artifact.
- `artifacts/` stores durable artifact files.
- `links.json` tracks current home links.
- no duplicated per-account `auth.json`
- no `accounts/<account>/manifest.json` legacy shape in the new model
- no deleting existing home auth files during registration or linking
- artifact links are verifiable by checking the target home artifact
- claimed links are metadata-only but still useful operational state

#### meta

- status: converging.
- promotion target: these invariants should be carried into the implementation request.

## Session.Notes

### Open Questions

- Migration path: should implementation migrate old files eagerly on first account command, lazily per provider, or with a separate migration helper?
- Command logger: how should account register/link/status events use the generalized command logger without coupling registry state to command history?
- Monitor integration: how should future `agentos agent accounts monitor` select accounts independently from registry existence while still using registry links for local context?
- Register-current helper: should we later add an explicit `--register-current` or separate helper command for preserving an unknown target-home auth before link?
- Claimed-link conflict details: which suspicious transitions should fail without `--force`?
- Link event log shape: what exact payload should generalized command logging store for link events?
- Registry corruption policy: how should invalid `accounts.json`, `links.json`, or malformed `artifacts.jsonl` be reported and repaired?

### References

- `src/agentos/agent/commands.py` - current account command surface.
- `src/agentos/codex/account_registry.py` - current Codex auth-file implementation.
- `src/agentos/claude/account_registry.py` - current metadata-only Claude account implementation.
- `tests/test_agent_account_registry_commands.py` - current behavior tests.

### Parking Lot

- Provider-specific account-local directories are parked until a provider has concrete account-local files that do not fit the three registries.

## Session.Log

- 2026-05-14: Created initial consolidated account registry design artifact from chat discussion.
- 2026-05-14: Upgraded artifact into active `Design.Session` format after loading `trigger-design-session` / `hugentics-designer` guidance.
- 2026-05-14: Rewrote artifact to better fit `Design.Session` style: compact `Design.Index` fundamentals, examples in appendices, and open questions in `Session.Notes`.
- 2026-05-14: Settled `link` as the single owner of account-to-home association for all account types. `register` creates account metadata; `link --provider ... --account ... --home ...` creates the appropriate provider/account link based on registered metadata and capabilities.
- 2026-05-14: Settled initial link conflict policy: valid re-linking proceeds without `--force`, suspicious claimed-link transitions can require `--force`, and link events should be logged with previous-link context.
- 2026-05-14: Settled that `--force` may overwrite broken or unreadable target-home auth state. This is an explicit caller-responsibility path.
- 2026-05-14: Settled that `--force` may also overwrite valid but unknown target-home auth state. Normal link remains non-interactive and fails with registration guidance.
- 2026-05-14: Clarified that valid target-home auth from a known account is not an unknown-account conflict. `link` should register the new artifact for that known account before switching.
- 2026-05-14: Rejected a separate provider capabilities registry. Provider support is explicit in code: account registry data feeds the provider engine, and unsupported paths fail from the provider implementation.
- 2026-05-14: Produced implementation request `590-agent-account-registry-consolidation-impl-req.md`.
