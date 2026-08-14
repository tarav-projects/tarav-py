# Agent Profile Home Current Account Policy - impl-req

## Impl.Abstract

- **scope:** add a profile-level account policy that lets selected profiles run with the currently materialized provider-home auth when no explicit account is passed, while still validating that auth against Agentos account state and preserving explicit `--account` / `-a` materialization behavior
- **status:** implemented
- **source:** 2026-06-15 follow-up to `notes/live/645-agent-account-auth-interface-redesign-impl-req.md`; user wants the default `accounts[0]` behavior preserved globally, but wants an opt-in profile policy for shared homes such as `codex-main` where plain `acodex` should keep using the current `~/.codex/auth.json` if it is valid instead of overwriting it with the profile default
- **owning project:** `agentos-py`
- **primary paths:** `src/agentos/agent/config.py`, `src/agentos/agent/primitives.py`, `src/agentos/codex/agent.py`, `src/agentos/codex/account_registry.py`, `tests/test_agent_profiles.py`, `tests/test_agent_run_account_preflight.py`
- **related surfaces:** `notes/live/645-agent-account-auth-interface-redesign-impl-req.md`, `notes/live/629-agent-profile-ssot-and-account-events-impl-req.md`, `notes/live/630-agent-profile-legacy-cleanout-impl-req.md`, `agentos-md/skills/tarav-agent-account-management/SKILL.md`

## Impl.Index

### Runtime.Intent.Authority

Runtime intent remains profile + CLI args.

Accepted model:

```text
Agent.Run.Intent = Agent.Profile + CLI.Args
```

Hard.Evidence:

- `src/agentos/agent/config.py` loads profiles and intentionally sets the default account from `accounts[0]`.
- `src/agentos/agent/profile_scope.py` validates account overrides against the profile account list.
- `notes/live/645-agent-account-auth-interface-redesign-impl-req.md` established that `--account` / `-a` is the explicit one-run account selection and that `--provider` with `--profile` is only an assertion.
- Current `src/agentos/codex/agent.py::prepare_codex_run(...)` computes `requested_account = command_config.account or profile_account`; for a multi-account shared-home profile, no `-a` therefore selects `accounts[0]` and may materialize that account into the resolved home.

Implementation direction:

- Preserve the default behavior when no policy is configured: no `-a` uses `accounts[0]`.
- Add an explicit profile policy value for shared homes:

```json
"account_policy": "home-current"
```

- For `home-current`, no `-a` means "use the current resolved home credential only if it resolves to an allowed recognized account/auth state."
- For `home-current`, explicit `--account` / `-a` still wins and uses the existing reconcile/materialize behavior.
- Do not make current home auth a global source of run intent. It is selected only because the profile explicitly opted into that policy.

### Profile.Schema

The policy must integrate with the existing profile loader, not bypass it.

Hard.Evidence:

- `src/agentos/agent/config.py::_reject_removed_profile_fields(...)` currently rejects `account_policy` as a removed field.
- `src/agentos/agent/primitives.py::AgentConfig` has no account policy field.
- `AgentConfig.summary()` and `identity_key()` include profile fields that affect behavior.
- `tests/test_agent_profiles.py` already covers profile loading, provider assertion, account defaults, and parser behavior.

Implementation direction:

- Reintroduce `account_policy` as a supported profile field, not as legacy compatibility.
- Valid values:
  - omitted or `"profile-default"`: current behavior, `accounts[0]` is the no-`-a` selected account.
  - `"home-current"`: no `-a` uses validated current home auth and must not materialize `accounts[0]`.
- Unknown values should fail profile load with a clear `CliError`.
- Add the field to `AgentConfig`, `summary()`, and `identity_key()`.
- Keep provider-neutral parsing in `agent.config`; provider-specific meaning belongs under provider prepare-run implementations.

### Codex.HomeCurrent.Semantics

Codex is the first provider that needs `home-current` behavior because Codex uses a mutable `auth.json` inside `CODEX_HOME`.

Target behavior:

```text
profile account_policy = home-current
no -a:
  inspect resolved CODEX_HOME/auth.json
  if current auth maps to an allowed recognized account state -> do not overwrite, run
  if current auth is fresh known-account auth -> register/reconcile where safe, then run without forcing profile default
  if current auth is missing/broken/unknown/outside profile accounts -> fail preflight with a clear message

-a br:
  validate br is allowed by profile
  reconcile/register/promote br as existing policy does
  materialize br into resolved CODEX_HOME/auth.json
  run
```

Hard.Evidence:

- `src/agentos/codex/account_registry.py::inspect_codex_account_home(...)` classifies homes as `missing`, `broken`, `unknown`, `registered`, `known-account-new-hash`, or `matching-active`.
- `src/agentos/codex/account_reconcile.py::reconcile_codex_accounts(...)` can register fresh known-account auth and sync homes based on existing evidence.
- `src/agentos/codex/agent.py::_active_home_account(...)` currently returns an account only for `matching-active`; additional validation logic is needed for `registered` and `known-account-new-hash`.

Implementation direction:

- Add a Codex helper for home-current validation/preparation. Keep it inside `agentos.codex`; generic `agentos.agent` code must not inspect `auth.json`.
- The helper should return preamble lines or raise `CliError`; it must not silently materialize `accounts[0]`.
- Accepted current-home states:
  - `matching-active`: allow only if the resolved account is in profile accounts when the profile has an account list.
  - `registered`: allow only if the registered artifact maps to exactly one allowed profile account; do not require it to be active.
  - `known-account-new-hash`: run scoped reconcile/register for the matched allowed account; then allow if still recognized.
- Rejected current-home states:
  - `missing`: no credential to run.
  - `broken`: invalid credential file.
  - `unknown`: not registered or matched to an Agentos account.
  - ambiguous or outside profile account list: profile does not allow this credential.

### No.Legacy.Allowed

This policy must not restore legacy linked-home authority.

Rules:

- Do not recreate `links.json`.
- Do not infer selected account from account events.
- Do not make home auth the implicit default for every profile.
- Do not change the meaning of `accounts[0]` for profiles without `account_policy: "home-current"`.
- Do not add a CLI flag that users must remember for this normal profile behavior; the accepted control surface is profile-level policy.
- Do not let generic `agentos agent` command code branch on Codex auth-file classifications.
- Do not implement fallback from invalid home auth to `accounts[0]` under `home-current`; that would reintroduce surprising overwrite behavior.

### Integration.Shape

The change should land as a coherent extension of existing subsystems.

Implementation direction:

- Profile subsystem owns policy parsing and validation.
- Run-preparation subsystem transports the resolved `AgentConfig` to provider code through the existing prepare-run call path.
- Codex provider owns policy execution for Codex auth classifications.
- Existing account registry/reconcile/status functions remain the shared source for auth state and should be reused rather than duplicating auth parsing in `CodexAgent`.
- Account events remain audit-only. Home-current validation should record no materialization event when no mutation occurs.
- `agent accounts status` and `agent accounts reconcile` remain diagnostic/admin operations; normal `agent run` behavior is controlled by profile + args.

## Execution.Plan

### Slice 1 - Profile Policy Field

- Add `account_policy` to `AgentConfig`.
- Parse `account_policy` from profile JSON in `src/agentos/agent/config.py`.
- Remove `account_policy` from the removed-field rejection list.
- Validate values: omitted / `"profile-default"` / `"home-current"`.
- Include non-default policy in `AgentConfig.summary()` and include the field in `identity_key()`.

Observable result:

- A profile with `"account_policy": "home-current"` loads successfully and exposes the policy.
- A profile with an unknown `account_policy` fails to load.
- Existing profiles without the field behave as before.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_agent_profiles.py -q
```

Target test additions:

- profile with `account_policy: "home-current"` loads and summarizes the policy.
- invalid `account_policy` raises `CliError`.
- omitted policy preserves existing `accounts[0]` default account behavior.

### Slice 2 - Codex Home-Current No-Account Validation

- Add Codex prepare-run branch:
  - active only when `agent.account_policy == "home-current"` and `command_config.account` is empty.
  - inspect resolved `agent.home`.
  - validate the current home auth classification against allowed profile accounts.
  - run scoped reconcile/register only for recognized fresh known-account auth where existing reconcile policy supports it.
  - return no materialization line when no mutation occurs.
  - raise clear `CliError` for missing/broken/unknown/out-of-profile/ambiguous home auth.
- Preserve current Codex behavior for omitted/default policy.
- Preserve explicit `-a` / `--account` behavior for all policies.

Observable result:

```bash
agentos agent run --profile codex-main --dry-run --prompt test
```

with `codex-main.account_policy = "home-current"` does not show `would materialize ... from account <accounts[0]>` when `~/.codex/auth.json` is a valid allowed current auth.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_agent_run_account_preflight.py tests/test_codex_account_reconcile.py -q
```

Target test additions:

- `home-current` no `-a` with `matching-active` home for an allowed account does not mutate or print materialization.
- `home-current` no `-a` with current auth for an account outside profile accounts raises.
- `home-current` no `-a` with missing/broken/unknown auth raises and does not materialize `accounts[0]`.
- `home-current` with explicit `-a br` still materializes `br`.
- default/omitted policy still materializes `accounts[0]` as existing tests expect.

### Slice 3 - Real Profile And CLI Smoke

- Update the local `codex-main` profile only if the user explicitly wants the implementation step to mutate local runtime config; do not bake personal config changes into tests.
- Add or update docs/help text only if the field is documented in an existing profile/account-management surface.
- Run installed CLI smoke after refreshing `agentos-cli` if command behavior is tested through the installed executable.

Observable result:

```bash
agentos agent run --profile codex-main -a br --dry-run --prompt test
agentos agent run --profile codex-main --dry-run --prompt test
```

show explicit account materialization for the first command and home-current validation/no-overwrite behavior for the second only when the profile is configured with `account_policy: "home-current"`.

Validation:

```bash
uv run ruff check src/agentos/agent src/agentos/codex tests
uv run pytest tests/test_agent_profiles.py tests/test_agent_run_account_preflight.py tests/test_codex_account_reconcile.py -q
uv run pytest -q
```

## Risks And Deviation Triggers

- If `home-current` requires a live provider call to prove token validity, do not add it silently. Start with local recognized-auth validation and surface the limitation; live verification belongs in reconcile/ping/status surfaces unless explicitly designed.
- If `registered` / `known-account-new-hash` cannot be mapped to exactly one allowed profile account, fail instead of guessing.
- If profile loader changes conflict with prior removal of `account_policy`, record that this is a deliberate new policy field with different semantics, not a legacy restoration.
- If a generic helper starts importing Codex account-registry details, stop and move the logic back into `agentos.codex`.
- If tests need to mutate `~/.agentos/profiles/codex-main.json`, stop; tests should use temporary profile fixtures.

## Acceptance.Signals

- Profiles without `account_policy` preserve current `accounts[0]` default behavior.
- `account_policy: "home-current"` is accepted by profile loading and visible in config summaries.
- Under `home-current`, no `-a` never materializes `accounts[0]` into the resolved Codex home.
- Under `home-current`, no `-a` runs only when the current Codex home auth is recognized and allowed by the profile.
- Under `home-current`, invalid current home auth fails clearly and leaves the home unchanged.
- Explicit `-a` remains the override that materializes the requested allowed account into the resolved home.
- No `links.json`, linked-home authority, account-event inference, or generic Codex-auth branching is introduced.

## Impl.Log

- 2026-06-15: Created from user-approved design direction. The accepted model preserves default `accounts[0]` behavior globally and adds opt-in `account_policy: "home-current"` for shared mutable homes; home-current validates current auth but does not overwrite invalid auth with the profile default.
- 2026-06-15: Implemented in `agentos-py`. Added `AgentConfig.account_policy`, profile parsing/validation, profile template/list integration, and Codex `home-current` prepare-run validation for recognized allowed current home auth.
- 2026-06-15: Local runtime profile files such as `~/.agentos/profiles/codex-main.json` were not mutated because the execution plan required explicit user intent for local config changes.
- 2026-06-15: Verification passed: focused profile/Codex reconcile suites, Ruff over touched agent/Codex/tests surfaces, full `uv run pytest -q`, and editable `agentos-cli` reinstall.
