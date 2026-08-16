# AGENTS.md

## Keep AGENTS.md Updated (required)

- Updating this file is **required**, not optional, whenever a change affects what it
  documents (architecture, subsystems, logging, CLI surface, conventions, gaps).
- Treat the doc update as part of the change — land it in the same unit of work, not as
  a later follow-up. If a section becomes stale or wrong, fix it in the same pass.

## Python Tooling Preference

- Use `uv` as the default Python environment and package management system.
- Prefer `uv sync`, `uv run`, and `uv tool install` over direct `pip`/`venv` workflows.
- `_DEPRECATED/` contains tracked historical snapshots and is excluded from Ruff's maintained-tree checks; repository-wide Ruff commands still cover the active distribution, tests, and tooling.

## Modular Monolith

- `agentos-py` is the single maintained Python distribution. It contains the runtime, umbrella CLI, daemon, Chatlas, Canvas, Iterante, and Iterante v2 beneath `src/agentos/`.
- `agentos.runtime.create_runtime()` is the composition root. CLI and daemon adapters import it; neither spawns the umbrella CLI to perform subsystem work.
- Cohesive systems remain importable namespaces. Provider-neutral orchestration lives in `agentos.agent`; every concrete provider adapter lives under `agentos.agent.providers.<provider>`. Reusable CLI primitives live under `agentos.stdlib`. Do not recreate retired top-level provider or stdlib packages.
- `ARCHITECTURE.md` is the maintained namespace and dependency-direction map. Architecture changes must update it and `tests/test_architecture.py` together.
- `agentos._core.persistence` owns the shared fsynced atomic text/JSON replacement contract. Callers retain schema validation, domain locking, and error translation.
- The distribution owns four scripts: `agentos`, `agentos-daemon`, `iterante`, and `iterante2`.
- The maintained distribution must resolve from ordinary package sources without sibling-repository path dependencies.

## Run agentos cli
- check `agentos --version` to confirm that it is installed on the system.
- run `agentos` to see the available commands and options.
- Prefer direct `agentos ...` shell commands over `uv run agentos ...` when `agentos` is already installed.
- All Python entrypoints are owned here. After changing an entrypoint or installed command behavior, refresh them with `uv tool install --reinstall --editable .` from `agentos-py`.
- `agentos index linter` supports explicit reviewed surfaces (`--index`, `--appendix`) and complete depot-root discovery via `--depot`; depot discovery includes `000-INDEX.md`, chapter folders, `appendix/`, `agendix/`, and first-class `issues/`. Agendix and issues are depot surfaces, not separate CLI input flags.
- `src/agentos/index/model/` is the parser-backed model layer for index surfaces. It exposes `parse_index_file`, `parse_depot`, typed nodes such as `BlockHeading`/`KernelLine`/`RouterEntry`, and the shared `IndexLineAnchorOccurrenceGroup` used by anchor-aware parser consumers.
- `src/agentos/index/policy.py` centralizes built-in surface policy. `issues/NNN-issues.md` contains grounded temporary `Issue.I####[.Dotted.Name]` blocks; `agentos index issues --depot ...` computes open/resolved standing from reviewed `[DC]` lines without importing Chatlas.
- `src/agentos/index/model/identity.py` separates canonical Index-line body, typed statement, and attached triplet identities. The attachment triplet is `Line.Type + body + Anchor.Id` with trailing anchors excluded from the body; `Index.Linter/Anchor.Collision` uses it over the complete configured floor and permits one anchor to repeat only on an identical triplet.
- `src/agentos/index/line_manifest.py` builds the parser-owned `agentos.index-line-manifest.v3`: selected line identity, `Line.Type`, `Index.Line.Body`, source fingerprints, enclosing block, block-bounded sibling context, and explicit `agreed|ambiguous` anchor-occurrence standing. `agentos index line manifest show|materialize` is the canonical command; application relationship projection and volatile materialization are injected at the composition root.
- A normal `agentos index linter --depot ...` run writes a fingerprinted, non-authoritative anchor locator beneath the current workspace's ignored `.agentos/state/`. Anchor-selected manifests verify and parse only the locator's named source files when it is current, then fall back to full depot parsing when it is missing or stale. Comprehensive occurrence agreement remains a normal-lint responsibility.
- index concept refs in block headings, router entries, and appendix/agendix filenames now accept both legacy `:` and canonical `::` type-statement sigils during the migration window; `agentos index linter` warns on legacy single-colon usage via `Index.Linter/TypeStatement.LegacySigil`, including router surfaces.
- the linter exposes an external-check socket: `run_linter(..., extra_checks=...)` and `register_index_commands(..., extra_linter_checks=...)`; bridges (e.g. the Chatlas grounding-provenance check) register in `agentos.cli`, while the lower-level Index modules never import them (`Dependency.Profile.Split`).
- index-linter ownership is split by concern: `index/linter.py` is the stable public orchestration/reporting facade, `index/poi.py` maps internal findings to registered POI classes and deterministic instances, `_linter_models.py` owns shared state, parsed-document loading, and `LinterCheckBinding`, `_linter_structure.py` owns surface/router/depot checks, and `_linter_parser_checks.py` owns line/anchor/grounding semantic checks. Parser-backed checks declare their applicable `IndexSurfaceKind`s in bindings and execute over that projection of the complete parsed `Floor.Model`; bindings own applicability and activation, not POI class semantics.
- core parser-backed line checks: typed-line bracket syntax, known act codes, `[GR]` trailing anchor (warnings), `AS:` outside `agendix/` as `Index.Linter/Source.Axis.Placement` (error), and issue filename/identity/typed-grounded-line structure; depot-discovered agendix and issues files participate through explicit check bindings and appear in ordinary surface/file inventory and `--scope` resolution.
- `agentos index linter --coverage line` enables `Index.Linter/Line.Unlinked` warnings for chapter and appendix kernel lines; `--warn-unlinked` is a compatibility alias for this meter. Agendix kernel lines are checked for anchors by default.
- `agentos index linter --coverage block` enables `Index.Linter/Block.Ungrounded`: a chapter concept block is covered iff every kernel line in it carries a trailing anchor (grounding is a line property; empty blocks count covered). `--coverage all` enables both block and line meters.
- `agentos index linter --scope <path>` filters reported findings, per-check counts, summaries, and coverage meters to configured files under the file or directory scope while checks still run over the full configured depot.
- `agentos index linter --anchor <anchor>` is the line-subject projection: optional citation sigils are normalized, every requested anchor must exist, parser-bound checks receive only matching `KernelLine`s, and JSON publishes joinable `Index.Line` subjects. Depot-wide reportable checks are listed under `selection.omitted_depot_checks`; naming one explicitly with `--check` opts it back in.
- `agentos index linter --show-passed` adds an `[OK]` row for each successful check to text output; structured JSON already includes every check status.
- `agentos index blocks --depot <path> [--sort gr-density] [--scope <path>] [--limit N] [--json]` lists concept blocks with `Grounding.Density` (unique inline anchors / kernel lines) and grounded-line coverage (`grounded_lines`/`kernel_lines`); `--sort gr-density` ascending is the grounding/enrichment worklist. Computation lives in `agentos.index.model.stats` (`block_grounding_stats`), importable without the CLI.
- `agentos skw` (alias `agentos skillware`) is the Skillware build/check toolchain. Package build/check/bless/status use `--skill <path>`; project-scope `check` and exact `bless --poi <hash>` omit it. A project check starts at `.agentos/project.json`, then evaluates nested packages and typed `code_surfaces` from the project `.skw/skw.json`. `agentos skw context --skill <path> [--target <runtime-file>] [--json]` audits cross-package `--reachable-from` assertions when no target is given, projects package-qualified witness paths, or resolves each local declared loading path separately with addressed runtime dependencies and whole-file `Projected.Context` assembly.
- `src/agentos/surfaces/` owns deliberately small host-native normal models. Shared primitives stop at `SourceSpan` and `SourceDiagnostic`; Python and Markdown models grow only for facts required by current consumers and never import Skillware. Markdown fence facts use marker-aware complete boundaries and are consumed at parser/adapter boundaries by Skillware, `stdlib.mdblocks`, `index.model`, and Chatlas Index audit; downstream linters continue consuming their domain models. Architecture tests enforce that dependency direction.
- `agentos surfaces normalize --file <path> [--language python|markdown] [--json]` exposes native normal models. Language is inferred from `.py`, `.pyi`, `.md`, or `.markdown` when omitted and unresolved extensions are errors; file input is always a named option.
- Project `.skw/skw.json` `code_surfaces` entries carry `language`, project-relative `include`, and optional `exclude` globs. The shared selector/policy engine lives in `skillware/_code_model.py` and `_code_surfaces.py`; `skillware/adapters/` maps native models into one `SkwSurfaceModel`, which the shared parser consumes. `_code_python.py` is composition only.
- Configured Python code is strict: every file requires one line-1 Skw annotation, every other attachment is illegal, and every tokenizer-confirmed comment outside Skw machinery is a default-on `Non.Skw.Annotation` POI unless the Python normalizer classifies its complete syntax as a recognized external-tool directive. The conservative directive allowlist lives in `surfaces/python/normalize.py`; malformed or prose-bearing near-directives remain POIs. Project-scope `agentos skw bless --poi <hash>` suppresses one exact exceptional comment through `.skw/lock.json`; bulk code-comment blessing is rejected.
- Skillware sources use the v2 named-block `$kw` grammar and compile from `.skw/src/**/*.skw.md` (legacy `.skillware/src` remains readable during the rename window). The parser is total above its floor and emits diagnostics for malformed or unclosed machinery.
- Skillware models a `Routing.Table` as an addressed `--routing-table` annotation containing independently addressed `--router-row` annotations by explicit `--table` membership. Rows carry strict flags, aliases, semantic matching, defaults, destinations, load targets, and `--when`/`--then` prompts; `--routing-view calls|modules|full` compiles deterministic projections from that one table. Addressed routing annotations resolve to canonical nonempty dependency content; local `--load` targets and duplicate explicit keys are checked.
- A managed target may declare several addressed top-of-file `--context-loading-path` annotations with repeatable ordered `--step` runnable paths. The declaring target is the implicit final step; each path must contain `SKILL.md`, may include explicit skill-local `AGENTS.md` files before it, and requires every later dynamic edge to resolve through a `Routing.Table --load`. Repeatable `--loading-dep <file>.skw.md^<address>` values declare runtime content that must resolve, be materially compiled into its provider, and occur earlier on every path. Package configs may declare a stable `id`; registered `@<id>/path` router loads are typed whole-file cross-skill edges, and file-point `--reachable-from <runtime-file>` assertions require at least one deterministic witness path. `src/agentos/skillware/context.py` owns local projection, package graph, reachability, and dependency validation; `.skw/AGENTS.md` is builder guidance and is never projected as consumer context.
- `check` adapts stable producer kinds into the common POI report and retains existing 10-character hashes, selectors, unlock requirements, blessing records, and nonzero-on-POI exit policy. `src/agentos/skillware/` owns build/check/bless operations; `src/agentos/skw/` owns shared network drift algorithms.
- Skillware dependency roles additionally include repeatable `--dev-from` (whole-target builder context) and `--cite` (must remain explicit in compiled output). A line-1 self-closing `--context-assembly` declaration makes the complete `.skw.md` file a `Context.Assembly.Module`; its `--from` targets define its direct package-local coverage boundary. Any dependency role using an assembly-covered source without `--dev-from <assembly-file>` raises suppressible `context-assembly-bypass`; an invisible citation raises `uncited-dependency`. Role-qualified dependencies on derived recipes participate in stale detection.
- `agentos forum post|check|read` is the simple cross-project forum. It writes daily Markdown post files under `~/Documents/agentos/forum/posts/` by default (`AGENTOS_FORUM_ROOT` override) and tracks unread state in `~/.agentos/forum-cursor.json` (`AGENTOS_FORUM_CURSOR` override for tests). `agentos future forum` is retired rather than aliased.
- agent configuration ownership is split by concern: `agent/config.py` is the stable orchestration/API surface, `agent/_config_models.py` owns shared provider/config models and canonical chat-provider specs, and `agent/_config_entry.py` owns config-entry decoding and validation.
- agent run model selection is explicit-only: `agentos agent run` passes `--model` only when provided via CLI `--model` or profile `default_model`; a missing profile model does not fall back to a provider hardcoded run model.

## Hook System

- `src/agentos/hooks/` owns the provider-neutral `Agentos.Hook` model, exact-name callback registry, sequential dispatcher, and thin CLI registrar.
- `HookInvocation` carries `name`, optional open-string `ctx_type`, and an opaque JSON-object `ctx`; dispatch never interprets provider fields or selects callbacks from `ctx_type`.
- `HookRegistry.register(...)` preserves registration order. Dispatch gives each callback an isolated copy of the original context, ignores callback return values, and continues after ordinary callback exceptions.
- `HookRegistry` has one sequential callback lane. The hook CLI never dispatches callbacks locally: every valid invocation is submitted once to the daemon, which owns callback discovery and execution.
- Callback failures log only hook name, callback identity, and exception type through the `agentos.hooks` logger. Raw context and exception text are excluded because provider context may contain prompts or secrets.
- The public ingress is `agentos hook --name <hook-name> [--ctx-type <ctx-type>] [--wait]` with exactly one context source: canonical harness input `--ctx-from-stdin` or manual inline input `--ctx <json>`. Default success means daemon acceptance; `--wait` holds the socket through dispatch completion and fails when completion cannot be observed.
- Provider-specific lifecycle mappings and subsystem callback registrations belong in subsystem registrars composed by `agentos.runtime`; the hook foundation has no provider mappings.
- `agent.statusline.context` means an agent harness has published its current native status-line context. Claude Code maps its native `statusLine` callback here; the daemon-owned account-usage consumer stores only supported quota facts, writes changed snapshots immediately, and throttles identical account observations to one per 60 seconds.
- The built-in Chatlas `agent.turn.stop` daemon callback runs the canonical `chatlas_update(...)` pipeline narrowed to the hook's provider and active session id with incremental append trust. It does not warm a separate model, produce semantic `Chat.Index` surfaces, or spawn an agent.

## Chatlas Source Selection

- `chatlas.sources` is the authority for native provider-home ingestion. Each source may set boolean `scannable` (default `true`); non-scannable sources remain configured inventory but never become live provider instances for update, provider query, or live GC scanning.
- Source selection does not mutate or hide existing Chatlas-owned raw/index data. `ProviderHomeAdapter` retains its per-session symlinked-source rejection as a final ingestion defense.

## Chatlas2 Experiment

- `src/tarav/chatlas2/` owns the isolated Chatlas2 Normal Model experiment. It may import current Chatlas archive and index mechanics, but `src/tarav/chatlas/` must not import Chatlas2.
- Chatlas2 reviews every relevant retained artifact, versions each independently, and assembles a retention-biased chronological event tape. Keep semantic annotations shallow and conservative; raw artifacts remain the fallback authority.
- Supported vertical slices are Codex `codex.rollout.5f98` plus Claude Code `claude.transcript.1ecc` (`promptSource`-capable) and `claude.transcript.b17b` (legacy no-`promptSource`). Raw-version suffixes are opaque identities, not a sequence. The prompt-source-capable Claude mapping recovers accepted human suggestions, typed text-plus-image content, and non-meta legacy-shaped direct messages retained in mixed artifacts. In either Claude family, a human-origin `queued_command` attachment is a `User.Event` and user `Chat.Message` starting at the attachment's queue timestamp; it may become the nearest conservative input in the following `Agent.Loaded.Context`. Claude timed records become `Unresolved.Event` when neither user nor agent origin is structurally supported; untimed sidecar records remain available only in the raw artifact.
- Raw-model version is dispatch/provenance metadata and never participates in `Event.Address` or `Chat.Message.Address`; Claude's two compatible normalizers share parsing and event assembly but keep separate direct user-message mapping rules.
- Chatlas2 Normal Model v6 gives events, `Chat.Message`, and `Chat.Turn` separate provider-derived stable addresses plus hashes over deliberately selected state. `Chat.Turn` is derived after the lossless multi-artifact event union as maximal same-origin user/agent runs; unresolved events remain on the tape ungrouped, every message has exactly one containing turn, and a turn may have zero or several messages. Each event carries an opaque native-payload digest excluded from `Event.Hash` and `Chat.Message.Hash` but included in `Chat.Turn.Hash`, so whole-turn drift does not broaden text-grounding identity. Normal Events contain no provider-native records by default; `content` remains the narrow message-text projection. `normalize --include-raw` optionally adds source-associated normalizer evidence, and normalization remains stateless.
- Chatlas2 caches completed compact models under `chatlas2/model-cache/<identity_hash>/` as `metadata.json` plus independently readable event, message, turn, and loaded-context JSONL collections. Cache freshness derives from session identity, ordered transcript path/size/mtime fingerprints, Normal Model schema, and producer commit. The cache is disposable and never stores `--include-raw` models. Ordinary consumers use the canonical Normal Model provider: it reuses a fresh cache or transparently rebuilds a missing/stale one; `normalize --refresh` forces replacement, while `normalize --include-raw` computes directly without touching the cache. Cached readers apply `Scan.Decode.Verify`: safe literal/regex scans select candidates, JSON decoding follows only for candidates, and decoded object checks remain authoritative with limits counted after verification.
- `tarav chatlas2 views list|get` is the first read-projection route over canonical Normal Model content. Its implemented views are `full` (the unchanged complete model), `transcript` (all chronological Chat.Message records), `user` (user-side Chat.Message records), and `events` (the chronological event tape). Collection views stream through the provider reader and apply `--limit` during iteration; `full` rejects a limit. Views are disposable and own no normalization, identity, or cache policy. `replay` and `zip-transcript` are intentionally not ported yet.
- `tarav chatlas2 messages list|find` exposes chronological message lookup, full support-member refs, and diagnostic time through the provider's stream reader; `--limit` bounds matching records during iteration. Chatlas2 Anchory requests complete Normal Model content through the same provider and owns no cache policy or model-retention slot. Generic `anchory support preview|register` stores ordered user-message support in `tarav.chatlas2.message-support.v1`; line `preview|register|resolve|batch` uses `tarav.chatlas2.line-anchor-dossier.v2` with independent support, gate, and provenance relationships while remaining able to read v1 dossiers. Runtime readers dispatch mixed current-Chatlas `c…` and Chatlas2 `d…` records. Every stored member is `{session, message_address, message_hash, at}`; `at` is redundant evidence, never reference identity.
- `tarav chatlas2 turns list|get` streams compact turns, resolves a containing turn by either turn address or message address, and hydrates selected turns on demand. Hydration loads only member event/message cache records and the exact raw JSONL lines cited by their source observations; it does not attach native payloads to the cached Normal Model.
- `tests/chatlas2/conformance/` is the hermetic, content-addressed conformance corpus. Artifact ingress is always the documented interactive `prepare` then `register` route; tests use included anonymous artifacts and never depend on a live Chatlas archive.
- `tarav chatlas2 corpus verify|check|list` reads the corpus; `corpus ingest prepare|register` grows it explicitly. Preparation uses an opaque-text anonymizer and rechecks recognized specimens before registration.

## Chatlas Touch Heuristics

- `tarav chatlas touch-heuristics quotes --session <selector>` is the read-only quotation detector over one authoritative Normal Model. It accepts a native session id, canonical URI, or identity-hash prefix and defaults to `--min-length 40 --threshold 0.75 --lookback 5`.
- Each qualifying user/predecessor-assistant turn pair emits `Touch.Evidence` with both `Normal.Turn.Ref`s, original and normalized aligned spans, score, match kind, and assistant-turn distance. Findings are returned only; the tool never annotates or persists them.

## Daemon System

- `src/agentos/daemon/` owns the local closed Unix-socket protocol, client, foreground runtime, serial worker lane, control-command registrar, and operational log.
- Hook submission is acceptance-only by default. A waiting request keeps its connection open until the same serial worker completes dispatch; callback failures remain isolated and still produce a completed dispatch. There is no inline fallback or durable inbox: default delivery failure is logged and dropped, while `--wait` reports failure.
- `agentos daemon run|start|status|stop|install|uninstall` controls the runtime and its user service. `run` stays in the foreground; without an installed service, `start` launches the dedicated `agentos-daemon` entrypoint detached. With the service installed, `start` delegates to launchd.
- `src/agentos/daemon/launchd.py` owns the macOS user LaunchAgent at `~/Library/LaunchAgents/org.agentos.daemon.plist`. `install` atomically writes an Agentos-owned plist and bootstraps it; `uninstall` boots it out and removes only an ownership-validated plist.
- The LaunchAgent invokes the absolute `agentos-daemon` executable, uses `RunAtLoad=true` for login startup, and uses `KeepAlive.SuccessfulExit=false` for abnormal-exit recovery. A clean socket-driven `daemon stop` exits successfully and therefore remains stopped until login or explicit `start`.
- Requests can only ping, stop, or submit a validated hook invocation. Accepted hook work lives in process memory and runs serially; arbitrary command execution, retry, durable spooling, and inline fallback are not part of this POC.
- Hook delivery waits only for acceptance. An unavailable daemon is logged and does not fail the harness-facing hook command.

## Compatibility Policy

- Do not add backward-compatibility aliases or compatibility layers unless explicitly requested.
- Prefer clean namespace and interface changes over preserving legacy command paths.

## Wayfinder System

- `src/agentos/wayfinder/` owns portable `Wayfinder.Reference` models, global root-location memory, composable resolution, traces, and structured resolution POIs.
- Canonical references are strict versioned JSON. `index://<package-id>/<block-path>` is sugar for the first `index.block` reference type and must parse back to that canonical object.
- The global registry lives at `~/.agentos/wayfinder/registry.json` (`AGENTOS_WAYFINDER_REGISTRY` override). It stores a root's last verified absolute location plus open relocation hints; the location is operational evidence, never resource identity or authority.
- `Wayfinder` resolves references through injected domain resolver functions. Index owns the `index.block` resolver in `agentos.index.wayfinder`; it uses `agentos.index.model.parse_depot` and does not implement a second parser. Runtime composes it with the generic Wayfinder dispatcher.
- `agentos wayfinder register|resolve|check` is a thin structured-JSON CLI. Index depot dependencies now resolve package identities from Wayfinder, while `index.default_depends` remains policy in the global Agentos config.
- Agents may inspect and discover resources directly. Wayfinder is deterministic code infrastructure, not a constraint on agent exploration.

## POI System

- `src/agentos/poi/` owns the shared `POI.Instance`, `POI.Catalog`, `POI.Linter.Report`, diagnostics channel, check-selection utilities, grouped renderer, and `POI.Explain` command machinery.
- A POI class identity is its canonical Wayfinder `index.block` reference. Producer finding codes are catalog lookup keys, not a second class identity.
- `agentos.index.poi_catalog.discover_poi_catalog()` derives class registrations from the dedicated `poi/` Index chapters of Package.Skill roots registered in Wayfinder; the lower-level `POI.Catalog` model does not import Index.
- `POI.Instance.create` derives a stable occurrence ID from class identity, target, and concrete evidence; presentation wording and severity do not churn identity.
- Included validators retain domain findings only behind one reporting adapter; public linter JSON uses `poi_classes`, `pois`, `diagnostics`, `summary`, and `domain`.
- Skillware uses producer-established 10-character instance IDs so existing blessings and lock records remain valid. Parser failures additionally occupy the separate diagnostics channel.
- `src/agentos/skw/` owns the backend-neutral `Skw.Network` finding algorithms. The former general-looking `agentos.skwlint` module and parallel `Poi` model are retired.
- Renderers resolve each class once, present its authoritative description once, then list compact instances. A class-resolution POI remains visible beside the original instances.
- The Index linter keeps `LinterFinding` inside check execution and converts scoped findings at the reporting boundary. Each `LinterCheck` declares its POI-owning package; an undocumented finding still produces the expected class reference so documentation failure remains visible. Public JSON uses `poi_classes` and `pois`, not a duplicate `findings` representation.
- `agentos poi explain <class> [--json]` accepts a discovered finding code or a canonical/sugar Wayfinder reference. `agentos.cli` discovers one index-backed catalog and injects it into both explanation and Index rendering.
- Chatlas command ownership is split at the CLI boundary: `chatlas/commands.py` composes the public parser tree while `chatlas/_command_support.py` owns command actions and shared argument translation.

## Anchory System

- `src/agentos/anchory/` owns depot-scoped anchor dictionaries and their public library interface.
- `AnchoryDepot` receives the exact Anchory root; applications such as Chatlas derive that root from their own depot.
- Anchory owns record persistence, locking, registration, counter allocation, key composition, resolution, amendment, query, structural checks, and the depot registry.
- `AnchoryDepot.amend(..., validator=...)` runs an optional application-owned validator under the exclusive mutation lock with the depot root plus defensive copies of the current and proposed records. `register_anchory_commands(..., amend_validator=...)` carries the same hook to the CLI composition root; generic Anchory never imports application semantics.
- Key grammar: `^<ns-prefix><alloc-prefix>-<counter><tag?>` (e.g. `^c20260718-4u`). The namespace's one-letter prefix comes from its `meta.json` (`namespace set/get`); the alloc-prefix is a caller convention (chatlas: `YYYYMMDD`); the counter is anchory-allocated per (namespace, alloc-prefix) ignoring tags; the optional single-letter tag is caller-supplied decoration (chatlas: `u` user turn / `a` assistant turn).
- `register(record, *, anchor|alloc_prefix, tag, namespace)` stores a prebuilt record. `register_derived(record_factory, *, alloc_prefix, tag, namespace)` allocates first and derives an anchor-dependent record atomically under the same lock. `resolve` returns an `AnchoryResolution` (anchor, namespace, record, `tag_mismatch`) — a mistagged citation resolves with `tag_mismatch=True` instead of not-found (keys shard by their untagged base).
- Depot registry at `~/.agentos/anchory/registry.json` (`AGENTOS_ANCHORY_REGISTRY` override): depot touches auto-register idempotently, equivalent recent entries are not rewritten, and updates prune missing depot roots; `resolve` without `--depot` runs `Pwd.Upward.Search` over registered depots nearest the cwd, then the global depot `~/.agentos/anchory/depot` (`AGENTOS_ANCHORY_GLOBAL_DEPOT` override). Registry writes are best-effort and never raise.
- `AnchoryRuntimeCache(capacity=...)` is a bounded caller-owned RAM cache for one operation. `AnchoryDepot` uses one by default, and consumers may share one across depot objects; repeated resolutions reuse copied results while register/amend/namespace mutations invalidate the depot's cached results.
- `AgentosTestEnvironment` and the `agentos-py` suite isolate both Anchory registry paths under temporary test state; tests must not write to the operator registry.
- `check` findings carry `severity`; tag-less keys in a prefixed namespace are warnings (amendable backlog), `ok` means no errors.
- Applications own record meaning, alloc-prefix conventions, tag alphabets, and any Git lifecycle around their depot. Chatlas registers into namespace `chatlas` (prefix `c`), computes the turn tag from the landing turn's producer, and `agentos chatlas anchory migrate` re-keyed the legacy bare-key depot.
- The index toolchain enforces the grammar on surfaces: `parser.py` `ANCHOR_RE` accepts composed keys and `Index.Linter/Anchor.Unprefixed` (warning) flags bare citations.
- `agentos anchory ...` is registered by `agentos.cli` as a thin wrapper over the library.
- `agentos anchory scan --depot ... --src-file ... --regex ... [--json]` is a read-only source-file query feed: it extracts anchor candidates from text, resolves them against the depot, and never mutates records.

## Bloberia System

- `src/agentos/bloberia/` owns the importable query:value record library and thin command registrar.
- `BloberiaDepot` receives one exact explicit root; v1 has no discovery, implicit/global depot, namespaces, or Anchory integration.
- canonical records are `{"_bloberia": {...}, "value": ...}`; the library owns opaque UUID identity, timestamps, and revision while applications own any JSON-serializable value.
- records live individually under `<depot>/records/`; create/edit use depot locking and atomic replacement, and `check` reports corruption without mutation.
- structural queries are recursive JSON-object subset matches over the complete canonical record; arrays and scalars compare by equality.
- public operations are `create`, `get`, `edit`, `query`, and `check`; edit replaces the full application value.
- records may live in a `Bloberia.Record.Namespace`: a subfolder under `records/`, of arbitrary depth, addressed as a relative path prefix. `create`/`get`/`edit`/`query` take an optional `namespace`; `namespaces()` lists the prefixes present without reading a record.
- a namespace is **placement only** — it carries no meaning Bloberia enforces and is not part of record identity. It is data *outside* the record, so an application that lets a fact live only in the path owns that risk; the namespace should duplicate something already inside the value.
- omitting the namespace preserves the old meaning: reads walk `records/` recursively so a flat depot stays readable, and `get(id)` searches every namespace rather than failing. That fallback costs one walk of the depot — pass the namespace when you know it.
- `check` walks recursively. A check that only globbed `records/*.json` would report **ok** on a namespaced depot by finding nothing, which is worse than no check.
- unsafe namespaces (absolute, `..`, empty segments) are rejected rather than silently rerooted.
- locking stays depot-wide; namespaces partition reads, not writes.
- `agentos bloberia ...` is registered by `agentos.cli` as a thin JSON CLI over the library and requires `--depot` for every operation.

## Workspaces

- `src/agentos/workspaces/` owns `Run.Workspace`: one-run agentic workspaces rooted at `~/.agentos/workspaces/<date>-<slug>/` (`AGENTOS_WORKSPACES_ROOT`, then `--root`). A workspace is a `Volatile.Surface` — no stable surface may depend on it, the dependency arrow points outward only, and content leaves by copy rather than by anything linking in. That is what makes deleting one routine.
- **Exactly one surface is required, its `AGENTS.md`.** Prose an agent landing cold needs (kind, purpose, provenance, how to run it) plus a `### manifest` section of `- key: value` lines carrying `kind`, `created`, `status`, and `extracted`. One file, so prose and machine state cannot drift; a sidecar JSON would be a second authority that quietly disagrees with the thing people edit. Absent keys read as defaults — a hand-written workspace is still a workspace — but an unknown `status` is an error naming the file.
- **`status` and `extracted` are what make disposal decidable.** Nothing is deleted while nobody can tell whether anything left. `sweep` reads exactly those two fields plus mtime.
- **`init` is gated on an unlock receipt.** `workspaces/GUIDE.md` is a package resource carrying its `Skw.Surface.Token` in its last line; `agentos workspace guide` prints it, and `init --unlock <token>` compares against the token parsed from that file. The surface is the authority for its own token — there is no registry here. Refusal names the guide command and **never** prints the token, per `Poi.Bless`'s rule that refusal identifies the missing surface without disclosing it. Rotate the token when the guide changes materially: that forces a re-read and is the migration lever for the workspace contract.
- **This is a second, smaller unlock path beside Skillware's**, not a generalization of it. Skillware's (`skillware/_build_core.py`, `<package>/.skw/unlock-tokens.json`) resolves `.skw.md` surfaces and is consumed only by `Poi.Bless` against POI kinds. Routing `workspace init` through it would need cross-repo Wayfinder addressing for one consumer. If a third consumer appears, unify them then — see `Impl.Req` 623 D1.
- **Git inside a workspace, never around one.** `init` runs `git init` plus one commit, and refuses when the resolved root is itself inside a worktree. A failed repository init removes the directory rather than leaving a workspace without its history.
- `agentos workspace guide|init|list|show|sweep`. `list` reports every directory including ones it cannot parse, marked `unreadable` — a disposal listing that silently drops rows is worse than one that admits confusion. `sweep` lists candidates with the reason each qualified and deletes nothing; `--apply` deletes exactly that set. Unreadable workspaces are never swept: those are the ones a person should look at.

## Tournament System

- `src/agentos/tournament/` owns the domain-blind comparative-evaluation engine: it asks a consumer definition which two players compete, presents each one, frames the match itself, spawns one judge, validates the answer, and appends a verdict. It never interprets what a player represents.
- The durable object is the append-only verdict record. Any ranking is a read-side fold and is deliberately not stored — `Standing` is parked by design decision.
- **The engine holds no pool and enumerates no pairs.** Each call to the definition's `match_players` hook yields the players of one match; returning `None` ends a run before its budget. Declaring a pool up front is not a precondition for running matches, which is what lets a pool be unbounded, computed, or streamed.
- **Matches are N-way, and arity is a per-match choice.** `match_players` may return 2 to 26 players and may return a different count on each call; the engine imposes no size. Arity is the resolution knob: a 4-way match fills twelve comparison-slots per judge run against a pairwise match's two, so grading 1,033 items at ten comparisons each costs ~861 spawns instead of ~5,165. Where that stops paying against judge discrimination is empirical, not designable. The upper bound of 26 is label exhaustion, not a design position.
- **The engine composes the prompt, not the consumer.** `runner.compose_verbatim` builds the `Match.Verbatim` from the definition's `question`, its optional `criteria`, the presentations under engine-owned `A:`…`Z:` labels, and the answer contract. The judge ranks *positions*; the engine decodes each back through the order it ran. A consumer free to label the candidates could silently invert every verdict it recorded, so that hazard is unreachable rather than guarded.
- **The prompt is described as data, then rendered.** `template.py` builds a `Match.Template` — `{template_version, sections}` naming its parts by `sha256:` address — and `render_template` produces the bytes. The three component kinds are the `Match.Brief` (question plus criteria, one component because they change together), one `Player.Presentation` per player, and the `Match.Footnote.Template` (ranking instruction plus both submit commands, holes unbound). Position labels are generated from arity and are not a component: engine frame, but interleaved between presentations rather than trailing them. Sections record `origin` — `definition` or `engine` — so a reworded question and a changed submit instruction are distinguishable rather than both reading as "template changed".
- **Templates exist so old verdicts survive new engines.** Rendering is pure data work, so reassembly needs a renderer that reads templates, not the engine version that ran the match. `tests/test_tournament_template.py` pins the frame that predates templates as an oracle and asserts byte equality across arities 2/4/26, criteria present and absent, ticket present and absent. That equality is the load-bearing property: a verbatim that cannot be rebuilt exactly cannot be checked against `verbatim_hash`.
- **A `Match.Frame` is the definition's composed prompt.** `frame.py` owns a closed node vocabulary — `Text`, `Raw`, `Table`, `Sequence`, `Section`, `Cite`, `Players`, `Shuffle` — that a definition assembles into one `Frame` and returns from the `match_frame` hook. The node types are **structural, not domain-named**: there is no `Question` or `Glossary` type, there is a `Table` and what it means is its label. Naming instances as types is exactly what made the three-section template inextensible, and it is why the type vocabulary of the index typing tournament had nowhere to live but inside each of five duplicated cards.
- **Content is open; operations are closed.** New material composes out of the node types without an engine change. Operations cannot, because each needs engine machinery — seeding, recording, reproducibility. `shuffle` is the whole set until something earns a second entry. A definition calling `random.shuffle` itself produces a permutation the engine can neither reproduce nor record, which is a hole in the instrument rather than a convenience.
- **`shuffle` is refused where order is meaning.** A `Sequence` is ordered by construction and a `Table` may declare `ordered=True`; both raise at construction rather than being silently permuted. An unordered table is a lookup cited by key, so shuffling only removes a positional hint — which is the point, since listing exactly the codes in play would leak the answer set.
- **The engine owns the roster; the definition owns the card.** `Players()` is a placeholder, never a list a definition fills — control substitution, sampling, and position labelling stay engine work. Exactly one must appear: none renders a prompt with no candidates, two would ask the engine which labelling is real.
- **A cite resolves before any spawn.** `present_player` may return a node instead of a string, and a `Cite(table, key)` in a card renders as the bare key while the material lives once in the frame's table. `runner._prepared` is where the two hooks meet, so it is the only place the cite can be checked — and it runs before the ticket is minted, because an unresolvable reference is a definition bug that must not cost a judge run.
- **Every node addresses under `(type, version, payload)`.** The version is inside the hash because a node type whose rendering changes must not rebuild an old verdict into text its judge never saw.
- **Two template versions, both renderable.** Without a frame `build_template` emits version 1 — the fixed brief/candidates/footnote — and that path is unchanged byte for byte. With a frame it emits version 2, where the whole frame is one component and the footnote still trails. One component and not one per node: the frame is identical across every match of a run, so the per-match variation is the presentations and that is already where dedup pays.
- **A permutation is a binding, not template content.** `frame_operations` rides `template_bindings` beside the ticket id, keyed by the shuffle site's depth-first index. Two matches of one frame that shuffled differently share one template address and rebuild to different bytes — which is what makes the shared table dedup while each match stays exactly reproducible.
- **Per-run values are bindings, not template content.** The ticket id, the depot root as it appears in the rendered command, and arity fill the footnote's holes at render time. They ride the verdict as `template_bindings` rather than inside the template — a template restating its run's ticket would be unique per run and dedup nothing. The depot root is there because it is rendered into the judge's prompt and recorded nowhere else; without it a depot that moved would fail every reassembly for a reason no record explains.
- **`components.py` is the depot-wide `Match.Component.Registry`.** `put(bytes) -> "sha256:…"` writes under the hash of the content and is a no-op when present; `get` raises `ComponentMissingError` naming the address. Layout shards on the first two hex characters. Writes go temp-file-then-`os.replace` because `run_pool` fans out over threads and several matches register the same component at once — content addressing makes that idempotent, but a reader must never see a half-written file. The temp name is unique per *writer*, not per content: threads racing to one final path is the normal case, and a shared temp name has one consume the other's file.
- **The verbatim is derived, never stored.** The verdict carries `template` (one address, which resolves the whole run) and `template_bindings`; `reassemble(store, verdict)` renders and returns. It does not verify and does not repair — comparing the rebuilt hash to `verbatim_hash` is the caller's call, because a silent repair would destroy the only evidence of a mismatch. A verdict recorded before templates raises `TemplateMissingError`, distinct from a missing component.
- `agentos tournament verbatim --tournament X --verdict Y [--json]` rebuilds and prints the exact prompt that verdict's judge received. `--json` carries `verbatim`, `verbatim_hash`, `rebuilt_hash`, and `matches`; the text form prints a warning line when they disagree.
- **Two required hooks, no defaults:** `match_players` and `match_identity`. A definition missing either fails at load naming both. `present_player` defaults to `str(player)`, `verdict_slot` to `{}`, `controls` to no pool, `match_frame` to no frame, and `player_label`/`match_label` to unlabeled.
- **Labels are recorded grouping tags the engine never interprets.** `player_label(ctx)` returns an opaque string or `None` for the player on the context; `match_label(ctx)` does the same for the whole match. They land on the verdict as `player_labels` (unlabeled players are absent rather than null, so the mapping *is* the labeled set) and `match_label`, ride the ticket for the same reason `controls` does, and the slot may not shadow either. An empty or whitespace-only return is a `HookReturnError` — that is an invisible group in the fold, not an unlabeled player.
- **A label never reaches the judge.** It is reader-side, exactly like a control's declared band: a presentation tagged `registered` would be the strongest signal in the prompt and would void every verdict carrying it. `_labels` runs beside identity, before the shuffle, and nothing it returns enters the render path. `test_labels_never_reach_the_judge` pins this on *rendered bytes* — a labeled match and its unlabeled twin must be byte-identical — rather than on the current call graph.
- **Labels are free to vary across a player's matches.** The engine never compares a label against a previous verdict's, so a fold groups over label *occurrences* rather than assuming one label per player. That also makes relabeling mid-tournament a readable event instead of a corruption.
- **A label describes; match identity distinguishes.** If two matches should not have their verdicts averaged together, that is identity's job. Labeling the difference and leaving identity alone yields a clean-looking split in the read over a silently pooled average underneath it.
- **Run parameters are consumer-owned and engine-opaque.** `agentos tournament run|preview --param key=value` (repeatable, last-wins) reaches every hook as `ctx.params`, a `MappingProxyType` — the same mapping is handed to every call of a run, so a mutable view would let one hook change what the next one sees. `_run_params` rejects a malformed entry at the boundary with a `CliError`; nothing validates *meaning*, because no engine code path reads a key. The engine's own knobs stay named CLI parameters with their own validation points.
- **Parameters are deliberately not on the verdict.** A verdict already carries its players, presented order, verbatim hash, and template address, so a parameter that only selects *which* matches get produced needs no record — the produced match is self-describing. A parameter that changes what a given identity *means* is the existing consumer obligation to make it a different match.
- **Controls calibrate the instrument.** `controls(ctx)` returns a *pool* — `{player: "high"|"low"}` — and the module attribute `control_rate` (default `0.0`) says how often the engine substitutes one in. There is no middle band: mid-pack is where noise lives, so a middle expectation is not falsifiable at any affordable volume. The hook returns the pool rather than one control per call because *which* control lands in *which* match is engine work.
- **Substitution precedes identity.** One control at most replaces one pool player, both drawn by the engine, before `present_player` or `match_identity` sees the roster — a match carrying a control is a different match from the one without, and substituting later would merge two different comparisons under one id. A control already among the match's players is skipped rather than re-drawn: re-drawing would make the effective rate depend on pool overlap. `preview_match` substitutes too, because a preview renders a *valid* match.
- **Controls exist to separate three indistinguishable null results.** A flat pool means the pool has no signal, *or* the question is ineffective, *or* the judge cannot discriminate. If a `low` control does not sink and a `high` one does not rise, the instrument is reporting on itself and the pool's flatness says nothing. The engine records the bands and holds them apart; it does not judge whether a control converged — that is a reader's call.
- The verdict envelope and the ticket both carry `controls`. It travels on the ticket because `submit` builds the verdict from the ticket alone and never loads the definition the bands were declared in; a ticket file written before the field loads as uncontrolled. The slot may not shadow it.
- `report.py` reports controls in their own `controls` list, with the band beside the counts, and excludes them from `players`. Folded in, a low control sits in the weak tail looking exactly like a finding. Their comparisons stay on the pool's rows — those are the matches that calibrate anything. `poi.py` reads `players`, so a control can no longer raise `Player.LowStanding`, which is exactly right.
- Identity and the verbatim hash are separate mechanisms. Identity is consumer-supplied, required, and derived **before** the shuffle from the players in canonical order — `HookContext` deliberately does not carry the presented order, because identity that varied with the shuffle would make every repeat run a distinct match and stop accumulation. The hash is engine-added evidence taken **after** the shuffle. A consumer may adopt the hash as its identity, but nothing makes that a default.
- Hooks may randomize *which* players meet — that is sampling strategy. The engine randomizes exactly two things: presentation order and control substitution. `locking.verify` checks for writes after every hook call, and `random` writes nothing.
- `pairing.py` holds strategies **for definitions, not for the engine**: `round_robin`, `least_played`, `random_pair`, `random_players` (N-ary). Nothing in the engine imports it and a test asserts that. Note the snapshot freezes the definition file but *not* its imports — see `Issue.I0001` in `tarav-pkg/issues/100-issues.md`, deliberately open.
- A `Tournament.Depot` is one rooted directory defaulting to `~/.agentos/tournament` (`AGENTOS_TOURNAMENT_DEPOT`, then `--depot`, override it). `definitions/<tournament-id>/` holds the frozen snapshot and its lock sidecar; `records/<tournament-id>/` is the Bloberia namespace holding that tournament's record and every verdict. Listing tournaments reads namespace directories instead of scanning the depot. `components/` is the fourth child and the only one that is **not** per-tournament — dedup across tournaments is free, so it is allowed.
- The tournament id is minted by `TournamentStore`, not adopted from Bloberia's record id: the namespace must exist before the record is written, and a tournament is a namespace rather than a record.
- The definition file is snapshotted at creation and every match executes the snapshot — load-bearing, not convenient, since a definition edited mid-tournament silently makes later verdicts incomparable. `load_definition` creates; `open_definition` reopens by **verifying** the snapshot, because re-recording would re-authorize a tampered one.
- **An outcome is a strict total ordering or a no-contest.** A decided answer is `{"outcome": ["C", "A", "D", "B"]}` — position labels, best first; a refusal is `{"outcome": "no_contest", "refusal_reason": "..."}`. `validate_verdict_answer(answer, arity=N)` requires a permutation of exactly the labels presented: a missing, repeated, or invented label is a contract violation, not a silently dropped comparison. A repeat is the judge placing two players at equal rank, which the design forbids — equivalence is recovered from orderings that disagree across repeated matches. Validation is mandatory; iterante's opt-in leniency is deliberately not carried over.
- **The judge is never asked to attribute its refusal.** Which player or question a refusal indicts is read from the records, which already carry who was in which refused match — asking the judge was asking it to do the fold's job from inside one match.
- The verdict envelope carries `ordering` (the players best first, `null` for a no-contest), `refusal_reason`, and the `ticket` that produced it. Arity is `len(players)` and is never stored separately, because a second copy could only disagree with the first.
- **The judge answers by running a command, not by printing.** `runner.py` mints a `Tournament.Ticket` before the spawn and renders a fully formed `agentos tournament submit --depot ... --ticket ... --ranking A,B,C` into the frame; `stdout` is not read at all. This is what makes a contract violation actionable — the error reaches the agent that made it, in the context that can still fix it, instead of surfacing to an orchestrator after the spawn is gone. The example ranking in that command is deliberately rotated, never the presentation order: with `A,B,C,D` as the template, a judge copying it and a judge genuinely finding the candidates already ranked are indistinguishable in the records.
- **A judge needs its provider's tool grant or it will silently do nothing.** `JudgeSpawn.agent_argv` passes provider flags through; for claude-code that is `--agent-arg=--allowedTools --agent-arg=Bash`. Use the `=` form — argparse's `append` swallows a bare `--allowedTools` as a flag. Without the grant the spawn declines the command, exits 0, and the match records as unanswered.
- **A validated verdict outranks a nonzero exit.** Once the answer travels out of band the exit code stops being evidence that anything failed; the runner asks whether the ticket was redeemed. The exit code is recorded on the ticket.
- `src/agentos/tournament/tickets.py` owns `<depot>/tickets/<id>.json`: plain mutable JSON, deliberately **not** Bloberia, which is what keeps verdicts append-only. A ticket carries everything the verdict needs except the outcome, so a submission names only its ticket and its ranking and a confused judge cannot describe a match it was never given. Arity resolves from the ticket too.
- Only *contract* rejections count against the attempt cap (default 3) — those are the ones a retry can fix. A submission against a redeemed or exhausted ticket is refused without incrementing.
- Redemption marks rather than deletes. Collection is by age: `run` sweeps before minting and `agentos tournament gc` does it explicitly, with a one-week horizon that makes racing a live submission structurally impossible.
- `runner.py` spawns judges with `process_mode="capture"`; the captured stream is no longer parsed but the spawn still must not inherit a terminal.
- `run_pool` fans out over a `ThreadPoolExecutor`, keeps results in hook order, and collects failures as data in a `failures[]` envelope rather than raising. That envelope is the orchestration primitive. Repeat runs of a match are the feature, so nothing is skipped on prior success.
- `report.py` folds its player set **from the verdicts**, not from a declared pool. A player whose payload was edited out of the definition keeps its accumulated history instead of vanishing from the read.
- `report.py` no longer folds an attribution axis; `reason_samples` is keyed by refused match.
- **Pairwise comparisons are extracted at read time, never stored.** For ranks `i < j` the earlier player beat the later one, so one 4-way ordering yields six comparisons and one 10-way yields forty-five. Keeping the match whole is deliberate: a later fold can still see which comparisons shared one judgment. `wins`/`losses` therefore grow with arity while `matches` counts one per match — do not conflate them. No weighting, discounting, or rank-distance treatment is applied here; reading is the consumer's concern.
- `poi.py` owns three engine-scoped POI classes (`Tournament.Linter/Player.LowStanding`, `Player.Unjudgeable`, `Definition.Incoherent`). Two floors, not one: `MIN_MATCHES_FOR_STANDING = 6` and a lower `MIN_MATCHES_FOR_UNJUDGEABLE = 3`, because clustered refusals are a sharper finding than a low score.
- `agentos tournament create|list|run|show|submit|gc|preview|verbatim` is registered by `agentos.cli`.
- `tournament preview --tournament X [--match-index N] [--seed N] [--json]` renders one real match and prints it. It mints a genuine ticket, so the output is byte-identical to what a judge receives and can be answered by hand with `tournament submit` — that is the difference from `run --dry-run`, which mints nothing and therefore shows a prompt missing its submit instruction. Use it to iterate on a definition's `question` and `criteria` without spending spawns.
- Tickets carry a `kind` — `match` or `preview` — defaulted so files written before the field still load. It marks **provenance, never permission**: a preview ticket is a real ticket, answerable by hand, and answering it records an ordinary verdict. The field exists because an unredeemed preview would otherwise be indistinguishable from a match a judge failed to answer, and an afternoon of tuning would erase the one place judge failure is recorded. `sweep()` and `tournament gc` report removals split by kind for the same reason. `create` takes only a definition. `run` carries `--budget --concurrency --provider --profile --home --model --account --timeout --dry-run`, and `--budget` is an upper bound the definition may end early.
- Known debt: no adaptive sampling, no cross-tournament aggregation, and no match cache — the last left open pending the chivo registry question.

## Skillware Edition History

- `src/agentos/skillware/edition_history.py` owns the importable `EditionHistoryService`, backed by one `BloberiaDepot`; CLI commands default to the owning project's `.agentos/state/bloberia/edition-history` and retain `--depot` as an override.
- file identity is the stable Agentos `project_id` plus project-relative POSIX path; record inputs resolve the full Git commit identity and commit time.
- one `skw.edition-session` application record associates one file edition with one neutral Chatlas session identity; repeated equivalent record calls are idempotent.
- every association embeds a required `chatlas.support-set.v1` object with nonempty exact event members, including at least one member from the associated session; `agentos-py` validates intrinsic structure and requires an injected `EditionSupportResolver` for live resolution without importing Chatlas.
- `list` validates associations and merges them onto the file's complete `git log --follow` edition sequence; unsupported Git commits remain visible with empty sessions and supported/unsupported metrics. The default `check` only requires one valid association per target; opt-in completeness reports `unsupported-git-edition` through `edition-history check --complete` or project `skw check --check unsupported-git-edition`.
- `agentos skw edition-history record|amend|list|check` is the thin JSON CLI; `record` requires support and `amend` replaces a named association's complete support set after file-identity and live-resolution validation. `agentos.cli` injects `agentos.chatlas` exact-event resolution; the foundation service retains no Chatlas dependency.

## Markdown Block Scanning Preference

- When a task requires extracting markdown blocks, use `agentos stdlib mdblocks blocks` first.
- Use `agentos stdlib mdblocks links` when you need companion `path#Lline` references for those blocks.
- Use `agentos stdlib mdblocks find --query ...` for deterministic block retrieval by text/regex.
- Prefer these commands over ad-hoc manual block parsing from raw file reads.

## Logging System

Seven separate JSONL/account record mechanisms exist; they are not yet unified.

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
   - Writers: provider account-status usage fetches, the Codex `agent.turn.stop`
     quota consumer (`source=session_hook`), and the Claude
     `agent.statusline.context` consumer (`source=statusline_hook`).
   - Readers: account-status registry fallback and the monitor limits-tracking workflow.
   - Hook observations are resolved to a registered account by provider identity and
     may be read account-wide even when the observing home differs from the monitor
     home. Purpose: normalized provider usage facts only. Do not persist raw provider
     hook contexts here.

4. **Hook context sample log** — `src/agentos/hooks/sampling.py`.
   - File: `~/.agentos/hooks/context-samples.jsonl`,
     schema v1:
     `{schema_version, class, recorded_at, hook_name, ctx_type, ctx}`.
   - Writer: the built-in `agent.prompt.submit` callback for explicit development
     sampling of opaque provider hook contexts.
   - Retention: bounded per hook-name/context-type sample set; default last 50 samples
     across time.
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

7. **Daemon operational log** — `src/agentos/daemon/log.py`.
   - File: `~/.agentos/daemon/log/YYYYMMDD.jsonl` (daily roll), schema v1.
   - Writers: hook delivery and daemon lifecycle/acceptance/dispatch/failure paths.
   - Privacy: directories are `0700`, files are `0600`, and records exclude opaque
     context plus exception text; only hook/context type, callback id, event id, stage,
     process id, and exception type are eligible.

### Known gaps (integration targets)
- The accounts log has no **user-facing reader CLI** yet — `agentos accounts log`
  (tail/query) is the next follow-up (a programmatic reader exists).
- Multiple JSONL stacks have divergent schemas/roll cadence/dirs; only the activity log
  has a user-facing reader. Folding shared event-log needs into one primitive is the
  broader deferred unification.
