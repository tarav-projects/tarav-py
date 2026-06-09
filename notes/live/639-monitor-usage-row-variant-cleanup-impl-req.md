# Monitor Usage Row Variant Cleanup - impl-req

## Impl.Abstract

- **scope:** clean up the newly added monitor `usage/time` display-variant model by replacing parallel label/value variant tuples with a paired row-variant model.
- **status:** implemented.
- **source:** autonomous `hugentics-codebase-cleaner` pass after implementing Weekly Burst pressure display in the account monitor.
- **goal:** reduce repeated/parallel state in `MonitorUsageTimeRow`, keep row animation semantics easier to reason about, and preserve the visible monitor behavior.
- **strong constraint:** this is a narrow cleanup. Do not redesign monitor rendering, provider status parsing, or account monitor workflow scheduling.

## Impl.Index

### Current.State

- `MonitorUsageTimeRow` currently has:
  - `label`
  - `value`
  - `label_variants`
  - `value_variants`
  - `variant_interval_ticks`
- `_active_label()` and `_active_value()` select variants independently by indexing separate tuples.
- The current Weekly Burst display happens to provide two labels and two values in the same order:
  - `usage/time [used]` + percent value
  - `time/usage [left]` + Burst value
- This is a classic parallel-array shape: the intended invariant lives in construction discipline, not in the data model.

### Cleanup.Target

- Introduce a small row-variant data model in `src/agentos/agent/monitor/models.py`, for example:

```python
@dataclass(frozen=True)
class MonitorColumnVariant:
    label: str
    value: str
```

- Replace `label_variants` and `value_variants` on `MonitorUsageTimeRow` with one field:

```python
variants: tuple[MonitorColumnVariant, ...] = ()
```

- `MonitorUsageTimeRow` should select one active variant, then render its paired label/value together.
- A row without variants should continue rendering its base `label` and `value`.
- JSON/debug output should expose paired variants as a list of objects rather than parallel arrays.

### Accepted.Behavior

- Visible monitor behavior remains the same:

```text
usage/time [used]      | ... [%]                      | Weekly
time/usage [left]      | ... [Burst]                  | Weekly
```

- Variant switching remains every 5 draw ticks.
- The Weekly Burst pressure calculation remains unchanged.
- Burst rows and unsupported providers remain unvariantized.

### No.Legacy.Allowed

- Do not keep `label_variants` / `value_variants` as compatibility aliases.
- Do not add migration code for old JSON frame shapes.
- Do not add a broader row animation framework.
- Do not change the account-status or usage-registry data sources.

## Execution.Plan

### Slice 1 - Replace Parallel Variant Fields

Status: implemented.

- Add a paired monitor column variant model in `models.py`.
- Change `MonitorUsageTimeRow` to use `variants`.
- Simplify active variant selection so label and value come from the same object.
- Check:
  - non-variant rows still render base label/value
  - variant rows switch paired label/value every 5 draw ticks

### Slice 2 - Update Workflow Construction

Status: implemented.

- Update `_account_limit_rows(...)` in `workflows.py` to construct paired variants for Weekly Burst rows.
- Preserve `burst_unit` metadata and percent canonical fields.
- Check:
  - Codex/Claude Weekly rows still get used/left variants
  - Burst rows and unsupported providers still do not get variants

### Slice 3 - Update Tests And Validation

Status: implemented.

- Update monitor tests to assert paired `variants` JSON instead of parallel arrays.
- Run:

```sh
uv run pytest tests/test_agent_monitor_auto_prime.py -q
uv run pytest tests/test_agent_account_registry.py tests/test_agent_monitor_auto_prime.py -q
uv run ruff check src/agentos/agent/monitor tests/test_agent_monitor_auto_prime.py
```

- Smoke:

```sh
agentos agent accounts monitor --once --json | rg -n 'variants|time/usage \[left\]|left_ratio|\[Burst\]'
```

## Impl.Log

- Created by `hugentics-codebase-cleaner` to remove the parallel label/value variant shape introduced during Weekly Burst pressure implementation.
- Implemented paired `MonitorColumnVariant` objects for usage-time row display variants, replacing parallel `label_variants` / `value_variants`.
- Updated Weekly Burst pressure workflow construction to build paired variants for `[used]` and `[left]` displays.
- Validation completed:
  - `uv run pytest tests/test_agent_monitor_auto_prime.py -q` -> 24 passed.
  - `uv run pytest tests/test_agent_account_registry.py tests/test_agent_monitor_auto_prime.py -q` -> 26 passed.
  - `uv run ruff check src/agentos/agent/monitor tests/test_agent_monitor_auto_prime.py` -> passed.
  - `agentos agent accounts monitor --once --json | rg -n 'variants|time/usage \[left\]|left_ratio|\[Burst\]'` -> passed.
- Follow-up display-control change: usage-row variants no longer rotate on draw ticks. `r` now toggles the active variant through a display-only monitor alarm, while draw-tick animation remains available for overflow marquee text.
