# Agent Run Account Preflight - impl-req

## Impl.Abstract

- **scope:** add account-auth preflight repair to `agentos agent run` and `agentos agent ping` so resolved Codex homes with Agentos link records are refreshed to the linked account's active artifact before launching the provider command
- **status:** implemented
- **source:** 2026-06-04 discussion after `codex-br` and `codex-mm` failed or drifted because provider homes had stale `auth.json` artifacts relative to the account registry
- **owning project:** `agentos-py`
- **primary paths:** `src/agentos/agent/commands.py`, `src/agentos/agent/providers.py`, `src/agentos/agent/run_runtime.py`, `src/agentos/codex/account_reconcile.py`, `src/agentos/codex/account_registry.py`, `tests/test_codex_account_reconcile.py`, new focused tests for `agent run` / `agent ping`
- **related surfaces:** `notes/live/590-agent-account-registry-consolidation-impl-req.md`, `notes/live/597-agent-command-build-and-run-config-impl-req.md`, `notes/live/627-codex-auth-reconciliation-impl-req.md`

## Impl.Index

### Existing.Infrastructure.Reuse

The implementation must reuse the existing account registry and reconciliation infrastructure.

Hard.Evidence:

- `src/agentos/agent/account_registry.py` owns provider-scoped `accounts.json`, `artifacts.jsonl`, `artifacts/`, and `links.json`.
- `src/agentos/codex/account_registry.py` exposes `inspect_codex_account_home(...)` and `link_codex_account_to_home(...)`.
- `src/agentos/codex/account_reconcile.py` exposes `reconcile_codex_accounts(...)`, discovers linked/configured/system homes, and syncs stale linked homes through `link_codex_account_to_home(...)`.
- `src/agentos/codex/account_status.py` already calls `reconcile_codex_accounts(account=..., register_discovered=True, sync_stale_links=True, record_event=False)` before reading usage.
- `src/agentos/agent/commands.py` resolves `agent run` / `agent ping` targets and then directly calls `agent.run(...)`; that path currently skips the Codex account preflight.

Implementation direction:

- Do not duplicate auth-copy policy in `agent run`.
- Introduce a small run preflight layer that dispatches to existing provider reconciliation.
- For Codex, call `reconcile_codex_accounts(...)` scoped to the resolved home and intended account when available.

### Defect.Boundary

The observed defect is not missing link/status capability; it is that normal provider launches skip the capability.

Hard.Evidence:

- `agentos agent accounts status --provider codex --home /Users/pereiro/.codex-mm --json` exposes `link.account`, `classification`, and `link_consistency`.
- `agentos agent accounts link --provider codex --home <home> --account <alias> --force` repairs the home to the active artifact.
- `agentos agent ping --provider codex --profile codex-br --model gpt-5.4-mini` succeeds after relinking.
- Plain `agent run` / `agent ping` can use a profile whose home is linked but stale, because no preflight runs before the provider process starts.

Implementation direction:

- Add the preflight at the `agentos agent` command layer after profile/home resolution and before `agent.run(...)`.
- Apply it to both `run` and `ping`; both are provider launches and both rely on the same resolved home.
- Do not move this concern into downstream callers such as `md-library`.

### Account.Semantics

`--account` is an assertion/selection control. Absence of `--account` must still repair stale linked homes.

Accepted behavior:

- No `--account`, linked home: refresh the linked account automatically if the linked home is stale or missing its active artifact.
- No `--account`, unlinked home: do not mutate; launch as-is.
- `--account mm`, unlinked home: link `mm` into that home, then launch.
- `--account mm`, linked to `mm`: refresh if stale, then launch.
- `--account mm`, linked to another account: fail clearly unless an explicit force switch is added in a later design.

Rationale:

- Link registry records are trusted intent. If a home is already linked to `codex/mm`, keeping it current is expected maintenance, not a surprising account switch.
- Raw `auth.json` contents are not sufficient intent. Unlinked homes with unknown or merely registered auth must not be overwritten unless the caller explicitly names an account.
- `--account` must not silently override a different existing link; account switches are too risky without an explicit force surface.

### Provider.Scope

Implement only Codex artifact-backed preflight in the first request.

Hard.Evidence:

- Codex is artifact-backed through copied `auth.json` files and has implemented reconcile semantics.
- Claude Code and Copilot already reject `--account` in provider `build_command(...)` paths or use claimed/token models that are not equivalent to Codex active artifacts.
- The account registry supports multiple provider link kinds, but only Codex has the exact stale `auth.json` defect reported here.

Implementation direction:

- Add provider-neutral preflight structure only where it reduces command duplication.
- Keep Codex mechanics under `agentos.codex`.
- Non-Codex providers should no-op unless they already expose a safe provider preflight.

### Observability

Run preflight should be visible enough to debug without leaking auth material.

Required output behavior:

- If preflight mutates a home during normal `agent run` / `ping`, print one concise line before launching:
  - `[agentos] refreshed codex auth for profile codex-mm from account mm`
- If no mutation is needed, keep normal launches quiet.
- `--dry-run` should show the planned preflight action without mutating:
  - `[agentos] would refresh codex auth for profile codex-mm from account mm`
- Do not print token contents, raw auth JSON, or full artifact files.

Implementation direction:

- Reuse `reconcile_codex_accounts(... check=True ...)` for dry-run preflight planning where practical.
- The preflight result may return action summaries to command code; formatting can be minimal and stable.

## Execution.Plan

### Slice 1 - Extract Run Target Preflight Hook

- Add an internal helper near `agentos.agent.commands` or a small new module, for example `agentos.agent.run_preflight`.
- Inputs: resolved `Agent`, `AgentCommandConfig`, config start path, dry-run flag, and optionally profile name for human output.
- Call this helper from `_cmd_agent_run` and `_cmd_agent_ping` after `_resolve_agent_run(...)` / `_resolve_agent_run_target(...)` and before `agent.run(...)`.
- Return concise setup/status lines for dry-run and normal mutation.

Observable result:

- A test can monkeypatch the Codex preflight helper and verify `agent run` and `agent ping` call it before provider launch.

Validation:

```bash
uv run pytest tests/test_agent_run_account_preflight.py -q
```

### Slice 2 - Codex Linked-Home Auto-Refresh Without `--account`

- Implement Codex preflight for resolved homes that already have link records.
- Inspect the resolved home through existing status/reconcile machinery.
- If the linked home is stale or missing, call `reconcile_codex_accounts(home=agent.home, register_discovered=True, sync_stale_links=True, ...)`.
- If the linked home is already `matching-active` / verified, no-op.
- If the home has no link record and no explicit account, no-op.

Observable result:

- A stale linked `/tmp/codex-mm/auth.json` is refreshed to the active `codex/mm` artifact by `agentos agent run --provider codex --profile codex-mm --dry-run` in check mode and by normal run before provider process launch.

Validation:

```bash
uv run pytest tests/test_codex_account_reconcile.py tests/test_agent_run_account_preflight.py -q
```

### Slice 3 - Explicit `--account` Semantics

- When `--account <alias>` is passed for Codex:
  - If resolved home is unlinked, call `link_codex_account_to_home(home=agent.home, account=<alias>)`.
  - If resolved home is linked to the same alias, refresh through reconcile.
  - If resolved home is linked to a different alias, fail with a clear `CliError`.
- Preserve existing provider behavior for unsupported `--account` providers.
- Do not add force account switching in this slice unless already trivial and requested; the safe default is fail.

Observable result:

- `agentos agent run --provider codex --home /tmp/new-codex --account mm --dry-run` reports a planned link.
- A home linked to `br` fails if run with `--account mm`.

Validation:

```bash
uv run pytest tests/test_agent_run_account_preflight.py -q
```

### Slice 4 - Dry-Run And Human Output

- Integrate preflight lines with existing `agent.run_dry(...)` output.
- In dry-run mode, do not mutate auth files or link registry.
- In normal mode, print a concise preflight line only when an action occurred.
- Keep the provider command output unchanged after preflight lines.

Observable result:

```bash
agentos agent run --provider codex --profile codex-mm --model gpt-5.4-mini --dry-run --prompt ping
```

shows planned preflight only when the home is stale or would be linked, then prints the resolved provider command.

Validation:

```bash
uv run pytest tests/test_agent_run_account_preflight.py -q
```

### Slice 5 - Focused End-To-End Smoke

- Create fixture-driven tests using existing `_helpers.codex_auth_json(...)` and `write_global_config(...)`.
- Assert file hashes and registry state, not auth contents.
- Run a local installed-CLI smoke only if safe in the developer environment.

Validation:

```bash
uv run ruff check src/agentos/agent src/agentos/codex tests
uv run pytest tests/test_codex_account_reconcile.py tests/test_agent_run_account_preflight.py -q
uv run pytest -q
```

## Risks And Deviation Triggers

- If `reconcile_codex_accounts(home=...)` rejects configured-but-unlinked homes needed for explicit `--account`, use `link_codex_account_to_home(...)` directly for that explicit-link case and keep reconcile for linked refresh.
- If check-mode reconcile cannot cleanly express an explicit unlinked-home link, add a small dry-run planning helper that reads `links.json` and account registry without writing.
- If adding preflight to command code creates circular imports, place provider dispatch in a narrow `agentos.agent.run_preflight` module and import provider modules inside functions.
- If `--account` is currently intended to pass through to provider-native CLI for Codex, stop and confirm before changing semantics. Current code preserves `account` in `AgentCommandConfig` but Codex does not use it for argv construction.
- If normal preflight output disrupts machine consumers, restrict normal output to stderr or add a quiet option. Do not hide dry-run preflight lines.

## Acceptance.Signals

- `agentos agent run --provider codex --profile codex-mm ...` refreshes a stale linked home before launching, even without `--account`.
- `agentos agent ping --provider codex --profile codex-mm ...` uses the same preflight.
- Unlinked Codex homes are not mutated unless `--account` is explicit.
- Explicit `--account` can link an unlinked Codex home and can refresh a same-account linked home.
- Explicit `--account` fails on a different existing home link.
- Dry-run reports planned preflight actions without mutating files.
- Implementation reuses `inspect_codex_account_home(...)`, `reconcile_codex_accounts(...)`, and `link_codex_account_to_home(...)`.
- Existing account register/link/status/reconcile tests continue to pass.

## Impl.Log

- 2026-06-04: Created follow-up implementation request after confirming existing Codex reconciliation handles stale linked home repair, but `agent run` and `agent ping` do not invoke it. This request intentionally builds on `627-codex-auth-reconciliation-impl-req.md`, whose `Runtime.Hooks` block deferred broad pre-run mutation until an account-aware linked-home policy existed.
- 2026-06-04: Implemented Codex run/ping account preflight. Added `agentos.agent.run_preflight`, wired it into `agentos agent run` and `agentos agent ping`, added dry-run preflight lines, explicit `--account` link/assert semantics, and focused tests in `tests/test_agent_run_account_preflight.py`. During execution, found and corrected a reconciliation gap: a home could be link-verified while still not matching the account's active artifact, so `_may_sync_home(...)` now allows syncing artifact links whose classification is not `matching-active`. Verified with `uv run ruff check src/agentos/agent src/agentos/codex tests`, `uv run pytest tests/test_codex_account_reconcile.py tests/test_agent_run_account_preflight.py -q` (14 passed), and `uv run pytest -q` (45 passed).
