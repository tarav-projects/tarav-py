# Monitor Weekly Burst Units - impl-req

## Impl.Abstract

- **scope:** add a Weekly `usage/time` display variant in Burst units to the account monitor, reusing the existing monitor row animation framework.
- **status:** implemented.
- **source:** current account-monitor discussion after a 30-day usage-registry back-of-envelope computation showed stable empirical weekly/burst ratios: Codex around `15.7%` weekly per full Burst, Claude around `9.0%` weekly per full Burst.
- **goal:** make Weekly quota pace easier to reason about by showing both used percent pace and remaining Weekly capacity/time in Burst units.
- **strong constraint:** this is a monitor display/model change, not a new monitor workflow. The measure updates when `limits-tracking` refreshes account status. The display alternation is a row animation driven by monitor draw ticks, consistent with the existing animation design.

## Impl.Index

### Current.State.Evidence

- `LimitsTrackingWorkflow` renders account status rows from `src/agentos/agent/monitor/workflows.py`.
- `_account_limit_rows(...)` currently emits `MonitorUsageTimeRow` and `MonitorResetRow` for every usage-over-time limit.
- Existing Weekly rows render percent units only:

```text
    usage/time          |  63% /  40% = 1.6            | Weekly
```

- `src/agentos/agent/monitor/models.py` already has row classes with semantic fields and animation state.
- `notes/live/609-monitor-row-render-animations-impl-req.md` established the accepted monitor animation framework:
  - workflows write semantic row data
  - the draw loop owns visual progression
  - animation uses draw ticks, not wall-clock time
  - rows own rendered display output
  - JSON/debug output should preserve semantic row data
- Provider account-status models expose enough data to detect the Weekly limit:
  - `limit_id == "weekly"` or `period_duration_mins == 10080`
  - `usage_over_time.used_percent`
  - `period_started_at` / `period_ends_at` / `resets_at`, used by `_elapsed_percent(...)`

### Accepted.Behavior

- Keep the existing percent `usage/time` meaning:

```text
weekly_used_percent / weekly_elapsed_percent = weekly_pace_ratio
```

- Add a Burst-unit remaining-capacity equivalent for Weekly limits:

```text
usage_burst_units_left = (100 - weekly_used_percent) / weekly_burst_percent
time_burst_units_left = seconds_until_weekly_reset / 5h
left_ratio = time_burst_units_left / usage_burst_units_left
```

- The `[left]` Burst-unit row means:

```text
how many full-Burst equivalents of Weekly quota remain
/
how many 5-hour Burst windows remain before Weekly reset
```

- Example:

```text
weekly_burst_percent = 15.7
weekly_used_percent = 63
hours_until_weekly_reset = 38.5

usage_burst_units_left = 2.4
time_burst_units_left = 7.7
left_ratio = 3.2
```

- User-facing display should alternate the Weekly `usage/time` units every 5 draw ticks:

```text
    usage/time [used]   |  63% /  40% = 1.6 [%]        | Weekly
    time/usage [left]   | 7.7 / 2.4 = 3.2 [Burst]      | Weekly
```

- The alternation is a row-display animation, not a workflow refresh. The computed semantic values are refreshed only when `limits-tracking` refreshes the account status.
- Do not rotate or otherwise alter the Burst limit's own rows for this feature. The word `Burst` in `[Burst]` is a unit for the Weekly row.

### Ratio.Source.Policy

- First implementation uses pinned provider-level constants from the 30-day registry computation:
  - `codex`: `15.7`
  - `claude-code`: `9.0`
- These constants mean "one 100% Burst consumes approximately this many Weekly percentage points."
- Apply only to providers where both Burst and Weekly limits apply:
  - `codex`
  - `claude-code`
- Do not apply to `copilot-cli` or unknown providers.
- Do not build history-derived ratio recalculation in this slice. A future workflow can derive/update ratios from the usage registry after the display model is proven useful.

### Animation.Design

- Reuse the existing monitor row animation framework from `609-monitor-row-render-animations-impl-req.md`.
- Add a row-level display variant animation for `MonitorUsageTimeRow` or a narrowly-scoped subclass/model extension.
- The animation chooses between semantic display variants every 5 draw ticks.
- The animation must be draw-tick-driven through existing frame/row animation stepping.
- The animation must not depend on wall-clock time.
- The animation must not cause `limits-tracking` to refresh more frequently.
- Overflow marquee animation, if present on the same cell, must still work. If implementation finds these animation types conflict, prefer a simple composition rule:
  - unit variant is selected first
  - the selected text is then rendered through existing fixed-width/overflow behavior

### Data.Model

- Preserve existing `MonitorUsageTimeRow` fields:
  - `used_percent`
  - `elapsed_percent`
  - `ratio`
  - `label`
  - `suffix`
- Add semantic fields only if needed for JSON/debug visibility, for example:
  - `variants`
  - `burst_unit`
  - `weekly_burst_percent`
  - `usage_burst_units_left`
  - `time_burst_units_left`
  - `left_ratio`
- The raw state/frame summary should expose enough data to verify the Burst-unit calculation without parsing rendered text.
- Do not replace percent values with Burst values in semantic fields. Percent remains canonical; Burst units are derived display data.

### Formatting.Policy

- Keep the current label and suffix:

```text
label:  "    usage/time [used]" / "    time/usage [left]"
suffix: "Weekly"
```

- Percent display should include an explicit unit marker:

```text
 63% /  40% = 1.6 [%]
```

- Burst-unit display should use one decimal place for Burst values:

```text
7.7 / 2.4 = 3.2 [Burst]
```

- Ratio formatting should match the current `usage/time` ratio formatting unless implementation needs minor width tuning.
- If remaining usage quota is zero, the Burst-unit `[left]` display should use the existing `n/a` ratio behavior.

### No.Legacy.Allowed

- Do not add a separate monitor workflow for this measure.
- Do not make provider account-status capabilities compute monitor-only display data.
- Do not parse rendered row text to recover semantics.
- Do not add wall-clock animation logic.
- Do not rotate the Burst limit's own row.
- Do not add registry-history analysis to the live monitor path in this implementation.
- Do not remove the existing percent `usage/time` display.

## Execution.Plan

### Slice 1 - Add Weekly Burst Ratio Support

Status: implemented.

- Add a small provider-ratio lookup near monitor workflow rendering code or monitor display helpers.
- Support only `codex` and `claude-code`.
- Keep constants local and clearly named, for example `WEEKLY_BURST_PERCENT_BY_PROVIDER`.
- Check:
  - Codex uses `15.7`
  - Claude uses `9.0`
  - unknown providers produce only the existing percent display

### Slice 2 - Compute Burst-Unit Usage/Time Variants

Status: implemented.

- In `_account_limit_rows(...)`, when the current limit is Weekly and a provider ratio is available, compute:
  - `usage_burst_units_left`
  - `time_burst_units_left`
  - `left_ratio`
- Preserve percent values as canonical row metadata.
- Add focused helper functions for:
  - detecting Weekly limit
  - formatting Burst-unit usage/time values
  - building display variants
- Check:
  - remaining Weekly percent with Codex ratio `15.7` formats as about `7.7 / 2.4 = 3.2 [Burst]` when 38.5 hours remain
  - Burst-unit ratio compares remaining Burst windows against remaining usage capacity so values greater than `1` mean quota pressure / overuse
  - zero remaining usage quota formats as `n/a`

### Slice 3 - Add Unit-Variant Row Animation

Status: implemented.

- Extend `MonitorUsageTimeRow` or add a narrow monitor row display-variant mechanism so one semantic row can render multiple label/value variants.
- Use a 5-draw-tick phase:

```text
ticks 0-4:  usage/time [used] percent variant
ticks 5-9:  time/usage [left] Burst-unit variant
repeat
```

- Ensure this animation advances through existing frame/row animation stepping, matching the monitor animation design.
- Ensure workflow refreshes only replace semantic row data; they do not drive the unit alternation.
- Check:
  - drawing the same visible frame across ticks alternates variants
  - a newly refreshed frame starts from a deterministic variant state
  - non-Weekly rows remain static apart from existing overflow behavior

### Slice 4 - Render And JSON Tests

Status: implemented.

- Add monitor rendering tests around `limits-tracking` frame output:
  - `[used]` percent Weekly variant appears
  - `[left]` Burst-unit Weekly variant appears after animation ticks
  - Burst limit rows do not gain the Burst-unit weekly variant
  - unsupported providers do not gain the Burst-unit variant
- Add JSON/frame summary assertions if semantic Burst-unit fields are added.
- Keep tests focused on row behavior and workflow-produced frame rows, not provider network calls.

### Slice 5 - Validation

Status: implemented.

- Run focused monitor tests:

```sh
uv run pytest tests/test_agent_monitor_auto_prime.py -q
```

- Run broader account/monitor tests if touched surfaces require it:

```sh
uv run pytest tests/test_agent_account_registry.py tests/test_agent_monitor_auto_prime.py -q
```

- Run lint:

```sh
uv run ruff check src/agentos/agent/monitor tests/test_agent_monitor_auto_prime.py
```

- Refresh installed CLI if runtime code changed:

```sh
uv tool install --reinstall --editable .
```

- Manual smoke:

```sh
agentos agent accounts monitor --once
agentos agent accounts monitor --max-ticks 12 --interval-sec 1
```

- Acceptance signals:
  - Weekly `usage/time` can be read in `[used]` percent units and `[left]` Burst units.
  - The Burst-unit display uses provider-specific empirical ratios.
  - The display alternates every 5 draw ticks using the existing animation framework.
  - The measure updates only on `limits-tracking` account-status refresh.
  - Burst limit rows remain their normal rows.

## Impl.Log

- Created from the account-monitor design discussion. The accepted implementation treats Burst units as a display variant of Weekly `usage/time`, not a new workflow and not a provider capability change.
- Implementation decision: the monitor value column was widened from 24 to 25 display cells so the requested `[Burst]` value shape fits as a static unit variant instead of immediately entering overflow scrolling.
- Implementation decision: `MonitorUsageTimeRow` now owns optional paired `variants` for alternate label/value display. Percent fields remain canonical, and remaining Burst-unit metadata is exposed under `burst_unit` for JSON/debug verification.
- Correction: the first implementation converted both Weekly usage and elapsed time by the same weekly/burst ratio, preserving the original ratio and not answering the user's question. The corrected implementation uses `[left]` semantics over remaining Weekly quota and remaining 5-hour Burst windows before Weekly reset.
- Correction: the `[left]` ratio was then flipped to `time/usage` so values greater than `1` mean overuse / quota pressure, matching the intuition of the existing `[used]` pace ratio.
- Correction: the used/left display switch is no longer automatic. Draw-tick animation remains for overflow marquee text, while usage type selection is a separate display toggle driven by the `r` key in the live monitor.
- Validation deviation: `uv tool install --reinstall --editable .` failed because the current `agentos-py` package reports no executable entrypoints and `uv` removed the tool during reinstall. Corrective action was to reinstall the actual executable owner with `uv tool install --reinstall --editable ../agentos-cli`, which succeeded and installed `agentos`.
- Validation completed:
  - `uv run pytest tests/test_agent_monitor_auto_prime.py -q` -> 22 passed.
  - `uv run pytest tests/test_agent_account_registry.py tests/test_agent_monitor_auto_prime.py -q` -> 24 passed.
  - `uv run ruff check src/agentos/agent/monitor tests/test_agent_monitor_auto_prime.py` -> passed.
  - `uv tool install --reinstall --editable ../agentos-cli` -> passed.
  - `agentos --version` -> `agentos 0.1.0`.
  - `agentos agent accounts monitor --once` -> passed after CLI reinstall.
  - `agentos agent accounts monitor --max-ticks 12 --interval-sec 1` -> passed after CLI reinstall.
  - `agentos agent accounts monitor --once --json | rg -n 'variants|usage_burst_units_left|time_burst_units_left|left_ratio|\[left\]|\[Burst\]'` -> passed, showing live `time/usage [left]` Burst value variants with remaining usage/time fields.
