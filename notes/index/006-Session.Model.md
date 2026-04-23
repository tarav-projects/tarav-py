# Session.Model

Standard provider-neutral data model for representing an agent coding session on disk.

---

## What It Is
- A canonical on-disk representation of an agent session — the same thing Claude Code, Codex, Copilot, and others each store in their own proprietary format, expressed as one standard schema.
- A portable session format: normalize once at the provider boundary, then every downstream tool works against the same shape.
- Not a runtime protocol. Not an observability schema. Not a forensic report. It is the **interchange format** for agent session data.

## Analogy
- Providers have their own internal storage formats. `Session.Model` is the MIME/IMAP equivalent — the common representation that any tool can read and write, regardless of which agent produced it.

## Canonical Surfaces
- `session` — identity, lineage, timestamps
- `agent_instance` — provider family, instance, fingerprint
- `sources` — backing raw artifacts with location and role
- `chat.messages` — role/content with visibility, typed content blocks
- `chat.model_runs` — turn-scoped execution spans, reasoning traces
- `chat.tool_invocations` — joined tool call lifecycle (request → execution → result)
- `chat.events` — raw event stream, provider-typed
- `chat.usage` — token/cost accounting with honest scope boundaries
- `normalization` — normalizer metadata, warnings, coverage

## Extension Pattern
- Canonical fields are provider-neutral and truthful.
- Provider-specific data lives under bounded `native` fields.
- Every normalized record links back to raw source via `source_refs`.
- Do not promote provider-specific fields to canonical unless they describe the same concept across providers.

## Normalization Boundary

```text
provider raw artifacts
  → provider normalizer
  → Session.Model
  → common services (export, search, summary, replay, UI)
```

## Design Rules
- Preserve raw evidence; do not discard provider-specific data.
- Do not invent precision — if raw data is aggregate, keep it aggregate.
- Do not parse semi-structured text into canonical fields without reliable structured evidence.
- Prefer additive schema evolution over rewriting raw artifacts.
- Honest fidelity over fake uniformity.

## Current State
- Schema version: 1 (experimental)
- Implemented normalizers: Codex (`codex.raw_rollout.experimental.v1`), Copilot CLI (`copilot-cli.raw_events.experimental.v1`)
- Exposed via: `agentos chatlas experimental export`

## Prior Art Assessment (2026-04-23)
- No existing standard covers this problem. See `notes/live/540-agent-session-model-standards-research.md`.
- Agent Client Protocol: runtime protocol (create/resume/close), not a data model for persisted sessions. Complementary.
- OpenTelemetry GenAI: attribute vocabulary for observability, not a session schema. Field naming alignment is worth considering.
- OpenAI messages array: request-level format, no session lifecycle. Used as building block.
- A2A, MCP, FIPA: solve different problems (inter-agent delegation, tool access, legacy agent comms).

## Related
- Architecture: `notes/live/534-chatlas-standard-chat-model.md`
- Implementation plan: `notes/live/538-chatlas-provider-normalizers-plan.md`
- Standards research: `notes/live/540-agent-session-model-standards-research.md`
