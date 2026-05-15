# Account Status Registry Fallback - impl-req

## Impl.Abstract

- **scope:** replace Claude account-status cache fallback with usage-registry fallback, and expose enough usage freshness metadata for the monitor to show when displayed data was refreshed.
- **status:** implemented.
- **source:** follow-up design alignment after `604-agent-usage-registry-impl-req.md`; user explicitly approved deleting the Claude `~/.agentos/cache/account-status/...` usage cache and using `~/.agentos/agent/usage-registry/YYYYMM-usage.jsonl` as the only prior-observation persistence surface.
- **goal:** simplify the account-status persistence model: successful fresh provider fetches append usage records; failed fresh fetches can optionally reuse the latest matching usage-registry record; the monitor makes fallback age visible.

## Impl.Index

### Current.State.Evidence

- `src/agentos/agent/usage_registry.py` currently owns append-only monthly writes under:

```txt
~/.agentos/agent/usage-registry/YYYYMM-usage.jsonl
```

- Each record has homogeneous metadata plus raw provider payload:
  - `schema_version`
  - `class`
  - `recorded_at`
  - `provider`
  - `account`
  - `home`
  - `source`
  - `payload`
- `src/agentos/claude/account_status.py` still has a separate Claude usage cache path:

```txt
~/.agentos/cache/account-status/<provider>/<account>/oauth_usage_get.json
```

- Claude `_account_usage_GET(...)` currently:
  - reads fresh cache before fetching
  - writes cache after successful provider fetch
  - reads stale cache after provider failure
  - annotates cache payloads with `agentos_cache`
- This duplicates the new registry role and should be removed.

### Target.Model

- The usage registry is the only persisted previous-observation surface for account usage data.
- There is no Claude account-status usage cache after this implementation.
- Fresh successful provider fetch:
  - parse the raw payload into monitor-usable limits
  - append one usage-registry record when `record_usage=True`
  - return fresh account status
- Fresh provider fetch failure:
  - if fallback is enabled, read the latest matching usage-registry record
  - parse that record payload into monitor-usable limits
  - return account status with fallback metadata
  - do not append a new registry record
- If no matching registry record exists, return the original usage error.

### AccountStatus.Contract

- Extend the account-status capability with an explicit fallback option:

```python
agent.account_status(
    record_usage: bool = True,
    fallback_to_usage_registry: bool = True,
) -> AccountStatus
```

- Update `AgentBase`, the `Agent` protocol, `CodexAgent`, and `ClaudeAgent` signatures consistently.
- Claude should use the fallback option immediately.
- Codex may accept the option and pass it through, but Codex fallback behavior can remain out of scope unless it falls out naturally from shared helpers.
- `record_usage=False` must still prevent registry appends.
- `fallback_to_usage_registry=False` must preserve direct provider-failure behavior and not read the registry.

### Registry.Read.API

- Extend `agentos.agent.usage_registry` with a focused latest-record lookup, for example:

```python
latest_usage_record(
    *,
    provider: str,
    account: str,
    home: Path,
    source: str,
) -> Mapping[str, Any] | None
```

- Lookup behavior:
  - read newest monthly registry files first
  - read each file from the end toward the beginning
  - stop at the first record matching `provider`, `account`, resolved `home`, and `source`
  - do not read the whole registry when a recent matching record exists
  - validate only enough structure to safely return a matching record
- The implementation may use a simple reverse-line helper that seeks from the end of a file by chunks. Do not introduce a database or index.

### Freshness.Metadata

- Account status should expose whether usage came from a fresh provider fetch or registry fallback through `AccountStatus.raw`.
- For registry fallback, include metadata like:

```json
"usage_record": {
  "status": "registry_fallback",
  "recorded_at": "...",
  "age_sec": 1234,
  "source": "oauth_usage_get"
}
```

- For fresh provider fetches, include metadata like:

```json
"usage_record": {
  "status": "fresh",
  "recorded_at": null,
  "source": "oauth_usage_get"
}
```

- The normalized `limits` remain the parsed monitor-usable model. The raw provider payload remains in `raw["usage"]`.
- Do not add `agentos_cache` metadata anywhere in the final Claude GET path.

### Monitor.Display

- The monitor should surface refresh timing for data it displays.
- Minimal acceptable first display: add a line under each account only when `raw["usage_record"]` has meaningful freshness metadata.
- Example shape:

```txt
      refreshed | Fri 05-15 15:03 | 12m ago
```

- If the data is fresh in the current account-status call, the monitor may show `refreshed | now`.
- If the data came from registry fallback, the monitor must show the registry record timestamp/age.
- Keep the existing usage/time and reset lines unchanged.

### Removed.Surface

- Delete the Claude usage GET cache machinery:
  - cache path construction under `~/.agentos/cache/account-status/...`
  - cache read helper
  - cache write helper
  - cache metadata helper
  - stale-cache fallback logic
- Remove or rewrite tests that assert cache behavior.
- Do not keep compatibility aliases, transitional cache reads, or dual cache/registry behavior.

### Out.Of.Scope

- Do not migrate existing Claude cache files.
- Do not delete user files from `~/.agentos/cache/account-status/...`; simply stop reading/writing them.
- Do not add a registry query CLI.
- Do not normalize provider payloads.
- Do not change the usage registry append record shape except where needed for read helpers.
- Do not redesign monitor layout beyond the refresh line.

## Execution.Plan

### Slice 1 - Add Registry Latest Lookup

Status: completed.

- Add a latest-record read helper to `src/agentos/agent/usage_registry.py`.
- Implement reverse monthly-file scanning:
  - newest `*-usage.jsonl` file first
  - newest lines first within a file
  - stop at first matching record
- Match by provider, account, resolved home, and source.
- Add focused tests that:
  - append multiple mixed records
  - confirm latest matching record wins
  - confirm different provider/account/home/source records are ignored
  - confirm the reader can find records without requiring a whole-registry load API.

### Slice 2 - Extend AccountStatus Signature

Status: completed.

- Update `AgentBase.account_status(...)` and the `Agent` protocol with `fallback_to_usage_registry: bool = True`.
- Update `CodexAgent.account_status(...)` and `ClaudeAgent.account_status(...)` signatures.
- Update provider-local implementation function signatures.
- Update test doubles that define `account_status(...)`.
- Check that existing callers still work through defaults.

### Slice 3 - Replace Claude Cache With Registry Fallback

Status: completed.

- Remove Claude usage GET cache reads/writes and `agentos_cache` metadata.
- Make `_account_usage_GET(...)` fetch the provider first.
- On successful fetch:
  - parse limits
  - return raw payload as the recordable payload
  - include fresh usage-record metadata for `AccountStatus.raw`
- On provider failure:
  - if `fallback_to_usage_registry=True`, call the latest registry lookup
  - parse the matching record payload
  - return parsed limits with fallback metadata
  - keep the live error in raw metadata so it is inspectable
  - if fallback is disabled or no record exists, return the live usage error
- Add tests for:
  - fresh fetch writes registry and does not write cache
  - provider failure falls back to latest matching registry record
  - provider failure with fallback disabled returns an error
  - provider failure with no matching registry record returns an error
  - `record_usage=False` still skips appends

### Slice 4 - Show Refresh Metadata In Monitor

Status: completed.

- Extend the limits-tracking workflow/frame output to render refresh metadata from `AccountStatus.raw["usage_record"]`.
- Keep the existing account block format and usage/reset rows unchanged.
- Add focused tests for plain output showing refresh metadata for:
  - fresh data
  - registry fallback data
- Avoid changing Rich bar rendering unless needed to display the new text row.

### Slice 5 - Validation

Status: completed.

- Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

- Run full suite if practical:

```sh
uv run pytest -q
```

- Run lint on touched files:

```sh
uv run ruff check src/agentos/agent src/agentos/claude src/agentos/codex tests/test_agent_account_registry_commands.py
```

- Refresh installed CLI:

```sh
uv tool install --reinstall --editable .
```

- Manual smoke:

```sh
agentos agent accounts monitor --once
```

- Verify no new Claude cache writes occur under:

```txt
~/.agentos/cache/account-status/
```

## Impl.Log

- 2026-05-15: Drafted from design alignment. Core correction: remove the Claude account-status cache completely and use the usage registry as the only fallback source for previous successful usage observations.
- 2026-05-15: Implemented. Added reverse JSONL lookup for latest matching usage records; extended `account_status(...)` with `fallback_to_usage_registry`; removed Claude usage GET cache reads/writes/metadata; wired Claude provider failure to registry fallback; exposed `raw["usage_record"]`; added monitor refreshed lines; validated with focused tests, full test suite, lint, CLI reinstall, and monitor smoke.
