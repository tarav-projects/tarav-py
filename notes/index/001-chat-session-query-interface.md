# Chat Session Query Interface

## Query-First Session Resolution

- `agentos chat session` query surfaces should accept one generic session query string instead of splitting the CLI into `id` versus `name`.
- Provider-specific identity concepts are provider details, not cross-provider CLI concepts.
- Each provider resolves the query using all strategies it supports.
- Current examples:
  - Claude Code: `session_id`, desktop `title`
  - Codex: `session_id`, `thread_name`
  - OpenClaw: `session_id`, logical `session_key`
  - Copilot CLI, Gemini CLI, OpenCode: native session ids
- `find` and `extract` should share the same query-resolution model.
- Inventory/reporting commands like `list` and `stats` may still expose provider-native ids in output.
