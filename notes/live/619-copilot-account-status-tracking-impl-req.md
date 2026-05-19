# Copilot Account Status Tracking - impl-req

## Impl.Abstract

- **scope:** add first-class `copilot-cli` usage-status tracking to the active `Agentos.Agent` account-status and monitor stack.
- **status:** implemented.
- **source:** follow-up from account monitor work after researching the deprecated Copilot stats implementation, current `CopilotAgent`, current Codex/Claude `account_status` paths, Copilot CLI help, and GitHub Copilot usage documentation.
- **goal:** make registered Copilot accounts behave like Codex and Claude accounts for `agent.account_status(...)`, usage-registry recording, registry fallback, and `limits-tracking` monitor display.
- **strong constraint:** use the same provider-owned design as the current Codex and Claude paths. Do not revive deprecated stats orchestration. Do not add a parallel monitor-specific Copilot fetch.

## Impl.Index

### Current.State

- `src/agentos/copilot/agent.py` defines `CopilotAgent`, but it currently only owns session discovery/loading and command construction.
- `CopilotAgent` does not override `AgentBase.account_status(...)`, so active Copilot agents do not support account-status tracking.
- `src/agentos/codex/agent.py` delegates `CodexAgent.account_status(...)` to `src/agentos/codex/account_status.py`.
- `src/agentos/claude/agent.py` delegates `ClaudeAgent.account_status(...)` to `src/agentos/claude/account_status.py`.
- `src/agentos/agent/commands.py` currently restricts account-management provider choices to `codex` and `claude-code`.
- `src/agentos/agent/monitor/workflows.py` currently knows registry sources and usage-record parsers only for Codex and Claude.
- The active usage registry is provider-neutral and stores successful fresh observations under `~/.agentos/agent/usage-registry/YYYYMM-usage.jsonl`.

### Deprecated.Evidence

- `_DEPRECATED/agent-accounts-stats/copilot/accounts.py` already implemented a working Copilot usage fetch using:
  - `gh auth token`
  - `GET https://api.github.com/copilot_internal/user`
  - Copilot/VS Code style headers
  - parser logic for `quota_snapshots`, `monthly_quotas`, and `limited_user_quotas`
- `_DEPRECATED/agent-accounts-stats/agent/accounts.py` contains the old Copilot parser:
  - `_parse_copilot_usage_response(...)`
  - `_parse_copilot_quota_snapshots(...)`
  - `_copilot_limit_from_snapshot(...)`
  - monthly reset bound helpers
- A local probe on 2026-05-18 confirmed `copilot_internal/user` still returns usable usage data, including:
  - `login`
  - `copilot_plan`
  - `quota_reset_date_utc`
  - `quota_snapshots.premium_interactions.percent_remaining`
  - `quota_snapshots.premium_interactions.remaining`
  - `quota_snapshots.premium_interactions.entitlement`

### Online.Evidence

- GitHub Copilot documentation describes premium requests as monthly allowance data and says unused requests reset monthly.
- GitHub Copilot CLI help confirms each prompt consumes monthly premium-request quota.
- Copilot CLI help exposes `/usage`, but it is an interactive command. Do not start by automating `/usage`.
- GitHub REST billing usage endpoints exist, but the locally configured `gh` token currently lacks the `user` scope and the public endpoint returned `404` for the local token. Treat this as a possible future source, not the first implementation source.

### Identity.Model

- Use the existing `AccountIdentity` runtime model:
  - `provider_account_id`
  - `email`
  - `label`
  - `raw`
- Keep the persisted account-registry convention:
  - registry field `account_id` maps into `AccountIdentity.provider_account_id`
- Copilot registry records should use:

```json
{
  "provider": "copilot-cli",
  "account": "jp",
  "account_id": "josePereiro",
  "label": "GitHub Copilot jp"
}
```

- The local `account` alias is Agentos-owned, like `jp`.
- The Copilot provider identity is GitHub `login`, returned by `copilot_internal/user`.
- Email is optional for Copilot unless a later source reliably provides it.
- `CopilotAgent.account_status(...)` should compare:
  - expected `provider_account_id`: registry `account_id`
  - fetched `provider_account_id`: payload `login`
- If both are present and differ, return `identity_match="mismatched"` and include a normal setup error, matching Codex/Claude behavior.

### AccountStatus.Contract

- Add a provider-local implementation module:

```txt
src/agentos/copilot/account_status.py
```

- The public provider method should be:

```python
CopilotAgent.account_status(
    *,
    record_usage: bool = True,
    fallback_to_usage_registry: bool = True,
) -> AccountStatus
```

- The implementation shape should mirror Codex/Claude:

```text
CopilotAgent.account_status()
  -> _copilot_account_status_impl(...)
      -> validate account context and home
      -> load registered account
      -> inspect home/link/identity
      -> _account_usage_internal_user(...)
      -> _parse_copilot_usage_response(...)
      -> append usage registry record on fresh success
      -> fall back to usage registry on live usage fetch failure when enabled
```

- Do not add obsolete `account_stats(...)` or deprecated payload orchestration.
- Do not make the monitor call Copilot-specific HTTP directly.

### Home.And.Command.Model

- Copilot CLI documents `COPILOT_HOME` as the home override.
- `CopilotAgent.build_command(...)` should set `COPILOT_HOME` when `self.home` is present, analogous to:
  - Codex setting `CODEX_HOME`
  - Claude setting `CLAUDE_CONFIG_DIR`
- Account status should assume the configured Copilot system home is already set up and linked. It should not bootstrap login.
- Registration and linking should follow the existing account registry mechanics under `~/.agentos/accounts/copilot-cli/`.

### Usage.Source

- Initial live usage source:

```text
copilot_internal_user
```

- Fetch method:
  - get token with `gh auth token`
  - call `https://api.github.com/copilot_internal/user`
  - pass the Copilot-style headers from the deprecated implementation unless current testing shows they are unnecessary
- Parse the raw response into current `AccountLimit` objects.
- Preserve the raw provider payload in `AccountStatus.raw["usage"]`.
- Append the same raw payload to the usage registry only on fresh successful usage-limit fetch.

### Limit.Mapping

- Prefer `quota_snapshots.premium_interactions` for the monitor-visible usage line.
- Optionally parse `quota_snapshots.chat` only when it represents a meaningful limited quota.
- Ignore unlimited placeholder limits that have no useful entitlement/remaining/percent pressure.
- Map Copilot premium usage into:
  - `limit_class="usage_over_time"`
  - `limit_name="premium"`
  - `limit_label="Premium"`
  - `used_percent=round(100 - percent_remaining)`
  - `period_ends_at=quota_reset_date_utc`
  - `period_started_at` derived as the previous month boundary matching the reset instant, following the deprecated implementation
  - `period_duration_mins` derived from those bounds
- The monitor already renders unknown durations by label, so monthly Copilot rows do not need to pretend to be Burst or Weekly.

### Registry.Fallback

- Add a Copilot parser function for usage-registry payloads, analogous to:
  - `codex_usage_record_limits(...)`
  - `claude_statusline_usage_record_limits(...)`
- On live fetch failure, `CopilotAgent.account_status(...)` should use `latest_usage_record(...)` when `fallback_to_usage_registry=True`.
- Returned fallback status should carry `raw["usage_record"]` metadata compatible with existing monitor freshness and fetch-error display.
- Fallback is not a cache and must not suppress live fetch attempts. It is only used after live fetch failure.

### Monitor.Integration

- Extend `LimitsTrackingWorkflow` usage-registry support for Copilot:
  - source: `copilot_internal_user`
  - parser: Copilot usage-record parser
- The monitor should not need a provider-specific display path if Copilot returns normal `AccountStatus` limits.
- The visible account title can initially be `copilot-cli/jp:`. Provider icon/color polish is out of scope unless it is already a small local convention.

### No.Legacy.Allowed

- Do not restore `_DEPRECATED/agent-accounts-stats` modules or imports.
- Do not add `account_stats(...)` compatibility.
- Do not implement Copilot in monitor code by bypassing `agent.account_status(...)`.
- Do not copy the deprecated aggregate stats database shape.
- Do not use `/usage` automation for the first implementation.
- Do not normalize the usage-registry payload beyond existing homogeneous registry metadata.

## Execution.Plan

### Slice 1 - Add Copilot Registry Support

Status: complete.

- Extend account-management provider choices to include `copilot-cli`.
- Add Copilot account registry helpers only if provider-specific registration needs more than the generic registry API.
- Register Copilot by local alias plus `account_id` equal to GitHub login.
- Add tests that a Copilot registry record with `account_id="josePereiro"` can be loaded and inspected.
- Check:
  - `agentos agent accounts status --provider copilot-cli --json` is accepted
  - existing Codex/Claude account status behavior is unchanged

### Slice 2 - Add Copilot Home And Command Environment

Status: complete.

- Update `CopilotAgent.build_command(...)` to include `COPILOT_HOME=str(self.home)` when a home is configured.
- Keep `--account` unsupported for native Copilot CLI command construction, matching current behavior.
- Add tests for command construction with and without home.
- Check:
  - dry-run/build-command tests show `COPILOT_HOME` without leaking unrelated behavior

### Slice 3 - Implement Copilot AccountStatus Capability

Status: complete.

- Add `src/agentos/copilot/account_status.py`.
- Implement `_copilot_account_status_impl(...)`.
- Load the registered account and construct expected `AccountIdentity`.
- Fetch live payload with `_account_usage_internal_user(...)`.
- Parse payload into `AccountLimit` objects.
- Set:
  - `check_status`
  - `usage_status`
  - `identity_match`
  - `auth_summary`
  - `usage_summary`
  - `raw`
- Wire `CopilotAgent.account_status(...)` to delegate into this module.
- Check:
  - successful fake payload returns `usage_status="ok"`
  - mismatched `login` returns a setup identity mismatch
  - missing account/home errors follow Codex/Claude style

### Slice 4 - Add Usage Registry Writes And Fallback

Status: complete.

- Append usage records for successful fresh `copilot_internal_user` fetches when `record_usage=True`.
- Do not append on setup errors, usage errors, or registry fallback.
- Add `copilot_usage_record_limits(...)`.
- Use latest registry fallback on live fetch failure when enabled.
- Add tests for:
  - fresh success writes one registry record
  - `record_usage=False` writes none
  - live error plus existing registry record returns monitor-usable fallback limits
  - live error without registry record returns `usage_status="error"`

### Slice 5 - Wire Monitor Registry Priming

Status: complete.

- Extend `src/agentos/agent/monitor/workflows.py` with Copilot source/parser support.
- Ensure setup priming can show latest Copilot quota data before the first live refresh.
- Add focused monitor tests using a registry record for `copilot-cli/jp`.
- Check:
  - monitor frame displays a Copilot account with a `usage/time` row from registry data
  - fetch errors appear as existing `fetch error` rows when fallback data is used

### Slice 6 - Validate With Local Account

Status: complete.

- Create or use a registered Copilot account:

```sh
agentos agent accounts register --provider copilot-cli --account jp --account-id josePereiro --label "GitHub Copilot jp"
```

- Link/use system home:

```txt
~/.agentos/agent/homes/copilot-cli/jp
```

- Run:

```sh
agentos agent accounts status --provider copilot-cli --json
agentos agent accounts monitor --once
```

- Check:
  - `provider_account_id` verifies against `login`
  - usage registry receives a `copilot_internal_user` record
  - monitor renders Copilot premium quota without provider-specific monitor fetching

### Slice 7 - Test And Install

Status: complete.

- Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py tests/test_agent_commands.py -q
```

- Run lint on touched paths:

```sh
uv run ruff check src/agentos/copilot src/agentos/agent tests/test_agent_account_registry_commands.py tests/test_agent_commands.py
```

- Refresh installed CLI after runtime changes:

```sh
uv tool install --reinstall --editable .
```

- Smoke:

```sh
agentos --version
agentos agent accounts status --provider copilot-cli --json
agentos agent accounts monitor --once
```

## Impl.Log

- Created as the execution handoff for adding `copilot-cli` usage-status tracking to the current provider-owned `account_status` stack. The plan intentionally follows the Codex and Claude module pattern and excludes deprecated stats orchestration.
- Implemented provider-owned Copilot account registry support in `src/agentos/copilot/account_registry.py` and CLI registration/linking support in `src/agentos/agent/commands.py`.
- Implemented Copilot system-home command environment support in `src/agentos/copilot/agent.py`; `build_command(...)` now emits `COPILOT_HOME` when a home is configured while preserving the existing `--account` rejection.
- Implemented `src/agentos/copilot/account_status.py` with `CopilotAgent.account_status(...) -> _copilot_account_status_impl(...)`, live `copilot_internal_user` usage fetch through `gh auth token`, identity verification against `payload.login`, `AccountLimit` parsing, usage-registry writes, and registry fallback after live fetch failure.
- Extended `LimitsTrackingWorkflow` registry priming for `copilot-cli` using source `copilot_internal_user` and parser `copilot_usage_record_limits(...)`; monitor display remains generic and receives normal `AccountStatus` summaries.
- Created and linked the local Copilot system home requested during execution:
  - registered account: `copilot-cli/jp`
  - provider account id: `josePereiro`
  - system home: `~/.agentos/agent/homes/copilot-cli/jp`
  - link kind: `claimed`
- Updated `~/.agentos/config.json` monitor targets to include `{"provider": "copilot-cli", "account": "jp"}` so the monitor uses the system home through the registered account path.
- Validation evidence:
  - `uv run pytest tests/test_agent_account_registry_commands.py tests/test_agent_commands.py -q` -> `150 passed`.
  - `uv run ruff check src/agentos/copilot src/agentos/agent tests/test_agent_account_registry_commands.py tests/test_agent_commands.py` -> `All checks passed!`.
  - `uv tool install --reinstall --editable .` refreshed the installed `agentos` executable.
  - Live `CopilotAgent.account_status(record_usage=True)` verified `provider_account_id == "josePereiro"`, returned `usage_status="ok"`, and produced `usage_summary="Premium 16%"`.
  - `agentos agent accounts monitor --once` rendered `copilot-cli/jp` with a `Premium` usage/time row from the usage registry.
- No deprecated stats modules were restored or imported, no `account_stats(...)` compatibility was added, and the monitor does not perform Copilot-specific fetching.
