# AGENTS.md

## Keep AGENTS.md Updated (required)

- Updating this file is **required**, not optional, whenever a change affects what it
  documents (architecture, subsystems, logging, CLI surface, conventions, gaps).
- Treat the doc update as part of the change — land it in the same unit of work, not as
  a later follow-up. If a section becomes stale or wrong, fix it in the same pass.

## Python Tooling Preference

- Use `uv` as the default Python environment and package management system.
- Prefer `uv sync`, `uv run`, and `uv tool install` over direct `pip`/`venv` workflows.

## Run agentos cli
- check `agentos --version` to confirm that it is installed on the system.
- run `agentos` to see the available commands and options.
- Prefer direct `agentos ...` shell commands over `uv run agentos ...` when `agentos` is already installed.
- The `agentos` executable is owned by `agentos-cli`, not this package. After changing CLI entrypoint or command-registration code, refresh the installed executable from `agentos-cli/` with `uv tool install --reinstall --editable .` so `~/.local/bin/agentos` stays in sync.
- Changes limited to library/runtime code in `agentos-py` do not require reinstalling `agentos-cli` unless they affect the installed CLI behavior you are actively testing.
- `agentos index linter` supports both explicit surfaces (`--index`, `--appendix`) and depot-root discovery via `--depot`; prefer `--depot` for package-skill indexes that follow `000-INDEX.md` + chapter folders + `appendix/`.
- `src/agentos/index/model/` is the parser-backed model layer for index surfaces. It exposes `parse_index_file`, `parse_depot`, typed nodes such as `BlockHeading`/`KernelLine`/`RouterEntry`, and block-anchor query helpers for parser consumers.
- the linter exposes an external-check socket: `run_linter(..., extra_checks=...)` and `register_index_commands(..., extra_linter_checks=...)`; bridges (e.g. the chatlas grounding-provenance check) register at the composition root (`agentos-cli`), the core never imports them (`Dependency.Profile.Split`).
- core parser-backed line checks: typed-line bracket syntax, known act codes, `[GR]` trailing anchor (warnings), and `AS:` outside `agendix/` as `Index.Linter/Source.Axis.Placement` (error); `agendix/` files are discovered next to `appendix/` for these checks.
- `agentos index linter --coverage line` enables `Index.Linter/Line.Unlinked` warnings for chapter and appendix kernel lines; `--warn-unlinked` is a compatibility alias for this meter. Agendix kernel lines are checked for anchors by default.
- `agentos index linter --coverage block` enables `Index.Linter/Block.Ungrounded`, measuring chapter concept blocks by presence of `[GR]`-anchored `Grounding.Head` appendix evidence. `--coverage all` enables both block and line meters.
- `agentos index linter --scope <path>` filters reported findings, per-check counts, summaries, and coverage meters to configured files under the file or directory scope while checks still run over the full configured depot.
- `agentos index blocks --depot <path> [--sort gr-density] [--scope <path>] [--limit N] [--json]` lists concept blocks with `Grounding.Density` (unique inline anchors / kernel lines) and the evidence-board flag; `--sort gr-density` ascending is the grounding/enrichment worklist. Computation lives in `agentos.index.model.stats` (`block_grounding_stats`), importable without the CLI.
- `agentos skillware <build|check|status> --skill <path> [--json]` is the Skillware toolchain: a skill's runnable files compile from `.skillware/src/**/*.skw.md` sources (markdown plus `[!skw]` callout recipes — `copy` bodies CPU-refreshed, `derived` bodies agent-authored in src). `build` refreshes copies, compiles, and writes `.skillware/lock.json`; `check` reports `never-built`/`stale-build`/`hand-edited`/`copy-drift`/`derived-stale`/`ok` and exits non-zero on findings (derived dep hashes persist until the body is re-derived — build never blesses stale derived content); `status` inventories managed files. `Dotted.Name` locators resolve via depots in `.skillware/skillware.json`. Library: `src/agentos/skillware/` (`model.py` parsing, `build.py` expansion/lock/check), importable without the CLI. Skillware superseded the 583 `agentos skills imports` manifest system.

## Compatibility Policy

- Do not add backward-compatibility aliases or compatibility layers unless explicitly requested.
- Prefer clean namespace and interface changes over preserving legacy command paths.

## Anchory System

- `src/agentos/anchory/` owns depot-scoped anchor dictionaries and their public library interface.
- `AnchoryDepot` receives the exact Anchory root; applications such as Chatlas derive that root from their own depot.
- Anchory owns record persistence, locking, registration, prefix allocation, resolution, amendment, query, and structural checks.
- Applications own record meaning, allocation prefix conventions, and any Git lifecycle around their depot.
- `agentos anchory ...` is registered by `agentos-cli` as a thin wrapper over the library.
- `agentos anchory scan --depot ... --src-file ... --regex ... [--json]` is a read-only source-file query feed: it extracts anchor candidates from text, resolves them against the depot, and never mutates records.

## Markdown Block Scanning Preference

- When a task requires extracting markdown blocks, use `agentos stdlib mdblocks blocks` first.
- Use `agentos stdlib mdblocks links` when you need companion `path#Lline` references for those blocks.
- Use `agentos stdlib mdblocks find --query ...` for deterministic block retrieval by text/regex.
- Prefer these commands over ad-hoc manual block parsing from raw file reads.

## Logging System

Four separate JSONL mechanisms exist; they are not yet unified.

1. **Activity log (command logger)** — `src/agentos/_core/project_command_log.py`.
   - File: `~/.agentos/activity/YYYYMM.jsonl` (monthly roll), schema v2:
     `{schema_version, timetag, event_type, command, argv, status, payload}`.
   - Writers: `record_project_command_from_args` from prefix/utils/forum/mission/skills
     handlers — project commands only.
   - Reader: `agentos … utils cmd-logger {path,tail,query}` (rare-use activity log).

2. **Monitor log** — `src/agentos/agent/monitor_log.py`.
   - File: `~/.agentos/agent/monitor-log/YYYYMMDD.jsonl` (daily roll), schema v1:
     `{schema_version, class, recorded_at, event, tick, provider, account, home, payload}`.
   - Writers: monitor loop (`monitor_start`, `workflow_error`, `config_stale`) and
     workflows (`target_transition`, …) — **operational events only**. Best-effort:
     never raises into the monitor loop. (Rotation events go to the accounts log, #4,
     not here.)
   - Reader: none (write-only; no CLI surfaces it).

3. **Accounts registry** — `src/agentos/agent/auth_registry.py` (state, not an event log).
   - `active.json` (pointer map), `captures.jsonl` (append-only, joins `ref_id`→
     `artifact_id` for reconstruction), `artifacts/<sha>`. No rotation/activation
     event log here.

4. **Accounts lifecycle log** — `src/agentos/agent/accounts_log.py`.
   - File: `~/.agentos/agent/accounts-log/YYYYMMDD.jsonl` (daily roll), schema v1:
     `{schema_version, class, recorded_at, event, provider, account, method, home, payload}`.
   - Writers: emitted **inside the lifecycle primitives** — `capture` (capture.py, new
     capture only), `activate` (activation.py), `materialize` (materialization.py, real
     home write only), `rotate` (rotation.py, real pointer move only). Emit only on a real
     effect — never on `dry_run`/`check`/no-op. Secret-free: ids only, never `Auth.Data`.
     Best-effort: never raises into a primitive. Because the `_all` sweeps and the CLI
     handlers funnel through the per-item primitives, every consumer logs uniformly.
   - Reader: `accounts_log.read_recent_events(*, event, limit)` — a programmatic,
     newest-first tail (used by the monitor). No user-facing CLI yet.
   - Monitor: the TUI `account-rotation` block (last-5 rotations) reads `event="rotate"`
     from this log via `read_recent_events`. The monitor sweep is drive-only and keeps
     no in-state ring; rotation logging lives in the `rotate` primitive.

### Known gaps (integration targets)
- The accounts log has no **user-facing reader CLI** yet — `agentos accounts log`
  (tail/query) is the next follow-up (a programmatic reader exists).
- Two parallel JSONL stacks (activity + monitor) with divergent schemas/roll cadence/dirs;
  only the activity log has a reader. Folding all stacks into one shared event-log primitive
  is the broader deferred unification.
