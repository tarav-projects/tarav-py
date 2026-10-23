# Chatlas Typesense search over stored Normal Models

<!-- tarav.sessions
0d8af26c = codex:01a168fe-92d6-7410-a7f7-7c15cf921b95 @0d8af26c5b8dff7be764aac420b13df80bb530919d551881ae7d1afcc2400744
-->

## Impl.Abstract

Knowledge.Surface: wiki. Status: executing; deployment pending operator. Develop / Wiki / Autonomous.
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

### Live POC acceptance — required, not optional

The User requires following the implementation through a real deployed test:
find the first chats where Kernel.Writing was discussed. Completion requires
the running Studio Typesense product to index the stored Normal Models, then
return dated early conversations for `kernel writing` (including the historical
`kernel writting` spelling). Verify their exact Message/Turn references against
the Normal Model files and report earliest relevant sessions with quotations.
Local fixture tests or a reference scan alone do not complete this POC.
<!-- tarav.breadcrumb 6e88361e9a08 -->

Add `search --order oldest|newest|relevance` to express this through the product
API. Prepare a read-only literal reference set from existing Normal Model files
to compare against live results. Review semantic relevance: the topic is the
Kernel.Writing discipline, not operating-system kernels. Group repeated chunks
into conversations before presenting the earliest results. Report missing dates,
indexing errors and approximate-retrieval limits instead of claiming exhaustive
historical coverage. The operator-run machine boundary still applies; remain
pending until deployment and the real POC are verified.

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

- [ ] Live POC (required): after operator service/client apply, enable the
  separately configured CLI route, finish Normal Model-only ingestion, run
  oldest-first searches for Kernel.Writing and spelling variants, resolve exact
  returned source records, compare to the read-only reference set and report the
  earliest verified conversations. Do not close this request at code publication.

- [x] Feature: machine-neutral HTTP adapter, Normal Model projection, resumable
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
- Request was cold-reloaded before source edits. Implemented the l2 consumer and
  registrar injection with no lower-layer imports of the consumer. The adapter
  contains no host/SSH logic and calls no provider/cache/normalization readers.
- Initial real-CLI/HTTP contract suite: 15 tests passed in 13.75 seconds. Broader
  integration, routing, usage, Chatlas and architecture verification: 103 passed
  in 57.86 seconds. Whole-source Ruff passed; default collection is 666 tests.
- Reinstalled Tarav with `uv tool install --reinstall --editable .`; no Typesense
  executable, server or embedding model was installed on this Mac. Full root
  Project status --all is running in /tmp/typesense-root-status.json.
- Product Breadcrumb capture ran. The HTTP fixture helper has no directly
  supported User anchor: submission reports no provisional markers; its audit
  has zero labels/POIs. No invented support was added. Other changed surfaces
  submit/audit with refreshed existing positions and no unresolved POIs.
- Concurrent work: another workflow's start checkpoints 721cb46e (Python) and
  d90be81 (Markdown) absorbed this workflow's files as pre-existing external work.
  Preserve those commits and their work. Own later commits contain only this
  request's remaining changes; no other workflow's design is implemented here.
- Ops preparation: pinned native Typesense 30.2 ARM64 artifact from its official
  formula, root-owned service configuration, private index/key and loopback-only
  listener, separate personal GitHub client checkout and explicit Normal Model
  transfer. Both owning state playbooks passed syntax checks through ./run.
  YAML parsing and LaunchDaemon native plist validation passed. A first ad-hoc
  validator hit this Mac's broken Homebrew XML module, then missing Jinja in a
  different Python; used Ansible's actual interpreter to render and native plutil
  to validate, without modifying unrelated Python installations.
- Manual contract review found that stored Event times are opaque strings, and
  ordinary Chatlas Query tolerates unparsable values. Added a regression first:
  unknown-time session import failed with an ISO parse error. The consumer now
  retains exact event references and text while omitting unavailable dates,
  matching that boundary. Rechecked the regression and focused suite below.
- Final isolated adapter suite passed 17 tests, including the timestamp regression
  and oldest-first POC request. Full shared root status completed all 1,351 checks
  with no incomplete suite, but reported 25 test failures while the concurrent
  Program redesign removed states.py before updating its importers. Those are not
  presented as a Typesense pass. An isolated detached worktree at 721cb46e with
  only this workflow's fixes is running the full pytest suite independently;
  /tmp/typesense-isolated-full-tests.log retains its output.
- Read-only Normal Model inventory: 10,167 current-schema headers declare 220,029
  Messages. The completed Git-only upload was checked separately: remote/local
  HEAD 37dbfe86578f53313c6c72a5fb193f3363d50f35 matches, remote .git is 4.1 GiB,
  and git fsck --connectivity-only --no-reflogs passed. No checkout or source
  mutation was performed. Normal Models remain a separate explicit transfer.
- Live POC reference preparation read only existing Normal Model files: 132
  candidate models contain 540 literal Kernel.Writing/Writting message matches.
  Exact coordinates and excerpts remain local in
  /tmp/typesense-kernel-poc-reference.json, not in public source fixtures. Manual
  neighboring-message review separates an earlier reading/writing interface from
  the first clear proposal of the writing discipline. This is a reference scan,
  not a claimed Typesense search result or completed POC.
- Full isolated test run finished: 668 passed in 484.60 seconds. After the
  concurrent Program workflow committed its changes, current shared-checkout
  verification passed all 94 Typesense/routing/architecture tests in 37.86
  seconds. Current Typesense source/tests Ruff and diff whitespace checks passed.
- Product slice/evidence commit 3a9cea35 passed its commit Breadcrumb audit.
  Concurrent Program commits 8517607f and 15ab6232 conserved the remaining
  shared architecture/runtime files and captured labels; no external work was
  reverted or discarded. Source publication and the live operator/POC steps
  remain below; no local Typesense installation was performed.
- Outgoing source-history scan identified one historical generic-api-key false
  positive in GitleaksRun.record_example. AST review confirmed its repository key
  equals the same 40-character example Git SHA used for head, not a credential.
  Recorded the exact finding fingerprint in .gitleaksignore per the publishing
  runbook, without changing the example, suppressing a rule or rewriting history.
  Markdown outgoing history scan found no leaks. Source scan was rerun below.
