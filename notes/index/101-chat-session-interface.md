# Chat Session Interface

Background note from earlier session-interface work. Keep as context, not as a canonical reserved note.

---

## Flat Chat Session Inventory
- Provider should stop being the top-level grouping model and become a field on each session row.
- `agentos chat session` inventory commands should operate on one cross-provider session inventory by default.
- Sorting and limiting apply across the full inventory, not inside per-provider buckets.
- Provider-grouped views are secondary diagnostics, not the default interface.

---
## Query-First Session Resolution
- `agentos chat session` query surfaces should accept one generic session query string instead of splitting the CLI into provider-specific concepts.
- Provider-specific identity concepts are provider details, not cross-provider CLI concepts.
- Query aliases should map native fields into shared concepts while preserving provider-native fields in the response.
- Current native identity examples: Claude `session_id` and desktop `title`; Codex `session_id` and `thread_name`; OpenClaw `session_id` and `session_key`; Copilot CLI, Gemini CLI, and OpenCode native ids.
- `find` and `extract` should share the same query-resolution model.
