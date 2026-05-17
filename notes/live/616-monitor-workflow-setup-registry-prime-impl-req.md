# Monitor Workflow Setup Registry Prime - impl-req

## Impl.Abstract

- **scope:** extend the monitor workflow protocol from a single alarm-driven method to a two-phase workflow interface:
  - `setup(state, frame)`
  - `loop(state, frame, trigger)`
- **status:** implemented.
- **source:** follow-up from the monitor clock/alarm implementation. The monitor now has a main render loop, a workflow thread, clock-owned alarms, and a `limits-tracking | next in N ticks` display.
- **goal:** make the first monitor display useful before live provider fetches complete by letting workflows prime their frame from fast local data. For `limits-tracking`, setup should show the last available usage/quota data from the usage registry without calling providers.
- **strong constraint:** replace the current `MonitorWorkflow.run(...)` protocol cleanly. Do not keep compatibility aliases or adapter shims for the old single-method workflow API.

## Impl.Index

### Current.State

- `src/agentos/agent/monitor/loop.py` currently defines `MonitorWorkflow.run(state, frame, trigger)`.
- The workflow thread waits for fired alarm snapshots before preparing the working frame and calling workflow code.
- `LimitsTrackingWorkflow.run(...)` currently handles all work:
  - update workflow state
  - decide whether fired alarms require a provider refresh
  - call `agent.account_status()` for live data
  - render the frame block
- The first useful frame depends on the startup alarm workflow cycle completing.
- If provider fetches are slow, the monitor can render a waiting or fetching state even though the usage registry may already contain recent quota data.

### Accepted.Workflow.Interface

- All monitor workflows must implement:
  - `setup(state, frame)`
  - `loop(state, frame, trigger)`
- `setup(...)` is called exactly once per monitor run by the workflow thread.
- `loop(...)` is called for each workflow cycle produced by clock-fired alarms.
- `setup(...)` receives the same shared `MonitorState` and the workflow-owned `MonitorFrame`.
- `setup(...)` does not receive a trigger snapshot because it is not alarm-driven.
- The old workflow method name `run(...)` must be deleted from the monitor workflow protocol and current workflow implementations.

### Setup.Semantics

- `setup(...)` is for fast local initialization only.
- `setup(...)` must not call provider commands or perform live network/API fetches.
- `setup(...)` may read local Agentos state such as account registry, home metadata, and the usage registry.
- `setup(...)` may mutate workflow state and frame in the same way `loop(...)` does.
- If setup cannot find local quota data, it should render a clear placeholder for the target instead of failing the monitor.
- Setup errors follow the monitor rule that workflow errors never crash the loop:
  - workflow-owned expected errors should be rendered in the frame
  - unexpected errors should be captured by `MonitorLoop` using the same frame/state error mechanism used for workflow loop errors

### MonitorLoop.Ownership

- The workflow thread should publish one setup frame before waiting for alarm snapshots.
- Main loop ownership remains unchanged:
  - main/render thread owns `visible_frame`
  - workflow thread owns `working_frame`
  - frame ownership transfers only through the existing ready/swap mechanism
- Setup should use the same frame publication path as loop cycles.
- The monitor clock remains the only source of loop activation.
- Startup alarm behavior remains:
  - `startup` still fires and schedules the first live `loop(...)` cycle
  - setup does not replace the startup live fetch
  - setup just gives the monitor a useful local frame while live fetches are running

### LimitsTracking.Setup

- `LimitsTrackingWorkflow.setup(...)` should prime target state from the usage registry.
- For each configured target:
  - look up the latest matching usage record for the target provider/account/home
  - parse it into the same account-status-summary shape currently rendered by `_target_rows(...)`
  - mark the target as registry-backed/local, not freshly fetched
  - record enough metadata for display freshness, including `recorded_at`, source, and age
- The setup frame should reuse the existing `limits-tracking` block shape and row rendering.
- The setup frame should show the same quota rows the monitor already shows for live/fallback account status when enough registry data exists.
- If no matching registry record exists for a target, render a simple placeholder such as `usage | waiting for first fetch`.

### Usage.Registry.Shape

- Current registry API:
  - `src/agentos/agent/usage_registry.py`
  - `latest_usage_record(provider, account, home, source)`
- Current successful sources:
  - Codex: `CODEX_APP_SERVER_USAGE_SOURCE = "app_server"`
  - Claude Code: `CLAUDE_STATUSLINE_USAGE_SOURCE = "statusline_rate_limits"`
- The implementation should centralize source selection for monitor setup.
- Avoid duplicating provider payload parsing in the monitor when a provider parser already exists.
- If provider payload parsers are private but needed by setup, prefer extracting provider-local helper functions with clear names over copying parse logic into `monitor/workflows.py`.
- Do not add legacy source fallbacks. Use the active source for each provider.

### Display.Freshness

- Setup-loaded data should not display as `fresh`.
- It should use a registry/latest freshness marker so the account header can show the record time and age.
- Existing rendering already understands `registry_fallback` metadata well enough to display recorded time and age; implementation may reuse that display shape if it keeps the semantics clear in state/raw metadata.
- If a later live loop fetch succeeds, it replaces setup data with normal fresh account status.
- If a later live loop fetch fails and `account_status()` falls back to the registry, the existing fallback error row behavior should remain intact.

### Delete.Old.System

- Delete `MonitorWorkflow.run(...)` as the monitor protocol method.
- Delete current calls to `workflow.run(...)`.
- Delete tests that preserve the old single-method workflow protocol.
- Do not keep `run = loop` aliases or duck-typed fallback calls.
- Do not make setup optional for current workflows; every workflow must implement the two-method interface.

## Execution.Plan

### Slice 1 - Replace Workflow Protocol With Setup/Loop

Status: completed.

- Update `MonitorWorkflow` in `src/agentos/agent/monitor/loop.py` to require `setup(...)` and `loop(...)`.
- Rename `LimitsTrackingWorkflow.run(...)` to `loop(...)`.
- Update test workflow classes to implement both methods.
- Check:
  - no `workflow.run(...)` call remains in monitor code
  - no `LimitsTrackingWorkflow.run` remains
  - focused monitor tests still execute workflow cycles through `loop(...)`

### Slice 2 - Publish Setup Frame Before Alarm Loops

Status: completed.

- In the workflow thread, prepare `working_frame`, call each workflow `setup(...)`, and publish that frame once before waiting for alarm snapshots.
- Reuse the same ready/swap publication path as normal workflow cycles.
- Capture unexpected setup exceptions into frame/state errors with clear `setup` context.
- Check:
  - monitor can render a setup-produced frame before a slow startup live fetch completes
  - setup errors do not crash the monitor
  - frame ownership remains unchanged

### Slice 3 - Add Registry Prime Data Path For Limits Tracking

Status: completed.

- Add a small `LimitsTrackingWorkflow.setup(...)` implementation.
- For each target, read latest usage registry data using the active provider source:
  - codex -> `app_server`
  - claude-code -> `statusline_rate_limits`
- Convert the registry record into target state compatible with existing `_target_rows(...)`.
- Do not call `build_registered_account_agent(...)` or `agent.account_status()` from setup.
- Check:
  - setup loads local registry records without provider calls
  - missing records produce a visible placeholder
  - setup state is replaced by live loop state after a successful startup fetch

### Slice 4 - Centralize Registry Payload Parsing

Status: completed.

- Reuse or extract provider parsing helpers so registry payloads are parsed once per provider model.
- Keep provider-specific parse knowledge near provider account-status code, not scattered through monitor display logic.
- If parse extraction changes provider modules, keep exports narrow and named for usage-record parsing.
- Check:
  - codex registry payload renders the same limit rows as live codex account status
  - claude statusline registry payload renders the same limit rows as live claude account status
  - invalid registry payload is rendered as a target-local setup error, not a monitor crash

### Slice 5 - Update Tests Around Startup Behavior

Status: completed.

- Add tests for the new workflow interface:
  - setup called once
  - loop called on fired alarms
  - old `run(...)` protocol not used
- Add a slow-live-fetch monitor test proving setup frame is visible while startup loop is still fetching.
- Add `limits-tracking` tests with usage registry records:
  - latest registry data appears on first render without provider calls
  - no registry record shows placeholder
  - later live fetch replaces setup data
- Check:
  - tests use shared monitor alarm constants, not repeated alarm string literals
  - tests do not preserve the old single-method workflow protocol

### Slice 6 - Validation

Status: completed.

- Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

- Run lint:

```sh
uv run ruff check src/agentos/agent/monitor src/agentos/agent/commands.py src/agentos/codex/account_status.py src/agentos/claude/account_status.py tests/test_agent_account_registry_commands.py
```

- Refresh installed CLI if CLI/runtime files changed:

```sh
uv tool install --reinstall --editable .
```

- Manual smoke:

```sh
agentos agent accounts monitor --once
agentos agent accounts monitor --once --json
agentos agent accounts monitor --max-ticks 2 --interval-sec 0.05
```

- Acceptance signals:
  - first displayed `limits-tracking` frame can come from local registry data
  - startup live fetch still happens via the clock alarm
  - provider fetches are not called from setup
  - workflow protocol is `setup(...)` plus `loop(...)`
  - no old `run(...)` monitor workflow API remains

## Impl.Log

- Created to implement the accepted two-phase workflow interface and registry-backed first frame for `limits-tracking`. The current monitor clock/alarm system remains the scheduler; setup is a one-time workflow-thread initialization phase, not a new trigger source.
- Implemented `MonitorWorkflow.setup(...)` plus `MonitorWorkflow.loop(...)` and deleted the old workflow `run(...)` protocol/call path.
- Added workflow-thread setup publication through the existing working-frame ready/swap path. The main loop now tracks whether a visible frame has been published explicitly instead of treating tick `0` as an empty-frame sentinel.
- Added `LimitsTrackingWorkflow.setup(...)` registry priming. It reads `latest_usage_record(...)` for active provider sources only, renders registry-backed quota rows when present, and renders `usage | waiting for first fetch` when no record exists.
- Added `registry_latest` usage-record metadata for setup-loaded data so headers show recorded time and age without rendering a fallback fetch-error line.
- Extracted provider-local usage-record parser helpers:
  - `codex_usage_record_limits(...)`
  - `claude_statusline_usage_record_limits(...)`
- Updated monitor tests to use the setup/loop interface and added direct coverage for setup-first-frame rendering and provider-free registry priming.
- Validation completed:
  - `uv run ruff check src/agentos/agent/monitor src/agentos/agent/commands.py src/agentos/agent/account_status.py src/agentos/codex/account_status.py src/agentos/claude/account_status.py tests/test_agent_account_registry_commands.py`
  - `uv run pytest tests/test_agent_account_registry_commands.py -q` -> 88 passed
  - `uv tool install --reinstall --editable .`
  - `agentos agent accounts monitor --once`
  - `agentos agent accounts monitor --once --json`
  - `agentos agent accounts monitor --max-ticks 2 --interval-sec 0.05`
