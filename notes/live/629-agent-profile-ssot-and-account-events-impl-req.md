# Agent Profile SSOT And Account Events - impl-req

## Impl.Abstract

- **scope:** replace the split authority between `agent.instances` / profile-like config and account `links.json` with first-class agent profile files as the single source of truth for intended runtime binding, and move account operation history into a global rolling account event log
- **status:** implemented
- **source:** 2026-06-04 design discussion after implementing `628-agent-run-account-preflight-impl-req.md`; user identified that `profile.account` and `links.json[home].account` would create two authorities for the same runnable-agent account binding
- **owning project:** `agentos-py`
- **primary paths:** `src/agentos/agent/config.py`, `src/agentos/agent/providers.py`, `src/agentos/agent/commands.py`, `src/agentos/agent/account_registry.py`, provider account modules under `src/agentos/{codex,claude,copilot}/`, tests under `tests/`
- **related surfaces:** `notes/live/590-agent-account-registry-consolidation-impl-req.md`, `notes/live/627-codex-auth-reconciliation-impl-req.md`, `notes/live/628-agent-run-account-preflight-impl-req.md`

## Impl.Index

### Profile.Intent.Authority

An agent profile is the single source of truth for a named runnable agent's intended runtime binding.

Accepted model:

```text
Agent.Profile
  owns intended provider, home, account, model/default_model, run args, env, ping config, session discovery config

Account.Registry
  owns account identities, metadata, active artifacts

Account.Event.Log
  records what happened during register/materialize/run/link/change operations
```

Hard.Evidence:

- Current `src/agentos/agent/config.py` loads `agent.instances` from global/project config into `AgentConfig`.
- Current `src/agentos/agent/account_registry.py` also stores `links.json`, which maps provider homes to accounts.
- Current `628-agent-run-account-preflight-impl-req.md` made run-time preflight use account link records to infer intended account when `--account` is absent.
- The user explicitly rejected this as a permanent model: the profile system and account link system must not both answer "which account is linked to this profile?"

Implementation direction:

- Add first-class profile storage under `~/.agentos/profiles/<name>.json`.
- Add `account` to profile-owned `AgentConfig` loading and summaries.
- Treat profile-owned `account` as the intended account binding for `agent run --profile <name>`.
- Stop using `links.json` as run intent for profile-bound homes.

### Profile.File.Storage

Profiles should be split out from `~/.agentos/config.json`.

Target layout:

```text
~/.agentos/
  config.json                  # global provider-level config and global settings
  profiles/
    codex-mm.json
    codex-br.json
  accounts/
    events/
      20260604.jsonl
    codex/
      accounts.json
      artifacts.jsonl
      artifacts/
```

Profile file shape:

```json
{
  "schema_version": 1,
  "id": "codex-mm",
  "provider": "codex",
  "home": "/Users/pereiro/.codex-mm",
  "account": "mm",
  "default_model": "gpt-5.4-mini",
  "run_args": ["--dangerously-bypass-approvals-and-sandbox"],
  "env": {},
  "ping": {
    "model": "gpt-5.4-mini"
  }
}
```

Notes:

- Use one file per profile to reduce write contention and profile-edit race risk.
- Keep provider-level `cli_command` and similar shared settings in `~/.agentos/config.json`.
- Profile file fields should reuse the existing `agent.instances[]` field names where possible so migration is straightforward.
- Use `YYYYMMDD.jsonl` for rolling account event files. This is the sortable date form for daily logs.

### Link.Registry.Demotion

`links.json` should not remain the source of home/account intent.

Accepted model:

- Profile-owned homes derive intended account from the profile.
- Account materialization writes auth into the provider home according to profile intent.
- Account operation history is append-only events, not a mutable home/account registry.
- A historical event may include `home`, `account`, `profile`, and `provider`, but it is evidence of what happened, not authority for what should happen next.

Implementation direction:

- Stop adding new run-time behavior that depends on `links.json` for profile-bound homes.
- Add event logging before removing `links.json` writes, so observability remains.
- Retain legacy `links.json` reads only as a temporary migration/fallback surface while profile files are introduced.
- New profile-bound `accounts link` behavior should update profile account binding, then materialize auth, then append an event.

### Account.Event.Log

Account events are global, provider-tagged, and rolling by day.

Target path:

```text
~/.agentos/accounts/events/YYYYMMDD.jsonl
```

Event examples:

```json
{"time":"2026-06-04T16:22:31Z","event":"account.artifact.registered","provider":"codex","account":"mm","artifact_id":"cabcb25b8...","source":"agent.accounts.register"}
{"time":"2026-06-04T16:25:11Z","event":"account.auth.materialized","provider":"codex","profile":"codex-mm","home":"/Users/pereiro/.codex-mm","account":"mm","artifact_id":"cabcb25b8...","source":"agent.run"}
{"time":"2026-06-04T16:27:09Z","event":"profile.account.changed","provider":"codex","profile":"codex-mm","from_account":"br","to_account":"mm","source":"agent.accounts.link"}
```

Rules:

- Events are append-only.
- Events are not source of truth.
- Every event includes `time`, `event`, `provider`, and `source`.
- Secret-bearing auth JSON and tokens never appear in events.
- `home -> account` may be recorded as event data for audit/debug, but no command should infer profile intent from the event log.

### Run.Surface.Unification

`--profile` should be the normal complete-bundle selector.

Accepted CLI direction:

```bash
agentos agent run --profile codex-mm
agentos agent ping --profile codex-mm
```

Semantics:

- `--profile <name>` loads `~/.agentos/profiles/<name>.json`.
- `--provider` is not required when `--profile` is set.
- If `--provider` is supplied with `--profile`, it is an assertion/filter, not an override. Mismatch fails.
- Without `--profile`, no default provider/profile guessing. The caller must provide enough ad hoc construction fields, especially provider and home for stateful providers.
- `--account` in profile mode is an assertion/change request depending on command:
  - `agent run --profile codex-mm --account mm`: assert/use same intended account.
  - `agent accounts link --profile codex-mm --account br`: change the profile account binding to `br`, materialize auth, and append events.

### MdLibrary.Surface.Alignment

Downstream callers should not need separate terminology for Agentos profiles.

Design direction:

- `md-library` can use `--profile` directly if the flag name does not collide with md-library semantics.
- `--agent-instance` and `--profile` should not remain separate long-term concepts if both mean "configured Agentos runnable agent."
- Migration can preserve `--agent-instance` temporarily as an alias, but the stable concept should be Agentos profile.

## Execution.Plan

### Slice 1 - Profile File Model And Loader

- Add profile path helpers under `agentos.agent`, for example:
  - `profiles_root() -> ~/.agentos/profiles`
  - `profile_path(name) -> ~/.agentos/profiles/<name>.json`
  - `load_agent_profiles(...)`
- Parse each profile file into the existing `AgentConfig` model.
- Add `account` parsing to `agent_config_from_config_entry(...)` or a shared profile-entry parser.
- Keep existing provider-level config loading from `~/.agentos/config.json`.
- Do not remove legacy `agent.instances` yet.

Observable result:

- A test can create `~/.agentos/profiles/codex-mm.json` and `agentos agent list` / internal loaders see `codex-mm` as an `AgentConfig` with provider, home, account, and defaults.

Validation:

```bash
uv run pytest tests/test_agent_profiles.py -q
```

### Slice 2 - Profile-First Resolution

- Update `resolve_agent_config(...)` so `--profile <name>` can resolve without `--provider`.
- If `--provider` is supplied with `--profile`, validate the profile provider matches.
- Remove provider-only default guessing from `agent run` / `agent ping` resolution; provider-only mode should fail unless enough ad hoc construction fields are supplied.
- Keep legacy `agent.instances` available as fallback only while migration exists.

Observable result:

```bash
agentos agent run --profile codex-mm --dry-run --prompt hello
```

works without `--provider`, and:

```bash
agentos agent run --provider claude-code --profile codex-mm --dry-run --prompt hello
```

fails with a provider/profile mismatch.

Validation:

```bash
uv run pytest tests/test_agent_profiles.py tests/test_agent_run_account_preflight.py -q
```

### Slice 3 - Account Event Log

- Replace or supplement `record_account_event(...)` so account operations append to:

```text
~/.agentos/accounts/events/YYYYMMDD.jsonl
```

- Include provider as an event field.
- Use UTC date from the event timestamp.
- Preserve existing project/activity command logging only if it remains useful; do not make it the account event authority.
- Add tests for daily file selection, append format, required fields, and no token/auth content.

Observable result:

- Registering or materializing account auth creates an event line in the daily global account event file.

Validation:

```bash
uv run pytest tests/test_agent_account_events.py -q
```

### Slice 4 - Profile-Owned Account Materialization

- Change Codex run preflight to prefer `agent.account` from profile configuration as the intended binding.
- Materialize the active artifact for `profile.account` into `profile.home`.
- Update/append events for materialization.
- Do not infer intended account from `links.json` when `agent.account` is present.
- For profile-bound homes, conflicting legacy link state is stale/derived and should be overwritten by materialization, not treated as a competing source of intent.

Observable result:

- If profile `codex-mm` says `account=mm` and legacy `links.json` says that home was linked to `br`, `agentos agent run --profile codex-mm --dry-run` reports/plans materialization for `mm`; normal run materializes `mm`.

Validation:

```bash
uv run pytest tests/test_agent_profiles.py tests/test_agent_run_account_preflight.py tests/test_codex_account_reconcile.py -q
```

### Slice 5 - Account Link Command Writes Profiles

- Add `agentos agent accounts link --profile <profile> --account <account>`.
- In profile mode, update `~/.agentos/profiles/<profile>.json` account field, materialize account auth into the profile home, and append `profile.account.changed` and `account.auth.materialized` events.
- If `--provider/--home` link mode is retained for ad hoc/manual use, reject it when the home is owned by a profile unless the user uses `--profile`.
- Stop treating provider/home link mode as the normal path for runnable agents.

Observable result:

```bash
agentos agent accounts link --profile codex-mm --account mm
```

changes only `profiles/codex-mm.json`, auth materialization, and account events.

Validation:

```bash
uv run pytest tests/test_agent_profiles.py tests/test_agent_account_events.py tests/test_agent_account_registry_commands.py -q
```

### Slice 6 - Legacy Link Registry Demotion And Migration

- Add migration support from `agent.instances[]` into profile files.
- Add migration support from existing `links.json` only when it can safely enrich a profile missing `account`.
- Make `agent list` or `agent profiles migrate --check` report legacy config that should be migrated.
- Stop writing `links.json` in profile-owned flows.
- Keep read-only legacy fallback for one transition slice if needed, then remove it in a later cleanup request.

Observable result:

- Existing configured instances can be migrated into profile files.
- New profile-owned runs no longer create or depend on `links.json`.

Validation:

```bash
uv run pytest tests/test_agent_profiles.py tests/test_agent_account_events.py tests/test_codex_account_reconcile.py -q
```

### Slice 7 - Md-Library Flag Alignment

- In `md-library`, add `--profile` as the preferred way to select an Agentos profile when iterating.
- Keep `--agent-instance` only as a temporary alias if needed for compatibility.
- Pass profile through to Agentos without requiring a separate `--agent`/provider selection when profile contains provider.

Observable result:

```bash
md-library iterate --profile codex-mm -m gpt-5.4-mini
```

selects the Codex profile bundle and runs the same mission path currently reached by `--agent-instance codex-mm`.

Validation:

```bash
uv run pytest -q
```

in `md-library`, plus a dry-run CLI smoke.

## Risks And Deviation Triggers

- If `AgentConfig` cannot cleanly represent profile-owned `account`, stop and adjust the model before layering profile storage on top.
- If legacy `links.json` removal breaks account status or monitor behavior, keep a temporary read-only compatibility path and log the remaining dependency in `Impl.Log`.
- If profile file writes need locking to be safe, use atomic writes first and defer cross-process locks unless tests or real commands expose a race.
- If `YYYYMMDD` rolling event files conflict with an explicit naming requirement, stop and confirm before implementation; do not write both date formats.
- If `md-library --profile` collides with existing md-library semantics, use `--agent-profile` there while keeping Agentos as `--profile`.

## Acceptance.Signals

- Agent profiles can live as separate files under `~/.agentos/profiles/<name>.json`.
- A profile can contain provider, home, account, default model, run args, env, and ping config.
- `agentos agent run --profile codex-mm` works without `--provider`.
- `--provider` with `--profile` is an assertion and fails on mismatch.
- Provider-only `agent run --provider codex` does not silently guess a configured/default profile.
- Profile account binding is the source of truth for profile runs.
- Profile-bound run/materialization does not infer intended account from `links.json`.
- Account events are written to global rolling files under `~/.agentos/accounts/events/YYYYMMDD.jsonl`, with provider as a field.
- New profile-owned flows do not require `links.json` as authority.
- `agent accounts link --profile <profile> --account <account>` updates the profile binding and materializes auth.
- Existing account artifact registry behavior remains intact.
- Existing tests plus new profile/event/preflight tests pass.

## Impl.Log

- 2026-06-04: Created implementation request from discussion. Accepted direction: profile files are the source of truth for named runnable agent account binding; account registries own artifacts/metadata; global rolling account event logs record what happened; `links.json` is demoted and should not remain an authority for profile-owned homes.
- 2026-06-04: Implemented profile files under `~/.agentos/profiles/<name>.json`, account parsing into `AgentConfig`, profile-first resolution without required `--provider`, and provider/profile assertion semantics. Provider-only run/ping now requires `--home` when no profile is supplied.
- 2026-06-04: Implemented global account events under `~/.agentos/accounts/events/YYYYMMDD.jsonl` with provider/source/status fields and auth-payload redaction. Profile run/ping and `agent accounts link --profile` now append `account.auth.materialized` events.
- 2026-06-04: Implemented profile-owned Codex materialization: `agent.account` is preferred as intended binding, stale/conflicting legacy `links.json` state is ignored during profile materialization, and legacy links are only a fallback when no profile account exists. Profile-owned Codex materialization copies auth without writing `links.json`.
- 2026-06-04: Implemented `agentos agent accounts link --profile <profile> --account <account>` to update the profile account field, materialize auth into the profile home, and append `profile.account.changed` plus materialization events. Provider/home link mode remains for ad hoc/manual account operations; profile-owned Codex link mode does not write `links.json`.
- 2026-06-04: Implemented `agentos agent profiles migrate` with `--check` support. Legacy `agent.instances[]` entries can be reported or written as profile files, and legacy `links.json` can safely enrich a migrating profile only when the profile lacks an account.
- 2026-06-04: Implemented md-library `iterate --profile` as the preferred Agentos profile selector. `--agent-instance` remains a temporary alias. When profile is supplied without `--agent`, md-library emits `agentos agent run --profile <profile>` without `--provider`; `--agent` with profile remains a provider assertion.
- 2026-06-04: Validation passed: `uv run ruff check src/agentos/agent src/agentos/codex tests`; `uv run pytest -q` in `agentos-py` (52 passed); `uv run pytest -q` in `md-library` (74 passed, 11 subtests passed); md-library dry-run smoke emitted `agentos agent run --cwd /Users/pereiro/Documents/md-library --non-interactive --profile codex-mm --model gpt-5.4-mini ...`.
