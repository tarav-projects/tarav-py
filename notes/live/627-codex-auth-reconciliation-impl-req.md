# Codex Auth Reconciliation - impl-req

## Impl.Abstract

- **scope:** add an account-auth reconciliation path that captures refreshed Codex `auth.json` files from known homes, registers fresh artifacts as active for the same account, and syncs stale linked Codex homes to the active artifact
- **status:** implemented
- **source:** user request on 2026-05-23 after diagnosing `codex-br` using a fresh `/Users/pereiro/.codex-br/auth.json` while the Agentos managed system home still had an older linked artifact
- **owning project:** `agentos-py`
- **primary paths:** `src/agentos/agent/account_registry.py`, `src/agentos/agent/commands.py`, `src/agentos/agent/providers.py`, `src/agentos/agent/monitor/workflows.py`, `src/agentos/codex/account_registry.py`, `src/agentos/codex/account_status.py`, `tests/test_e2e_agent_accounts.py`, `tests/test_e2e_agent_usage.py`
- **related design:** `notes/live/588-agent-account-registry-consolidated-design-session.md`, `notes/live/590-agent-account-registry-consolidation-impl-req.md`, `notes/live/596-minimal-active-account-usage-capability-impl-req.md`, `notes/live/599-monitor-limits-tracking-account-status-impl-req.md`

## Impl.Index

### Existing.Registry.Foundation

The current account registry model is the correct foundation and must not be replaced.

Hard.Evidence:

- `src/agentos/agent/account_registry.py` owns provider-scoped `accounts.json`, `artifacts.jsonl`, `artifacts/`, and `links.json`.
- `src/agentos/codex/account_registry.py` already registers Codex auth artifacts, stores them by hash, updates `active_artifact_id`, links active artifacts into homes, and inspects home state.
- `notes/live/590-agent-account-registry-consolidation-impl-req.md` states that registering a new artifact for the same known account updates `active_artifact_id`.

Implementation direction:

- Keep `accounts.json.active_artifact_id` as the explicit source of current active auth.
- Keep `artifacts.jsonl` as append/idempotent history.
- Keep `links.json` as current home association.
- Add reconciliation as a layer that uses the existing register/link/status primitives.

### Reconciliation.Policy

Reconciliation applies only to known homes and only mutates safe cases.

Known homes:

- homes present in provider `links.json`;
- configured Codex instance homes from `agent.instances`;
- Agentos system homes for registered Codex accounts, defaulting to `~/.agentos/agent/homes/codex/<account>`.

Rules:

- If a known home has valid Codex auth for a known account with an unregistered hash, register it and make it active by default.
- If the exact artifact is already registered, registration is a noop.
- If the home has valid Codex auth for an unknown account, do not mutate; emit a warning.
- If the home has broken or unreadable auth, do not mutate; emit a warning.
- If a linked home is stale for its linked account, sync it to the account's active artifact.
- Do not auto-overwrite unlinked user/configured homes. They can be sources of fresh auth, not sync targets.
- Agentos managed system homes may be overwritten to match the active artifact.

Conflict rule:

- If multiple known homes for the same account expose different unregistered fresh hashes in one pass, register all valid artifacts. Choose active by `last_refresh`, then JWT `iat`, then file mtime. Include a warning that multiple fresh artifacts were observed.

### General.Interface

The public orchestration should be provider-neutral enough to mirror later, while the mechanics remain Codex-specific for this implementation.

Target shape:

- add a small common reconciliation model under `agentos.agent`, for example `account_reconcile.py`;
- add provider dispatch in the command/provider boundary rather than hard-coding reconciliation logic into generic monitor workflows;
- implement only Codex provider behavior in this request.

Suggested common concepts:

- `AccountReconcileRequest`: provider, optional homes/accounts, booleans for register discovered artifacts and sync stale links.
- `AccountReconcileResult`: provider, scanned homes, actions, warnings, errors.
- action types such as `registered_artifact`, `activated_artifact`, `synced_linked_home`, `noop`, `warning`.

Provider-specific mechanics:

- Codex reads `auth.json`, uses `read_codex_auth_info(...)`, `inspect_codex_account_home(...)`, `register_codex_account_from_auth_file(...)`, and `link_codex_account_to_home(...)`.
- Later providers can implement the same conceptual interface without requiring Codex auth-file assumptions in the common layer.

### Command.Surface

Add an explicit CLI for debug and tests.

Target command:

```bash
agentos agent accounts reconcile --provider codex [--json]
```

Optional useful flags:

- `--account <account>` narrows reconciliation to one registered account.
- `--home <home>` includes or narrows to a specific known home; unknown homes should require an explicit provider/account-safe path or be rejected for the first slice.
- `--check` reports intended actions without mutation.

The command should print concise human output and stable JSON containing scanned homes, actions, warnings, and final account active artifacts.

### Runtime.Hooks

Automatic behavior should reuse the same reconciler rather than duplicating policy.

Initial hook points:

- Codex account status path before live usage fetch in `src/agentos/codex/account_status.py`.
- Monitor `limits-tracking` indirectly through account status, because `src/agentos/agent/monitor/workflows.py` calls `agent.account_status()`.

Do not initially add broad pre-run mutation for normal `agent run`. Agent runs may use user homes, and unexpected home overwrites are higher risk. A later slice may add account-aware pre-run reconciliation only when the run target is explicitly linked or account-managed.

### Safety.And.Observability

Reconciliation must be safe by default and easy to explain.

Required safety behavior:

- no arbitrary filesystem scanning;
- no token or auth JSON content in output;
- warnings for unknown account auth and broken auth;
- no mutation on mismatched or ambiguous account aliases;
- no overwrite of unlinked user/configured homes;
- stale linked homes updated only through existing link mechanics so `links.json` remains truthful.

Observability:

- record command/activity events for explicit reconciliation, if existing account command logging supports it without broad refactor;
- include action summaries in account status raw payload when an automatic reconciliation occurred;
- make tests assert action kind and final registry/link state, not secret-bearing file content.

## Execution.Plan

### Slice 1 - Common Reconciliation Model And Codex Home Discovery

- Add provider-neutral result/request dataclasses or typed dictionaries in a small `agentos.agent` module.
- Add Codex known-home discovery that combines `links.json`, configured Codex instance homes, and registered account system homes.
- Keep discovery deterministic and deduplicated by resolved path.
- Do not mutate files in this slice.

Observable result:

- A test can call the discovery/reconcile check path and see only known homes returned.

Validation:

```bash
uv run pytest tests/test_e2e_agent_accounts.py -q
```

### Slice 2 - Codex Capture Of Fresh Known-Account Auth

- Implement Codex reconciliation for `known-account-new-hash`.
- Register the new auth artifact using existing register logic.
- Make the registered artifact active by default.
- Treat already registered artifacts as noop.
- Emit warnings and skip mutation for unknown-account and broken auth homes.
- Implement conflict selection using `last_refresh`, JWT `iat`, then mtime when multiple fresh artifacts are observed for the same account.

Observable result:

- A known Codex home with a new `auth.json` updates `artifacts.jsonl`, stores `artifacts/<sha>.auth.json`, and updates `accounts.json.active_artifact_id`.
- Unknown auth produces a warning and does not create an account or artifact.

Validation:

```bash
uv run pytest tests/test_e2e_agent_accounts.py tests/test_e2e_agent_usage.py -q
```

### Slice 3 - Sync Stale Linked Codex Homes

- Detect linked Codex homes whose link artifact or home auth hash is stale against the linked account's active artifact.
- Sync stale linked homes through `link_codex_account_to_home(...)` or an equivalent provider helper that preserves link semantics.
- Restrict automatic overwrite to linked homes and Agentos managed system homes.
- Do not overwrite unlinked configured/user homes.

Observable result:

- If `/Users/pereiro/.codex-br/auth.json` is captured as active, `/Users/pereiro/.agentos/agent/homes/codex/br/auth.json` becomes the same artifact when that system home is linked for `br`.

Validation:

```bash
uv run pytest tests/test_e2e_agent_accounts.py -q
```

### Slice 4 - CLI Surface

- Add `agentos agent accounts reconcile --provider codex`.
- Support `--json`.
- Add `--check` if it can be implemented without delaying the first useful endpoint; otherwise defer with a clear TODO in the Impl.Log.
- Keep human output short: scanned count, action count, warning count, and key actions.

Observable result:

```bash
agentos agent accounts reconcile --provider codex --json
```

returns stable JSON with status, provider, homes, actions, warnings, and final active artifacts.

Validation:

```bash
uv run pytest tests/test_e2e_agent_accounts.py -q
agentos agent accounts reconcile --provider codex --json
```

### Slice 5 - Account Status And Monitor Hook

- Invoke Codex reconciliation before live usage fetch in `CodexAgent.account_status()`.
- Keep automatic reconciliation scoped to the target account/home and known-home policy.
- Include reconciliation action metadata in `AccountStatus.raw` when actions occurred.
- Confirm monitor benefits without monitor-specific auth logic, because limits tracking already calls `agent.account_status()`.

Observable result:

- `agentos agent accounts monitor --once --json` sees current Codex auth for linked system homes after a known configured home refresh.
- `usage_status` no longer fails or returns stale state solely because the linked system home missed a newer active artifact.

Validation:

```bash
uv run pytest tests/test_e2e_agent_usage.py tests/test_agent_monitor_auto_prime.py -q
agentos agent accounts monitor --once --json
```

### Slice 6 - Full Focused Verification

- Run focused formatting/lint checks on touched modules.
- Run account, usage, and monitor tests.
- Run the full `agentos-py` test suite if the focused suite passes.

Validation:

```bash
uv run ruff check src/agentos/agent src/agentos/codex tests
uv run pytest tests/test_e2e_agent_accounts.py tests/test_e2e_agent_usage.py tests/test_agent_monitor_auto_prime.py -q
uv run pytest -q
```

## Risks And Deviation Triggers

- If common reconciliation abstractions start forcing Codex auth-file details into generic code, stop and move those details back under `agentos.codex`.
- If conflict selection cannot be made deterministic from available metadata, register all candidates but do not auto-activate; report a warning and require manual selection.
- If `link_codex_account_to_home(...)` is too command-shaped for internal sync, introduce a provider helper that shares the same safety checks instead of bypassing link semantics.
- If automatic status reconciliation makes status unexpectedly slow, keep the explicit CLI and restrict automatic status reconciliation to the target account/home first.
- If tests require secret-shaped auth fixtures, use existing JWT/auth fixture helpers and avoid committing real auth material.

## Acceptance.Signals

- Registering a new Codex `auth.json` still makes it the account active artifact by default.
- A reconciliation pass scans only known Codex homes.
- A fresh `auth.json` discovered in a known home for a known account is registered and activated.
- Unknown-account and broken auth homes produce warnings and no mutation.
- Stale linked Codex homes are updated to the active artifact.
- Unlinked configured/user homes are never overwritten automatically.
- `agentos agent accounts reconcile --provider codex --json` exposes what happened in a testable form.
- Codex account status and monitor usage paths benefit from reconciliation without duplicating provider-specific policy in monitor workflows.
- Existing account register/link/status behavior remains intact.

## Impl.Log

- 2026-05-23: Created implementation request from discussion after `codex-br` auth drift diagnosis. The accepted design keeps `active_artifact_id` explicit, treats fresh same-account registration as active by default, scans only known homes, registers fresh known-account auth, warns/noops on unknown accounts, and syncs stale linked Codex homes.
- 2026-05-23: Implemented Codex reconciliation. Added provider-neutral reconcile result/request models, Codex known-home discovery from links/configured instances/system homes, safe registration/activation of newer known-account auth, stale linked/system-home sync through existing link mechanics, `agentos agent accounts reconcile --provider codex`, and the Codex account-status hook used by monitor. During execution, tightened the activation heuristic so unregistered stale linked auth is registered as history but does not replace a newer active artifact. Verified with `uv run ruff check src/agentos/agent src/agentos/codex tests`, `uv run pytest -q`, and installed-CLI dry-run JSON smoke check.
