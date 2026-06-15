# Agent Account Auth Interface Redesign - impl-req

## Impl.Abstract

- **scope:** redesign the `agentos agent` account/auth interface so runtime state is resolved only from profile + CLI args, provider auth preparation is capability-backed, and Codex/Claude account mechanics use explicit inspect/register/reconcile/materialize operations instead of the user-facing "link" mental model
- **status:** implemented
- **source:** 2026-06-15 discussion after diagnosing `acodex` materializing `codex-main` from the first configured account and clarifying that `accounts[0]` is intentional profile default behavior
- **owning project:** `agentos-py`
- **primary paths:** `src/agentos/agent/commands.py`, `src/agentos/agent/config.py`, `src/agentos/agent/primitives.py`, `src/agentos/agent/profile_scope.py`, `src/agentos/agent/account_reconcile.py`, `src/agentos/codex/agent.py`, `src/agentos/codex/account_registry.py`, `src/agentos/codex/account_reconcile.py`, `src/agentos/claude/agent.py`, `src/agentos/claude/account_registry.py`, `src/agentos/claude/account_reconcile.py`, tests under `tests/`
- **related surfaces:** `notes/live/627-codex-auth-reconciliation-impl-req.md`, `notes/live/628-agent-run-account-preflight-impl-req.md`, `notes/live/629-agent-profile-ssot-and-account-events-impl-req.md`, `notes/live/630-agent-profile-legacy-cleanout-impl-req.md`, `notes/live/637-profile-scope-helper-cleanup-impl-req.md`, `agentos-md/skills/agentos-agent-account-management/SKILL.md`

## Impl.Index

### Runtime.Intent.Authority

Runtime state for `agentos agent run` must be defined by profile + CLI args.

Accepted model:

```text
Agent.Run.Intent = Agent.Profile + CLI.Args
```

Hard.Evidence:

- `src/agentos/agent/config.py` loads profile files from `~/.agentos/profiles/<id>.json`.
- `src/agentos/agent/config.py` currently sets `AgentConfig.account = accounts[0] if accounts else None`; this is intentional profile default behavior.
- `src/agentos/agent/profile_scope.py` centralizes account/home override validation against profile `accounts` and `homes`.
- `notes/live/629-agent-profile-ssot-and-account-events-impl-req.md` defines profiles as the single source of truth for intended runnable-agent binding.
- `notes/live/630-agent-profile-legacy-cleanout-impl-req.md` removes `links.json` as a maintained account state surface.

Implementation direction:

- Preserve `accounts[0]` as the profile default account.
- Preserve `--account <id>` as a one-run selected account, scoped by the profile's allowed accounts.
- Treat `--provider` with `--profile` as an assertion/filter, not as runtime state authority.
- Do not infer run intent from current provider-home auth contents, account events, or former link records.
- Home auth state is material runtime state, not intent authority.

### General.Provider.Split

`agentos agent` should expose general orchestration; providers should own provider-specific auth mechanics.

Hard.Evidence:

- `src/agentos/agent/primitives.py` provides shared `AgentConfig`, `RunnableMixin`, `RunCapable`, and `AccountStatusCapable`.
- Provider agents subclass `AgentConfig`: `CodexAgent`, `ClaudeAgent`, and `CopilotAgent`.
- `CodexAgent.run(...)` already performs Codex-specific preflight before launching.
- `ClaudeAgent.run(...)` already performs Claude-specific OAuth-token env injection before launching.
- `notes/live/570-provider-agent-account-capability-refactor-impl-req.md` moved account collection behind provider-agent capabilities.

Target flow:

```text
agentos agent run
  -> resolve AgentConfig from profile + args
  -> validate account/home scope
  -> call provider prepare-run capability when available
  -> launch provider command
  -> record non-secret events
```

Implementation direction:

- Add or consolidate a provider-facing prepare-run capability with a small common request/result model.
- Keep generic command code ignorant of Codex `auth.json`, Claude keychain/config, and OAuth-token details.
- Provider prepare-run implementations should return concise preflight lines and event payload hints without leaking secrets.

### Account.Auth.Subsystem

Account/auth management should be its own subsystem, with the runner as one caller.

Accepted state split:

```text
Profile.Intent.Authority
  owns provider, homes, allowed/default accounts, default model, run args, env

Account.Registry
  owns account aliases, artifact ids, active artifact pointers, verification metadata

Provider.Auth.Subsystem
  owns native mechanics: inspect, register, reconcile, materialize, prepare-run

Account.Event.Log
  records what happened; it does not decide future runtime state
```

Hard.Evidence:

- `agentos-md/skills/agentos-agent-account-management/SKILL.md` distinguishes registered, active, verified, and freshest credential states.
- `src/agentos/agent/account_registry.py` owns provider-scoped account records, artifact records, verification records, and account events.
- `src/agentos/codex/account_reconcile.py` and `src/agentos/claude/account_reconcile.py` already expose provider-specific reconciliation flows behind the shared `AccountReconcileRequest` / `AccountReconcileResult` shape.

Implementation direction:

- Use these verbs as the stable mental model:
  - `status` / `inspect`: read current registry and provider-home state.
  - `register`: archive a provider credential artifact.
  - `reconcile`: compare known state, register/promote/sync safe cases, report warnings.
  - `materialize`: write or inject the selected active credential into a provider runtime target.
  - `prepare-run`: provider-owned composition used by runners before launch.
- Treat `link` as legacy/transitional terminology unless kept as an alias.

### Codex.Auth.Semantics

Codex is artifact-backed and home-materialized through `auth.json`.

Hard.Evidence:

- `src/agentos/codex/account_registry.py` reads, registers, inspects, and copies Codex `auth.json` artifacts.
- `src/agentos/codex/account_reconcile.py` discovers configured/system Codex homes, registers fresh known-account auth, activates verified artifacts, and syncs known homes.
- `src/agentos/codex/agent.py` currently runs preflight that may call `link_codex_account_to_home(...)` or `reconcile_codex_accounts(...)`.
- `agentos-md/skills/agentos-agent-account-management/references/codex-auth-json.md` describes Codex `auth.json` diagnosis, registration, and live validation.

Target run behavior:

```text
agentos agent run --profile codex-main --account mm -- ...
  -> validate mm is allowed by codex-main
  -> resolve target CODEX_HOME from profile/--home
  -> reconcile Codex account mm across known homes
  -> choose/promote active usable artifact according to existing policy
  -> materialize active artifact into target CODEX_HOME/auth.json
  -> launch Codex
```

Implementation direction:

- Move direct run preflight copy/reconcile branching behind a Codex prepare-run/auth subsystem function.
- Explicit `--account` should trigger full Codex account preparation, not only copy whatever artifact is currently active if a fresher known artifact is available.
- No pre-run `agent accounts link --home ...` should be required for normal Codex runs.
- `acodex --account mm ...` should be the accepted normal interface for a one-run account selection.

### Claude.Auth.Semantics

Claude uses provider-specific auth forms and should share the same general interface without forcing Codex semantics onto Claude.

Hard.Evidence:

- `src/agentos/claude/agent.py` resolves account from `--account` or profile default.
- `src/agentos/claude/agent.py` injects `CLAUDE_CODE_OAUTH_TOKEN` for registered `oauth-token-env` accounts.
- `src/agentos/claude/account_registry.py` supports `ambient-browser-login` and `oauth-token-env` auth kinds.
- `src/agentos/claude/account_reconcile.py` inspects configured/system homes, registers ambient auth artifacts, can ping-verify candidates, and promotes verified ambient auth.

Target run behavior:

```text
agentos agent run --profile claude-jp [--account browser-jp] -- ...
  -> validate selected account is allowed by profile
  -> resolve CLAUDE_CONFIG_DIR/home from profile/--home
  -> provider prepare-run chooses auth strategy
  -> launch Claude
```

Provider-specific preparation:

- `oauth-token-env`: load managed token artifact and inject `CLAUDE_CODE_OAUTH_TOKEN` into the launched process.
- `ambient-browser-login`: inspect/reconcile native Claude home auth only where safe and supported; do not pretend this is Codex-style `auth.json` materialization.

Implementation direction:

- Keep the general request/result model the same.
- Let Claude prepare-run return "injected oauth token" for token accounts and no-op or targeted reconcile for ambient accounts.
- `materialize` should be capability-backed and may be unsupported for some Claude auth kinds.

### Command.Surface

Account commands should expose a provider-neutral shape while remaining capability-backed.

Target stable surface:

```bash
agentos agent run --profile <profile> [--account <account>] [--home <home>] -- ...
agentos agent accounts status --provider <provider> [--home <home>]
agentos agent accounts reconcile --provider <provider> [--account <account>] [--home <home>] [--check]
agentos agent accounts materialize --provider <provider> --account <account> --home <home> [--check] [--force]
```

Current drift:

- `agent accounts link --provider codex --account mm --home ~/.codex` only materializes auth into a home after `links.json` removal.
- `agent accounts link --profile codex-main --account mm` also changes profile account order/default, then materializes auth.
- The word `link` implies a durable home/account association that no longer exists.

Implementation direction:

- Add `agent accounts materialize` as the explicit low-level/manual operation.
- Keep `agent accounts link` only as a compatibility alias or remove it if compatibility is not required by the current policy.
- Do not make `materialize --profile` change profile defaults. Profile mutation needs a separate explicit profile command if retained.
- If a profile-default mutation command is needed, prefer a profile-owned verb such as `agent profiles account set --profile <profile> --account <account>` over `accounts link --profile`.

### No.Legacy.Allowed

Do not reintroduce removed link-authority semantics.

Hard.Evidence:

- `notes/live/630-agent-profile-legacy-cleanout-impl-req.md` explicitly removed `links.json` as a maintained state surface.
- The user's current direction rejects the linking concept as a runtime mental model.

Rules:

- Do not recreate `links.json`.
- Do not infer selected account from historical account events.
- Do not infer selected account from current home auth except as provider status/diagnostic evidence.
- Do not allow `agent accounts materialize` to become runtime intent authority.
- Do not let generic `agentos agent` command code branch on provider auth-file formats.

## Execution.Plan

### Slice 1 - Prepare-Run Capability Model

- Add a small provider-facing prepare-run request/result surface under `agentos.agent`, for example `agentos.agent.run_preflight` or `agentos.agent.run_prepare`.
- Inputs: resolved `AgentConfig`, `AgentCommandConfig`, run start path/cwd, dry-run flag, and source string.
- Output: preamble lines, event payloads or action summaries, and optional command environment/display overrides.
- Wire `agent run` / `agent ping` through this surface without changing provider behavior yet.
- Keep provider-specific logic inside provider modules.

Observable result:

- Existing Codex and Claude run/ping behavior remains unchanged, but the call path has a shared prepare-run seam.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_agent_run_account_preflight.py tests/test_claude_account_status.py -q
```

Additional check:

```bash
uv run ruff check src/agentos/agent src/agentos/codex src/agentos/claude tests
```

### Slice 2 - Codex Run Preparation Uses Reconcile Then Materialize

- Move Codex preflight policy out of ad hoc branching in `CodexAgent.run(...)` / `run_dry(...)` into a Codex auth preparation helper.
- For selected account from `--account` or profile default:
  - validate account scope remains handled by existing profile helpers;
  - run scoped Codex reconciliation for that account/home;
  - register/promote fresher known auth according to existing reconcile policy;
  - materialize the selected active artifact into the resolved run home;
  - record `account.auth.materialized` only when an action occurs.
- Preserve quiet no-op behavior when the target home is already prepared.
- Preserve dry-run behavior with `would materialize` / `would refresh` style lines and no mutation.

Observable result:

```bash
agentos agent run --profile codex-main --account mm --dry-run -- "hello"
```

shows a planned Codex auth preparation only when the target home would change, and normal run prepares `~/.codex/auth.json` for `mm` before launch.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_agent_run_account_preflight.py tests/test_codex_account_reconcile.py -q
```

Target test additions:

- explicit `--account` on a multi-account profile prepares the selected account, not `accounts[0]`;
- scoped prepare-run discovers/registers a fresher known artifact before materializing;
- no `--account` still uses `accounts[0]` as profile default;
- unallowed `--account` still fails through profile-scope validation.

### Slice 3 - Claude Run Preparation Capability

- Move Claude OAuth-token injection behind the same prepare-run surface.
- Keep `oauth-token-env` behavior stable:
  - selected account loads the managed token;
  - run injects `CLAUDE_CODE_OAUTH_TOKEN`;
  - dry-run displays safe token placeholder only.
- Keep ambient browser-login behavior conservative:
  - no Codex-style forced materialization;
  - optional targeted reconcile only if existing tests and safety policy already support it;
  - post-success ambient auth promotion remains provider-owned.
- Make unsupported materialization explicit for Claude auth kinds that cannot be safely materialized.

Observable result:

```bash
agentos agent run --profile claude-jp --dry-run --prompt ping
```

keeps existing command/env behavior, and OAuth-token profiles still show safe token display in dry-run.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_claude_account_status.py tests/test_claude_account_reconcile.py tests/test_agent_run_account_preflight.py -q
```

Target test additions:

- Claude `oauth-token-env` prepare-run returns env override through the common surface;
- Claude ambient auth does not call Codex-style materialization;
- unsupported materialization returns a clear provider/auth-kind error.

### Slice 4 - Add `agent accounts materialize`

- Add a provider-neutral `agentos agent accounts materialize` command.
- Required flags:
  - `--provider`
  - `--account`
  - `--home`
- Optional flags:
  - `--check`
  - `--force` where the provider supports forceful overwrite
  - `--json`
- Implement Codex first by calling the same Codex auth subsystem used by run preparation.
- For Claude, either implement only supported auth kinds or return a clear capability error.
- Keep output language as "materialized", not "linked".

Observable result:

```bash
agentos agent accounts materialize --provider codex --account mm --home ~/.codex --check
```

reports the planned Codex materialization without changing `auth.json`.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_agent_profiles.py tests/test_agent_run_account_preflight.py tests/test_codex_account_reconcile.py -q
```

CLI smoke after install/update if implementation changes installed command behavior:

```bash
agentos agent accounts materialize --provider codex --account mm --home ~/.codex --check
```

### Slice 5 - Demote Or Remove `agent accounts link`

- Decide implementation posture according to repository compatibility policy:
  - preferred under current no-legacy policy: remove `link` if no active required caller remains;
  - fallback: keep `link` as a compatibility alias that prints/returns materialize terminology and delegates to `materialize`.
- Remove profile-mutation behavior from account materialization surfaces.
- If profile default mutation is still needed, add a profile-owned command:

```bash
agentos agent profiles account set --profile codex-main --account mm
```

- That profile command should only change profile account order/default and should not imply a provider-home materialization unless explicitly designed as a combined operation.

Observable result:

- Users no longer need or see "link" as the normal account-auth operation for running.
- Profile mutation and provider-home materialization are separate surfaces.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_agent_profiles.py tests/test_agent_account_events.py -q
```

Search check:

```bash
rg -n "accounts link|Linked .* account|link --profile|link --provider|links\\.json" src/agentos tests README.md notes/live
```

Expected active-code result depends on chosen compatibility posture; historical notes may still match.

### Slice 6 - Command Help And Account Management Docs

- Update command help for `agent accounts`.
- Update `agentos-md/skills/agentos-agent-account-management/SKILL.md` and provider references so normal run guidance uses profile/run-driven account selection:

```bash
agentos agent run --profile codex-main --account mm -- ...
```

- Replace ordinary "link this first" guidance with `materialize` only for manual/admin repair.
- Document provider-specific capability differences:
  - Codex materializes `auth.json`;
  - Claude OAuth-token injects env;
  - Claude ambient auth may reconcile/promote native home auth but is not Codex-style materialization.

Observable result:

- A reader can understand that runtime state comes from profile + args, while account commands inspect/register/reconcile/materialize provider credentials.

Validation:

```bash
agentos agent accounts --help
agentos agent accounts materialize --help
rg -n "link the active artifact|accounts link|linked home" agentos-md/skills/agentos-agent-account-management README.md src/agentos tests
```

### Slice 7 - Focused And Full Verification

- Run focused behavior suites for profile scope, run preflight, Codex reconcile, Claude account behavior, and account events.
- Run Ruff on touched modules.
- Run full test suite after focused suites pass.
- Reinstall editable CLI only if command registration/help changed in the active installed tool.

Validation:

```bash
uv run pytest tests/test_agent_profiles.py tests/test_agent_run_account_preflight.py tests/test_codex_account_reconcile.py tests/test_claude_account_reconcile.py tests/test_claude_account_status.py tests/test_agent_account_events.py -q
uv run ruff check src/agentos/agent src/agentos/codex src/agentos/claude tests
uv run pytest -q
```

## Risks And Deviation Triggers

- If the common prepare-run model starts encoding Codex-specific `auth.json` assumptions, stop and move those details back under `agentos.codex`.
- If `materialize` cannot be meaningfully provider-neutral for Claude/Copilot, keep the command provider-neutral but capability-backed, with clear unsupported errors.
- If removing `link` breaks known external callers, keep it temporarily as an alias and record a follow-up removal request; do not restore link-authority semantics.
- If Codex reconciliation cannot safely prove a fresher artifact is usable, preserve the existing verified/active policy and surface a warning rather than silently promoting.
- If `agent accounts materialize --profile` seems tempting during implementation, stop: profile mutation and credential materialization are separate concerns in this design.
- If command output preamble lines disrupt machine callers, consider moving normal preflight lines to stderr or restricting output to action cases; do not hide dry-run planned actions.

## Acceptance.Signals

- `agentos agent run --profile codex-main --account mm -- ...` prepares the resolved Codex home for `mm` before launch.
- `agentos agent run --profile codex-main -- ...` still uses the profile default account, currently `accounts[0]`.
- `--account` selection is validated against profile allowed accounts.
- Normal running does not require `agent accounts link`.
- Codex auth preparation reuses reconcile/register/materialize behavior rather than duplicating auth-copy policy in command code.
- Claude uses the same general prepare-run contract while preserving provider-specific OAuth-token env injection and ambient auth behavior.
- `agent accounts materialize` exists as a manual/admin operation for providers/auth kinds that support it.
- No active runtime code reintroduces durable linked-home authority.
- Account events remain audit evidence only, not runtime intent.

## Impl.Log

- 2026-06-15: Created from user-approved design direction. The key accepted decision is that all run state is profile + CLI args; account/auth management is a provider-owned subsystem used by runners; `link` should be demoted or removed as a runtime mental model.
- 2026-06-15: Executed in `agentos-py`. Added the shared prepare-run result surface, moved Codex/Claude run preparation behind provider prepare-run methods, added `agent accounts materialize`, removed the user-facing `agent accounts link` command path, and updated account-management docs.
- 2026-06-15: Decided not to add `agent profiles account set` in this execution because profile default mutation was optional in the plan and normal operation is now `agent run --profile ... --account ...`; no current test or caller required the extra profile-owned mutation command.
- 2026-06-15: Verification passed: focused account/profile/provider suites, Ruff over touched code and tests, full `uv run pytest -q`, installed CLI help smoke for `agent accounts` and `agent accounts materialize`.
- 2026-06-15: Installation note: per current workspace split, `agentos-py` no longer provides the executable. Refreshing the installed command must use editable `agentos-cli`, which aggregates `agentos-py`.
