# Agent Run Terminal Capture - impl-req

## Impl-Req State

Implemented: `agentos agent ping` captures agent output through a provider-neutral terminal runner rather than provider-specific command changes.

## User Intent

`agentos agent ping` should run through the same Agentos agent machinery used by all configured agents, while capturing the command output for inspection. Agentos must not special-case Codex or make provider CLIs aware that Agentos is calling them.

## Why This Exists

The current ping implementation asks `Agent.run(...)` for captured output. The shared runtime implements this with `subprocess.run(..., capture_output=True, text=True)`, which replaces stdout and stderr with pipes.

That is not equivalent to running a command in a terminal and observing what it prints. Terminal-oriented commands can detect the pipe-backed stdio and fail with errors such as `stdout is not a terminal` or `stdin is not a terminal`.

## Current Situation

Relevant observed failure:

```sh
agentos agent ping --provider codex --profile codex-tk
Error: stdout is not a terminal
```

The failure is not a Codex command-shape problem. It is a Python process-control problem: Agentos is using pipe capture when it needs terminal capture.

Current implementation surfaces:

- `src/agentos/agent/run_runtime.py`
  - `AgentRunRequest.capture_output`
  - `AgentRunResult.stdout`
  - `execute_agent_run_command(...)`
- Provider agents call `execute_agent_run_command(...)`:
  - `src/agentos/codex/agent.py`
  - `src/agentos/claude/agent.py`
  - `src/agentos/copilot/agent.py`
  - `src/agentos/pi/agent.py`
- `src/agentos/agent/commands.py`
  - `agent ping` builds an `AgentRunRequest(prompt="ping", argv=(), capture_output=True, ...)`

There is local precedent for PTY-based terminal interaction in `src/agentos/claude/accounts.py`.

## Requested Change

Implement a general terminal-capture execution path for all agent runs that request captured output.

When `AgentRunRequest.capture_output` is true, Agentos should launch the configured command under a pseudo-terminal so the child process sees terminal-backed stdio, while Agentos reads from the PTY master and returns the captured terminal transcript.

Do not special-case Codex. Do not rewrite provider commands to non-interactive provider subcommands. Agentos is only caller machinery and should remain command-agnostic at this layer.

## Constraints And Invariants

- Keep provider commands opaque. The runtime should not inspect or rewrite command argv based on provider.
- `Agent.run(...)` remains the path used by `agent ping`.
- Normal `agent run` behavior must keep streaming directly through the current terminal by default.
- Capture behavior must be generic for every provider agent using `execute_agent_run_command(...)`.
- A terminal capture stream is a combined terminal transcript. Do not pretend PTY capture cleanly separates stdout from stderr.
- Preserve existing `FileNotFoundError` handling and exit-code propagation.
- Avoid adding external dependencies unless there is a clear reason; Python stdlib `pty`, `os`, `select`, and `subprocess` are sufficient on the current Unix-like target.
- Do not disturb unrelated Chatlas changes currently present in the worktree.

## Out Of Scope

- No Codex-specific command rewrite such as switching to `codex exec`.
- No provider-specific ping protocol.
- No broad redesign of agent config.
- No Windows PTY support unless the codebase already has a policy for it.
- No attempt to parse terminal UI output into structured provider responses.

## Acceptance Signals

- `agentos agent ping --provider codex --profile codex-tk` no longer fails immediately because stdio is not a terminal.
- A focused test proves that capture mode gives the child process terminal-backed stdin/stdout/stderr.
- Existing tests for normal `agent run` still prove uncaptured runs do not use pipe capture.
- `agent ping` still calls provider `Agent.run(...)` with `capture_output=True`.
- The captured result returns a terminal transcript without provider-specific command handling.
- Focused agent command tests pass.

## Implementation Shape

1. Add a general PTY capture helper in `src/agentos/agent/run_runtime.py`.

   Behavior slice: when `execute_agent_run_command(..., capture_output=True)` runs a simple command that prints `sys.stdin.isatty()`, `sys.stdout.isatty()`, and `sys.stderr.isatty()`, the captured transcript should show all three as true.

   Check: add a unit test that runs a Python one-liner through the real helper when feasible, or monkeypatches the low-level process boundary if the suite avoids real subprocesses.

2. Route capture mode through the PTY helper.

   Behavior slice: `capture_output=False` keeps the existing `subprocess.run(list(command), cwd=..., env=..., check=False)` shape; `capture_output=True` uses PTY capture.

   Check: keep or update existing tests so both execution modes are explicit.

3. Represent PTY output honestly.

   Behavior slice: the returned `AgentRunResult` includes the captured terminal transcript. If the existing API is kept, place the PTY transcript in `stdout` and leave `stderr` unset or empty. If adding a clearer field such as `terminal_output`, update `agent ping` and tests accordingly.

   Check: `agent ping` prints the captured transcript once and exits with the provider command exit code.

4. Add timeout/process cleanup if needed.

   Behavior slice: a hanging capture-mode command does not leave a child process behind when interrupted or timed out.

   Check: use existing agent `timeout_sec` only if it is already threaded into run execution; otherwise keep this slice minimal and document any follow-up needed.

## Relevant Files Or Surfaces

- `src/agentos/agent/run_runtime.py`
- `src/agentos/agent/commands.py`
- `src/agentos/agent/primitives.py`
- `src/agentos/codex/agent.py`
- `src/agentos/claude/agent.py`
- `src/agentos/copilot/agent.py`
- `src/agentos/pi/agent.py`
- `src/agentos/claude/accounts.py` for existing PTY precedent
- `tests/test_agent_commands.py`
- Command to reproduce: `agentos agent ping --provider codex --profile codex-tk`

## Open Questions

- Should `AgentRunResult` gain `terminal_output` to avoid overloading `stdout`, or should the first implementation keep `stdout` for a smaller API change?
- Should `AgentRunRequest.capture_output` be renamed or supplemented with an enum such as `output_mode = "stream" | "pipe" | "terminal"`? The current immediate need is terminal capture, not pipe capture.
- Should `timeout_sec` from agent config be threaded into `Agent.run(...)` execution as part of this change, or handled as a follow-up?

## Related Impl-Reqs

- `572-provider-native-agent-run-capability-impl-req.md`
- `574-agent-run-prompt-and-argv-split-impl-req.md`

## End Log

- 2026-05-12: Created after `agentos agent ping --provider codex --profile codex-tk` exposed that pipe capture is the wrong implementation for terminal-oriented agent commands. The requested fix is provider-neutral PTY terminal capture for all agents.
- 2026-05-12: Implemented in `src/agentos/agent/run_runtime.py` by routing `capture_output=True` through a PTY-backed terminal capture helper shared by every provider that calls `execute_agent_run_command(...)`. Updated `AgentRunResult` to expose `terminal_output`, updated `agent ping` to print that combined transcript, added focused PTY coverage in `tests/test_agent_commands.py`, and refreshed the installed `agentos` CLI.
