# Agent Profile Legacy Cleanout - impl-req

## Impl.Abstract

- **scope:** remove legacy code paths and terminology left after `629-agent-profile-ssot-and-account-events-impl-req.md`, making Agentos profiles the only named runnable-agent configuration model and removing md-library's `agent-instance` terminology
- **status:** implemented
- **source:** 2026-06-04 post-629 cleanup check; user asked to clear all legacy code/terminology after confirming remaining `agent.instances`, `links.json`, `--agent-instance`, and `agent_instance` surfaces
- **owning project:** `agentos-py`
- **secondary project:** `md-library`
- **primary paths:** `src/agentos/agent/config.py`, `src/agentos/agent/providers.py`, `src/agentos/agent/commands.py`, `src/agentos/agent/account_registry.py`, provider account modules under `src/agentos/{codex,claude,copilot}/`, `src/agentos/codex/linking.py`, md-library `src/md_library/{agents.py,cli.py,iterate.py}`, md-library package docs/tests
- **related surfaces:** `notes/live/629-agent-profile-ssot-and-account-events-impl-req.md`, `notes/live/628-agent-run-account-preflight-impl-req.md`

## Impl.Index

### Cleanup.Intent

This is a removal request, not a migration-polish request.

Accepted direction:

- Profiles are the only named runnable-agent configuration concept.
- `agent.instances[]` is no longer a runtime configuration input.
- `--agent-instance` is no longer a supported md-library CLI term.
- `links.json` is no longer an authority for runnable-agent intent or a normal account-operation store.
- Transitional fallback code introduced or retained by 629 should be deleted once this request executes.

Hard.Evidence:

- `629` intentionally left temporary fallback and migration scaffolding:
  - legacy `agent.instances` reads in `agent.config.load_agent_configs(...)`
  - `_resolve_legacy_profile_config(...)` in `agent.providers`
  - `agent profiles migrate`
  - md-library `--agent-instance` alias
  - read-only `links.json` fallback in account/preflight/status surfaces
- User now explicitly requested clearing all legacy code/terminology.

Implementation posture:

- Do not preserve backward compatibility for removed terms.
- Remove old APIs/flags/tests instead of marking them deprecated.
- Keep only current profile/account/event terminology in command help, code names, tests, and docs.

### Agent.Profile.Only

`~/.agentos/profiles/<name>.json` becomes the only named runnable-agent configuration input.

Remove:

- Loading `agent.instances[]` from global/project config during normal `load_agent_configs(...)`.
- Runtime fallback from missing profile file to legacy `agent.instances`.
- Error text and validation text that presents `agent.instances` as active config.
- Migration command surfaces whose only purpose is converting `agent.instances`.

Keep:

- Provider-level `agent.providers` config in `~/.agentos/config.json`.
- `AgentConfig.instance_id` as an internal field if renaming it would create broad churn; but user-facing text should say `profile` / `profile id`.
- Profile file parsing and writing from 629.

Deviation trigger:

- If monitor/session/index code cannot function without `AgentConfig.instance_id`, keep the field internally for this slice and log a later data-model rename request. Do not keep user-facing `instance` terminology.

### Account.Link.Registry.Removal

`links.json` should stop being a maintained account state surface.

Remove or replace:

- `links_path`, `load_links`, `upsert_link`, `write_links`, `_link_records`, and `link_count` reporting from `agent.account_registry`, unless a non-profile provider has a current hard dependency that cannot be replaced in-slice.
- Provider link writes to `links.json` from Codex, Claude, and Copilot account link commands.
- Status logic that treats `links.json` as current truth.
- Reconcile discovery from `links.json`.

Keep:

- Account registry: accounts, artifacts, active artifacts.
- Global account event logs under `~/.agentos/accounts/events/YYYYMMDD.jsonl`.
- Provider-home inspection based on actual provider auth files and registered account/artifact data.
- Explicit `agent accounts link --provider --home --account` as an ad hoc materialization operation if still useful, but it must copy/materialize/claim and append events without writing `links.json`.

Hard.Evidence:

- 629 already made profile-owned Codex materialization skip `links.json`.
- `src/agentos/agent/account_registry.py` still defines and exports link registry helpers.
- Claude/Copilot account code still writes claimed links.
- Claude/Copilot status code still reads links.

Deviation trigger:

- If a provider cannot inspect actual home auth and only has claimed-link behavior today, either replace claimed-link status with event/account-record evidence or remove claimed-link status output. Do not preserve `links.json` as a live registry.

### MdLibrary.Profile.Terminology

md-library should use Agentos profile terminology directly.

Remove:

- `--agent-instance` CLI alias.
- `agent_instance` Python parameter/variable names.
- Runtime metadata key `agent_instance`.
- Package docs that describe configured Agentos instances.
- Tests that use `agent_instance`.

Replace with:

- `--profile`
- `profile`
- Runtime metadata key `profile`
- Docs that describe Agentos profiles and provider assertion via `--agent`.

Hard.Evidence:

- `src/md_library/cli.py` currently registers `--profile` and `--agent-instance` with `dest="agent_instance"`.
- `src/md_library/agents.py` and `src/md_library/iterate.py` still use `agent_instance`.
- `skills/md-library-pkg/SKILL.md` still documents `--agent-instance`.

### Codex.Mux.Profile.Alignment

Codex mux still uses old instance terminology and global `agent.instances` config.

Remove or replace:

- `codex.mux.default_instance_id`.
- `_load_global_agent_instances(...)`.
- Error messages saying `agent.instances`.

Replace with:

- `codex.mux.default_profile`, resolving through `~/.agentos/profiles/<name>.json`.
- Error messages saying `profile`.
- Tests that prove mux default profile uses profile file config.

Deviation trigger:

- If Codex mux is obsolete after the account-profile model, remove mux profile integration instead of preserving a stale surface. Confirm by usage search before deleting public command paths.

## Execution.Plan

### Slice 1 - Agentos Profile-Only Runtime Resolution

- Remove legacy `agent.instances` loading from `load_agent_configs(...)`.
- Remove `_resolve_legacy_profile_config(...)` from provider resolution.
- Remove `load_agent_configs_with_defaults(...)` if no longer used; otherwise rename/rework it so it does not imply provider-default guessing.
- Update list/ping/run errors and tests to use profile terminology only.

Observable result:

```bash
agentos agent run --profile codex-mm --dry-run --prompt hello
```

resolves only profile files, and a missing profile fails with `agent profile not found`.

Validation:

```bash
uv run pytest tests/test_agent_profiles.py tests/test_agent_run_account_preflight.py -q
rg -n "agent\\.instances|_resolve_legacy_profile_config|load_agent_configs_with_defaults" src/agentos tests
```

The `rg` result must contain no active code references except historical notes if notes are searched.

### Slice 2 - Remove Agent Profile Migration Surface

- Remove `agent profiles migrate` command and its implementation.
- Remove tests that assert migration from `agent.instances`.
- Remove migration-only helper functions.
- Remove 629 migration wording from active docs if those docs are updated as part of execution.

Observable result:

```bash
agentos agent profiles migrate --check
```

is no longer a registered command.

Validation:

```bash
uv run pytest tests/test_agent_profiles.py -q
rg -n "profiles migrate|agent\\.instances|legacy instance|legacy profile" src/agentos tests
```

### Slice 3 - Remove Account Link Registry

- Remove `links.json` helper API from `agentos.agent.account_registry`.
- Stop Codex/Claude/Copilot account link operations from writing link records.
- Replace account status rendering so it does not report link consistency or linked account from `links.json`.
- Replace reconcile home discovery from links with profile homes, explicit `--home`, registered system homes, or actual provider homes only.
- Update tests to assert events and actual auth/materialization state rather than link records.

Observable result:

- Running any account link/materialization operation appends account events but does not create `~/.agentos/accounts/<provider>/links.json`.
- `agent accounts status` output has no link registry count or link consistency fields.

Validation:

```bash
uv run pytest tests/test_agent_account_events.py tests/test_agent_profiles.py tests/test_agent_run_account_preflight.py tests/test_codex_account_reconcile.py -q
rg -n "links\\.json|load_links|upsert_link|write_links|link_consistency|Linked account|link_count" src/agentos tests
```

Expected result: no active code/test references except unrelated names such as `skills-routing-links.json`.

### Slice 4 - Codex Mux Profile Terminology

- Replace `codex.mux.default_instance_id` with `codex.mux.default_profile`.
- Resolve the default through profile files instead of `agent.instances`.
- Rename local functions and error messages away from `instance`.
- Update tests or add focused tests for mux default profile resolution.

Observable result:

- Codex mux config can reference a profile file by `default_profile`.
- No Codex mux code reads `agent.instances`.

Validation:

```bash
uv run pytest tests -q
rg -n "default_instance_id|agent\\.instances|_load_global_agent_instances" src/agentos tests
```

### Slice 5 - Md-Library Profile-Only CLI Terminology

- Remove `--agent-instance` from `md-library iterate`.
- Rename Python parameters and variables from `agent_instance` to `profile`.
- Change runtime metadata from `agent_instance` to `profile`.
- Keep `--agent` only as optional provider assertion; if no `--profile`, preserve current explicit agent/provider behavior only if still required by md-library.
- Update tests and package docs.

Observable result:

```bash
md-library iterate --proj-random --profile codex-mm -m gpt-5.4-mini --dry-run -n 1 -N 1 --no-commit
```

prints an `agentos agent run ... --profile codex-mm ...` command and runtime metadata with `profile: codex-mm`.

Validation:

```bash
uv run pytest -q
uv run python -m md_library.cli iterate --proj-random --profile codex-mm -m gpt-5.4-mini --dry-run -n 1 -N 1 --no-commit
rg -n "agent-instance|agent_instance|agentos instance|instance default|AUTO_AGENT_INSTANCE" src tests skills/md-library-pkg AGENTS.md
```

Expected result: no active md-library code/docs references to Agentos instances.

### Slice 6 - Global Terminology Audit

- Run final repository-wide searches in both repos.
- Rename or remove any remaining user-facing `instance` references that mean Agentos profile.
- Leave internal `instance_id` only if it is purely structural and explicitly logged as deferred model-field cleanup; otherwise rename it.
- Update `630` Impl.Log with removals and any intentional residuals.

Validation:

In `agentos-py`:

```bash
uv run ruff check src/agentos tests
uv run pytest -q
rg -n "agent\\.instances|default_instance_id|agent-instance|agent_instance|legacy|deprecated|compat|links\\.json|load_links|upsert_link" src/agentos tests
```

In `md-library`:

```bash
uv run pytest -q
rg -n "agent-instance|agent_instance|agentos instance|legacy|deprecated|compat" src tests skills/md-library-pkg AGENTS.md
```

Search findings must be classified:

- removed,
- unrelated word usage,
- historical notes only,
- or explicitly deferred with reason in `Impl.Log`.

## Risks And Deviation Triggers

- If removing `links.json` breaks Claude/Copilot status because those providers have no inspectable home auth file, do not keep the link registry. Replace status with account registry/event-derived information or remove unsupported status fields.
- If removing `agent.instances` breaks project-local profile selection in an unexpected subsystem, stop and decide whether that subsystem should use profile files or whether the subsystem is obsolete.
- If `AgentConfig.instance_id` rename causes broad churn in session identity/storage code, keep the internal field for this request but eliminate user-facing terminology and log a follow-up.
- If md-library still needs a provider-only no-profile mode for non-profile local testing, keep `--agent` but make docs clear that configured reusable agents are profiles.

## Acceptance.Signals

- `agentos-py` has no active runtime loading from `agent.instances[]`.
- `agentos-py` has no `_resolve_legacy_profile_config(...)`.
- `agent profiles migrate` is removed.
- `links.json` is not written, read, reported, or exported by active account-management code.
- Account operations use account registry + artifact registry + global events, not mutable link registry state.
- Codex mux no longer uses `default_instance_id` or `agent.instances`.
- md-library has no `--agent-instance` flag.
- md-library code/tests/docs use `profile`, not `agent_instance`, for Agentos profile selection.
- Validation suites pass in both repos.
- Final grep audit has no unclassified active legacy references.

## Impl.Log

- 2026-06-04: Created implementation request from post-629 cleanup check. Remaining legacy surfaces identified in Agentos (`agent.instances`, legacy profile fallback, migration command, `links.json`, Codex mux `default_instance_id`) and md-library (`--agent-instance`, `agent_instance`, instance-oriented runtime metadata/docs). Accepted direction: remove legacy code and terminology rather than preserving compatibility.
- 2026-06-04: Implemented cleanup. Agentos now loads named runnable agents only from profile files, removed `agent profiles migrate`, removed runtime fallback to `agent.instances`, removed `links.json` helper APIs and writes, moved account status/reconcile/preflight to actual auth + account/artifact/event state, and changed Codex mux from `default_instance_id` to `default_profile`. md-library now uses `--profile` / `profile` through CLI, command building, runtime metadata, tests, and package docs; `--agent-instance` and `agent_instance` are removed. Intentional residual: `AgentConfig.instance_id` remains an internal structural field because broader session/storage identity still uses it; user-facing surfaces now say profile.
- 2026-06-04: Validation passed. Agentos: `uv run ruff check src/agentos tests`, `uv run pytest -q` (51 passed). md-library: `uv run pytest -q` (74 passed, 11 subtests passed) and dry-run `uv run python -m md_library.cli iterate --proj-random --profile codex-mm -m gpt-5.4-mini --dry-run -n 1 -N 1 --no-commit` emitted `agentos agent run ... --profile codex-mm ...` with runtime metadata `profile: codex-mm`. Final grep residuals classified as unrelated: Agentos `skills-routing-links.json`, mdblocks block `link_count`, Tara tapes compatibility comment; md-library root AGENTS note about the old deprecated iteration skill.
