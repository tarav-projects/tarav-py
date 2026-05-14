# Agent Account Registry Consolidation - design-session

## Session.Abstract

- intent: design the next `agentos agent accounts` registry model around explicit account, artifact, and link registries.
- active focus: continue account lifecycle design after the consolidated registry implementation.
- references: current implementation under `src/agentos/*/account_registry.py`, `src/agentos/agent/commands.py`, and tests in `tests/test_agent_account_registry_commands.py`.
- implementation: `590-agent-account-registry-consolidation-impl-req.md` completed the base registry consolidation.
- state: implemented; continuing follow-up design.
- next: converge remaining account lifecycle threads, especially monitor integration, explicit current-home preservation helpers, migration/repair policy, and status UX cleanup.

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

- status: closed; implemented by `590-agent-account-registry-consolidation-impl-req.md`.
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

- status: closed; implemented by `590-agent-account-registry-consolidation-impl-req.md`.
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

- status: closed; implemented by `590-agent-account-registry-consolidation-impl-req.md`.
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

- status: closed for new writes; implemented by `590-agent-account-registry-consolidation-impl-req.md`.
- settled: new command paths use the compact provider-scoped shape and do not recreate legacy per-account manifests or duplicated per-account auth files.
- open follow-up: decide whether existing local legacy data needs an explicit migration or cleanup command.

### Register.Command

`agentos agent accounts register` feeds `Account.Registry` and, when applicable, `Artifact.Registry`.

For artifact-backed providers, registration validates the incoming artifact, stores it durably, records it idempotently, and updates the account metadata with the active artifact pointer.

For metadata-only providers, registration validates required metadata and writes account metadata. Home association belongs to `link`; `register --home` is deprecated.

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

- status: closed; implemented by `590-agent-account-registry-consolidation-impl-req.md`.
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

- status: closed; implemented by `590-agent-account-registry-consolidation-impl-req.md`.
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

- status: closed for base reconciliation; implemented by `590-agent-account-registry-consolidation-impl-req.md`.
- settled: status reconciles the three registries and reports claimed links as claimed/unverified rather than artifact-verified.
- open follow-up: review and tighten default human output phrasing for claimed, verified, stale, missing, broken, and mismatched home states.

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

- status: closed; carried into `590-agent-account-registry-consolidation-impl-req.md` and implemented.
- promotion target: durable registry invariants should eventually be promoted out of this live-note into the relevant index surface.

### Agentos.Agent.System.Home

`Agentos.Agent.System.Home` is the Agentos-managed provider home for a registered account.

It is a system-owned execution home, analogous to system Python: Agentos applications can use it for provider operations without polluting user homes. The home is not owned by a single app. `agentos agent accounts monitor` is the first consumer.

#### appendix

Default shape:

```text
~/.agentos/agent/homes/<provider>/<account>
```

Example:

```text
~/.agentos/agent/homes/codex/jp
```

Each registered account should have one Agentos agent system home. The home must contain whatever provider-specific auth/config state is required for that provider account to run.

Agentos applications should validate the home before using it. If the home is missing or unusable, they should fail the target with setup guidance rather than silently falling back to user homes.

#### meta

- status: active design target.
- settled: system homes live under `~/.agentos/agent/homes/<provider>/<account>`.
- settled: system homes are Agentos-owned and app-shared, not monitor-specific.
- settled: applications validate system homes and report setup guidance when missing or unusable.
- open: exact setup helper command or workflow for creating a system home from a registered account.

### Account.Monitor

`agentos agent accounts monitor` is the account-monitoring loop for registered Agentos accounts.

The monitor is registered-account-first. Monitor configuration names registered accounts, and Agentos agent system homes are execution context for those accounts.

The first installed workflow is `limits-tracking`, which reproduces the useful account usage and limits behavior from the deprecated stats command while moving it behind a general monitor loop.

#### appendix

Config shape:

```json
{
  "agent": {
    "accounts": {
      "monitor": [
        {
          "workflow": "limits-tracking",
          "targets": [
            {
              "provider": "codex",
              "account": "jp",
              "home": "~/.agentos/agent/homes/codex/jp"
            },
            {
              "provider": "codex",
              "account": "mm"
            }
          ],
          "refresh_interval_sec": 60,
          "usage_total": {
            "label": "Selected accounts aggregate",
            "targets": [
              {
                "provider": "codex",
                "account": "jp"
              },
              {
                "provider": "codex",
                "account": "mm"
              }
            ],
            "limit_class": "usage_over_time",
            "limit_name": "weekly"
          }
        }
      ]
    }
  }
}
```

`agent.accounts.monitor` is an ordered vector of workflow configs. Workflow order is config order.

Targets reference registered accounts by `{provider, account}`. `home` is optional. If omitted, the provider implementation derives the Agentos agent system home, with this default shape:

```text
~/.agentos/agent/homes/<provider>/<account>
```

Monitor does not prepare Agentos agent system homes. It validates each target home and reports setup guidance when the home is missing or unusable.

CLI filters narrow configured targets. When multiple filters are supplied, composition is AND across filter dimensions.

Loop model:

```text
MonitorLoop
    owns loop cadence and workflow ordering
    holds MonitorState
    holds MonitorFrame
    calls workflows once per tick
    renders the current MonitorFrame

MonitorState
    persistent in-memory state across loop ticks
    owns loop metadata
    exposes public workflow data space

MonitorFrame
    per-tick render/work frame
    receives display blocks, warnings, errors, and status lines

MonitorWorkflow
    mutates MonitorState and MonitorFrame in place
    throttles its own slow work
```

Workflow interface:

```python
class MonitorWorkflow(Protocol):
    name: str

    def run(self, state: MonitorState, frame: MonitorFrame) -> None:
        ...
```

`MonitorLoop` attempts one tick per second. Workflows are responsible for deciding whether slow work is due. A workflow may update the frame from cached state, fetch fresh data, or return without modifying the frame.

`LimitsTrackingWorkflow` owns its refresh throttle:

```python
if now - last_refresh_at < refresh_interval_sec:
    return

fetch provider usage
store latest model data in MonitorState
write display data into MonitorFrame
```

#### meta

- status: active design target.
- settled: monitor is registered-account-first.
- settled: `agent.accounts.monitor` is an ordered vector of workflow configs.
- settled: first installed workflow is `limits-tracking`.
- settled: `MonitorLoop` runs once per second and workflow throttling is workflow-owned.
- settled: workflows mutate `MonitorState` and `MonitorFrame` in place.
- settled: `MonitorState` is persistent in-memory loop state.
- settled: `MonitorFrame` is the per-tick TUI/render frame.
- settled: monitor uses Agentos agent system homes as target execution context.
- settled: monitor validates target system homes and reports setup guidance instead of preparing them automatically.
- open: claimed/browser-login account support in Agentos agent system homes.
- open: exact provider capability surface for fetching usage data from registered accounts.

## Session.Notes

### Open Questions

- Agentos agent system home setup - decide the helper command or workflow for creating `~/.agentos/agent/homes/<provider>/<account>` from a registered account.
- Claimed/browser-login monitor support - decide how metadata-only accounts run in Agentos agent system homes without relying on user-home ambient login state.
- Usage capability surface - decide whether the old `Agent.account_stats(AccountStatsRequest)` returns as-is or becomes a narrower account usage capability for monitor workflows.
- Monitor history - decide whether `limits-tracking` persists latest/history snapshots during the first implementation or only renders the live TUI.
- Monitor CLI filters - decide which filters are needed initially beyond `--provider` and `--account`.
- Register-current helper - decide whether to add an explicit `--register-current` or separate helper command for preserving an unknown target-home auth before link.
- Migration/cleanup policy - decide whether existing local legacy registry files need an explicit migrate/cleanup command, or whether "new writes only" is sufficient.
- Status UX wording - decide default human output for claimed, verified, stale, missing, broken, and mismatched home states.
- Status command logging - decide whether `status` emits command-log events or remains read-only and unlogged.
- Registry repair policy - decide whether Agentos provides a repair command for invalid `accounts.json`, `links.json`, and malformed `artifacts.jsonl`, or only reports the problem.

### Closed Questions

- Registry storage shape is closed: provider-scoped `accounts.json`, `artifacts.jsonl`, `links.json`, and `artifacts/`.
- Account metadata owns `active_artifact_id`.
- Artifact files are durable evidence and backup material, not per-account active files.
- `links.json` is current state keyed by provider/home.
- `register` does not create home links; `register --home` is deprecated.
- `link` owns home association for artifact-backed and claimed accounts.
- Claimed links use `link` without a `--kind` flag.
- Valid re-linking does not require `--force`.
- Unknown or broken target-home auth fails without `--force`.
- `--force` is the caller-responsibility overwrite path for unknown or broken target-home state.
- Known target-home auth is registered before switching.
- Register/link events use generalized command logging as observability, not as registry source of truth.
- A separate provider capabilities registry was rejected.
- Monitor configuration lives under `agent.accounts.monitor` as an ordered vector of workflow configs.
- Monitor targets are registered-account references.
- `MonitorLoop`, `MonitorState`, `MonitorFrame`, and `MonitorWorkflow` are the core monitor abstractions.
- `limits-tracking` is the first installed monitor workflow.
- `Agentos.Agent.System.Home` is the app-shared Agentos-managed provider home for a registered account.
- Monitor validates Agentos agent system homes and reports setup guidance instead of preparing them automatically.

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
- 2026-05-14: Refreshed session after `590` implementation. Marked base registry, register, link, status reconciliation, invariants, and event logging decisions as closed; carried monitor integration, current-home preservation helpers, migration/cleanup, status UX, status logging, and registry repair forward as follow-up design threads.
- 2026-05-14: Added `Account.Monitor` design with ordered workflow config, agent system homes, monitor loop abstractions, and `limits-tracking` as the first installed workflow.
- 2026-05-14: Added `Agentos.Agent.System.Home` and revised monitor homes to `~/.agentos/agent/homes/<provider>/<account>` with validate-and-report behavior.
