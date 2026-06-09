# Monitor Weekly Burst Units - impl-req

## Impl.Abstract

- **scope:** add a Weekly `usage/time` display variant in Burst units to the account monitor, reusing the existing monitor row animation framework.
- **status:** ready for implementation.
- **source:** current account-monitor discussion after a 30-day usage-registry back-of-envelope computation showed stable empirical weekly/burst ratios: Codex around `15.7%` weekly per full Burst, Claude around `9.0%` weekly per full Burst.
- **goal:** make Weekly quota pace easier to reason about by expressing both Weekly usage consumed and Weekly time elapsed in equivalent Burst units, while preserving the existing percent-based `usage/time` semantics.
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

- Add a Burst-unit equivalent for Weekly limits:

```text
weekly_used_bursts = weekly_used_percent / weekly_burst_percent
weekly_elapsed_bursts = weekly_elapsed_percent / weekly_burst_percent
weekly_pace_ratio = weekly_used_bursts / weekly_elapsed_bursts
```

- The Burst-unit row means:

```text
how many Burst-equivalents of Weekly quota have been consumed
/
how many Burst-equivalents of Weekly time have passed
```

- Example:

```text
weekly_burst_percent = 15.7
weekly_used_percent = 63
weekly_elapsed_percent = 40

weekly_used_bursts = 4.0
weekly_elapsed_bursts = 2.5
weekly_pace_ratio = 1.6
```

- User-facing display should alternate the Weekly `usage/time` units every 5 draw ticks:

```text
    usage/time          |  63% /  40% = 1.6 [%]        | Weekly
    usage/time          | 4.0 / 2.5 = 1.6 [Burst]      | Weekly
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
  - `unit_variants`
  - `active_unit`
  - `burst_unit`
  - `weekly_burst_percent`
  - `used_burst_units`
  - `elapsed_burst_units`
- The raw state/frame summary should expose enough data to verify the Burst-unit calculation without parsing rendered text.
- Do not replace percent values with Burst values in semantic fields. Percent remains canonical; Burst units are derived display data.

### Formatting.Policy

- Keep the current label and suffix:

```text
label:  "    usage/time"
suffix: "Weekly"
```

- Percent display should include an explicit unit marker:

```text
 63% /  40% = 1.6 [%]
```

- Burst-unit display should use one decimal place for Burst values:

```text
4.0 / 2.5 = 1.6 [Burst]
```

- Ratio formatting should match the current `usage/time` ratio formatting unless implementation needs minor width tuning.
- If elapsed percent is zero, both percent and Burst-unit displays should use the existing `n/a` ratio behavior.

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

Status: pending.

- Add a small provider-ratio lookup near monitor workflow rendering code or monitor display helpers.
- Support only `codex` and `claude-code`.
- Keep constants local and clearly named, for example `WEEKLY_BURST_PERCENT_BY_PROVIDER`.
- Check:
  - Codex uses `15.7`
  - Claude uses `9.0`
  - unknown providers produce only the existing percent display

### Slice 2 - Compute Burst-Unit Usage/Time Variants

Status: pending.

- In `_account_limit_rows(...)`, when the current limit is Weekly and a provider ratio is available, compute:
  - `used_burst_units`
  - `elapsed_burst_units`
  - the same `usage/time` ratio already computed from percent values
- Preserve percent values as canonical row metadata.
- Add focused helper functions for:
  - detecting Weekly limit
  - formatting Burst-unit usage/time values
  - building display variants
- Check:
  - `63% / 40%` with Codex ratio `15.7` formats as about `4.0 / 2.5 = 1.6 [Burst]`
  - ratio remains unchanged between percent and Burst-unit display
  - zero elapsed time still formats as `n/a`

### Slice 3 - Add Unit-Variant Row Animation

Status: pending.

- Extend `MonitorUsageTimeRow` or add a narrow monitor row display-variant mechanism so one semantic row can render multiple unit variants.
- Use a 5-draw-tick phase:

```text
ticks 0-4:  percent variant
ticks 5-9:  Burst-unit variant
repeat
```

- Ensure this animation advances through existing frame/row animation stepping, matching the monitor animation design.
- Ensure workflow refreshes only replace semantic row data; they do not drive the unit alternation.
- Check:
  - drawing the same visible frame across ticks alternates variants
  - a newly refreshed frame starts from a deterministic variant state
  - non-Weekly rows remain static apart from existing overflow behavior

### Slice 4 - Render And JSON Tests

Status: pending.

- Add monitor rendering tests around `limits-tracking` frame output:
  - percent Weekly variant appears
  - Burst-unit Weekly variant appears after animation ticks
  - Burst limit rows do not gain the Burst-unit weekly variant
  - unsupported providers do not gain the Burst-unit variant
- Add JSON/frame summary assertions if semantic Burst-unit fields are added.
- Keep tests focused on row behavior and workflow-produced frame rows, not provider network calls.

### Slice 5 - Validation

Status: pending.

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
  - Weekly `usage/time` can be read in percent units and Burst units.
  - The Burst-unit display uses provider-specific empirical ratios.
  - The display alternates every 5 draw ticks using the existing animation framework.
  - The measure updates only on `limits-tracking` account-status refresh.
  - Burst limit rows remain their normal rows.

## Impl.Log

- Created from the account-monitor design discussion. The accepted implementation treats Burst units as a display variant of Weekly `usage/time`, not a new workflow and not a provider capability change.
