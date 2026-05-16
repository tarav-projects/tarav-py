# Usage Registry Archive Migration - impl-req

## Impl.Abstract

- **scope:** create a transient live-script migration that converts archived legacy account usage stats into current-standard Agentos usage-registry JSONL records, validates the complete generated registry, and then updates the active registry only after a clean dry-run.
- **status:** implemented and executed.
- **source:** follow-up to `604-agent-usage-registry-impl-req.md` and `606-account-status-registry-fallback-impl-req.md`; user explicitly selected a temporary live-script migration flow, not a permanent CLI command, and explicitly required that archive data must never be deleted.
- **goal:** migrate historical successful account-usage observations into `~/.agentos/agent/usage-registry/YYYYMM-usage.jsonl` using current registry standards, without carrying legacy stats shape forward and without risking archived source data.

## Impl.Index

### Migration.Boundary

- This is a transient migration tool.
- Do not add a permanent `agentos` command.
- Add a live script under:

```txt
dev/live/NNN-migrate-agent-usage-registry.py
```

- Allocate the live-script prefix with:

```sh
agentos stdlib prefix next --project-base agentos-py --target dev/live
```

- The script is allowed to know the legacy archive shapes.
- Runtime provider code, monitor code, and registry read/write APIs must not gain legacy stats knowledge.
- No runtime fallback to old stats archives is allowed.

### Archive.Safety.Invariant

- Archive data is read-only evidence.
- The migration script must never delete, move, rewrite, truncate, compact, clean up, or otherwise mutate anything under:

```txt
~/.agentos/archive/
```

- The script must open archive inputs for reading only.
- Archive cleanup is explicitly out of scope.
- Any future desire to delete/archive-prune must be a separate explicit operation, never a side effect of this migration.

### Source.Archives

- Process all migration inputs from archives, including the archived snapshot of the current registry.
- Do not use the active registry as an input source for conversion/dedupe.
- Current known inputs:

```txt
~/.agentos/archive/20260516T011731Z/raw/
  history/segments/202603.jsonl
  history/segments/202604.jsonl
  history/segments/202605.jsonl
  history/tape.json
  latest.json

~/.agentos/archive/20260516T012119Z/raw/archive/20260515T183834Z/raw/
  history/segments/202605.jsonl
  history/tape.json
  latest.json

~/.agentos/archive/20260516T022536Z/raw/agent-usage-registry/
  202605-usage.jsonl
```

- Treat the archived usage registry as the baseline registry state.
- Treat the two legacy stats archives as conversion sources.
- The active target remains:

```txt
~/.agentos/agent/usage-registry/
```

### Current.Registry.Standard

- Generated rows must be normal usage-registry rows:

```json
{
  "schema_version": 1,
  "class": "agentos.agent.usage-record",
  "recorded_at": "2026-05-10T13:26:42Z",
  "provider": "codex",
  "account": "jp",
  "home": "/Users/pereiro/.agentos/agent/homes/codex/jp",
  "source": "app_server",
  "payload": {}
}
```

- Required fields:
  - `schema_version`
  - `class`
  - `recorded_at`
  - `provider`
  - `account`
  - `home`
  - `source`
  - `payload`
- Do not nest old stats account records wholesale.
- Do not preserve old monitor summaries, labels, command metadata, counters, or history wrappers in the registry payload.
- Preserve provider usage-limit payloads in the current registry envelope.

### Legacy.Account.Mapping

- Use an explicit mapping table. Do not infer accounts from labels, emails, homes, or provider summaries.
- Initial mapping:

```txt
codex/codex-jp        -> codex / jp         / ~/.agentos/agent/homes/codex/jp
codex/codex-mm        -> codex / mm         / ~/.agentos/agent/homes/codex/mm
codex/codex-tk        -> codex / tk         / ~/.agentos/agent/homes/codex/tk
codex/codex-br        -> codex / br         / ~/.agentos/agent/homes/codex/br
claude-code/claude-main -> claude-code / browser-jp / ~/.agentos/agent/homes/claude-code/browser-jp
```

- Skip unmapped Copilot observations for this migration unless the mapping is explicitly extended:

```txt
codex/codex-main
copilot-cli/copilot-main
copilot/copilot-main
```

- If a successful usage observation is not mapped and is not explicitly skipped, dry-run must fail and print the offending entry context.
- Known legacy wrinkle: `codex/codex-main` has a small number of successful old observations. The first dry-run loop proved that mapping it to `codex/jp` causes timestamp conflicts with `codex-jp`, so it is explicitly skipped as ambiguous legacy singleton data.

### Legacy.Payload.Mapping

- Import only successful usage observations:

```txt
providers[].accounts[] where usage_status == "ok"
```

- For Codex:
  - legacy `usage_source`: `app-server`
  - current `source`: `app_server`
  - current `payload`: `provider_status.rate_limits`
  - validate payload contains `rateLimits` and `rateLimitsByLimitId`
- For Claude Code:
  - legacy `usage_source`: `interactive-statusline` or `live-refresh`
  - current `source`: `statusline_rate_limits`
  - current `payload`: a current-standard raw statusline-rate-limit payload built by stacked adapters for stale Claude formats
  - adapter 1: `provider_status.live_usage_refresh.statusline.rate_limits`
  - adapter 2: `usage.limits` for early `live-refresh` rows that only expose rate-limit data there
  - validate payload contains at least one usable `five_hour` or `seven_day` limit with utilization and reset time
- Do not label historical Claude statusline observations as `oauth_usage_get`.
- Do not import unavailable, empty, or error observations.
- Do not import incomplete successful Claude observations that have reset timing but no utilization percentage; count them as incomplete skips.

### Dry.Run.Development.Loop

- The script is developed through repeated dry-runs.
- Dry-run must execute the full conversion and validation pipeline without writing the active registry.
- On each candidate old entry:
  - parse the source JSONL record
  - select successful usage observations
  - map provider/account/home/source
  - build the exact new registry row
  - validate the row against current registry standards
  - validate provider-specific payload shape
  - check duplicate identity
- If anything fails, stop and report the concrete offending entry:
  - archive path
  - line number
  - snapshot `recorded_at`
  - legacy provider/account id
  - legacy `usage_status`
  - legacy `usage_source`
  - reason
  - compact JSON excerpt of the problematic observation
- Then patch the script mapping/parser and repeat until all intended archive data is parsable.

### Duplicate.Policy

- The migration must detect duplicates before writing.
- Dedupe must cover:
  - generated rows from all legacy archives
  - baseline rows from the archived active registry snapshot
  - duplicate observations within the same archive
- Use a deterministic identity, for example:

```txt
provider + account + home + source + recorded_at + canonical payload hash
```

- Exact duplicates should be counted and skipped.
- Conflicting duplicates with the same identity but different payload must fail dry-run and print both entries.
- Do not append duplicate rows to the active registry.

### Staged.Registry.Rebuild

- Do not append old historical May records after newer May rows.
- `latest_usage_record(...)` scans monthly files newest-line-first; appending older records at the end would make stale records appear newer.
- The real run must build a complete staged registry from:
  - archived active-registry baseline rows
  - converted legacy stats rows
- Group rows by `recorded_at` month.
- Sort each monthly file by `recorded_at` ascending, with deterministic tie-breakers.
- Write the staged output to a temporary migration workspace first.
- Validate staged JSONL files before touching the active target.
- Only after validation may the active target be updated from staged files.

### Active.Target.Safety

- The active registry path is:

```txt
~/.agentos/agent/usage-registry/
```

- Before replacing any active monthly file, compare the active file against the archived active-registry baseline for that same file.
- If the active file has changed since the archive snapshot, abort and ask for a new archive snapshot or explicit realignment.
- This prevents losing records written after the safety archive was captured.
- Do not update the active registry partially. If replacement is needed, prepare all files first, validate all files, then replace touched month files as one controlled final step.

### Reporting

- Dry-run report must include:
  - archives scanned
  - source files scanned
  - source lines scanned
  - successful observations selected
  - rows generated
  - exact duplicates skipped
  - explicitly skipped accounts
  - unmapped entries
  - conflicts
  - monthly files that would be written
  - per provider/account counts
- Real-run report must include:
  - staged directory
  - active files replaced
  - final row counts per monthly file
  - validation result

### Out.Of.Scope

- Do not delete archive data.
- Do not mutate archive data.
- Do not add a permanent CLI command.
- Do not add runtime legacy readers.
- Do not migrate Copilot unless the user explicitly provides a current account mapping.
- Do not normalize usage history into summaries, aggregates, latest files, or a database.
- Do not change monitor behavior.
- Do not change provider `account_status(...)` behavior.

## Execution.Plan

### Slice 1 - Add Transient Live Script Skeleton

Status: completed.

- Allocate the next live-script prefix under `dev/live`.
- Add a Python live script for the migration.
- Implement arguments:
  - `--dry-run` default behavior
  - `--write` explicit real-run flag
  - optional `--limit N` for development sampling
  - optional `--show-entry-on-error/--no-show-entry-on-error`, default on
- Hard-code the current archive paths first. This is acceptable because the script is transient and archive-specific.
- Check:
  - `--dry-run --limit 1` runs without touching `~/.agentos/agent/usage-registry`
  - no archive file is opened for writing

### Slice 2 - Parse Source Archives

Status: completed.

- Read legacy stats segment JSONL files from the two stats archives.
- Read archived active registry JSONL rows from `20260516T022536Z`.
- Track file path and line number for every source item.
- Ignore `latest.json` and `history/tape.json` for initial conversion if monthly segments contain the full needed data.
- Check:
  - parse counts match expectations from source files
  - malformed JSON fails with file/line context

### Slice 3 - Convert Legacy Observations

Status: completed.

- Select `usage_status == "ok"` observations.
- Apply explicit account mapping.
- Convert Codex `app-server` rows to `source="app_server"` and payload `provider_status.rate_limits`.
- Convert Claude statusline rows to `source="statusline_rate_limits"` and a current-standard statusline payload.
- Skip explicitly out-of-scope accounts such as Copilot with counted reasons.
- Fail on any unmapped successful observation not explicitly skipped.
- Check:
  - generated rows validate against current registry envelope
  - provider payload validation fails with the actual offending entry

### Slice 4 - Dedupe And Stage Complete Registry

Status: completed.

- Load archived active registry rows as baseline rows.
- Merge baseline rows with converted legacy rows.
- Detect exact duplicates and conflicts.
- Group by `YYYYMM` from `recorded_at`.
- Sort each month by `recorded_at` ascending with deterministic tie-breakers.
- Write staged JSONL files under a temporary migration workspace during dry-run and real-run.
- Check:
  - all staged lines parse as JSON
  - every line passes envelope validation
  - no duplicate identities remain
  - latest row for each provider/account/source is chronologically latest within its monthly file

### Slice 5 - Real Run Active Registry Update

Status: completed.

- Require `--write` for active updates.
- Before writing, compare active monthly files against the archived active-registry baseline and abort on drift.
- Replace touched monthly files from staged output only after all validation passes.
- Do not remove untouched active files.
- Do not remove or mutate any archive file.
- Check:
  - active registry files match staged files after write
  - archive files still exist and are byte-for-byte unchanged for sampled inputs

### Slice 6 - Post-Migration Validation

Status: completed.

- Parse all active usage-registry JSONL files.
- Run registry latest lookup checks for:
  - `codex/jp`
  - `codex/mm`
  - `codex/tk`
  - `codex/br`
  - `claude-code/browser-jp`
- Run monitor once:

```sh
agentos agent accounts monitor --once
```

- Check:
  - monitor still renders
  - no runtime legacy stats archive path is read by monitor/account-status
  - generated report is saved or copied into the terminal output for review

## Impl.Log

- Created from migration design discussion.
- The user emphasized the development loop: dry-run, validate entries on the fly, fail on concrete bad entries, patch mappings/parsers, repeat until all intended archive registries are parsable, then run a real write.
- The user explicitly constrained the migration to archived sources, including the archived active registry snapshot, rather than reading the active registry as input.
- Hard invariant added: never delete or mutate archive data.
- Implemented transient live script: `dev/live/611-migrate-agent-usage-registry.py`.
- Dry-run iteration exposed two stale Claude shapes. The script now stacks converters for statusline `rate_limits` and early `live-refresh` `usage.limits` rows into the same current registry row validator.
- Dry-run iteration exposed incomplete Claude successes with reset times but no utilization percentage; these are counted as incomplete skips rather than converted with invented values.
- Dry-run iteration exposed `codex-main`; attempting to map it to `codex/jp` created concrete timestamp conflicts with `codex-jp`, so the script explicitly skips it as ambiguous legacy singleton data.
- Clean dry-run completed with focused output:

```txt
usage-registry migration dry-run ok
archives: legacy=2 baseline=1
scanned: legacy_files=4 legacy_snapshots=24883 baseline_rows=1336
converted: successful=100994 generated=85750 skipped_non_ok=18113 skipped_incomplete=168 exact_duplicates=1
monthly_files:
  202603-usage.jsonl: 7326
  202604-usage.jsonl: 47596
  202605-usage.jsonl: 32163
active_target: not modified
```
- Added fresh active-registry archive snapshot `~/.agentos/archive/20260516T022253Z/raw/agent-usage-registry` after detecting 138 new active registry rows. The migration script now uses this snapshot as the baseline input.
- Executed the real migration with:

```sh
python3 dev/live/611-migrate-agent-usage-registry.py --write
```

- Write completed successfully and replaced the active registry with staged, validated monthly files:

```txt
202603-usage.jsonl: 7326
202604-usage.jsonl: 47596
202605-usage.jsonl: 32163
total: 87085
```

- Post-migration validation passed:
  - all active usage-registry JSONL files parse with `jq`
  - monthly files are sorted by `recorded_at`
  - active account totals are present for `codex/jp`, `codex/mm`, `codex/tk`, `codex/br`, and `claude-code/browser-jp`
  - source totals are `app_server=64565`, `oauth_usage_get=23`, `statusline_rate_limits=22497`
  - `agentos agent accounts monitor --once` renders successfully after migration
- Running the post-migration monitor verification wrote four fresh Codex records, raising the active registry total to `87089`. Archived the resulting active registry at `~/.agentos/archive/20260516T022536Z/raw/agent-usage-registry` and rewired the script baseline to that snapshot.
