# Agent subsystem

<!-- tarav.sessions
bbf9a2bc = claude-code:e6a6bdb2-fd7b-4f83-ba62-7e12a2e8e9d3 @bbf9a2bc779c0729ba14caf69c2af551be5aee583833eed4414a65b60ac88bec
-->

`tarav.l1.agent` holds agents, accounts, profiles, provider adapters and the
account monitor. It predates most current Tarav mechanics: it came over from
Agentos and kept its own config loader, JSONL logs and dataclass models.

## Integration state

The User judged it a very old system next to recent Tarav development and
asked to integrate it more without losing or materially changing its
functionality.
<!-- tarav.breadcrumb 2e884dbfbead -->
<!-- tarav.breadcrumb 9a5a508e792b -->

- Layering is clean: it imports only `l0` and `l1.hooks`. `actions` and
  `operator_context` depend on `agent.current_session`, and Chatlas uses its
  provider and home code, so it is a foundation rather than a leaf.
- Checks: `tarav.l2.agent_setup.AgentSetup` reports monitor-config loading,
  profile loading and each agent's `profile_check()` checkpoints as POIs under
  the Agents workflow. The System Project composes it, so `tarav check` on the
  System Project lists agent findings. It lives in l2 because a check module
  in `l1.agent` would import `actions` and close a cycle.
- Not integrated yet: Diagram-visible agent/account Types, Archive records for
  the usage registry, a registered config section with validation, log
  rotation.

## Agentos names

The User asked to clean the old Agentos leftovers from this system.
<!-- tarav.breadcrumb 50dd0462aade -->

- Logs under `~/.tarav/agent/` now write `tarav.agent.*` classes. Only the
  usage registry filters by class; it still reads `agentos.agent.usage-record`,
  so retained history is never rewritten.
- The global config class is `tarav.global.config`; the loader still accepts
  `agentos.global.config` for homes not yet migrated.
- Left in place on purpose: `agentos://chat-session/` URIs, which Chatlas
  persists in its session index, and the `*_agentos_*` helpers of `l0.project`.

## Known defects

- The Codex session hook in `~/.codex` attributes jp's quota to account `br`.
  The monitor reads the newest record from any source, so codex/br alternates
  between real and foreign data. The same home fails the `HomeMisaligned`
  check ("identity not among candidates").
<!-- tarav.breadcrumb ad3e6ea3584e -->
