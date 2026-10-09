# 886 — Reduce agent providers to Claude, Codex and Copilot — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Design.
Status: implemented.

Remove the agent providers Tarav is not working with: Gemini, OpenCode,
OpenClaw and Pi. Keep Claude Code, Codex and Copilot. The removed code stays
in Git history.

Non-goals: reorganizing the remaining agent code (request 887); any change to
how the three kept providers behave; migrating retained data.

## Design narrative

The User wants fewer supported providers: Claude, Codex and Copilot. The rest
are not in use, introduce noise, and can be recovered from Git history.
<!-- tarav.breadcrumb 6a50dbfe1601692271b87befd14493f4930e32fe1d82bb767000850355a6d643 -->

This is also the first step toward an explicit Agents workflow (request 887):
the code to organize becomes smaller.
<!-- tarav.breadcrumb 731d8b251682bf3a655734a729df80880571e224e53ecbd2bce5817f8ab693be -->

### Current behavior (observed 2026-10-09)

- `src/tarav/l1/agent/providers/` holds `claude_code` (2,581 lines), `codex`
  (1,712), `copilot_cli` (1,333), `gemini_cli` (597), `openclaw` (683),
  `opencode` (686) and `pi` (775).
- Outside those folders the four providers are named in
  `l1/agent/providers/registry.py` (imports, `agent_from_config` branches,
  `DEFAULT_RUN_PROVIDER_FAMILIES`, which includes `pi`),
  `l1/agent/providers/specs.py` (canonical families and home specs),
  `l1/agent/providers/extraction.py`, `l1/agent/_config_entry.py`,
  `l1/agent/_config_models.py`, `l1/agent/sessions.py`,
  `l1/agent/session_refs.py`, `l1/agent/run_runtime.py`,
  `l1/chatlas/index_writer.py` (artifact suffixes per provider and an
  `opencode` branch) and `tests/test_architecture.py`.
- The Chatlas archive on the User's machine (`~/Documents/tarav/chatlas/raw`
  and `index/sessions`) holds only `claude-code` and `codex`. No retained
  session belongs to a removed provider.

### Agent choices (proposals, not User decisions)

- Delete the four provider folders and every branch, spec, constant and test
  entry that names them. No compatibility alias and no "unsupported provider"
  shim beyond the error an unknown provider already gets.
- A user configuration that still names a removed provider fails as any
  unknown provider does. Check the User's own agent configuration for such
  entries and report them; do not edit files outside the repository.
- Guidance and skills in `tarav-md` that mention the removed providers are
  listed in the Impl.Log, not edited here.

### Open questions

- None blocking. Whether Copilot's support is complete enough to keep is not
  assessed here.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes:
`agents-workflow.md`, `daily/2026-10-09.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: done (Wiki notes written 2026-10-09).

## Execution.Plan

1. Start checkpoint. Delete the four folders; remove their names from the
   registry, specs, extraction, configuration models, sessions, session
   references, run runtime and Chatlas index writer.
2. Update `tests/test_architecture.py` and any test fixture that names them.
3. Verify: full test suite, Ruff, `tarav agent list`, `tarav chatlas update`
   on one session of each kept provider, `grep` shows no remaining name.
4. Breadcrumbs on changed surfaces, Wiki note update, completion commit.

## Impl.Log

- Designed 2026-10-09. Not executed.
- Executed 2026-10-09 at the User's request.
<!-- tarav.breadcrumb 39a437c8efcc6c9b0b7314a8f440e285005d205cf832531753bbcfbf9ab3f44d -->
- Start checkpoint `d7cc634` (empty: the scope held no changes of this
  request). Baseline: 244 tests passed, Ruff clean.
- Removed `src/tarav/l1/agent/providers/{gemini_cli,openclaw,opencode,pi}`
  (16 files) and every name of them in `providers/registry.py` (imports,
  `agent_from_config` branches, `DEFAULT_RUN_PROVIDER_FAMILIES`),
  `providers/specs.py`, `providers/extraction.py` (also the `opencode.db`
  session-id rule), `_config_models.py`, `_config_entry.py`,
  `session_refs.py`, `sessions.py`, `run_runtime.py`,
  `l1/chatlas/index_writer.py` and the forbidden-name list in
  `tests/test_architecture.py`. Generic home-spec mechanics that only
  OpenCode used (SQLite anchors) were left; request 887's inventory can judge
  them.
- Checks: 244 tests passed, Ruff clean, no remaining name in `src` or
  `tests`. `tarav chatlas update` works for a Claude Code session and for
  Codex; `tarav chatlas current-session` unchanged.
- Observation, outside the repository and not edited: the User's
  `~/.tarav/profiles/` holds five profiles of removed providers
  (`gemini-main.json`, `openclaw-main.json`, `opencode-main.json`,
  `pi-jp.json`, `pi-mm.json`). With them present every `tarav agent` command
  that loads profiles fails with "agent.profiles[11].provider must be one of:
  claude-code, codex, copilot-cli". With a copy of the home without those
  five files `tarav agent list` lists the eleven remaining profiles. Chatlas
  is not affected.
- `tarav-md` names the removed providers only in
  `notes/wiki/agents-workflow.md`, updated by this request.
- Product Breadcrumbs: 1 each in `providers/registry.py` and
  `providers/specs.py`; audits of all ten changed files clean.
- `tests/test_architecture.py` also holds another agent's uncommitted edits;
  only this request's lines were committed from it.
