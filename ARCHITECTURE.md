# Agentos Python Architecture

`agentos-py` is one modular-monolith distribution. Subsystems are importable
namespaces, but one release and one composition root keep their contracts aligned.

## Dependency direction

```text
entrypoints (agentos.cli, agentos.daemon)
                    |
              agentos.runtime
                    |
      domain systems and integration adapters
                    |
     agentos.surfaces, stdlib, and domain foundations
                    |
               agentos._core
```

- `agentos.runtime` constructs registries and injects cross-domain adapters.
- Domain foundations do not import runtime or CLI composition to obtain defaults.
- `_core` contains dependency-free infrastructure with proven multiple consumers;
  it does not contain product policy.
- `tarav.surfaces` contains deliberately small native source models and
  normalizers. It knows host syntax and neutral declaration structure but
  never imports downstream consumers or attachment policy.
- `stdlib` contains reusable user-facing primitives matching the existing
  `agentos stdlib ...` CLI namespace.

## Namespace map

- `agentos.agent`: provider-neutral agent, account, session, and monitor behavior.
- `agentos.agent.providers`: provider registry, home/extraction infrastructure,
  and concrete adapters under one package per provider.
- `agentos.chatlas`, `canvas`, `index`, `poi`, `wayfinder`, `skillware`,
  `anchory`, `bloberia`, `hooks`, `daemon`, and `tournament`: cohesive domains.
- `tarav.chatlas2`: isolated experimental normalization. It may reuse the
  current Chatlas archive and index mechanics; current Chatlas must never
  import Chatlas2.
- `agentos.stdlib.mdblocks|prefix|refs|utils`: reusable CLI/library primitives.
- `agentos.iterante` and `agentos.iterante2`: distinct runtimes sharing only
  mechanics whose behavior is identical under `agentos.iterante._shared`.
- `agentos.skw`: backend-neutral network algorithms consumed by Index and
  Skillware; it is intentionally independent from either consumer.
- `agentos.surfaces`: native Python and Markdown normal models plus only the
  tiny source-span and diagnostic primitives they share. Its `commands` adapter
  exposes `agentos surfaces normalize` without introducing Skillware coupling.

Provider-specific code belongs at
`agentos.agent.providers.<provider>`. For example, Codex quota hooks and session
models live under `agentos.agent.providers.codex`; they do not occupy a top-level
`agentos.codex` package.

## Integration boundaries

- Hooks owns validation and sequential dispatch. Runtime injects Daemon delivery.
- Wayfinder owns reference models, registry memory, and generic resolver dispatch.
  The `index.block` resolver reads parser-backed Markdown blocks. Skillware owns
  the `managed.block` resolver because it reads configured surfaces through
  native models and Skillware adapters; it never imports addressed modules.
  Runtime injects both resolvers into commands and report adapters.
- POI adapters live under `agentos.poi.adapters` when they bridge a producer
  domain to the common reporting model.
- Skillware's `_code_model` and `_code_surfaces` modules own language-neutral
  code selection and policy. Native normalizers under `agentos.surfaces`
  produce host facts without Skillware knowledge; `agentos.skillware.adapters`
  maps those models into the common `SkwSurfaceModel`, and the shared parser
  consumes that model rather than raw host text.
- Skillware's `related_surfaces` module traverses only explicit relationships
  exposed by resolved managed blocks. Root/direct/reachable projections are
  lazy, bounded, deterministic, cycle-safe, and retain partial diagnostics.
- Tarav POI producers use stable project-rooted managed-block references. Their
  canonical class blocks are annotations on producer code; the optional generic
  `POI.Catalog` primitive is not part of Tarav's executable discovery path.
- `tarav.index.report` adapts Index findings through the shared `POIInstance`
  model and builds the single JSON-serializable `Index.Linter.Run` document.
  Text and JSON renderers consume that document; neither reruns selection,
  class aggregation, or occurrence limiting.
- Index linting resolves one required project through `.tarav/project.json`, discovers
  native depots from their `000-INDEX.md` routers, and consumes annotated code exclusively
  from the typed `code_surfaces` selected by the project's `.skw/skw.json`. Skillware adapts
  those files through Tarav's native surface parsers; Index never performs its own language
  globbing or annotation recognition. Chat evidence is selected by typed references. No
  cwd-local HEAD or touch-authority manifest participates in a verdict.
- `tarav.index.capture` consumes that same discovered `SurfaceLine` model for Markdown and
  SKW hosting kinds, verifies grounded attachment triplets, and materializes missing
  `LineRecord`s without inventing a second annotation-specific record path.
- Markdown normalization is also consumed at parser boundaries by
  `agentos.stdlib.mdblocks`, `agentos.index.model`, and Chatlas Index-audit
  extraction. Separators, Index nodes, anchors, and lint policy remain in those
  domain models; their linters and downstream clients do not consume native
  surface models directly.
- Chatlas command behavior lives in `_command_support.py`; `commands.py` owns the
  public parser composition and registrar.
- Chatlas2 owns its raw-model recognition, normalization, event tape,
  annotations, and hermetic conformance corpus. The corpus stores best-effort
  anonymous provider artifacts by content digest; its anonymizer is an opaque
  text transform with no provider or Raw.Model dependency. Current Chatlas is
  used only by explicit corpus preparation, while committed checks reconstruct
  specimens locally. Codex `codex.rollout.5f98` and Claude Code
  `claude.transcript.1ecc` / `claude.transcript.b17b` are opaque recognized raw-model
  identities dispatched through compatible normalizers into the same Normal Model.
  The prompt-source-capable Claude normalizer also recognizes accepted human
  suggestions, typed text-block lists, and non-meta legacy-shaped direct
  messages retained inside mixed artifacts. Both Claude normalizers map
  human-origin `queued_command` attachments to user events/messages at their
  nested queue timestamp and may use them as the nearest evidenced loaded
  context for a following assistant request. Timed Claude records whose side
  is not structurally established remain `Unresolved.Event`.
  Raw-model identity remains provenance and does not enter stable place derivation.
  Normal Model v5 separates provider-derived stable places
  from current normalized state for both events and Chat.Message annotations.
  Event hashes cover only class, origin, start time, and deliberately projected
  provider-neutral content. Native records are absent by default; an explicit
  raw option adds source-associated, normalizer-owned diagnostic evidence at the
  model root without affecting identity or annotations. Membership
  carries full Event.Ref values, and stored Event.Ref or Chat.Message.Ref
  assertions resolve as MATCHED, AMENDED, or MISSING against only the supplied
  current model. Normalization is stateless, so superseded normalized states
  remain a concern of the raw archive and its Git history. Completed compact
  models may be atomically materialized into a disposable session-addressed
  cache: one metadata file plus independently readable event, message, and
  loaded-context JSONL collections. Cache freshness couples the session,
  ordered transcript fingerprints, Normal Model schema, and producer commit;
  raw-attached diagnostic models are never cached. A canonical provider hides
  this cache policy from consumers: default requests validate and transparently
  rebuild, refresh requests force replacement, and raw diagnostics compute
  directly. Chat.Message adds a
  provider-neutral primary-text projection plus pure discovery, derived-time,
  and bounded-neighborhood operations. Exact-session message reads stream the
  provider's cached collections and apply optional limits during iteration.
  `tarav chatlas2 views` provides disposable `full`, `transcript`, `user`, and
  `events` read projections without introducing a second model or cache policy;
  collection bounds stop their JSONL iteration, while `full` returns the
  complete canonical model unchanged. Replay and zip-transcript behavior remain
  outside this first migration slice. Query keeps session discovery separate
  from content reads: `chatlas2 sessions query` reuses Session.Index metadata,
  while `chatlas2 chat query` verifies one Chat.Message predicate against the
  current cache of every bounded selected session and returns only Normal Model
  records and stable refs. URI selection is direct; offset/limit pages provide
  bounded transcript traversal and return the next verified-message offset.
  Candidate scans and future indexes are never result
  authority. An explicit top-level `chatlas2 --update` brackets any leaf command
  with one structural delta pass through the maintained Provider.Home adapter,
  Raw.Archive copier, and Session.Index writer. It does not copy Chatlas1's
  result-driven escalation ladder and does not materialize Normal Models;
  ordinary cache validation observes changed archived sources afterward. The
  first Anchory consumer requests
  complete models through the same provider and
  stores exact user message refs and diagnostic `at` values in a separate
  `chatlas2` namespace while reusing the generic depot and Index-line attachment
  identity; it owns no cache-specific loader or model slot.
  Runtime is the only command-composition boundary between Chatlas2 and the
  maintained CLI.

## Shared infrastructure rule

Promote code to `_core` only after matching semantics exist in multiple domains.
`_core.persistence` is the model: it owns same-directory, fsynced atomic text and
JSON replacement, while each caller retains its schema, validation, and locking.

Architecture tests in `tests/test_architecture.py` enforce namespace placement,
the Hooks/Daemon boundary, and an acyclic top-level subsystem graph.
