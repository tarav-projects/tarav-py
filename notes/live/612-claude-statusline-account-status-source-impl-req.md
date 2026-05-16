# Claude StatusLine Account Status Source - impl-req

## Impl.Abstract

- **scope:** make Claude Code account usage status use a fresh `statusLine.rate_limits` capture as the active source, replacing the current `/api/oauth/usage` GET source in `_claude_account_status_impl()`.
- **status:** implemented.
- **source:** follow-up to `601-claude-statusline-rate-limits-impl-req.md`, the later GET experiment, and the current discussion after Anthropic repeatedly returned `429` for `/api/oauth/usage`. User explicitly requested the simple single-source statusLine implementation and rejected extra cache/source stacking.
- **goal:** `agent.account_status()` for `claude-code` should collect fresh Claude subscription limits from Claude Code statusLine using the registered account's Agentos system home, record successful observations as `statusline_rate_limits`, and use registry fallback only from `_claude_account_status_impl()` when live capture fails.

## Impl.Index

### Current.State.Evidence

- Current implementation point:

```txt
src/agentos/claude/account_status.py
  _claude_account_status_impl()
```

- Current selected usage source:

```txt
_claude_account_status_impl()
  -> _account_usage_statusline(cleanup_transcript=False)
  -> if usage_errors:
       _account_usage_registry_fallback(
         source="statusline_rate_limits",
         parser=_parse_claude_statusline_rate_limits,
         ...
       )
```

- `_account_usage_GET()` is live-GET-only and remains only as an isolated alternative implementation. It is not called by `_claude_account_status_impl()`.
- Active statusLine implementation:

```txt
_account_usage_statusline()
_run_claude_statusline_refresh_session()
_parse_claude_statusline_rate_limits()
```

- Local smoke showed statusLine capture works against the registered Claude system home and returns usable limits:

```txt
five_hour.used_percentage = 100
five_hour.resets_at      = 2026-05-16T04:00:00Z
seven_day.used_percentage = 15
seven_day.resets_at       = 2026-05-16T10:00:00Z
```

### Ownership.Split

- `_claude_account_status_impl()` is the implementation point for the Claude account-status capability.
- `_account_usage_statusline()` is only the source implementation for one live usage fetch.
- Registry fallback belongs in `_claude_account_status_impl()`, not inside `_account_usage_statusline()`.
- Target flow:

```txt
_claude_account_status_impl()
  -> _account_usage_statusline(cleanup_transcript=False)
  -> if usage_errors:
       _account_usage_registry_fallback(
         source="statusline_rate_limits",
         parser=_parse_claude_statusline_rate_limits,
         ...
       )
```

- Do not move account identity, home-link, registry recording, or fallback policy into the statusLine source function.

### StatusLine.Source.Contract

- Add or use a constant:

```python
CLAUDE_STATUSLINE_USAGE_SOURCE = "statusline_rate_limits"
```

- `_account_usage_statusline(...)` must return the same shape as `_account_usage_GET(...)`:

```python
tuple[
    tuple[AccountLimit, ...],
    tuple[AccountStatusError, ...],
    dict[str, Any] | None,  # usage_payload
    dict[str, Any] | None,  # usage_record_payload
    dict[str, Any] | None,  # usage_record_metadata
]
```

- Fresh success returns:

```txt
limits parsed from statusLine rate_limits
errors = ()
usage_payload = raw statusLine payload
usage_record_payload = raw statusLine payload
usage_record_metadata = fresh_usage_record_metadata(source="statusline_rate_limits")
```

- Failure returns:

```txt
limits = ()
errors = (AccountStatusError(...),)
usage_payload = None
usage_record_payload = None
usage_record_metadata = None
```

- `_account_usage_statusline()` must not perform registry fallback.

### Fresh.Capture.Only

- Every `_account_usage_statusline()` call should attempt a fresh statusLine capture.
- Caller/workflow code controls refresh frequency.
- Do not use the current statusLine payload cache in the active path.
- Remove active use of:

```txt
CLAUDE_STATUSLINE_CACHE_MAX_AGE_SEC
CLAUDE_STATUSLINE_STALE_FALLBACK_MAX_AGE_SEC
_load_cached_claude_statusline_payload(...)
_write_cached_claude_statusline_payload(...)
```

- Delete those helpers/constants if they become unused.
- Do not introduce a new statusLine cache, throttle, or stale-cache fallback.
- The existing GET throttle cache may remain only for the isolated `_account_usage_GET()` alternative implementation; it is not part of the active statusLine source.

### Implementation.Body

- Put the statusLine capture mechanics directly in `_account_usage_statusline()`.
- Do not keep `_collect_claude_statusline_payload()` as a separate orchestration helper unless implementation proves a narrow low-level helper is genuinely needed.
- `_account_usage_statusline()` should:
  - require/use the registered account `agent.home`
  - create/use the system-home workspace:

```txt
<agent.home>/agentos/workspaces/statusline-refresh
```

  - create a temporary capture script and temporary Claude settings file
  - configure `statusLine.command` to write stdin JSON into a temp capture file
  - run Claude Code with `agent.build_command(...)`, model `haiku`, and the registered account system home
  - wait for captured JSON containing `rate_limits`
  - parse with `_parse_claude_statusline_rate_limits(...)`
  - return the raw statusLine payload as recordable payload

- Existing low-level PTY helpers may remain if they are already local implementation mechanics. The requested simplification is about not splitting the statusLine source into extra source/cache orchestration layers.

### Transcript.Cleanup

- `_account_usage_statusline()` should accept:

```python
cleanup_transcript: bool = False
```

- Default is `False`; keep transcripts by default for debugging.
- If `cleanup_transcript=True`, cleanup is best-effort:
  - use existing transcript cleanup logic if available
  - cleanup failure must not fail the usage fetch
  - cleanup failure should not change `usage_status`

### Registry.Recording

- `_claude_account_status_impl()` remains the registry write boundary.
- On fresh statusLine success, append a usage registry row with:

```txt
provider = "claude-code"
account  = registered account name
home     = registered account system home
source   = "statusline_rate_limits"
payload  = raw statusLine payload
```

- `record_usage=False` must still skip appending.
- A registry fallback result must not append a new record.
- The append source should come from `usage_record_metadata["source"]` when available, not from a hard-coded GET constant.

### Registry.Fallback

- When live statusLine capture fails and `fallback_to_usage_registry=True`, `_claude_account_status_impl()` should call:

```txt
_account_usage_registry_fallback(
  source="statusline_rate_limits",
  parser=_parse_claude_statusline_rate_limits,
  live_error=<statusLine error>,
  fallback_to_usage_registry=True,
)
```

- Fallback should read only `statusline_rate_limits` records.
- Do not fall back to `oauth_usage_get` records in this slice. Mixing source payloads would hide source behavior and reintroduce source stacking.
- If no `statusline_rate_limits` registry record exists, return the live statusLine error as `usage_errors`.

### Out.Of.Scope

- Do not make `/api/oauth/usage` the primary source.
- Do not delete `_account_usage_GET()` in this slice.
- Do not call `_account_usage_GET()` as a fallback from statusLine.
- Do not implement web-cookie/browser usage scraping.
- Do not add new monitor formatting.
- Do not add new runtime abstractions for PTY execution.
- Do not add statusLine cache/throttle machinery.
- Do not remove existing GET-specific tests unless the tested behavior is no longer true after the fallback ownership refactor.

## Execution.Plan

### Slice 1 - Make StatusLine Source Live-Only Compatible

Status: completed.

- Change `_account_usage_statusline(...)` to return the same tuple shape as `_account_usage_GET(...)`.
- Inline the current `_collect_claude_statusline_payload(...)` orchestration into `_account_usage_statusline(...)`.
- Remove active statusLine cache reads/writes from this path.
- Add `cleanup_transcript: bool = False`.
- Keep transcript cleanup best-effort and only when requested.
- Check:
  - direct unit call returns `(limits, (), payload, payload, fresh_metadata)` on mocked capture success
  - direct unit call returns `((), (error,), None, None, None)` on mocked capture failure
  - no statusLine cache file is read or written in the active source path

### Slice 2 - Wire Claude Account Status To StatusLine

Status: completed.

- In `_claude_account_status_impl()`, replace:

```txt
_account_usage_GET(...)
```

with:

```txt
_account_usage_statusline(cleanup_transcript=False)
```

- On usage errors, call `_account_usage_registry_fallback(...)` with:
  - `source="statusline_rate_limits"`
  - `parser=_parse_claude_statusline_rate_limits`
- Ensure usage registry append uses the metadata source.
- Check:
  - `agent.account_status()` success appends `source="statusline_rate_limits"`
  - `record_usage=False` skips append
  - `fallback_to_usage_registry=False` returns the live statusLine error

### Slice 3 - Update Tests Around Source Ownership

Status: completed.

- Update tests that currently expect Claude account status to use GET as the active source.
- Keep GET tests as isolated alternative implementation tests:
  - live GET success
  - GET throttle behavior
  - GET error returns live error
- Add/update statusLine account-status tests:
  - successful statusLine account status populates `limits`
  - usage registry row source is `statusline_rate_limits`
  - registry fallback reads `statusline_rate_limits`
  - no fallback to `oauth_usage_get` for statusLine failures
  - `cleanup_transcript=False` does not call cleanup
  - `cleanup_transcript=True` calls cleanup best-effort

### Slice 4 - Local Validation

Status: completed.

- Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

- Run lint:

```sh
uv run ruff check src/agentos/claude/account_status.py tests/test_agent_account_registry_commands.py
```

- Run real smoke:

```sh
agentos agent accounts monitor --once
```

- Expected smoke result:
  - `claude-code/browser-jp` shows fresh statusLine data
  - no `/api/oauth/usage` 429 fetch error appears for the active source
  - registry receives a new Claude row with `source="statusline_rate_limits"`

### Slice 5 - Installed CLI Refresh

Status: completed.

- If code changes affect the installed `agentos` CLI, refresh the editable tool:

```sh
uv tool install --reinstall --editable .
```

- Re-run:

```sh
agentos agent accounts monitor --once
```

## Impl.Log

- Created from user-directed implementation design after Anthropic `/api/oauth/usage` continued returning `429` despite local throttle behavior.
- Key alignment decisions:
  - `_claude_account_status_impl()` owns registry fallback.
  - `_account_usage_statusline()` is live-source-only.
  - Every `_account_usage_statusline()` call attempts fresh statusLine capture.
  - Caller/workflow controls frequency.
  - No statusLine payload cache in the active path.
  - Transcript cleanup is optional, best-effort, and disabled by default.
- Implemented:
  - Added `CLAUDE_STATUSLINE_USAGE_SOURCE = "statusline_rate_limits"`.
  - Rewired `_claude_account_status_impl()` to call `_account_usage_statusline(cleanup_transcript=False)`.
  - Moved statusLine capture orchestration directly into `_account_usage_statusline(...)`.
  - Removed active statusLine cache helpers and stale-cache fallback behavior.
  - Kept `_account_usage_GET()` as an isolated alternative implementation.
  - Kept registry fallback in `_claude_account_status_impl()`, reading only `statusline_rate_limits` records for statusLine failures.
  - Updated tests so account-status behavior is statusLine-first while GET tests remain isolated.
- Verification:
  - `uv run pytest tests/test_agent_account_registry_commands.py -q` passed with `76 passed`.
  - `uv run ruff check src/agentos/claude/account_status.py tests/test_agent_account_registry_commands.py` passed.
  - `uv tool install --reinstall --editable .` refreshed the installed `agentos` executable.
  - `agentos agent accounts monitor --once` rendered fresh Claude statusLine data for `claude-code/browser-jp` without a GET `429` fetch error.
  - `~/.agentos/agent/usage-registry/202605-usage.jsonl` received a Claude row with `source="statusline_rate_limits"` at `2026-05-16T03:49:28.006837Z`.
