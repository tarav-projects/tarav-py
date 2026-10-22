# 952 — Agent subsystem integration and Agentos cleanup

<!-- tarav.sessions
bbf9a2bc = claude-code:e6a6bdb2-fd7b-4f83-ba62-7e12a2e8e9d3 @bbf9a2bc779c0729ba14caf69c2af551be5aee583833eed4414a65b60ac88bec
-->

## Impl.Abstract

Integrate `tarav.l1.agent` (accounts, profiles, monitor) more deeply with
current Tarav mechanics without losing or materially changing its behavior,
and clean it of leftover Agentos naming.

- Scope: Agentos remnants owned by the agent subsystem plus the global config
  class it lives in; a Check suite over agent configuration composed into the
  System Project; tests for the touched behavior; architecture doc row.
- Non-goals: Diagram-visible agent/account Types, Archive registration of the
  usage registry, log rotation, Agentos names owned by other subsystems
  (`l0.project` `*_agentos_*` helpers, daemon, hooks, stdlib, Chatlas).
- Status: ready → executing (Develop).

The User asked to update this "VERY old system", integrate it more, keep its
functionality, and clean the old Agentos stuff.
<!-- tarav.breadcrumb 353f52fa3fd1 -->
Anything removed that is not in a Git repository must land in an Attic.
<!-- tarav.breadcrumb d454aa04ae95 -->

## Knowledge.Surface

wiki

## Design narrative

### Current state (inspected 2026-10-22)

The prior assessment in this session found the subsystem cleanly layered
(imports only `l0._core`, `l0.kernel`, `l0.project`, `l1.hooks`) but shallowly
integrated: `AgentsWorkflow` is its only Tarav Type, it has no Check/POI
surface, config is read by its own loader, ~33 Agentos literals remain, and only
4 test files cover ~19k lines.
<!-- tarav.breadcrumb 32c18df0d5af -->

Agentos remnants inside the subsystem:

- Record class literals written to operational logs:
  `agentos.agent.usage-record` (`usage_registry.py:16`, also filtered on read
  at `:193`), `agentos.agent.monitor-log` (`monitor_log.py:13`),
  `agentos.agent.accounts-log` (`accounts_log.py:27`),
  `agentos.agent.providers.claude_code.statusline.last-run-log`
  (`providers/claude_code/account_status.py:880`). On disk every record in each
  log carries exactly one class (313k usage, 89k monitor, 13k accounts lines).
- Hook callback ids `agentos.agent.providers.{codex,claude-code}.account-quota-report`
  (`usage_hooks.py`); not persisted anywhere outside code (grep of homes,
  provider settings, `~/.tarav`).
- Cosmetic: thread names `agentos-monitor-*`, `User-Agent: claude-cli/agentos`,
  Codex app-server `clientInfo.name = "agentos"`, help text "Local AgentOS
  account alias".
- `# $kw:` header lines (legacy Agentos keyword index; no consumer in
  `src/`) on ~40 agent modules, many naming `Agentos.*` sources.
- Global config class `agentos.global.config`, validated by
  `l0/_core/home.py:65` and written on init (`:106`, `l0/testing.py:94`).

Deliberately left: `agentos://chat-session/` URIs (`agent/sessions.py:205,988`)
are also written by Chatlas `index_writer.py:107` into the persisted session
index, so renaming is a Chatlas data migration; `find_agentos_project_root`
belongs to `l0.project`.

### Decisions

- Rename class literals to `tarav.agent.*`. Only the usage registry filters by
  class on read; it keeps accepting the legacy literal so ~1 GB of retained
  history (burst baselines, stale fallbacks) stays readable without rewriting
  operational logs. Other logs are write-only; no reader change.
- Global config class becomes `tarav.global.config`; the loader accepts the
  legacy literal (the Studio server and older homes may still carry it), init
  writes the new one, and the local `~/.tarav/config.json` is migrated after
  depositing its prior snapshot in the Attic.
- Remove `$kw:` lines in the agent subsystem; Git history retains them.
- Integration through Checks (subsystem already has the semantics): a new
  `AgentSetup` TaravObject/CheckProvider runs
  (a) the monitor configuration loader, reporting its `CliError` as a POI
  instead of crashing the TUI, and
  (b) the existing `agent.profile_check()` checkpoints for every configured
  agent, one POI type per failed checkpoint. Compose the suite into
  `TaravSystemProject.Checks` next to the Attic suite. This would have
  surfaced the stale `claude-code/om` target as a finding.
- Alternative rejected for now: Diagram-visible AgentConfig Types — larger
  redesign, would change many call sites.

## Impl.Req.Wiki

- Product project: `tarav-py` (`/Users/pereiro/projects/taravangian-project/tarav-py`).
- Wiki: `tarav-py/notes/wiki/` (topical: `situation-chains.md`,
  `record-interfaces.md`); daily under `notes/wiki/daily/`.
- Supporting chat: Claude Code session `e6a6bdb2-fd7b-4f83-ba62-7e12a2e8e9d3`.
- Capture status: pending (completion pass).

## Execution.Plan

Core data shape: `AgentSetup(TaravObject, CheckProvider)` with record field
`config_root` (Tarav home); `AgentSetupSuite(CheckSuite)` producing
`MonitorConfigChain` (POI `MonitorConfigInvalid`) and one
`ProfileFitnessChain` per agent (POIs `AgentAccountNotRegistered`,
`AgentHomeMissing`, `AgentHomeMisaligned`, mapped from the existing checkpoint
ids). Each POI has a `POIResolutionAction`; types register in the runtime.

1. **Refactor — Agentos literals in agent subsystem.** Rename class literals,
   callback ids, thread names, client names, help text; remove `$kw:` lines;
   usage registry reads legacy class. Check: new test writes a record and reads
   both a new- and a legacy-class record; existing agent tests pass; ruff.
2. **Refactor — global config class.** `tarav.global.config` with legacy
   accepted on load; Attic deposit of current config; migrate it. Check: test
   for both literals; `tarav agent list` loads.
3. **Feature — agent setup checks.** `tarav/l1/agent/checks.py`, runtime
   registration, System Project composition. Check: tests with temp
   `TARAV_HOME` for a broken monitor target and a missing home; run suite on
   the real home and inspect findings.
4. **Docs.** `ARCHITECTURE.md` agent row mentions the check suite.

Risks / deviation triggers: profile `home_aligned` may produce POIs on the real
setup (informative, not a failure); runtime type registration conflicts; the
concurrent session editing Chatlas/breadcrumbs (do not touch its files).

## Impl.Log

- 2026-10-22: Design written in-session (Develop). Prior om account removal
  material deposited at
  `~/Documents/tarav/attic/deposits/20261022T221137Z-claude-code-om-account-retirement`.
- Start checkpoint: `7595c06` (external label-formats/notebook work from another
  session, `unknown-session`), `5fd3f0d` (this note). Baseline: 106 passed
  across agent, architecture, project-system and attic tests.
- Develop boundary: note reloaded through its Breadcrumb audit before execution.
- Slice 1 done. Removed 79 single-line `# $kw:` headers under
  `src/tarav/l1/agent/`; renamed log classes to `tarav.agent.{usage-record,
  monitor-log,accounts-log}` and the statusline last-run-log class; hook callback
  ids `tarav.agent.providers.*`; thread names `tarav-monitor-*`; Claude OAuth
  `User-Agent: claude-cli/tarav`; Codex app-server `clientInfo.name = "tarav"`;
  accounts help text. Usage registry reads `agentos.agent.usage-record` too.
  Checks: `tests/test_agent_usage_registry.py` 3 passed (new-class test failed
  against the old code); agent/architecture tests 78 passed; ruff clean; a live
  `tarav agent accounts monitor --once --json` still served all 7 targets from
  the retained registry. Breadcrumb `39a8b7f942c5` in `usage_registry.py`,
  audit ok.
- Discovered defect (out of scope, follow-up): the Codex session hook in
  `~/.codex` (`codex-main`, `home-current`) appends `source: session_hook`
  records labelled `account: br` whose payload is jp's quota (no `accountId`,
  jp's `resetsAt`). `latest_account_usage_record` picks the newest record across
  sources, so codex/br alternates between real br and jp data — the cause of the
  earlier "~55% while the account is empty" report.
- Slice 2 done (code). `GLOBAL_CONFIG_CLASS = "tarav.global.config"` in
  `l0/_core/home.py`; loader also accepts `agentos.global.config`; init and the
  `l0.testing` environment write the new class (test home dir renamed
  `tarav-home`). Checks: `tests/test_global_config_class.py` 4 passed (3 failed
  against the old loader); ruff clean; full suite 594 passed, 1 failed in
  `test_notebook_evidence.py` (another session's in-progress area; passes in
  isolation). Breadcrumb in `home.py`.
- Deviation: the live `~/.tarav/config.json` was migrated after an Attic
  deposit (`20261022T222514Z-global-config-agentos-class`) and reverted within a
  minute: the running monitor (pid 6885) and `tarav-daemon` hold the old loader,
  which rejected the new class (3 `CliError` monitor-log events). The file is
  byte-identical to the snapshot again. Migrate it after those processes restart.
- Note: the other session's checkpoint `247f77b` committed the slice 2 code as
  `unknown-session` external work before this slice's own commit; this commit
  adds the Breadcrumb label and log.
- Slice 3 done. Deviation: the checks first lived in `tarav/l1/agent/checks.py`,
  but `test_subsystem_import_graph_is_acyclic` failed — `actions` and
  `operator_context` already import `agent.current_session`, so `agent → actions`
  closed a cycle. Moved to `tarav/l2/agent_setup.py` (integration above the
  definitions it combines; Types keep `AGENTS_WORKFLOW_SHIP`).
  `AgentSetup` (TaravObject + CheckProvider) → `AgentSetupSuite`: chains
  `Tarav.Agents.MonitorConfig` (`Invalid`), `Tarav.Agents.Profiles` (`Invalid`),
  `Tarav.Agents.Fitness` (`AccountNotRegistered`, `HomeMissing`, `HomeMisaligned`;
  misalignment suppressed when the home is missing), each POI with a
  `POIResolutionAction`; registered in `l3/runtime.py`; composed into
  `TaravSystemProject.Checks` after the Attic suite.
  Checks: `tests/test_agent_setup_checks.py` 3 passed (the stale `claude-code/om`
  monitor target now yields `MonitorConfigInvalid` instead of a `CliError`);
  architecture + project-system tests 64 passed; ruff clean. Real surface:
  `tarav check --project ~/Documents/tarav/system` lists
  `Tarav.Agents.Fitness.HomeMisaligned.POI: 3` (codex-main unlisted account —
  same `~/.codex` mismatch as the session-hook defect; copilot-jp/main
  undeterminable), matching `tarav agent profile-check`.
  Breadcrumbs `436c9a74799b`, `f23bbde3b417` (`agent_setup.py`), `f6c5ccdf6df8`
  (`system.py`); `system.py` positions refreshed after line shifts; audits ok.
  `l3/runtime.py` also carries another session's unsubmitted marker
  (`0f5bad01`), committed here as found.
- Slice 4 done. `ARCHITECTURE.md`: `agent` row notes the `tarav.agent.*` log
  classes and the legacy usage-record read; new `l2.agent_setup` row. Marker
  placed after the table (a comment inside it would split the table); Breadcrumb
  `f973b051579a`; positions refreshed (122 labels, audit ok). The file also held
  another session's uncommitted PathNotebook paragraph, committed here as found.
  Check: `tests/test_architecture.py` passed.
