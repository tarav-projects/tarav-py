# Claude Usage GET Throttle Cache - impl-req

## Impl.Abstract

- **scope:** add a Claude-specific throttle cache under `_account_usage_GET` so `GET /api/oauth/usage` respects provider `Retry-After` windows and stops hammering the endpoint after HTTP 429.
- **status:** implemented.
- **source:** follow-up from monitor/account-status work. A direct local call to Claude usage GET returned `HTTP 429` with `Retry-After: 2852`, meaning the provider explicitly requested a roughly 47 minute wait.
- **goal:** keep the usage registry as the durable successful-observation system, while adding a separate implementation-specific throttle state for Claude usage fetching errors.

## Impl.Index

### Current.State.Evidence

- Claude account usage currently flows through `src/agentos/claude/account_status.py`.
- `ClaudeAgent.account_status()` calls `_claude_account_status_impl(...)`.
- `_claude_account_status_impl(...)` calls `_account_usage_GET(...)`.
- `_account_usage_GET(...)` now:
  - checks the Claude usage GET throttle file before live fetch
  - skips provider fetch while an active `Retry-After` window is present
  - calls `_fetch_claude_usage_payload(agent)` when no active throttle exists
  - on success parses limits and returns fresh usage metadata
  - on `AccountStatusError` falls back to `latest_usage_record(...)`
- `_fetch_claude_usage_payload(...)` catches `urllib.error.HTTPError`, calls `_read_http_error_detail(...)`, and raises `AccountStatusError(error_type="usage_api_http_error", message="claude usage API returned HTTP <status>", detail=detail, exit_code=<status>)`.
- `_read_http_error_detail(...)` captures HTTP status/body and normalizes integer `Retry-After` for HTTP 429 into `retry_after_sec` plus `retry_after_until`.
- Registry fallback metadata already carries the live error through `raw["usage_record"]["live_error"]`.
- Monitor rendering already displays fallback live errors as:

```txt
          fetch error       | claude usage API returned HTTP 429
```

### Boundary.Decision

- This is not a usage registry feature.
- This is not a general `account_status` cache.
- This is a Claude `_account_usage_GET` implementation detail for one specific source:

```txt
source = oauth_usage_get
```

- The usage registry remains the durable record of successful usage observations.
- The throttle cache stores only provider retry/backoff state. It must not store usage payloads.
- The throttle cache is safe to delete at any time.

### Throttle.Cache.Shape

- Store Claude usage GET throttle state under the Agentos cache tree, separate from the registry:

```txt
~/.agentos/cache/account-status/claude-code/<account>/oauth_usage_get-throttle.json
```

- The file should contain only throttle metadata, for example:

```json
{
  "schema_version": 1,
  "provider": "claude-code",
  "account": "browser-jp",
  "source": "oauth_usage_get",
  "reason": "http_429",
  "captured_at": "2026-05-15T18:02:00Z",
  "retry_after_sec": 2852,
  "retry_after_until": "2026-05-15T18:49:32Z",
  "live_error": {
    "type": "usage_api_http_error",
    "message": "claude usage API returned HTTP 429",
    "exit_code": 429,
    "detail": {
      "status": 429,
      "retry_after_sec": 2852,
      "retry_after_until": "2026-05-15T18:49:32Z"
    }
  }
}
```

- Do not store `payload`, `five_hour`, `seven_day`, or any usage-limit data in this cache.

### Runtime.Behavior

- Before calling `_fetch_claude_usage_payload(...)`, `_account_usage_GET(...)` should check for an active Claude usage GET throttle.
- If throttle exists and `retry_after_until` is in the future:
  - do not call the provider
  - synthesize or reuse an `AccountStatusError` representing the active throttle
  - fall back to `latest_usage_record(...)`
  - return `usage_status="ok"` when registry fallback succeeds
  - include throttle detail in `raw["usage_record"]["live_error"]`
- If throttle is expired, ignore it and attempt a live provider fetch.
- On successful live provider fetch:
  - clear the throttle file if present
  - return fresh usage metadata
  - allow the normal usage registry append path to record the successful payload
- On live HTTP 429 with `Retry-After`:
  - parse the header
  - write/update throttle cache
  - then use registry fallback
- On live HTTP 429 without a valid `Retry-After`:
  - do not invent a long persistent throttle unless implementation chooses a very small defensive local default
  - still return the live error through the existing fallback path
- Other errors such as timeout or invalid output should not write the 429 throttle cache.

### Header.Capture

- `_read_http_error_detail(...)` should capture enough HTTP headers for retry behavior.
- At minimum, parse:
  - `Retry-After`
- Store normalized fields in `AccountStatusError.detail`:

```json
{
  "status": 429,
  "retry_after_sec": 2852,
  "retry_after_until": "..."
}
```

- Preserve existing body capture behavior.
- The monitor can keep rendering the primary error message for now. Rendering retry timing is allowed if it falls out cleanly, but the core required behavior is to stop repeat live calls during the retry window.

### No.Legacy.Allowed

- Do not reintroduce the old Claude usage payload cache.
- Do not read or write `oauth_usage_get.json` usage payload caches.
- Do not keep dual behavior that caches usage data and registry data.
- Do not move this into a provider-agnostic account-status cache.

## Execution.Plan

### Slice 1 - Capture Retry-After In HTTP Errors

Status: completed.

- Update `_read_http_error_detail(...)` in `src/agentos/claude/account_status.py`.
- Parse valid integer `Retry-After` seconds from HTTP 429 responses.
- Add `retry_after_sec` and `retry_after_until` to the error detail.
- Preserve existing status/body detail behavior.
- Add focused tests for detail parsing from a fake `HTTPError`.

### Slice 2 - Add Claude Usage GET Throttle Helpers

Status: completed.

- Add helper functions local to `src/agentos/claude/account_status.py`:
  - `_claude_usage_get_throttle_path(agent)`
  - `_load_claude_usage_get_throttle(agent)`
  - `_write_claude_usage_get_throttle(agent, error)`
  - `_clear_claude_usage_get_throttle(agent)`
- Keep them scoped to `CLAUDE_USAGE_GET_SOURCE`.
- Ensure throttle files contain no usage payload data.
- Add tests for path, write/read, expired throttle ignored, and clear-on-success behavior.

### Slice 3 - Wire Throttle Into `_account_usage_GET`

Status: completed.

- Before live fetch, check active throttle.
- If active, skip `_fetch_claude_usage_payload(...)` and call `_account_usage_registry_fallback(...)` with a throttle live error.
- On live HTTP 429 with valid retry detail, write throttle and then registry-fallback.
- On live success, clear throttle and return fresh payload.
- Do not affect Codex account status or statusline fallback behavior.
- Add tests proving:
  - active throttle prevents provider fetch
  - active throttle plus registry record returns limits and `usage_status`-compatible fallback metadata
  - 429 writes throttle
  - live success clears throttle
  - non-429 errors do not write throttle

### Slice 4 - Preserve Monitor Behavior

Status: completed.

- Confirm monitor still renders fallback usage rows and a `fetch error` row.
- If retry detail is present and easy to include, append concise retry timing to the fetch error line, for example:

```txt
          fetch error       | claude usage API returned HTTP 429 | retry in 47m
```

- If adding retry text would complicate the renderer or tests, leave rendering unchanged and keep retry metadata available in raw JSON.
- Add or update focused tests only for behavior implemented in this slice.

### Slice 5 - Validation

Status: completed.

- Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

- Run full suite:

```sh
uv run pytest -q
```

- Run lint on touched files:

```sh
uv run ruff check src/agentos/claude src/agentos/agent/monitor tests/test_agent_account_registry_commands.py
```

- Run whitespace check:

```sh
git diff --check
```

- Refresh installed CLI if account-status or monitor CLI behavior changed:

```sh
uv tool install --reinstall --editable .
```

- Manual smoke:

```sh
agentos agent accounts monitor --once
```

- Verify no usage payload cache is written:

```txt
~/.agentos/cache/account-status/claude-code/<account>/oauth_usage_get.json
```

## Impl.Log

- 2026-05-15: Drafted from alignment after observing Claude `GET /api/oauth/usage` return `HTTP 429` with `Retry-After: 2852`. Design keeps the throttle cache under `_account_usage_GET` and explicitly separate from the usage registry.
- 2026-05-15: Implemented Claude GET throttle cache in `src/agentos/claude/account_status.py`. `_account_usage_GET(...)` now skips live provider calls during active retry windows, writes metadata-only `oauth_usage_get-throttle.json` on HTTP 429 with valid `Retry-After`, clears expired/successful throttles, and keeps usage data exclusively in the usage registry.
- 2026-05-15: Added focused tests for Retry-After parsing, metadata-only throttle files, active-throttle provider skipping, 429 throttle writes, success clearing, and non-429 no-write behavior in `tests/test_agent_account_registry_commands.py`.
- 2026-05-15: Validation passed: `uv run pytest tests/test_agent_account_registry_commands.py -q` (`67 passed`), `uv run pytest -q` (`345 passed`), `uv run ruff check src/agentos/claude src/agentos/agent/monitor tests/test_agent_account_registry_commands.py`, `git diff --check`, `uv tool install --reinstall --editable .`, and `agentos agent accounts monitor --once`. Removed a stale local `oauth_usage_get.json` payload cache and verified it was not recreated.
