# Monitor Limits Tracking Account Status - impl-req

## Impl.Abstract

- **scope:** replace the placeholder `limits-tracking` monitor workflow with a first minimal implementation that calls registered-account `account_status(refresh_usage=True)` and renders cached account limit status into the monitor frame.
- **status:** implemented.
- **source:** current monitor design discussion after active Codex `account_status` was implemented and moved onto the provider command-construction model.
- **goal:** make `agentos agent accounts monitor` show real account-status data for configured registered-account targets while preserving monitor loop mechanics: persistent `MonitorState`, persistent `MonitorFrame`, workflow-owned error reporting, and slow-work throttling.

## Impl.Index

### Current.State.Evidence

- Monitor config is loaded from `agent.accounts.monitor` in `src/agentos/agent/monitor/config.py`.
- Monitor config already accepts workflow entries with `workflow: "limits-tracking"` and `targets`.
- Monitor targets already validate registered accounts with `load_account(provider, account)`.
- Target homes default to `~/.agentos/agent/homes/<provider>/<account>`.
- `MonitorLoop` in `src/agentos/agent/monitor/loop.py` owns persistent `MonitorState` and `MonitorFrame`, calls workflows every tick, and catches unexpected workflow bugs as a final guard.
- `LimitsTrackingWorkflow` in `src/agentos/agent/monitor/workflows.py` now refreshes registered-account status, caches target summaries by refresh interval, and renders target state into its frame block.
- Active account status path exists:
  - `build_registered_account_agent(provider, account, home)`
  - `agent.account_status(refresh_usage=True)`
- Codex `account_status` validates account/home identity, checks auth, fetches limits through `codex app-server`, and returns an `AccountStatus` model.
- Registered-account agent construction now uses the provider default command configuration plus the linked account home, so monitor execution does not select or infer from `agent.instances`.

### Target.Behavior

- `limits-tracking` should use each configured target as the source of truth:

```python
agent = build_registered_account_agent(
    provider=target.provider,
    account=target.account,
    home=target.home,
)
status = agent.account_status(refresh_usage=True)
```

- The workflow must not run slow provider calls every monitor tick.
- The monitor loop may tick once per second, but `limits-tracking` should refresh each target only when its configured refresh interval has elapsed.
- Between refreshes, it should reuse the previous `AccountStatus.summary()` stored in `MonitorState`.
- The workflow must catch expected per-target errors and write them into `MonitorState` and `MonitorFrame`; the loop should not crash because one account cannot be refreshed.
- The minimal TUI/text frame should be simple and useful, not final UI polish.

### Workflow.Config

- Add optional workflow config:

```json
{
  "workflow": "limits-tracking",
  "refresh_interval_sec": 60,
  "targets": [
    {
      "provider": "codex",
      "account": "jp",
      "home": "~/.agentos/agent/homes/codex/jp"
    }
  ]
}
```

- If omitted, `refresh_interval_sec` should default to `60`.
- Config validation should reject non-number, boolean, zero, or negative values.
- Keep the value workflow-scoped for this first implementation. Do not add per-target interval config yet.

### State.Shape

- Use `state.data["limits-tracking"]` as the workflow public state.
- Store a stable per-target map keyed by a deterministic target key such as:

```txt
<provider>/<account>@<home>
```

- Each target state should include:
  - `provider`
  - `account`
  - `home`
  - `status`: `"ok" | "error" | "pending"`
  - `last_refresh_at_monotonic`
  - `last_refresh_tick`
  - `refresh_count`
  - `account_status` as `AccountStatus.summary()` when available
  - `error` summary when refresh fails

- Store monotonic timestamps only for runtime decisions. They do not need to be semantically durable.

### Frame.Shape

- `LimitsTrackingWorkflow` should keep one persistent frame block and replace it in place.
- Minimal block lines should include:

```txt
refresh_interval_sec: 60
codex/jp
  home: /Users/.../.agentos/agent/homes/codex/jp
  status: ok
  check: ok
  usage: ok
  limits: 5 hours 25%, 168 hours 40%
```

- For errors:

```txt
codex/jp
  home: /...
  status: error
  error: <short message>
```

- Frame block `data` should contain the same structured target summaries for JSON tests.

### Error.Policy

- Startup config errors remain normal CLI errors before loop creation:
  - unknown workflow
  - invalid refresh interval
  - missing registered account
  - invalid target shape
- Runtime target refresh errors are workflow-owned:
  - catch `Exception` around each target refresh
  - write an error target state
  - show a concise frame line
  - do not re-raise
- Unexpected workflow bugs may still be caught by `MonitorLoop` as a last-resort guard, but target failures should not rely on that.

### Out.Of.Scope

- Do not build final Rich layout polish.
- Do not add JSON renderer changes beyond existing `--json` raw object output.
- Do not add per-target refresh intervals.
- Do not implement provider-specific account status beyond the active Codex path.
- Do not bootstrap or repair missing monitor homes. Missing/unusable homes should appear as runtime target errors.

## Execution.Plan

### Slice 1 - Parse Refresh Interval

Status: implemented.

- Add `refresh_interval_sec` to `MonitorWorkflowConfig` or a workflow-specific config field available to `LimitsTrackingWorkflow`.
- Parse it in `src/agentos/agent/monitor/config.py`.
- Default to `60` when omitted.
- Reject invalid values with clear `CliError`.
- Check:
  - config tests for default interval
  - config tests for invalid interval

### Slice 2 - Implement Target Refresh And Cache

Status: implemented.

- In `LimitsTrackingWorkflow`, replace placeholder state with real per-target cache.
- For each target:
  - create/reuse target state
  - if no prior refresh or interval elapsed, build registered-account agent and call `account_status(refresh_usage=True)`
  - otherwise reuse cached status
- Use monotonic time for interval checks.
- Store `AccountStatus.summary()` in state.
- Check:
  - first tick refreshes
  - second tick inside interval does not refresh
  - tick after elapsed interval refreshes again

### Slice 3 - Runtime Error Capture

Status: implemented.

- Wrap each target refresh so expected runtime failures become target error records.
- Include error type and message in state/frame data.
- Do not allow a single failed target to stop other targets.
- Check:
  - failed target appears as `status: error`
  - another target in the same workflow can still refresh
  - loop does not receive/record unexpected workflow error for expected target failures

### Slice 4 - Frame And JSON Output

Status: implemented.

- Replace the `under construction` frame block with account status lines.
- Include simple limit summaries from `account_status["usage_summary"]` or from individual limits if needed.
- Keep block replacement stable across ticks.
- Check:
  - `agentos agent accounts monitor --once` no longer prints `under construction`
  - `--json` contains target status and account status summaries
  - existing frame/state persistence tests still pass

### Slice 5 - Validation And Manual Smoke

Status: implemented.

- Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

- Run broader related tests:

```sh
uv run pytest tests/test_agent_commands.py tests/test_agent_account_registry_commands.py tests/test_process_runner.py -q
```

- Run full suite:

```sh
uv run pytest -q
```

- After CLI changes, reinstall:

```sh
uv tool install --reinstall --editable .
```

- Manual smoke:

```sh
agentos agent accounts monitor --once --json
agentos agent accounts monitor --once
```

## Risks And Deviation Triggers

- Stop and realign if `MonitorWorkflowConfig` becomes too generic for workflow-specific settings and needs typed workflow config objects.
- Stop and realign if account-status refresh is too slow for default monitor UX and needs a higher default interval.
- Stop and realign if runtime errors cannot be represented cleanly in `MonitorState.data` without changing the state/frame model.
- Do not move refresh throttling into `MonitorLoop`; throttling belongs to workflows.

## Acceptance Signals

- `limits-tracking` calls registered-account `account_status(refresh_usage=True)` for configured targets.
- The workflow reuses cached status inside `refresh_interval_sec`.
- Runtime target errors are visible in state/frame and do not crash the monitor loop.
- `--once` and `--json` use the same loop path.
- Monitor output shows real account-status data instead of `under construction`.
- Existing monitor loop mechanics remain intact.

## Impl.Log

- 2026-05-14: Created as first minimal implementation request for connecting `limits-tracking` monitor workflow to active registered-account `account_status`.
- 2026-05-14: Implemented `refresh_interval_sec` monitor workflow config, target refresh/cache state, per-target runtime error capture, and account-status frame/JSON output. During smoke testing, `build_registered_account_agent` still selected through configured `agent.instances` and failed when Codex profiles were ambiguous; fixed it to build registered-account agents from provider defaults plus the linked home, matching the registered-account-first design.
- 2026-05-14: Validation passed: `uv run pytest tests/test_agent_account_registry_commands.py -q`, `uv run pytest tests/test_agent_commands.py tests/test_agent_account_registry_commands.py tests/test_process_runner.py -q`, `uv run pytest -q`, `uv run ruff check src/agentos/agent/monitor src/agentos/agent/providers.py tests/test_agent_account_registry_commands.py src/agentos/codex/account_status.py`, `uv tool install --reinstall --editable .`, `agentos agent accounts monitor --once --json`, and `agentos agent accounts monitor --once`.
