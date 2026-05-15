# Monitor Background Frame Swap - impl-req

## Impl.Abstract

- **scope:** move monitor workflow execution off the render/main thread by adding a cooperative background workflow loop that builds a working `MonitorFrame`, signals completion, and lets the main `MonitorLoop` swap frames between render ticks.
- **status:** implemented.
- **source:** current monitor design discussion after `limits-tracking` became a real account-status workflow with structured frame rows and Rich usage bars.
- **goal:** keep `agentos agent accounts monitor` rendering at roughly 1 Hz even when workflows perform slow operations such as fetching account status for multiple provider accounts.

## Impl.Index

### Current.State.Evidence

- `MonitorLoop` currently runs workflows synchronously in `src/agentos/agent/monitor/loop.py`.
- The current loop mutates one persistent `MonitorFrame` directly before rendering:
  - increments `state.tick`
  - sets `frame.tick`
  - resets `frame.status_lines`
  - calls each workflow serially with `workflow.run(state, frame)`
  - calls `on_tick(frame, state)`
- `LimitsTrackingWorkflow` in `src/agentos/agent/monitor/workflows.py` performs potentially slow provider operations by calling `agent.account_status(refresh_usage=True)`.
- `MonitorFrame` in `src/agentos/agent/monitor/models.py` now contains structured rows:
  - `MonitorTextRow`
  - `MonitorUsageTimeRow`
  - `MonitorResetRow`
- `RichMonitorRenderer` renders from `MonitorFrame`; rendering is frame-first and does not need deep `MonitorState` reads for the visible TUI.
- Workflow error policy already expects workflows to capture expected runtime errors into state/frame; `MonitorLoop` keeps a last-resort unexpected-error guard.

### Accepted.Design

- Keep one shared `MonitorState`.
- Keep one serial workflow sequence. Do not introduce per-workflow frames, per-workflow state snapshots, or per-workflow publications.
- Add double-buffered frames owned by `MonitorLoop`:
  - `visible_frame`: read by the main/render thread only.
  - `working_frame`: mutated by the workflow thread only.
- The workflow thread runs all configured workflows serially against the same shared `MonitorState` and the `working_frame`.
- The workflow thread never mutates `visible_frame`.
- The workflow thread never swaps frame references.
- When a full workflow cycle is complete, the workflow thread only signals that `working_frame` is ready.
- The main loop checks the ready signal once per render tick. If ready, it swaps `visible_frame` and `working_frame`.
- After the swap, the old visible frame becomes the next working frame and is reset before the workflow thread starts the next cycle.
- It is acceptable if the main loop swaps up to one second after the workflow cycle finishes.

### Synchronization.Model

- Use `threading.Event` for cooperative ownership signaling, not locks around workflow execution.
- Required events:
  - `working_frame_available`: set when the workflow thread may start mutating `working_frame`.
  - `working_frame_ready`: set when the workflow thread has finished a full workflow cycle.
  - `stop_requested`: set when the monitor should stop.
- Main loop behavior:

```python
while running:
    if working_frame_ready.is_set():
        visible_frame, working_frame = working_frame, visible_frame
        working_frame_ready.clear()
        working_frame_available.set()

    render(visible_frame, state)
    sleep_to_1hz()
```

- Workflow loop behavior:

```python
while not stop_requested.is_set():
    working_frame_available.wait()
    working_frame_available.clear()

    reset working_frame for the next workflow cycle
    run workflows serially over state + working_frame

    working_frame_ready.set()
    wait for the main loop to swap before starting again
```

- Do not hold locks during slow provider calls.
- Do not busy-wait in the workflow thread.
- The main loop must remain non-blocking except for its normal cadence sleep.

### Frame.Ownership

- `visible_frame` is read-only from the renderer's perspective.
- `working_frame` is write-only from the workflow thread's perspective until it signals ready.
- The main thread swaps frames only after the workflow thread has signaled completion.
- The workflow thread must not mutate `working_frame` after setting `working_frame_ready`.
- Before a new workflow cycle starts, reset the working frame into a clean render target.

### State.Policy

- `MonitorState` remains the shared state object.
- The workflow thread may mutate `MonitorState` while building the working frame.
- Rendering should remain frame-first; avoid making Rich rendering depend on deep `MonitorState` internals.
- JSON result paths may still include `MonitorState`; for this phase, eventual consistency is acceptable because the CLI output and TUI are frame-driven.
- If tests expose state/frame inconsistency as a practical issue, treat that as a deviation trigger and introduce a minimal state publication/snapshot only then.

### Tick.Policy

- The main loop owns render cadence.
- The workflow thread may perform slow work and should not force the main thread to wait.
- `MonitorState.tick` should continue to represent main-loop render ticks.
- `MonitorFrame.tick` on a working frame should indicate the render tick at which the workflow cycle was prepared or published. Pick one convention and make tests assert it.
- Prefer simple behavior:
  - main thread increments `state.tick` once per render tick.
  - before starting a workflow cycle, the working frame is prepared with the latest visible tick value available to the loop.

### Error.Policy

- Expected workflow/runtime errors remain workflow-owned and should be rendered into the working frame.
- Unexpected workflow bugs caught by `MonitorLoop` should be recorded into the working frame, not the visible frame.
- A workflow-thread exception must not kill the main monitor loop silently.
- If the workflow thread exits unexpectedly, the visible frame should show the last completed frame and the loop should surface a concise error in a subsequent frame or status line.

### CLI.Behavior

- `agentos agent accounts monitor` remains a loop.
- `--once` should still use the same monitor path, but it must wait for the first completed working frame before returning.
- `--max-ticks N` should render up to N main-loop ticks and return the latest visible frame/state.
- `--json` with finite ticks should return the latest visible frame plus current shared state.
- `--json` with infinite loop should print each visible frame after normal main-loop tick handling.
- Ctrl-C should request workflow-loop shutdown and stop cleanly.

### Out.Of.Scope

- Do not add per-workflow worker threads.
- Do not add per-workflow frame blocks/publications.
- Do not redesign `MonitorState` into immutable snapshots unless a concrete inconsistency forces it.
- Do not implement Claude account status as part of this change.
- Do not change the `limits-tracking` display format except where needed for the new loop mechanics.
- Do not add process pools or async/await infrastructure.

## Execution.Plan

### Slice 1 - Frame Reset Support

Status: complete.

- Add a small `MonitorFrame` reset/preparation method in `src/agentos/agent/monitor/models.py`.
- It should clear blocks, status lines, warnings, and errors, and set the target tick.
- Preserve existing row/block helpers.
- Check:
  - focused unit test that reset clears old blocks and assigns the new tick.

### Slice 2 - Background Workflow Loop Skeleton

Status: complete.

- Refactor `MonitorLoop` to own:
  - `visible_frame`
  - `working_frame`
  - `working_frame_available`
  - `working_frame_ready`
  - `stop_requested`
  - a workflow thread handle
- Start the workflow thread when `MonitorLoop.run(...)` begins.
- Keep workflows serial inside the workflow thread.
- The workflow thread should prepare/reset `working_frame`, run all workflows, then set `working_frame_ready`.
- Check:
  - a fake slow workflow does not block render ticks.
  - the workflow sees only the working frame.

### Slice 3 - Main-Thread Frame Swap

Status: complete.

- In the main loop, check `working_frame_ready.is_set()` once per tick.
- If ready:
  - swap `visible_frame` and `working_frame`
  - clear `working_frame_ready`
  - set `working_frame_available`
- Render only `visible_frame`.
- Check:
  - after a workflow cycle completes, a later render observes the new frame.
  - the workflow does not mutate the frame currently being rendered.

### Slice 4 - `--once` And Finite Loop Semantics

Status: complete.

- Ensure `--once` waits for one completed workflow frame before returning.
- Preserve the single loop path: do not add a separate one-pass workflow execution path.
- Ensure `--max-ticks` still stops deterministically.
- Check:
  - `agentos agent accounts monitor --once` prints a completed `limits-tracking` frame.
  - `--once --json` returns the completed visible frame.
  - `--max-ticks 1 --json` has deterministic behavior documented by tests.

### Slice 5 - Error And Shutdown Handling

Status: complete.

- Ensure unexpected workflow exceptions are captured into the working frame and state.
- Ensure Ctrl-C / normal loop exit sets `stop_requested`.
- Join the workflow thread with a small timeout on shutdown.
- Avoid hanging if the workflow thread is between cycles.
- Check:
  - failing workflow surfaces an error in a published frame.
  - loop shutdown does not leave a running worker thread in tests.

### Slice 6 - Validation And Smoke

Status: complete.

- Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

- Run related tests:

```sh
uv run pytest tests/test_agent_commands.py tests/test_agent_account_registry_commands.py tests/test_process_runner.py -q
```

- Run full suite:

```sh
uv run pytest -q
```

- Refresh installed CLI:

```sh
uv tool install --reinstall --editable .
```

- Manual smoke:

```sh
agentos agent accounts monitor --once
agentos agent accounts monitor --once --json
```

## Impl.Log

- 2026-05-15: Drafted from discussion. Key alignment: one background workflow loop, shared state, double-buffered frames, event-based ready/available coordination, main-thread-only frame swap.
- 2026-05-15: Implemented the background frame swap mechanics. `MonitorLoop` now owns `visible_frame`, `working_frame`, `working_frame_available`, `working_frame_ready`, `stop_requested`, and a daemon workflow thread. The main loop owns render cadence and swaps only completed working frames; the worker runs the configured workflows serially against the shared state and working frame.
- 2026-05-15: Added `MonitorFrame.prepare(tick=...)` and adjusted `LimitsTrackingWorkflow` block writing so reset working frames rebuild their blocks cleanly instead of relying on a stale persistent block index.
- 2026-05-15: Preserved one monitor path for loop, `--once`, finite ticks, and JSON. Finite JSON waits for the first completed frame so test/debug output contains completed monitor data; `--once` uses the same loop path and also waits for the first publication.
- 2026-05-15: Added focused tests for frame reset, background publication, slow-workflow non-blocking render ticks, workflow exception publication, and worker shutdown. Validation run so far: focused account monitor tests, related agent/process tests, and full suite passed.
