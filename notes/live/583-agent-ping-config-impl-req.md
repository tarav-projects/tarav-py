# Agent Ping Config - impl-req

## Impl-Req State

Implemented: `agentos agent ping` now uses first-class, provider-neutral ping configuration from `AgentConfig` instead of command-handler hardcoding.

## User Intent

Agent ping is a general capability for all runnable agents. The command should remain provider-neutral and should not know about Codex or any other provider-specific behavior.

The desired direction is to add ping configuration directly to `AgentConfig` rather than creating an external legacy layer or Codex-only workaround.

## Why This Exists

`agentos agent ping` currently runs through the shared agent machinery and now captures output through a PTY-backed terminal runner. That solved the stdio/terminal issue, but the behavior being run is still hardcoded in the CLI command handler:

- prompt is always `"ping"`
- argv is always empty
- the normal run command shape is reused implicitly

That is too narrow. Different agents may need a different ping prompt, raw ping argv, or a ping-disabled state. Agentos needs a general config shape so ping can be configured per agent instance without provider-specific branching.

## Current Situation

Relevant current code surfaces:

- `src/agentos/agent/commands.py`
  - `_cmd_agent_ping(...)` calls `_resolve_agent_run(..., prompt="ping", argv=(), capture_output=True)`.
- `src/agentos/agent/primitives.py`
  - `AgentConfig` and `AgentBase` include general run fields such as `cli_command`, `run_args`, `default_model`, `model_flag`, and `prompt_flag`.
  - There are no ping-specific fields.
- `src/agentos/agent/config.py`
  - Parses `agent.instances[]` fields into `AgentConfig`.
  - Provides provider-family defaults for normal run fields.
- `src/agentos/agent/run_runtime.py`
  - Builds provider commands from `AgentRunRequest`, `cli_command`, `run_args`, model fields, prompt fields, and raw argv.
  - Capture execution is already shared and provider-neutral.
- Provider agents using the common run runtime:
  - `src/agentos/codex/agent.py`
  - `src/agentos/claude/agent.py`
  - `src/agentos/copilot/agent.py`
  - `src/agentos/pi/agent.py`

Observed behavior after terminal capture:

```sh
agentos agent ping --provider codex --profile codex-mm
```

This no longer fails because stdio is not a terminal. It launches the configured Codex command and then enters Codex startup behavior. That confirms the runtime path is now terminal-correct, but it also shows that ping needs configurable command semantics instead of one universal hardcoded `"ping"` prompt.

## Requested Change

Add ping configuration to `AgentConfig` as a general capability for all runnable agents.

The clean target shape is an `AgentConfig`-owned ping configuration, either as a nested dataclass such as `AgentPingConfig` or equivalent direct fields. The exact internal naming may follow local code style, but the behavior should be:

- `agent ping` resolves the selected agent.
- The selected agent/config supplies the ping request details.
- The command still calls provider `Agent.run(...)`.
- The resulting `AgentRunRequest` uses `capture_output=True`.
- The runtime remains provider-neutral and command-agnostic.

Suggested configuration capabilities:

- ping prompt, for prompt-style pings.
- ping argv, for raw provider-argv-style pings.
- enabled/disabled state, if an agent cannot support meaningful ping.

Only one ping command shape should be active for an instance: prompt-style or argv-style, not both.

## Constraints And Invariants

- No Codex special-case.
- No provider-specific branch in `agent ping`.
- No provider command rewrite such as switching Codex to a different subcommand.
- No legacy compatibility aliases or duplicate old/new config paths.
- `Agent.run(...)` remains the execution path used by `agent ping`.
- `capture_output=True` remains part of ping execution.
- Ping config belongs on `AgentConfig`, because ping is a general agent capability.
- Normal `agent run` behavior must remain unchanged.
- Existing provider config fields for normal run behavior must keep their current meaning.
- Preserve current config validation style: typed dataclasses, explicit `CliError` messages, and JSON field validation in `agent_config_from_config_entry(...)`.
- Do not disturb unrelated Chatlas changes or the existing terminal-capture implementation beyond what this request requires.

## Out Of Scope

- No provider-specific ping protocol.
- No attempt to determine whether a provider's response means "healthy" beyond process exit code and captured transcript.
- No timeout redesign unless the current code already makes it straightforward.
- No Windows PTY or terminal behavior changes.
- No broad redesign of agent config, account config, or session discovery.

## Acceptance Signals

- `AgentConfig` exposes first-class ping configuration.
- `agent.instances[]` can configure ping behavior without changing provider code.
- `agent ping` builds its `AgentRunRequest` from the selected agent's ping config instead of hardcoding `prompt="ping"` and `argv=()`.
- A focused test proves a configured ping prompt is used.
- A focused test proves configured ping argv is used.
- A validation test proves prompt and argv cannot both be configured for ping.
- A test proves `agent ping` still invokes provider `Agent.run(...)` with `capture_output=True`.
- Normal `agent run` tests continue to pass.
- No implementation branch checks for `provider == "codex"` or any other provider inside ping execution.

## Implementation Shape

1. Add the config model.

   Behavior slice: `AgentConfig` can hold ping configuration and exposes it through `AgentBase`/`Agent.summary()` if useful for inspection.

   Check: constructing or loading an `AgentConfig` with ping fields yields the expected in-memory config without affecting existing run fields.

2. Parse and validate `agent.instances[]` ping config.

   Behavior slice: a config such as a nested `"ping"` object can describe either a prompt ping or an argv ping.

   Check: tests cover valid prompt ping, valid argv ping, and invalid prompt-plus-argv. Use existing config helper patterns in `tests/test_agent_commands.py` or adjacent config tests.

3. Route `agent ping` through config.

   Behavior slice: `_cmd_agent_ping(...)` resolves the selected agent, reads its ping config, creates an `AgentRunRequest` from it, and calls `agent.run(request)`.

   Check: monkeypatched provider tests assert the request uses the configured prompt or argv and always sets `capture_output=True`.

4. Preserve default behavior deliberately.

   Behavior slice: existing configs without ping fields should still have a sensible provider-neutral default if the product decision is to keep `agent ping` usable immediately. The default should live in config construction, not in the command handler.

   Check: the existing `agent ping` test either remains valid through the default ping config or is updated to assert the new default source.

5. Verify installed CLI behavior.

   Behavior slice: after implementation, refresh the installed CLI with `uv tool install --reinstall --editable .`.

   Check: run a temporary profile with configured ping argv/prompt to prove the installed `agentos agent ping` command uses config-driven ping behavior.

## Relevant Files Or Surfaces

- `src/agentos/agent/primitives.py`
- `src/agentos/agent/config.py`
- `src/agentos/agent/commands.py`
- `src/agentos/agent/run_runtime.py`
- `src/agentos/codex/agent.py`
- `src/agentos/claude/agent.py`
- `src/agentos/copilot/agent.py`
- `src/agentos/pi/agent.py`
- `tests/test_agent_commands.py`
- `notes/live/582-agent-run-terminal-capture-impl-req.md`

## Open Questions

- Should the public JSON config field be nested as `"ping": {"prompt": "...", "argv": [...]}` or represented as direct fields such as `"ping_prompt"` and `"ping_args"`?
- Should ping be enabled by default with prompt `"ping"`, or should unsupported/unconfigured ping produce a clear `CliError`?
- Should `agent list --json` include ping capability details, or should this stay internal until there is a broader capability-reporting surface?
- Should timeout handling for ping use existing `timeout_sec` now, or remain a follow-up after command shape is configurable?

## Related Impl-Reqs

- `582-agent-run-terminal-capture-impl-req.md`
- `574-agent-run-prompt-and-argv-split-impl-req.md`
- `572-provider-native-agent-run-capability-impl-req.md`

## End Log

- 2026-05-12: Created after terminal-capture work showed that `agent ping` now runs with terminal-backed stdio but still has hardcoded ping semantics in the command handler. The requested next step is first-class, provider-neutral ping configuration on `AgentConfig`.
- 2026-05-12: Implemented `AgentPingConfig` on `AgentConfig`/`AgentBase`, nested `agent.instances[].ping` parsing and validation, and config-driven `agent ping` request construction. Added focused tests for default capture, configured prompt, configured argv, and invalid prompt-plus-argv. Verified with focused tests, full test suite, CLI reinstall, and an installed CLI smoke using configured `ping.argv`.
