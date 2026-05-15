# Claude StatusLine Rate Limits Impl.Req

## Impl.Abstract

Status: implemented

Owner surface: `agentos-py`

Request: implement Claude subscription limit tracking for `agent.account_status()` using Claude Code `statusLine.rate_limits` as the only active Claude usage source for now.

Source context:

- Active monitor already renders `AccountStatus.limits` into `usage/time` and `resets` rows.
- Active Claude `account_status` currently validates registered account/home identity and auth, but returns `usage_status="unavailable"` with no limits.
- Deprecated stats implementation already used a Claude statusLine capture path before falling back to stream-json.
- Current decision: do not implement OAuth API, web cookies, or API-key paths in this phase. Focus on subscription accounts through the registered account's Agentos system home.

Target observable result:

```text
agentos agent accounts monitor --once
```

renders `claude-code/<account>` with Claude `Burst` and `Weekly` `usage/time` rows when `statusLine.rate_limits` is available.

## Impl.Index

### Registered Account Home Is The Execution Boundary

Claude usage refresh must run against the `Agent` built for the registered account and its configured `home`.

Evidence:

- User direction: monitor works on registered accounts and system homes, not browser sessions.
- Active `ClaudeAgent.build_command(...)` injects `CLAUDE_CONFIG_DIR=<agent.home>`.
- System home example: `~/.agentos/agent/homes/claude-code/browser-jp`.

Implementation implication:

- Do not read `~/.claude` unless it is explicitly the configured agent home.
- Do not use browser cookie scraping.
- Do not infer accounts from non-registered homes.

### StatusLine Is The Only Usage Source For This Slice

The Claude usage source for this implementation is Claude Code statusLine input JSON, specifically `rate_limits`.

Evidence:

- Claude Code docs expose `rate_limits` on status line input for Claude.ai subscribers after the first API response.
- Deprecated implementation already captured this payload by installing a temporary `statusLine` command.
- Local smoke showed stream-json `rate_limit_event` exists, but it can be partial and lacks full `used_percentage`.

Implementation implication:

- Port the statusLine capture mechanism.
- Do not add OAuth `/api/oauth/usage`.
- Do not add web `claude.ai/api/organizations/.../usage`.
- Do not use stream-json as a fallback in this Impl.Req unless explicitly approved later.

### AccountStatus Remains The Provider Contract

Claude statusLine data must be normalized into active `AccountStatus` and `AccountLimit` models.

Evidence:

- `src/agentos/agent/account_status.py` defines `UsageOverTimeLimitData`, `AccountLimit`, and `AccountStatus`.
- Monitor `LimitsTrackingWorkflow` consumes `account_status.summary()` and renders `limits`.
- Codex account status already maps provider limit windows into the same model.

Implementation implication:

- `five_hour` maps to `limit_name="burst"`, `limit_label="Burst"`, `period_duration_mins=300`.
- `seven_day` maps to `limit_name="weekly"`, `limit_label="Weekly"`, `period_duration_mins=10080`.
- Other Claude windows can be ignored for the first slice unless they are easy to preserve in `provider_limit` without rendering.

### Workflow Errors Must Be Data, Not Crashes

Usage refresh errors must be carried by `AccountStatus.usage_errors`; they must not crash the monitor loop.

Evidence:

- Existing monitor design constraint: workflow errors should be placed on State/Frame and returned, not crash the loop.
- Active Claude account status already returns setup/auth errors as `AccountStatusError`.

Implementation implication:

- If setup/auth validation fails, do not attempt usage refresh.
- If statusLine capture fails, return `usage_status="error"` with a specific `usage_errors` entry.
- If statusLine capture succeeds but has no usable `rate_limits`, return `usage_status="error"` with an invalid-output style error.

### PTY Mechanics Are Provider-Specific

The statusLine capture requires interactive Claude Code behavior, so it is a provider implementation detail.

Evidence:

- Deprecated implementation used `pty.openpty()` and `subprocess.Popen(...)`.
- Current `AgentRunConfig.process_mode` does not expose PTY capture semantics.

Implementation implication:

- It is acceptable for `agentos.claude.account_status` to own a small PTY helper for this phase.
- Command construction should still respect `agent.build_command(...)` where practical, but no broad runtime abstraction should be added in this slice.
- Keep the PTY code local and testable through injected collector/parsing functions.

## Execution.Plan

### Slice 1: Port StatusLine Payload Parsing

Status: completed

Change:

- Add pure parsing helpers in `src/agentos/claude/account_status.py` or a small adjacent module.
- Parse a captured statusLine payload containing `rate_limits`.
- Produce `AccountLimit` objects for `five_hour` and `seven_day`.

Path exercised:

- Python unit test calls parser with representative statusLine JSON.

Observable result:

- Parser returns two limits with `used_percent`, reset timestamps, period bounds, labels, and provider payloads.

Validation:

```sh
uv run pytest tests/test_agent_account_registry_commands.py::<new_parser_test> -q
```

### Slice 2: Add StatusLine Capture Collector

Status: completed

Change:

- Implement a Claude statusLine collector that:
  - creates a temp directory,
  - writes a capture script,
  - writes temporary Claude `settings.json`,
  - launches Claude Code with the account home,
  - sends a cheap prompt,
  - waits for captured statusLine JSON containing `rate_limits`,
  - terminates the PTY process cleanly.

Path exercised:

- Unit tests monkeypatch the collector boundary rather than launching real Claude.
- A real smoke run later exercises the PTY path.

Observable result:

- Collector returns raw statusLine JSON with `rate_limits` when run against a logged-in Claude system home.

Validation:

```sh
uv run pytest tests/test_agent_account_registry_commands.py::<new_collector_boundary_test> -q
```

### Slice 3: Wire Claude account_status()

Status: completed

Change:

- Update `claude_account_status(...)`:
  - keep existing account/home/identity validation,
  - run statusLine capture as the single provider account-status call,
  - set `usage_status="ok"` and `limits=(...)` on success,
  - set `usage_status="error"` and `usage_errors=(...)` on capture/parse failure,
  - keep `usage_status="unavailable"` only when local account/home validation prevents provider execution.

Path exercised:

- Existing provider builder -> `ClaudeAgent.account_status()` -> normalized `AccountStatus`.

Observable result:

- Claude account status summary includes `limits` for `five_hour` and `seven_day`.

Validation:

```sh
uv run pytest tests/test_agent_account_registry_commands.py::<new_claude_account_status_usage_test> -q
```

### Slice 4: Monitor End-To-End Smoke

Status: completed

Change:

- No monitor-specific formatting changes expected if `AccountStatus.limits` is populated correctly.
- Reinstall CLI after code changes.

Path exercised:

- `agentos agent accounts monitor --once` with configured `claude-code/browser-jp`.

Observable result:

```text
claude-code/browser-jp:
  usage/time | ... | Burst
      resets | ...
  usage/time | ... | Weekly
      resets | ...
```

Validation:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
uv run ruff check src/agentos/claude/account_status.py tests/test_agent_account_registry_commands.py
git diff --check
uv tool install --reinstall --editable .
agentos agent accounts monitor --once
```

## Risks And Deviation Triggers

- If Claude Code no longer runs `statusLine` in the temporary settings mode, stop and report. Do not silently switch to OAuth/web.
- If system home needs workspace trust or interactive first-run setup, return a clear `usage_errors` message and report the required setup command.
- If only `five_hour` is present, return that limit and keep usage status `ok`; do not invent weekly data.
- If parsing encounters extra Claude limit keys, preserve them in `provider_limit` only if this does not complicate the first slice.
- If PTY handling becomes large or duplicated, keep the first implementation local; broader AgentRun PTY abstraction is out of scope for this Impl.Req.

## Acceptance Signals

- `ClaudeAgent.account_status()` returns `usage_status="ok"` and at least one `AccountLimit` for a logged-in subscription account with statusLine `rate_limits`.
- The monitor shows Claude usage/time rows without provider-specific monitor code.
- Failures return `AccountStatus` with `usage_errors`; monitor does not crash.
- No OAuth/web-cookie/API-key code is introduced.

## Impl.Log

- Draft created from current design decision: implement Claude subscription usage via `statusLine.rate_limits` only.
- Implemented in `src/agentos/claude/account_status.py`: Claude usage refresh now captures Claude Code `statusLine.rate_limits` through a provider-local PTY helper, parses `five_hour` and `seven_day`, and maps them to `AccountStatus.limits`.
- Added tests in `tests/test_agent_account_registry_commands.py` for parser mapping, `ClaudeAgent.account_status()` success, and usage refresh errors as data.
- Collapsed account status to a single behavior: no `refresh_usage`, no `methods` selector, and no separate provider auth/ping command before fetching usage.
- No OAuth, web-cookie, API-key, or stream-json usage fallback was added.
