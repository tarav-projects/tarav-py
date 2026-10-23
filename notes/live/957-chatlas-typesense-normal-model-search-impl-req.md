# Chatlas Typesense search over stored Normal Models

<!-- tarav.sessions
0d8af26c = codex:01a168fe-92d6-7410-a7f7-7c15cf921b95 @0d8af26c5b8dff7be764aac420b13df80bb530919d551881ae7d1afcc2400744
-->

## Impl.Abstract

Knowledge.Surface: wiki. Status: designing. Develop / Wiki / Autonomous.
Implement a thin Typesense consumer in Tarav, publish Tarav to its existing
GitHub remote, and prepare deployment to the Studio. Install Typesense only on
the Studio, never on the control Mac. The accepted initial data is conversation
text, available speaker/date/provider metadata and exact Chatlas references.
<!-- tarav.breadcrumb 9fc7f0cba05b -->

The `tarav chatlas typesense` command is machine-neutral. It knows its endpoint,
configuration and input depot; the separate global CLI router supplies SSH and
Studio selection. The entire namespace is the intended route.
<!-- tarav.breadcrumb df651b2d4399 -->
<!-- tarav.breadcrumb 5fff9b38bc5e -->

Only existing Normal Model files are searchable inputs. Do not capture providers,
read raw transcripts or the Session Index, or trigger normalization as fallback.
<!-- tarav.breadcrumb 1d44fb57dcaf -->

## Design

Inspected the canonical ChatlasNormalModel DirectoryRecord (`main.json`, events,
messages and turns JSONL), its streaming readers and typed records, the CLI
composition in l3.runtime, current CLI routing, Chatlas cache mechanics and
Typesense 30.2's collection/import/search APIs. `provide_normal_model_reader`
may regenerate from raw, so it is deliberately not used. Use
`ChatlasNormalModel.open()` and its collection readers directly.

Data shape first: TypesenseConfig, a small HTTP client, projected message chunks
and a disposable sync checkpoint. One document is one bounded slice of one
Chat.Message. IDs derive from session identity, exact message address/hash and
chunk number. Store exact text offsets, message/event references and associated
Turn references, plus source Normal Model location. Date comes only from stored
Events. Current Normal Model headers carry no project field: do not invent one
or consult the Session Index to fill it in.

Agent choices: l2.chatlas_typesense owns the integration; l1.chatlas remains
independent. Give its command registrar an ordinary injected extension hook,
composed in l3.runtime like existing command integration hooks. Standard-library
HTTP avoids installing a search engine or embedding dependencies on the Mac.
Global configuration is ~/.tarav/chatlas-typesense.json, with API credentials
read from a private key file or environment, never argv or usage logs.

Typesense owns local embedding generation with the documented
ts/all-MiniLM-L12-v2 preset and hybrid ranking. The adapter owns only deterministic
text slicing (800 characters, 80-character overlap by default), schema mapping,
bulk upserts and source references. Character bounds do not promise token bounds;
this initial preset is primarily for English, and retrieval quality is unmeasured
until real Studio testing. No training, custom embedding loop or generated labels.

Sync hashes the Normal Model inputs and projection settings. A local disposable
checkpoint skips unchanged sessions only within the same Typesense index identity.
Checkpoint a session only after every import row succeeds. Upsert first, then
remove older source versions for that same session. Failed or malformed sessions
are reported, keep previous indexed data and get no success checkpoint. Missing
model directories never cause global deletion. Reads/search/status never create
collections. Sync creates a dedicated schema if absent and rejects incompatible
existing collections; it never silently drops one.

Boundary discipline: validate config, limits, time filters, model records and
HTTP/import responses; keep keys out of diagnostics and JSON results. Source files
are read only, including when stale. Compare before/after fingerprints when
assembling a session so concurrently changing models are not silently indexed.
Subtract before adding: no existing subsystem is replaced or migrated.

## Deployment constraints

Read Tankefac root, Ansible and state instructions. They require all Studio
mutation through Ansible, with the operator running `./run ... --check` and
then apply; the Agent cannot run those playbooks. Prepare concrete state tasks,
publish the Tarav code and stop deployment at that operator step, unless the User
explicitly changes the boundary. No hand-run SSH mutation or local Typesense
installation. Services run as services with a root-owned LaunchDaemon, private
data and loopback HTTP; the personal Tarav CLI runs as pereiro.

Observed data gap: normal-model/ is Git-ignored and has zero tracked files. The
.git-only upload is still running and the remote HEAD is not yet usable. Do not
hide this by normalizing raw data. Prepare an explicit Normal Model-only transfer
as part of deployment; it leaves the raw-depot Git test unchanged.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki. Context: chatlas-normal-model.md
and cli-routing.md. Capture in chatlas-typesense.md and daily/2026-10-23.md.
Companion requests: ../../../tarav-md/notes/live/879-chatlas-typesense-wiki-impl-req.md
and /Users/pereiro/projects/tankefactory-projects/tankefac-ansible/notes/live/105-chatlas-typesense-studio-impl-req.md.
The four exact User Turns declared above were resolved in one Chatlas freshness
pass. Product, request and Wiki Breadcrumb submission/audit are pending.

## Execution.Plan

- [ ] Feature: machine-neutral HTTP adapter, Normal Model projection, resumable
  sync, status/search commands and runtime registration. Prove actual CLI calls
  against an isolated HTTP contract server: exact references, long messages,
  metadata filters, row-level import failure, missing/corrupt sources, incremental
  resumption and source/index isolation. Existing routing/Chatlas/architecture
  tests remain green. No Typesense process or embedding model runs on this Mac.
- [ ] Deployment/documentation: Studio-only reproducible Ansible installation
  of pinned Typesense 30.2, Tarav GitHub checkout/install, private configuration,
  explicit Normal Model-only transfer and global route preparation. Verify syntax
  locally; operator owns remote check/apply. Publish Tarav source to GitHub after
  inspecting the outgoing scope. No hardcoded Studio/SSH in adapter modules.
- [ ] Verification/capture: install the updated Tarav entrypoint, run appropriate
  focused tests and full root Project status --all, submit/audit implemented
  Product.Surfaces and Wiki capture, evidence commits. Test live search after the
  operator applies deployment; otherwise report it as pending, not passed.

## Impl.Log

- Start checkpoints: Python 47f63caf; Markdown a26b3f91; Ansible 67c8f7b5.
  All three trees were clean. No subagent work requested or used.
- Known deployment boundary and missing Normal Model data were reported in chat.
  CLI neutrality and Normal Model-only input are explicit subsequent User steering.
