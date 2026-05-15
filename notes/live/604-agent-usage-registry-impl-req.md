# Agent Usage Registry - impl-req

## Impl.Abstract

- **scope:** implement the first minimal `Agentos.Agent` usage registry: an append-only monthly JSONL record of successful usage-limit fetches performed by provider `agent.account_status(...)` capabilities.
- **status:** implemented.
- **source:** design alignment from the account monitor / account status workstream, after deciding that usage history is not a cache and should be its own Agentos subsystem.
- **goal:** preserve successful provider usage-limit observations in a stable Agentos-owned registry so the monitor and future subsystems can build historical behavior without recreating the deprecated stats database shape.

## Impl.Index

### Registry.Boundary

- The usage registry is not an account-status cache.
- It is a stable Agentos subsystem owned by `Agentos.Agent`.
- Path:

```txt
~/.agentos/agent/usage-registry/
  YYYYMM-usage.jsonl
```

- The monthly file name is derived from the record timestamp. Example: `202605-usage.jsonl`.
- There is no per-provider or per-account folder in the first implementation.
- There is no `latest.json` in the first implementation.
- The registry is append-only. Query/index/read APIs are out of scope for this slice.

### Record.Shape

- Each JSONL line is one successful usage-limit observation.
- Metadata is homogeneous across providers.
- Payload is intentionally raw/flexible and provider-owned.
- Minimal envelope:

```json
{
  "schema_version": 1,
  "class": "agentos.agent.usage-record",
  "recorded_at": "2026-05-15T18:52:00Z",
  "provider": "claude-code",
  "account": "browser-jp",
  "home": "/Users/pereiro/.agentos/agent/homes/claude-code/browser-jp",
  "source": "oauth_usage_get",
  "payload": {}
}
```

- Required metadata:
  - `schema_version`
  - `class`
  - `recorded_at`
  - `provider`
  - `account`
  - `home`
  - `source`
  - `payload`
- `payload` should contain the provider/status payload used to build the monitor-visible usage limits. Do not normalize it in this implementation.

### Successful.Usage.Fetch

- A successful usage fetch means the provider capability has actual usage-limit data: the data used by the monitor to render usage/time and reset lines.
- Append records only when that data exists.
- Do not append for:
  - provider setup errors
  - unavailable usage
  - usage fetch errors
  - stale fallback payloads
  - cache hits that avoid a provider fetch
  - monitor render ticks
  - account status calls that do not fetch fresh usage-limit data

### AccountStatus.Contract

- `agent.account_status()` becomes the write boundary for usage records.
- Add an opt-out flag:

```python
agent.account_status(record_usage: bool = True) -> AccountStatus
```

- When `record_usage=True`, provider implementations append a usage record before returning, but only after a successful fresh usage-limit fetch.
- When `record_usage=False`, provider implementations must produce the same `AccountStatus` result without writing to the usage registry.
- Update the base `AgentBase` method, the `Agent` protocol, and provider implementations consistently.

### Registry.API

- Add a provider-neutral registry module under `agentos.agent`, for example:

```python
append_usage_record(
    *,
    provider: str,
    account: str,
    home: Path,
    source: str,
    payload: Mapping[str, Any],
) -> Path
```

- The registry API owns:
  - resolving `agentos_home_dir() / "agent" / "usage-registry"`
  - creating the directory
  - creating the UTC timestamp
  - selecting `YYYYMM-usage.jsonl`
  - writing compact JSON plus trailing newline
  - returning the written file path
  - minimal metadata validation
- Providers own:
  - deciding whether fresh usage-limit data exists
  - choosing `source`
  - passing the raw payload
  - honoring `record_usage`

### Provider.Integration

- Codex:
  - Existing successful usage source: app-server `account/rateLimits/read`.
  - Source label: `app_server`.
  - Payload should be the raw rate-limit result payload returned by `_fetch_account_usage_app_server_payload(...)`.
  - Append only after the payload parses into monitor-usable limits.
- Claude Code:
  - Existing successful usage source: OAuth usage GET.
  - Source label: `oauth_usage_get`.
  - Payload should be the raw usage API payload returned by the provider fetch path.
  - Do not append when returning an existing cached/stale payload. The registry records successful fetch observations, not reuse.

### Out.Of.Scope

- Do not rebuild the deprecated `~/.agentos/agent-account-stats` database.
- Do not migrate archived deprecated stats records.
- Do not add registry read/query commands.
- Do not add aggregation, latest derivation, summaries, or retention policies.
- Do not normalize provider payloads beyond the homogeneous record metadata envelope.
- Do not make the monitor write records directly. The monitor should keep calling `agent.account_status(...)`.

## Execution.Plan

### Slice 1 - Add Usage Registry Module

Status: completed.

- Add a small module under `src/agentos/agent/` for usage registry writes.
- Implement `append_usage_record(...)`.
- Use UTC timestamps and monthly `YYYYMM-usage.jsonl` file selection.
- Keep payload flexible but JSON-serializable.
- Add focused unit tests that:
  - patch the Agentos home directory to a temp location
  - append one record
  - assert the monthly file path
  - assert homogeneous metadata exists
  - assert payload is preserved raw

### Slice 2 - Extend AccountStatus Capability Signature

Status: completed.

- Update `AgentBase.account_status(...)` and the `Agent` protocol to accept `record_usage: bool = True`.
- Update `CodexAgent.account_status(...)` and `ClaudeAgent.account_status(...)` signatures.
- Pass the flag into provider-local implementation functions.
- Update test doubles and monitor tests that define `account_status` stubs.
- Check:
  - existing tests still pass with default behavior
  - tests can call `account_status(record_usage=False)`

### Slice 3 - Record Codex Successful Fetches

Status: completed.

- Thread the raw app-server rate-limit payload through the Codex account-status path.
- Append a registry record only when:
  - setup/check status permits usage fetch
  - app-server fetch succeeds
  - parser produces monitor-usable usage limits
  - `record_usage=True`
- Use source `app_server`.
- Do not append on errors or unavailable usage.
- Add focused tests around the Codex provider path with a fake payload and temp registry.

### Slice 4 - Record Claude Successful Fetches

Status: completed.

- Thread the raw OAuth usage GET payload through the Claude account-status path.
- Append a registry record only when:
  - setup/check status permits usage fetch
  - OAuth usage GET performs a fresh successful provider fetch
  - parser produces monitor-usable usage limits
  - `record_usage=True`
- Use source `oauth_usage_get`.
- Do not append when returning fresh cache or stale fallback payloads.
- Add focused tests for:
  - fresh successful fetch writes a record
  - `record_usage=False` does not write
  - cached/stale fallback paths do not write

### Slice 5 - Validation

Status: completed.

- Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

- Run the full suite if practical:

```sh
uv run pytest -q
```

- Run lint on touched files:

```sh
uv run ruff check src/agentos/agent src/agentos/codex src/agentos/claude tests/test_agent_account_registry_commands.py
```

- Refresh installed CLI after implementation:

```sh
uv tool install --reinstall --editable .
```

- Manual smoke:

```sh
agentos agent accounts monitor --once
ls ~/.agentos/agent/usage-registry
tail -n 5 ~/.agentos/agent/usage-registry/$(date -u +%Y%m)-usage.jsonl
```

## Impl.Log

- 2026-05-15: Drafted from design alignment. Key correction: usage history is a registry subsystem, not a cache. The first implementation writes successful fresh usage-limit fetches from `agent.account_status(...)` into one monthly append-only JSONL file under `~/.agentos/agent/usage-registry/`.
- 2026-05-15: Implemented the minimal usage registry. Added `agentos.agent.usage_registry.append_usage_record(...)`, extended provider `account_status(record_usage=True)` signatures, wired Codex app-server and Claude OAuth usage GET successful fresh fetches into the registry, and added focused tests for metadata, raw payload preservation, opt-out behavior, error/no-write behavior, and Claude cache/no-write behavior.
- 2026-05-15: Validation completed: `uv run pytest tests/test_agent_account_registry_commands.py -q`, `uv run pytest -q`, `uv run ruff check src/agentos/agent src/agentos/codex src/agentos/claude tests/test_agent_account_registry_commands.py`, `git diff --check`, `uv tool install --reinstall --editable .`, `agentos agent accounts monitor --once`, and registry inspection under `~/.agentos/agent/usage-registry/202605-usage.jsonl`.
