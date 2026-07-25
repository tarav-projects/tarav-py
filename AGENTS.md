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
- index concept refs in block headings, router entries, and appendix/agendix filenames now accept both legacy `:` and canonical `::` type-statement sigils during the migration window; `agentos index linter` warns on legacy single-colon usage via `Index.Linter/TypeStatement.LegacySigil`, including router surfaces.
- the linter exposes an external-check socket: `run_linter(..., extra_checks=...)` and `register_index_commands(..., extra_linter_checks=...)`; bridges (e.g. the chatlas grounding-provenance check) register at the composition root (`agentos-cli`), the core never imports them (`Dependency.Profile.Split`).
- core parser-backed line checks: typed-line bracket syntax, known act codes, `[GR]` trailing anchor (warnings), and `AS:` outside `agendix/` as `Index.Linter/Source.Axis.Placement` (error); `agendix/` files are discovered next to `appendix/` for these checks.
- `agentos index linter --coverage line` enables `Index.Linter/Line.Unlinked` warnings for chapter and appendix kernel lines; `--warn-unlinked` is a compatibility alias for this meter. Agendix kernel lines are checked for anchors by default.
- `agentos index linter --coverage block` enables `Index.Linter/Block.Ungrounded`: a chapter concept block is covered iff every kernel line in it carries a trailing anchor (grounding is a line property; empty blocks count covered). `--coverage all` enables both block and line meters.
- `agentos index linter --scope <path>` filters reported findings, per-check counts, summaries, and coverage meters to configured files under the file or directory scope while checks still run over the full configured depot.
- `agentos index blocks --depot <path> [--sort gr-density] [--scope <path>] [--limit N] [--json]` lists concept blocks with `Grounding.Density` (unique inline anchors / kernel lines) and grounded-line coverage (`grounded_lines`/`kernel_lines`); `--sort gr-density` ascending is the grounding/enrichment worklist. Computation lives in `agentos.index.model.stats` (`block_grounding_stats`), importable without the CLI.
- `agentos skw <build|check|bless|status> --skill <path> [--json]` (alias `agentos skillware`; project-scope `agentos skw check` with no `--skill` walks every package under `.agentos/project.json`) is the Skillware toolchain: a skill's runnable files compile from `.skw/src/**/*.skw.md` sources (legacy `.skillware/src` still read during the rename window). **v2 grammar** — the annotation is a *named block* and features are additive flags, not command words: `> $kw: [address] [--flags]` opens (the `$kw` sigil rides the carrier only on the two fence lines), `> --flag value` belonging lines are self-marked by `--` (`--cont` continues the previous flag), and `> $kw. end` (bare) closes a content block. Binding is a flag — `--derived` (agent-authored, materializing), `--copy` (CPU-refreshed, materializing), `--pointer` (by-reference); other flags are `--from` (dependency edge, repeatable), `--unlock-surface` (addressed context surface represented by one registry token), `--intent`, `--note [TYPE] … ^anchor` and `--supp … ^anchor` (typed+anchored `Index.Line`s), reserved `--to`. **Closure is by role in three cases**: a materializing block owns its `end`; a `Semantic.Router` (a block with nameless `--when`/`--then` row children carrying native bodies) owns one `end` while its rows peer-close; a declaration-only block (a `--from` dependency or a `--note` attach) self-closes with no `end`. The address is one explicit `Skw.Address.Schema` locator (`#region` relative / `path#region` absolute / `^label` src-span) and is the block's identity. The parser is **carrier-split** (`model.py`): a surface-agnostic `$kw` frame core plus a per-surface `Carrier` that strips its own syntax — `MARKDOWN_CARRIER` (machinery on `>` blockquote lines, ``` fences, `#` headings = the skw-skills backend) and `CODE_CARRIER` (carrier B: the comment *is* the carrier, `# $kw:` = the skw-code backend). Two entrypoints: `parse_skw_source` (markdown) and `parse_skw_code` (code). The parser is total above its floor (`Closure.Parser::Skw`): parse errors only for malformed/unclosed machinery, everything else is blocks or opaque text. `build` refreshes copies, compiles, and writes `.skw/lock.json`; `check` is a POI linter — kinds `parse-error`/`unresolvable` (gating, per file), `never-built`/`stale-build`/`hand-edited`/`copy-drift`/`derived-stale`/`undeclared-dependency`/`unhonored-dependency`/`dangling-dependency`/`malformed-note`/`address-mismatch`/`legacy-callout`/`non-skw-annotation`/`illegal-attachment`/`missing-header` plus configured edition-history findings — printing a once-per-kind legend plus bare rows with stable 10-hex POI hashes, exiting non-zero on any POI; project-level `.skw/skw.json` may define strict `edition_history.targets`, optional `edition_history.exclude`, and optional project-relative `edition_history.depot`, which project-scope `check` runs once. The **skw-code** checks (`build.py` `_code_surface_pois`) run over code surfaces discovered by machinery presence (a `.py` file carrying a real `# $kw:` block; merely mentioning `$kw` in a string is not managed): `non-skw-annotation` (a full-line comment that is not part of a `Skw.Annotation`) is **default-off**, opt-in via `--check non-skw-annotation`, suppress-blessable; `illegal-attachment` (a block attached off the sanctioned point) and `missing-header` (a managed file with no line-1 annotation) enforce the `CodeAttachPolicy` (`DEFAULT_CODE_POLICY` = file point only, line 1, exactly one, required — a struct with strict defaults `skw.json` will later relax) and are **default-on**, non-blessable; check selection filters `report.pois` by POI-kind selector (`--check`/`--skip`/`--list-checks`, shared `skwlint` core). `Poi.Unlock.Token` registries live with their context-provider package at `.skw/unlock-tokens.json`; target packages list them explicitly through `unlock_registries` in `skw.json`. Each strict schema-v1 entry maps one opaque token to one addressed `--unlock-surface` source and one or more POI kinds; the annotation points back to its registry with `--from`. `check` reports required surfaces without disclosing tokens. `bless --poi <hash> [--unlock <token>]` and `bless --kind <poi-kind> --all [--unlock <token>]` require every configured receipt before mutation; kinds absent from configured registries retain current behavior. `status` inventories managed files. `Dotted.Name` locators resolve via depots in `.skw/skw.json` (schema: `depots`/`surfaces`/`exclude`/`projects`/`unlock_registries`/`edition_history`, cascading across sibling projects), including block-heading canonical names and `### meta` aliases; canonical headings win over alias collisions. Library: `src/agentos/skillware/` (`model.py` parsing → typed `SkwRecipe`/`SkwConstruct`/`SkwDependency` + `SkwNote`, `build.py` expansion/lock/check/bless), importable without the CLI. Skillware superseded the 583 `agentos skills imports` manifest system.
- Skillware dependency roles additionally include repeatable `--dev-from` (whole-target builder context) and `--cite` (must remain explicit in compiled output). A line-1 self-closing `--context-assembly` declaration makes the complete `.skw.md` file a `Context.Assembly.Module`; its `--from` targets are direct package-local claims. Any dependency role using a claimed source without `--dev-from <assembly-file>` raises suppressible `context-assembly-bypass`; an invisible citation raises `uncited-dependency`. Role-qualified dependencies on derived recipes participate in stale detection.
- `agentos forum post|check|read` is the simple cross-project forum. It writes daily Markdown post files under `~/Documents/agentos/forum/posts/` by default (`AGENTOS_FORUM_ROOT` override) and tracks unread state in `~/.agentos/forum-cursor.json` (`AGENTOS_FORUM_CURSOR` override for tests). `agentos future forum` is retired rather than aliased.

## Compatibility Policy

- Do not add backward-compatibility aliases or compatibility layers unless explicitly requested.
- Prefer clean namespace and interface changes over preserving legacy command paths.

## Anchory System

- `src/agentos/anchory/` owns depot-scoped anchor dictionaries and their public library interface.
- `AnchoryDepot` receives the exact Anchory root; applications such as Chatlas derive that root from their own depot.
- Anchory owns record persistence, locking, registration, counter allocation, key composition, resolution, amendment, query, structural checks, and the depot registry.
- Key grammar: `^<ns-prefix><alloc-prefix>-<counter><tag?>` (e.g. `^c20260718-4u`). The namespace's one-letter prefix comes from its `meta.json` (`namespace set/get`); the alloc-prefix is a caller convention (chatlas: `YYYYMMDD`); the counter is anchory-allocated per (namespace, alloc-prefix) ignoring tags; the optional single-letter tag is caller-supplied decoration (chatlas: `u` user turn / `a` assistant turn).
- `register(record, *, anchor|alloc_prefix, tag, namespace)`; `resolve` returns an `AnchoryResolution` (anchor, namespace, record, `tag_mismatch`) — a mistagged citation resolves with `tag_mismatch=True` instead of not-found (keys shard by their untagged base).
- Depot registry at `~/.agentos/anchory/registry.json` (`AGENTOS_ANCHORY_REGISTRY` override): every depot touch auto-registers; `resolve` without `--depot` runs `Pwd.Upward.Search` over registered depots nearest the cwd, then the global depot `~/.agentos/anchory/depot` (`AGENTOS_ANCHORY_GLOBAL_DEPOT` override). Registry writes are best-effort and never raise.
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
- `list` validates and groups associations by edition; `check` requires at least one valid association for every target and reports malformed, duplicate, or structurally corrupt records. Project-scope `agentos skw check` applies the project-level `.skw/skw.json` `edition_history` selectors once when configured.
- `agentos skw edition-history record|list|check` is the thin JSON CLI; `record` requires `--support-json` or `--support-file`. The umbrella `agentos-cli` injects Chatlas exact-event resolution; discovery and semantic association judgment remain outside `agentos-py`.

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
