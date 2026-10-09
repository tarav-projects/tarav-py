# 887 — Agents workflow and the current session — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Design.
Status: ready, after request 886.

Make the existing agent code an explicit Tarav workflow, and give it the
first integration point the rest of Tarav needs: a Python answer to "which
session is the running agent in?", provided per provider.

Non-goals: rewriting or moving the agent modules; converting account and
profile findings to POIs; Context views for agents; the Operator Context
(request 888); changing what Chatlas archives.

## Design narrative

The minimum Tarav demands from the internal harness is that an agent can
reach its current session ID. Tarav has no workflow for running agents:
Chatlas is an archive concerned with transcripts. The earlier agent code
should be gathered so that "give me the current session" belongs to a
workflow, not only to a command.
<!-- tarav.breadcrumb f2641f1dd13b7cf123bae03c2498c684ce128a6fdf21c8475f82f1536a8e3aeb -->

The User wants an Agents workflow that gathers how Tarav interfaces with the
providers, with a submodule per provider as the code is already organized.
Chatlas keeps its functionality and focuses on transcripts. The code is old
but working: organize it, make it an explicit workflow, find its integration
points, bring it to the current philosophy. Do not remove it.
<!-- tarav.breadcrumb 0f4ca54b86d4943d617b94eac0206025f741258f309e67c59c8a4194f3a28e44 -->

### Current behavior (observed 2026-10-09)

- `src/tarav/l1/agent/` has about thirty modules and `providers/<provider>/`
  adapters. It declares no `TaravWorkflow`; `__init__.py` still carries
  `# $kw: --from Agentos.Agent.Adapter`. `AGENTS.md` already states that
  provider-neutral orchestration belongs in `tarav.l1.agent` and adapters in
  `tarav.l1.agent.providers.<provider>`.
- Other workflows declare an identity module and a `TaravWorkflow` subclass,
  for example `l1/references/identity.py` and `l1/references/workflow.py`,
  assembled in `l3/runtime.py`.
- The current session is resolved only in `l1/chatlas/commands.py`:
  `_CURRENT_SESSION_ENV` maps `codex` to `CODEX_THREAD_ID` and `claude-code`
  to `CLAUDE_CODE_SESSION_ID`; `tarav chatlas current-session` and
  `tarav chatlas update --current-session` use it.
- Chatlas already imports provider specs, configuration and session
  references from the agent package.

### Agent choices (proposals, not User decisions)

- **Workflow identity.** `tarav.l1.agent.identity` with a workflow Ship and
  `tarav.l1.agent.workflow` with the `TaravWorkflow` subclass, registered in
  the runtime like the others. No module is moved.
- **Current session as a provider capability.** A small capability class in
  the agent package; a provider adapter that can report its session inherits
  it and says how (today: an environment variable). Claude Code and Codex
  inherit it. Copilot inherits it only if its harness exposes the session;
  otherwise it does not, which is the honest state.
- **One Python entry point** in the agent package returning the provider and
  native session ID, or saying that no provider reports one. With several
  candidates and no provider named it reports the ambiguity; it does not guess.
- **Chatlas calls it.** `tarav chatlas current-session` and
  `--current-session` keep their behavior and output; the environment-variable
  table leaves Chatlas.
- **An inventory first**, as a section of `agents-workflow.md`: each module,
  what it does, whether anything uses it, where it touches the rest of Tarav.
  Read-only; it informs later requests and is not a refactor.

### Open questions

- Does the Copilot harness expose its session ID?
- Should the entry point return the neutral Chatlas identity too? Proposed:
  no; that is Chatlas's knowledge and the caller asks Chatlas.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes:
`agents-workflow.md`, `operator-context.md`, `daily/2026-10-09.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: done (Wiki notes written 2026-10-09).

## Execution.Plan

1. Start checkpoint. Inventory of `l1/agent` into the Wiki note.
2. Workflow identity and class; runtime registration; tests that the workflow
   and its Types are registered.
3. Capability class, the two (or three) adapters, the entry point; tests with
   set and unset environment variables, and the ambiguous case.
4. Chatlas commands call the entry point; existing Chatlas tests pass
   unchanged.
5. Full suite, Ruff, `tarav chatlas current-session --provider claude-code`
   in a live session; Breadcrumbs, `AGENTS.md` if a contract changed, Wiki,
   completion commit.

## Impl.Log

- Designed 2026-10-09. Not executed.
