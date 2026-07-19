# Usage-report normalization pipeline - impl-req

## Impl.Abstract

- **Scope:** add `agentos agent accounts usage-report`, a hook-facing command that accepts a full provider hook context on stdin, can sample bounded raw hook contexts into a private development log, normalizes any usage-limit facts Agentos understands, and appends a safe usage registry record for the account monitor to read.
- **Status:** partially implemented; Slices 1-2 complete.
- **Source context:** current chat design: provider hooks should stay dumb and pipe the full hook context object; Agentos owns extraction, account resolution, validation, throttling, registry append, and initial evidence capture. Index grounding: `Normalization.Pipeline::Account.Usage.Model` already models native usage artifacts -> `Account.Usage.Status`.
- **Current state:** `src/agentos/agent/usage_registry.py` already appends and reads provider/account/home/source keyed JSONL records. Provider `account_status` paths opportunistically write live usage records, and the monitor limits workflow primes/refreshes from the registry. There is no direct hook-facing writer CLI, no raw hook-context sample log, and monitor source selection currently assumes one exact source per provider.
- **Out of scope:** installing or mutating provider hook configuration in `~/.codex`, `~/.claude`, or any home; persisting raw hook contexts by default; introducing a general session-token telemetry store; changing auth capture/materialization behavior.

## Impl.Index

### Hook.Input.Boundary

- provider hooks call one stable command and pass the full hook context through stdin; hook scripts do not parse provider JSON.
- `usage-report` treats the hook context as `Raw.Source`; only provider/source `Raw.Normalizer`s inspect native hook shape.
- raw hook context is not persisted by default because hook payloads may contain prompts, paths, tool arguments, or future secrets.
- raw hook context sampling is an explicit development mode, separate from the usage registry, used to discover provider hook shapes before implementing normalizers.

### Hook.Context.Sample.Log

- add a private bounded auxiliary log for raw hook-context samples, not a usage registry and not a monitor log.
- default path: `~/.agentos/agent/usage-report-hook-samples/YYYYMMDD.jsonl`.
- records are envelope-wrapped with `recorded_at`, `provider`, `home`, optional `account`, sample reason/status, and `raw_context`.
- files must be written mode `0600`; assume samples may contain sensitive prompt, path, tool, environment-adjacent, or provider internals.
- retention is bounded, initially last 50 samples, preferably per provider/home to preserve useful local diversity without unbounded raw accumulation.
- production hooks can omit sampling after normalizers are stable; sampling exists to build fixture evidence, not as a permanent telemetry dependency.

### Usage.Source.Model

- add provider-qualified hook sources, not overloaded live-fetch sources: `codex_hook_context`, `claude_hook_context`, and future `copilot_hook_context`.
- hook-source registry payloads should be assembled `Account.Usage.Status` snapshots, minimally `{limits: [AccountLimit.summary(), ...], metadata: {...}}`.
- existing live-fetch sources remain unchanged: `app_server`, `statusline_rate_limits`, `copilot_internal_user`.
- a hook context that carries no recognized usage-limit facts is a successful no-op, not an error and not an empty/zero usage record.

### Account.Resolution

- `--provider` and `--home` are required for the first version; `--account` is optional.
- when `--account` is supplied, validate it against `auth_registry.account_exists(provider, account)`.
- when `--account` is omitted, infer it from the home auth identity using existing auth-method readers plus `auth_registry.resolve_account_by_identity`.
- unresolved identity yields no-op by default in quiet hook mode; `--json` reports the reason.

### Registry.Read.Path

- monitor/fallback readers must be able to read hook-source records; writing a new source without a reader path is incomplete.
- add a source parser for hook payloads that reconstructs `AccountLimit` objects from stored summaries.
- update limits-tracking source resolution from one source per provider to provider-specific source priority, preferring freshest valid records across supported sources or a documented priority rule.
- keep invalid registry payloads non-fatal: skip invalid candidate records or report the existing registry-payload error without breaking monitor operation.

### Throttle.Semantics

- `--min-interval-sec` checks the latest matching provider/account/home/source record before appending.
- throttled reports are no-ops with exit 0; `--json` reports `status: "throttled"` and the previous record age.
- default hook mode should be quiet and robust; validation failures should be visible under `--json` and stderr, but provider hooks should not be noisy on ordinary no-usage contexts.

## Execution.Plan

### Slice 1 - raw hook-context sample log

- Add `src/agentos/agent/usage_report.py` with a small public function such as `report_usage_from_hook_context(...)`.
- Implement the raw sample writer in the same module or a small companion module, with path creation, mode `0600`, JSONL append, and retention trimming.
- Inputs: provider, home, optional account, raw JSON object, max sample count, and sampling enabled/disabled.
- Outputs: a typed result or dict that includes sample path/count only when sampling happened.
- RED: tests prove samples are written outside the usage registry, file mode is private, retention trims to the configured maximum, and the full raw context is present only in the sample log.
- GREEN: implement with no provider command/network calls.
- Check: `uv run pytest tests/test_agent_usage_report.py`
- Status: complete.

### Slice 2 - accounts CLI sampling command

- Register `agentos agent accounts usage-report` in `src/agentos/agent/commands/accounts.py` with sampling support before any normalizer is required.
- CLI shape: `--provider`, `--home`, optional `--account`, optional `--source`, `--payload-stdin`, `--min-interval-sec`, `--sample-raw-context`, `--sample-max-records`, `--json`, `--quiet`.
- `--payload-stdin` reads one JSON object from stdin; reject arrays/scalars as invalid payload.
- with `--sample-raw-context`, the command writes the raw sample even when no usage facts are recognized.
- Text output should be one short line unless `--quiet`; JSON output should include command, status, provider, account if resolved, home, source, sample status/path when applicable, and written usage path if appended.
- RED: command tests cover sample append, sample retention, invalid JSON, account validation, and quiet no-op behavior.
- GREEN: implement without changing existing account lifecycle commands.
- Check: `uv run pytest tests/test_agent_accounts_usage_report_command.py`
- Status: complete.

### Slice 3 - provider hook evidence collection

- Wire local Codex and Claude hook scripts/configuration only after the sampling command exists and can be safely invoked with `--quiet`.
- Command template: `agentos agent accounts usage-report --provider <provider> --home "$HOME_VAR" --payload-stdin --sample-raw-context --sample-max-records 50 --quiet`.
- Do not implement parsing in the hook scripts; they only pipe the provider hook context.
- Collect enough local samples to identify real context shapes before writing source-specific normalizers.
- Check: invoke hooks manually or through provider sessions, then inspect `~/.agentos/agent/usage-report-hook-samples/` for bounded sample records.

### Slice 4 - hook-context normalizers from samples

- Implement `Raw.Normalizer`s only against observed sample fixtures checked into tests or built as minimized test fixtures from the sample log.
- Codex first if samples contain recognizable `rateLimits`/`tokenUsage` shapes equivalent to the current app-server payload; normalize through `codex_usage_record_limits`, and persist AccountLimit summaries.
- Claude second if samples contain a fixtureable statusline/rate-limit shape; otherwise keep Claude as sampled/no-usage and record the gap.
- Do not persist the full hook object in the usage registry; keep only safe metadata such as hook event name, provider source name, and optional session id when present.
- RED: fixture with extra prompt/tool fields proves those fields do not appear in the registry record.
- GREEN: normalized limits round-trip through the hook-source parser.
- Check: `uv run pytest tests/test_agent_usage_report.py tests/test_codex_usage_records.py`

### Slice 5 - monitor and fallback reader integration

- Add a hook-source parser in the monitor/account-usage read path that converts persisted AccountLimit summaries back to `AccountLimit`.
- Replace single-source lookup where needed with provider source candidates, including hook sources.
- Preserve existing behavior for live-fetch sources and existing registry files.
- RED: a limits-tracking target with only a hook-source registry record primes to `ok` and renders the expected limit row.
- GREEN: implement with explicit source priority/freshness behavior documented in tests.
- Check: `uv run pytest tests/test_agent_monitor_limits_tracking.py tests/test_codex_usage_records.py`

### Slice 6 - docs and installed CLI verification

- Update `AGENTS.md` because it documents Agentos logging/registry surfaces and currently omits both the usage registry and the new private hook-sample log.
- Run focused tests, then ruff on touched files.
- If CLI registration behavior is tested through the installed `agentos` executable, refresh `agentos-cli` per local guidance after code changes; otherwise direct package tests are enough for this slice.
- Check: `uv run pytest tests/test_agent_usage_report.py tests/test_agent_accounts_usage_report_command.py tests/test_agent_monitor_limits_tracking.py tests/test_codex_usage_records.py` and `uv run ruff check src/ tests/`

## Acceptance.Signals

- provider hook scripts can call `agentos agent accounts usage-report ... --payload-stdin --quiet` without embedding parsing logic.
- raw hook-context samples can be collected in a private bounded auxiliary log before normalizers exist.
- hook-source records are visible to the monitor limits workflow.
- the registry stores normalized usage facts and safe metadata, not raw hook contexts.
- no-usage and throttled hook calls exit successfully without writing records.
- existing live-fetch usage registry behavior remains unchanged.
- tests cover sample retention, append, throttle, account resolution, no-usage, invalid JSON, and monitor priming from hook records.

## Deviation.Triggers

- stop if implementation requires persisting raw hook context by default.
- stop if raw sample logging cannot be made bounded and private.
- stop if hook payloads only contain session token counts and no account-limit facts; that is a different normal model from the current monitor-consumed usage registry.
- stop if account inference needs provider network calls; hook reporting must stay cheap and local.
- stop if monitor support requires treating `Context.Hook` as the design concept; provider lifecycle hook context should remain a separate raw-source concept.

## Impl.Log

- 2026-07-18: Impl.Req created in `Alignment.Mode::Interactive` from the current design discussion. No Anchory anchors were minted in this pass; no fake citations were added.
- 2026-07-18: Updated design after user feedback: start with bounded raw hook-context sampling because provider hook object shapes are unknown; use collected samples as fixture evidence for later normalizers.
- 2026-07-18: Execution checkpoint commit `973f526` created after explicit user authorization to "commit ALL". Slice 1 implemented: `src/agentos/agent/usage_report.py` now writes private dated hook-context sample logs with per provider/account/home retention; `tests/test_agent_usage_report.py` covers path, mode `0600`, retention, registry separation, and unserializable payload rejection. `AGENTS.md` updated to document the usage registry and hook sample log.
- 2026-07-18: Slice 2 implemented: `agentos agent accounts usage-report` now accepts hook JSON from stdin and can write raw samples through `--sample-raw-context`; normal usage extraction still returns `no_usage` until the normalizer slice. Installed `agentos` refreshed via `agentos-cli` and smoke-tested. Claude `Stop` hook sample script wrote a sample record to `~/.agentos/agent/usage-report-hook-samples/20260718.jsonl`.
