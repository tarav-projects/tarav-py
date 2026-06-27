# 670 — monitor "non-aligned homes" block (drift-only, conditional)

## Impl.Abstract

- **Scope:** add a second, read-only status surface to the account monitor that
  lists the **current** non-aligned homes, alongside the existing last-5
  rotation-event log (668). The block is rendered **only when there is at least one
  drifted home** — when everything is aligned it is absent (no empty placeholder).
- **Filter (this iteration):** include only homes whose status starts with
  `drift` — i.e. `drift:home-newer`, `drift:home-older`, `drift:no-active`, and bare
  `drift`. **Exclude** `error:unlisted-account` and `undeterminable` (not actionable
  here; revisit later). User directive: "lets do only `drift:*` stuff at the moment".
- **Nature:** pure consumer of the existing drift primitive
  (`account_status_report.build_status_report` / `status_for_home`). Read-only:
  reads home files, no provider/network call, never writes a home. No new state ring
  — drift is *current* state, recomputed each sweep, not accumulated history.
- **Status:** NOT STARTED.
- **Source context:** this session's monitor work — follows 668 (the rotation log +
  `m` keystroke) and 666 (drift qualification). Design discussion: a sibling block,
  drift-only, conditional visibility; draft frame mockup approved by the user.
- **Out of scope:**
  - Any non-`drift:*` status (errors / undeterminable) — deliberately filtered out.
  - Auto-remediation. This block is display-only; remediation stays on the `m`
    keystroke (`materialize_sweep`) and the auto rotate sweep.
  - The real `agentos accounts` log mechanism (still deferred).
  - Touching the rotation-log block, the `m` keystroke, or sweep cadence.

## Impl.Index

### Block A: a drift-only consumer of the status report
- Current state (`Hard.Evidence`):
  - `account_status_report.build_status_report(provider)` →
    `{"homes": [status_for_home(t), …]}`; each entry is a dict with `status`,
    `home`, and (when known) `account`, `method`, `reason`
    (`src/agentos/agent/account_status_report.py:96`). Statuses are emitted at
    `status_for_home` (`account_status_report.py:51`): `aligned`,
    `drift:home-newer`, `drift:home-older`, `drift:no-active`, `drift`,
    `error:unlisted-account`, `undeterminable`.
  - The monitor already enumerates the provider set to sweep via
    `providers_with_auth_methods()`
    (`src/agentos/agent/auth_method_registry.py:31`), used by `sweep_rotations`
    (`src/agentos/agent/monitor/account_rotation.py:49`).
  - The monitor row type is `MonitorTextRow`
    (`from agentos.agent.monitor.models import MonitorTextRow`), already used by
    `rotation_block_rows` (`account_rotation.py:114`).
- Decision: add a small read-only helper in `account_rotation.py` (the monitor's
  account surface) that:
  1. iterates `providers_with_auth_methods()`,
  2. calls `build_status_report(provider)` per provider (best-effort per provider —
     a failure in one provider must not abort the others, mirroring
     `sweep_rotations`' per-provider `try/except`),
  3. keeps only entries whose `status` starts with `"drift"`,
  4. returns them as a flat list (provider attached) ordered deterministically
     (by provider, then home).
  Then a renderer turns that list into `list[MonitorTextRow]`, one row per drifted
  home. Row text mirrors the CLI status line shape (see
  `format_status_report`, `account_status_report.py:101`):
  `[<status>] <account>/<method>  <home>  — <reason>`. The `reason` is included
  (the approved mockup shows it). No empty-state placeholder row — emptiness is
  handled by Block B (the block isn't added at all).

### Block B: conditional second block in the workflow
- Current state (`Hard.Evidence`): `AccountRotationWorkflow._write_block`
  (`src/agentos/agent/monitor/workflows.py:1199`) unconditionally calls
  `frame.add_block(self.name, rows=rotation_block_rows(...), data=...)`.
  `MonitorFrame.add_block` (`src/agentos/agent/monitor/models.py:386`) always
  appends — there is no built-in "skip when empty"; conditional visibility is the
  caller's job.
- Decision: in `_write_block`, after adding the existing `account-rotation` block,
  compute the drift list (Block A). **Only if it is non-empty**, add a second block
  titled `non-aligned homes` with the rendered rows. When the list is empty, do not
  call `add_block` for it — the block is simply absent that frame.
- Cadence: the drift list is recomputed inside `_write_block`, which already runs on
  every `loop`/`setup` (startup, enter, the 60s periodic alarm, and after the `m`
  materialize sweep re-renders). No new alarm. Recompute-on-render is acceptable —
  it is read-only and bounded by the number of declared homes. (If a future profile
  count makes this heavy, cache in `state.data`; not needed now.)

## Execution.Plan

Two slices. Slice 1 builds and unit-tests the drift-only consumer (the observable
data). Slice 2 wires conditional rendering into the workflow. `No.Regression`: add
only the two behavior tests below.

### Slice 1 — drift-only consumer + renderer (Block A)
- Changes: in `src/agentos/agent/monitor/account_rotation.py`, add
  `collect_non_aligned_homes() -> list[dict[str, object]]` (sweeps
  `providers_with_auth_methods()`, calls `build_status_report` per provider with
  per-provider isolation, keeps `status.startswith("drift")`, attaches `provider`,
  deterministically ordered) and `non_aligned_block_rows(entries) ->
  list[MonitorTextRow]` (one row per entry, `[status] acct/method  home  — reason`).
  Export both in `__all__`.
- Path: monitor account surface → status-report primitive.
- Observable result: given a registry/profile state with a mix of aligned and
  drifted homes, `collect_non_aligned_homes()` returns exactly the `drift:*` homes
  (no `aligned`, no `error:*`, no `undeterminable`), and `non_aligned_block_rows`
  renders one `MonitorTextRow` per such home carrying its status label and home path.
- Check (RED→GREEN): new test module
  `tests/test_agent_non_aligned_homes_monitor.py`. RED first: assert
  `collect_non_aligned_homes()` returns only the drifted entries for a fixture with
  one aligned home + one `drift:home-older` home + one `error:unlisted-account`
  home (the error one must be excluded). Build the fixture the way the existing
  status-report tests do (see `tests/test_agent_account_status_report.py` for the
  profile + registry + home setup pattern). Assert the rendered rows include the
  drift status label and the home path, and exclude the aligned/error homes.

### Slice 2 — conditional second block in the workflow (Block B)
- Changes: in `AccountRotationWorkflow._write_block`
  (`src/agentos/agent/monitor/workflows.py`), after the existing
  `add_block(account-rotation, …)`, compute `collect_non_aligned_homes()`; if
  non-empty, `frame.add_block("non-aligned homes",
  rows=non_aligned_block_rows(entries), data={...})`. Import the two helpers
  alongside the existing `recent_from_state`/`rotation_block_rows` import.
- Path: monitor frame render.
- Observable result: a frame built when drift exists contains both the
  `account-rotation` block and a `non-aligned homes` block; a frame built when all
  homes are aligned contains the `account-rotation` block but **no** `non-aligned
  homes` block.
- Check (RED→GREEN): extend the new test module with a workflow-level test (follow
  the existing monitor-workflow test pattern in
  `tests/test_agent_account_rotation_monitor.py`): build a `MonitorFrame`, run the
  workflow's render path, and assert (a) with a drifted home present, a block titled
  `non-aligned homes` is in `frame.blocks`; (b) with only aligned homes, no block
  with that title is present. RED before the `_write_block` change, GREEN after.

### Risks / deviation triggers
- **Per-provider isolation:** `build_status_report` could raise for a misconfigured
  provider; wrap each provider call so one failure does not blank the whole block
  (mirror `sweep_rotations`). If isolation proves awkward, stop and surface rather
  than letting an exception escape to the monitor loop.
- **Status prefix coupling:** the filter keys on `status.startswith("drift")`.
  That is the agreed contract (all drift labels share the `drift` prefix); if a
  future status outside the drift family also starts with `drift`, revisit. Do not
  hard-code the four current labels — the prefix is the intended rule.
- **Title string** `non-aligned homes` is the block identity used by the Slice-2
  test; keep them in sync.
- **Scope guard:** do not add remediation, do not alter the rotation block, the `m`
  keystroke, or sweep cadence.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- `collect_non_aligned_homes()` returns only `drift:*` homes (errors/undeterminable
  excluded) across all providers.
- The monitor frame shows a `non-aligned homes` block when ≥1 home is drifted, and
  omits it entirely when all homes are aligned.

## Impl.Log

- (empty — not started)
