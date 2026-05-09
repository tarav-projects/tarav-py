# Agent Session Model Standards Research

Research into existing standards and models for describing a provider-agnostic
"agent chat session" (unifying Claude Code, Codex, Copilot, etc.).

Date: 2026-04-23

## Finding: No Single Universal Standard

The landscape is fragmented into several overlapping protocols, each addressing
a different layer. Convergence is accelerating but no one spec covers everything.

---

## Most Relevant to Our Goal

### 1. Agent Client Protocol (ACP)

- Site: https://agentclientprotocol.com
- GitHub: https://github.com/agentclientprotocol/agent-client-protocol
- Pitch: "LSP for AI coding agents" -- purpose-built for editor-to-coding-agent communication
- Transport: JSON-RPC 2.0
- Maturity: Active development, v0.19.x SDK
- Session model:
  - `session/new` -- create a conversation (with cwd, MCP server configs)
  - `session/load` -- resume a previous session (replays history to client)
  - `session/resume` -- restore context without replaying history
  - `session/close` -- terminate and free resources
  - Session forking (independent branch from existing session)
  - Mode switching (ask, architect, code)
  - Message roles: agent, user, thought
  - Tool calls/updates, plans
  - Session IDs (e.g. `sess_abc123def456`)
- **Verdict: closest existing spec to what we need**

### 2. OpenTelemetry GenAI Semantic Conventions

- Spec: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/
- Scope: shared vocabulary for describing/analyzing agent sessions cross-vendor
- Maturity: experimental but converging (March 2026)
- Key attributes:
  - `gen_ai.conversation.id` -- unique session/thread identifier
  - `gen_ai.agent.id`, `gen_ai.agent.name`, `gen_ai.agent.version`
  - `gen_ai.operation.name` -- `create_agent`, `invoke_agent`
  - `gen_ai.input.messages` / `gen_ai.output.messages`
  - `gen_ai.system_instructions`
- Hierarchical: Session > Trace > Span
- **Verdict: best option for session description/observability vocabulary**

### 3. OpenAI Messages Array

- Format: `[{role, content}]` with roles: system, user, assistant, tool
- Content: string or array of parts (text, image_url, etc.)
- Status: de facto universal wire format (Anthropic, Google, Mistral all use variants)
- Limitation: request-level only -- no session lifecycle, no persistence
- **Verdict: lowest-common-denominator message format, good building block**

---

## Broader Landscape

### A2A (Agent-to-Agent Protocol)
- Owner: Google / Linux Foundation
- Scope: inter-agent task delegation and collaboration
- Maturity: production (v1.2, March 2026), 150+ orgs
- Core unit: Task (not session). contextId groups related Tasks/Messages
- Messages have role ("user"/"agent") and Parts (text, file, structured data)
- Does NOT model internal agent conversation, only inter-agent handoff
- Spec: https://a2a-protocol.org/latest/specification/

### MCP (Model Context Protocol)
- Owner: Anthropic
- Scope: tool/resource access (client-server)
- Has transport-level session (Mcp-Session-Id) but no conversation model
- Complementary to conversation protocols, not a replacement

### ACP (IBM)
- Owner: IBM / BeeAI / Linux Foundation
- Scope: REST-native agent-to-agent messaging, multimodal
- Maturity: pre-alpha
- Has session management but too early stage

### ANP (Agent Network Protocol)
- Scope: decentralized agent discovery on the open internet
- Uses W3C DIDs, JSON-LD
- Maturity: draft/experimental

### FIPA ACL (Legacy)
- IEEE-standardized (2005), speech act theory based
- Historically important but effectively dead for modern LLM agents

### NIST AI Agent Standards Initiative
- Launched: February 2026
- Planned: AI Agent Interoperability Profile (Q4 2026)
- Status: RFI stage, very early

---

## Framework-Level Abstractions (No Convergence)

| Framework   | Session Abstraction                | Unit of Work               |
|-------------|------------------------------------|-----------------------------|
| LangGraph   | Stateful graph with checkpointing  | Graph execution + snapshots |
| CrewAI      | Crew + Agents + Tasks              | Task completion by role     |
| AutoGen     | Group chat / conversation          | Message exchange            |
| OpenAI SDK  | Thread + Run                       | Thread = conversation       |

All use OpenAI-style messages internally but wrap them in incompatible abstractions.

---

## Practical Stack for Unification

For unifying Claude Code / Codex / Copilot session representations:

1. **Agent Client Protocol** -- session lifecycle (create/load/resume/fork/close)
2. **OTel GenAI conventions** -- shared attribute vocabulary
3. **OpenAI messages array** -- message wire format

---

## Academic Reference

- "A Survey of Agent Interoperability Protocols" (Ehtesham et al., May 2025)
  https://arxiv.org/abs/2505.02279
  - Compares MCP, ACP, A2A, ANP
  - Proposes phased adoption: MCP -> A2A -> ACP -> ANP
  - Does NOT propose a unified session model

---

## Next Steps

- Deep-dive into Agent Client Protocol spec for session/message data model
- Compare ACP session model with our Chatlas model on the experimental branch
- Decide whether to adopt, adapt, or diverge from ACP
