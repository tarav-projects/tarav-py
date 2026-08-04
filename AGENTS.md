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
- `agentos index linter` supports explicit reviewed surfaces (`--index`, `--appendix`) and complete depot-root discovery via `--depot`; depot discovery includes `000-INDEX.md`, chapter folders, `appendix/`, and `agendix/`. Agendix is a depot surface, not a separate CLI input flag.
- `src/agentos/index/model/` is the parser-backed model layer for index surfaces. It exposes `parse_index_file`, `parse_depot`, typed nodes such as `BlockHeading`/`KernelLine`/`RouterEntry`, and block-anchor query helpers for parser consumers.
- `src/agentos/index/model/identity.py` owns versioned Index-line content identity: canonical `Line.Type + body` with trailing anchors excluded. `Index.Linter/Anchor.Collision` uses this identity over the complete configured floor and permits one anchor to repeat only on identical content.
- index concept refs in block headings, router entries, and appendix/agendix filenames now accept both legacy `:` and canonical `::` type-statement sigils during the migration window; `agentos index linter` warns on legacy single-colon usage via `Index.Linter/TypeStatement.LegacySigil`, including router surfaces.
- the linter exposes an external-check socket: `run_linter(..., extra_checks=...)` and `register_index_commands(..., extra_linter_checks=...)`; bridges (e.g. the chatlas grounding-provenance check) register at the composition root (`agentos-cli`), the core never imports them (`Dependency.Profile.Split`).
- index-linter ownership is split by concern: `index/linter.py` is the stable public orchestration/reporting facade, `index/poi.py` maps internal findings to registered POI classes and deterministic instances, `_linter_models.py` owns shared state, parsed-document loading, and `LinterCheckBinding`, `_linter_structure.py` owns surface/router/depot checks, and `_linter_parser_checks.py` owns line/anchor/grounding semantic checks. Parser-backed checks declare their applicable `IndexSurfaceKind`s in bindings and execute over that projection of the complete parsed `Floor.Model`; bindings own applicability and activation, not POI class semantics.
- core parser-backed line checks: typed-line bracket syntax, known act codes, `[GR]` trailing anchor (warnings), and `AS:` outside `agendix/` as `Index.Linter/Source.Axis.Placement` (error); depot-discovered agendix files participate through explicit check bindings and appear in ordinary surface/file inventory and `--scope` resolution.
- `agentos index linter --coverage line` enables `Index.Linter/Line.Unlinked` warnings for chapter and appendix kernel lines; `--warn-unlinked` is a compatibility alias for this meter. Agendix kernel lines are checked for anchors by default.
- `agentos index linter --coverage block` enables `Index.Linter/Block.Ungrounded`: a chapter concept block is covered iff every kernel line in it carries a trailing anchor (grounding is a line property; empty blocks count covered). `--coverage all` enables both block and line meters.
- `agentos index linter --scope <path>` filters reported findings, per-check counts, summaries, and coverage meters to configured files under the file or directory scope while checks still run over the full configured depot.
- `agentos index linter --show-passed` adds an `[OK]` row for each successful check to text output; structured JSON already includes every check status.
- `agentos index blocks --depot <path> [--sort gr-density] [--scope <path>] [--limit N] [--json]` lists concept blocks with `Grounding.Density` (unique inline anchors / kernel lines) and grounded-line coverage (`grounded_lines`/`kernel_lines`); `--sort gr-density` ascending is the grounding/enrichment worklist. Computation lives in `agentos.index.model.stats` (`block_grounding_stats`), importable without the CLI.
- `agentos skw <build|check|bless|status> --skill <path> [--json]` (alias `agentos skillware`) is the Skillware build/check toolchain; project-scope `check` walks packages under `.agentos/project.json`. `agentos skw context --skill <path> [--target <runtime-file>] [--json]` audits cross-package `--reachable-from` assertions when no target is given, projects package-qualified witness paths, or resolves each local declared loading path separately with addressed runtime dependencies and whole-file `Projected.Context` assembly.
- Skillware sources use the v2 named-block `$kw` grammar and compile from `.skw/src/**/*.skw.md` (legacy `.skillware/src` remains readable during the rename window). The parser is total above its floor and emits diagnostics for malformed or unclosed machinery.
- Skillware models a `Routing.Table` as an addressed `--routing-table` annotation containing independently addressed `--router-row` annotations by explicit `--table` membership. Rows carry strict flags, aliases, semantic matching, defaults, destinations, load targets, and `--when`/`--then` prompts; `--routing-view calls|modules|full` compiles deterministic projections from that one table. Addressed routing annotations resolve to canonical nonempty dependency content; local `--load` targets and duplicate explicit keys are checked.
- A managed target may declare several addressed top-of-file `--context-loading-path` annotations with repeatable ordered `--step` runnable paths. The declaring target is the implicit final step; each path must contain `SKILL.md`, may include explicit skill-local `AGENTS.md` files before it, and requires every later dynamic edge to resolve through a `Routing.Table --load`. Repeatable `--loading-dep <file>.skw.md^<address>` values declare runtime content that must resolve, be materially compiled into its provider, and occur earlier on every path. Package configs may declare a stable `id`; registered `@<id>/path` router loads are typed whole-file cross-skill edges, and file-point `--reachable-from <runtime-file>` assertions require at least one deterministic witness path. `src/agentos/skillware/context.py` owns local projection, package graph, reachability, and dependency validation; `.skw/AGENTS.md` is builder guidance and is never projected as consumer context.
- `check` adapts stable producer kinds into the common POI report and retains existing 10-character hashes, selectors, unlock requirements, blessing records, and nonzero-on-POI exit policy. `src/agentos/skillware/` owns build/check/bless operations; `src/agentos/skw/` owns shared network drift algorithms.
- Skillware dependency roles additionally include repeatable `--dev-from` (whole-target builder context) and `--cite` (must remain explicit in compiled output). A line-1 self-closing `--context-assembly` declaration makes the complete `.skw.md` file a `Context.Assembly.Module`; its `--from` targets define its direct package-local coverage boundary. Any dependency role using an assembly-covered source without `--dev-from <assembly-file>` raises suppressible `context-assembly-bypass`; an invisible citation raises `uncited-dependency`. Role-qualified dependencies on derived recipes participate in stale detection.
- `agentos forum post|check|read` is the simple cross-project forum. It writes daily Markdown post files under `~/Documents/agentos/forum/posts/` by default (`AGENTOS_FORUM_ROOT` override) and tracks unread state in `~/.agentos/forum-cursor.json` (`AGENTOS_FORUM_CURSOR` override for tests). `agentos future forum` is retired rather than aliased.
- agent configuration ownership is split by concern: `agent/config.py` is the stable orchestration/API surface, `agent/_config_models.py` owns shared provider/config models and canonical chat-provider specs, and `agent/_config_entry.py` owns config-entry decoding and validation.
- agent run model selection is explicit-only: `agentos agent run` passes `--model` only when provided via CLI `--model` or profile `default_model`; a missing profile model does not fall back to a provider hardcoded run model.

## Compatibility Policy

- Do not add backward-compatibility aliases or compatibility layers unless explicitly requested.
- Prefer clean namespace and interface changes over preserving legacy command paths.

## Wayfinder System

- `src/agentos/wayfinder/` owns portable `Wayfinder.Reference` models, global root-location memory, composable resolution, traces, and structured resolution POIs.
- Canonical references are strict versioned JSON. `index://<package-id>/<block-path>` is sugar for the first `index.block` reference type and must parse back to that canonical object.
- The global registry lives at `~/.agentos/wayfinder/registry.json` (`AGENTOS_WAYFINDER_REGISTRY` override). It stores a root's last verified absolute location plus open relocation hints; the location is operational evidence, never resource identity or authority.
- `Wayfinder` resolves roots through the registry and delegates the remaining address to the existing domain model. The `index.block` resolver uses `agentos.index.model.parse_depot`; it does not implement a second Index parser.
- `agentos wayfinder register|resolve|check` is a thin structured-JSON CLI. Index depot dependencies now resolve package identities from Wayfinder, while `index.default_depends` remains policy in the global Agentos config.
- Agents may inspect and discover resources directly. Wayfinder is deterministic code infrastructure, not a constraint on agent exploration.

## POI System

- `src/agentos/poi/` owns the shared `POI.Instance`, `POI.Catalog`, `POI.Linter.Report`, diagnostics channel, check-selection utilities, grouped renderer, and `POI.Explain` command machinery.
- A POI class identity is its canonical Wayfinder `index.block` reference. Producer finding codes are catalog lookup keys, not a second class identity.
- `POI.Catalog.discover()` derives class registrations from the dedicated `poi/` Index chapters of Package.Skill roots registered in Wayfinder; blocks in other chapters are not POI classes.
- `POI.Instance.create` derives a stable occurrence ID from class identity, target, and concrete evidence; presentation wording and severity do not churn identity.
- Included validators retain domain findings only behind one reporting adapter; public linter JSON uses `poi_classes`, `pois`, `diagnostics`, `summary`, and `domain`.
- Skillware uses producer-established 10-character instance IDs so existing blessings and lock records remain valid. Parser failures additionally occupy the separate diagnostics channel.
- `src/agentos/skw/` owns the backend-neutral `Skw.Network` finding algorithms. The former general-looking `agentos.skwlint` module and parallel `Poi` model are retired.
- Renderers resolve each class once, present its authoritative description once, then list compact instances. A class-resolution POI remains visible beside the original instances.
- The Index linter keeps `LinterFinding` inside check execution and converts scoped findings at the reporting boundary. Each `LinterCheck` declares its POI-owning package; an undocumented finding still produces the expected class reference so documentation failure remains visible. Public JSON uses `poi_classes` and `pois`, not a duplicate `findings` representation.
- `agentos poi explain <class> [--json]` accepts a discovered finding code or a canonical/sugar Wayfinder reference. `agentos-cli` discovers one index-backed catalog and injects it into both explanation and Index rendering.

## Anchory System

- `src/agentos/anchory/` owns depot-scoped anchor dictionaries and their public library interface.
- `AnchoryDepot` receives the exact Anchory root; applications such as Chatlas derive that root from their own depot.
- Anchory owns record persistence, locking, registration, counter allocation, key composition, resolution, amendment, query, structural checks, and the depot registry.
- `AnchoryDepot.amend(..., validator=...)` runs an optional application-owned validator under the exclusive mutation lock with the depot root plus defensive copies of the current and proposed records. `register_anchory_commands(..., amend_validator=...)` carries the same hook to the CLI composition root; generic Anchory never imports application semantics.
- Key grammar: `^<ns-prefix><alloc-prefix>-<counter><tag?>` (e.g. `^c20260718-4u`). The namespace's one-letter prefix comes from its `meta.json` (`namespace set/get`); the alloc-prefix is a caller convention (chatlas: `YYYYMMDD`); the counter is anchory-allocated per (namespace, alloc-prefix) ignoring tags; the optional single-letter tag is caller-supplied decoration (chatlas: `u` user turn / `a` assistant turn).
- `register(record, *, anchor|alloc_prefix, tag, namespace)`; `resolve` returns an `AnchoryResolution` (anchor, namespace, record, `tag_mismatch`) — a mistagged citation resolves with `tag_mismatch=True` instead of not-found (keys shard by their untagged base).
- Depot registry at `~/.agentos/anchory/registry.json` (`AGENTOS_ANCHORY_REGISTRY` override): depot touches auto-register idempotently, equivalent recent entries are not rewritten, and updates prune missing depot roots; `resolve` without `--depot` runs `Pwd.Upward.Search` over registered depots nearest the cwd, then the global depot `~/.agentos/anchory/depot` (`AGENTOS_ANCHORY_GLOBAL_DEPOT` override). Registry writes are best-effort and never raise.
- `AnchoryRuntimeCache(capacity=...)` is a bounded caller-owned RAM cache for one operation. `AnchoryDepot` uses one by default, and consumers may share one across depot objects; repeated resolutions reuse copied results while register/amend/namespace mutations invalidate the depot's cached results.
- `AgentosTestEnvironment` and the `agentos-py` suite isolate both Anchory registry paths under temporary test state; tests must not write to the operator registry.
- `check` findings carry `severity`; tag-less keys in a prefixed namespace are warnings (amendable backlog), `ok` means no errors.
- Applications own record meaning, alloc-prefix conventions, tag alphabets, and any Git lifecycle around their depot. Chatlas registers into namespace `chatlas` (prefix `c`), computes the turn tag from the landing turn's producer, and `agentos chatlas anchory migrate` re-keyed the legacy bare-key depot.
- The index toolchain enforces the grammar on surfaces: `parser.py` `ANCHOR_RE` accepts composed keys and `Index.Linter/Anchor.Unprefixed` (warning) flags bare citations.
- `agentos anchory ...` is registered by `agentos-cli` as a thin wrapper over the library.
- `agentos anchory scan --depot ... --src-file ... --regex ... [--json]` is a read-only source-file query feed: it extracts anchor candidates from text, resolves them against the depot, and never mutates records.

## Bloberia System

- `src/agentos/bloberia/` owns the importable query:value record library and thin command registrar.
- `BloberiaDepot` receives one exact explicit root; v1 has no discovery, implicit/global depot, namespaces, or Anchory integration.
- canonical records are `{"_bloberia": {...}, "value": ...}`; the library owns opaque UUID identity, timestamps, and revision while applications own any JSON-serializable value.
- records live individually under `<depot>/records/`; create/edit use depot locking and atomic replacement, and `check` reports corruption without mutation.
- structural queries are recursive JSON-object subset matches over the complete canonical record; arrays and scalars compare by equality.
- public operations are `create`, `get`, `edit`, `query`, and `check`; edit replaces the full application value.
- `agentos bloberia ...` is registered by `agentos-cli` as a thin JSON CLI over the library and requires `--depot` for every operation.

## Skillware Edition History

- `src/agentos/skillware/edition_history.py` owns the importable `EditionHistoryService`, backed by one `BloberiaDepot`; CLI commands default to the owning project's `.agentos/state/bloberia/edition-history` and retain `--depot` as an override.
- file identity is the stable Agentos `project_id` plus project-relative POSIX path; record inputs resolve the full Git commit identity and commit time.
- one `skw.edition-session` application record associates one file edition with one neutral Chatlas session identity; repeated equivalent record calls are idempotent.
- every association embeds a required `chatlas.support-set.v1` object with nonempty exact event members, including at least one member from the associated session; `agentos-py` validates intrinsic structure and requires an injected `EditionSupportResolver` for live resolution without importing Chatlas.
- `list` validates associations and merges them onto the file's complete `git log --follow` edition sequence; unsupported Git commits remain visible with empty sessions and supported/unsupported metrics. The default `check` only requires one valid association per target; opt-in completeness reports `unsupported-git-edition` through `edition-history check --complete` or project `skw check --check unsupported-git-edition`.
- `agentos skw edition-history record|amend|list|check` is the thin JSON CLI; `record` requires support and `amend` replaces a named association's complete support set after file-identity and live-resolution validation. The umbrella `agentos-cli` injects Chatlas exact-event resolution; discovery and semantic association judgment remain outside `agentos-py`.

## Markdown Block Scanning Preference

- When a task requires extracting markdown blocks, use `agentos stdlib mdblocks blocks` first.
- Use `agentos stdlib mdblocks links` when you need companion `path#Lline` references for those blocks.
- Use `agentos stdlib mdblocks find --query ...` for deterministic block retrieval by text/regex.
- Prefer these commands over ad-hoc manual block parsing from raw file reads.

## Logging System

Six separate JSONL/account record mechanisms exist; they are not yet unified.

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

3. **Usage registry** — `src/agentos/agent/usage_registry.py`.
   - File: `~/.agentos/agent/usage-registry/YYYYMM-usage.jsonl` (monthly roll),
     schema v1:
     `{schema_version, class, recorded_at, provider, account, home, source, payload}`.
   - Writers: provider account-status usage fetches and future normalized hook reports.
   - Readers: account-status registry fallback and the monitor limits-tracking workflow.
   - Purpose: normalized provider usage facts only. Do not persist raw provider hook
     contexts here.

4. **Usage-report hook sample log** — `src/agentos/agent/usage_report.py`.
   - File: `~/.agentos/agent/usage-report-hook-samples/YYYYMMDD.jsonl` (daily roll),
     schema v1:
     `{schema_version, class, recorded_at, provider, account, home, status, raw_context}`.
   - Writer: `append_hook_context_sample` for explicit development sampling of provider
     hook context objects.
   - Retention: bounded per provider/account/home sample set; default last 50 samples.
   - Privacy: file mode `0600`; samples may contain sensitive prompt/path/tool context.
     This is an auxiliary development log, not the monitor-consumed usage registry.

5. **Accounts registry** — `src/agentos/agent/auth_registry.py` (state, not an event log).
   - `active.json` (pointer map), `captures.jsonl` (append-only, joins `ref_id`→
     `artifact_id` for reconstruction), `artifacts/<sha>`. No rotation/activation
     event log here.

6. **Accounts lifecycle log** — `src/agentos/agent/accounts_log.py`.
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
- Multiple JSONL stacks have divergent schemas/roll cadence/dirs; only the activity log
  has a user-facing reader. Folding shared event-log needs into one primitive is the
  broader deferred unification.
