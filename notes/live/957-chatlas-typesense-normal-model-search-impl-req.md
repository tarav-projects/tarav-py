# Chatlas Typesense search over stored Normal Models

<!-- tarav.sessions
0d8af26c = codex:01a168fe-92d6-7410-a7f7-7c15cf921b95 @0d8af26c5b8dff7be764aac420b13df80bb530919d551881ae7d1afcc2400744
-->

## Impl.Abstract

Knowledge.Surface: wiki. Status: deployed; concurrent search/import stall reproduced, repair in progress. Develop / Wiki / Autonomous.
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

- [ ] Search stall bug fix: reproduce the User's exact query with bounded direct
  API reads, bypass unused curations through the documented API flag to avoid
  the matching v30.2 recursive-lock path, and cap search socket waits at 15s
  independently of the import timeout. Prove stalled-CLI failure and request
  semantics locally, publish the change, then operator deploy/restart and verify
  real search during ingestion. The existing server must be recovered first.
<!-- tarav.breadcrumb 8bce7330f6f9 -->

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
- [x] Deployment preparation/documentation: Studio-only reproducible Ansible installation
  of pinned Typesense 30.2, Tarav GitHub checkout/install, private configuration,
  explicit Normal Model-only transfer and global route preparation. Verify syntax
  locally; operator owns remote check/apply. Publish Tarav source to GitHub after
  inspecting the outgoing scope. No hardcoded Studio/SSH in adapter modules.
- [x] Code verification/capture: install the updated Tarav entrypoint, run appropriate
  focused tests and full root Project status --all, submit/audit implemented
  Product.Surfaces and Wiki capture, evidence commits. Test live search after the
  operator applies deployment; otherwise report it as pending, not passed.
- [x] Publish source and captured design to the existing GitHub main branches.
- [x] Operator apply: service check/apply, then the personal client check/apply
  including the explicit Normal Model-only transfer. Read retained Ansible logs
  before declaring the service installed or enabling the route.

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
- Both reviewed outgoing history scans passed with no leaks. Published source
  to tarav-projects/tarav-py main at d2ade66e345cfa053df9604552ec0b35a66e034c
  and design to tarav-projects/tarav-md main at
  862683d07d183e3a70ae383d7daf6d40e210ea08. Git push succeeded for each.
- Current operator ledger contains only syntax checks, no service/client apply.
  The operator's first concrete step is the tagged service --check command from
  the deployment guide. The live POC checkbox intentionally remains unchecked;
  no service install, full ingestion, route activation or live retrieval result
  has been claimed. Typesense was not installed on the control Mac.
- Operator service check/apply and personal client check/apply subsequently
  succeeded (retained Ansible logs 20261023-123623, 124056, 130309 and 130535).
  Tarav revision a1bad45d is installed remotely; the copied Normal Model root has
  10,169 directories. Live initial status reported 21 documents/one checkpoint.
- Enabled the independent global Typesense CLI route; routed status displayed
  its full SSH invocation and passed. Started full sync with tee output retained
  at /tmp/chatlas-typesense-sync.log. It reached 114 checkpointed sessions before
  imports, collection reads and the oldest-first POC search stopped responding.
  Health/debug/metrics still respond; Typesense 30.2 logs show a stuck request,
  a queued write and one inflight search. Similar upstream issue #3032 is a
  diagnostic lead, not an established cause. No live relevance result is claimed.
- Prepared an explicit Typesense-only recovery restart through its Ansible
  playbook (typesense_restart=true); the operator still owns the check/apply.
  Local stalled SSH clients were cancelled; remote requests may outlive them
  until timeout. Full ingestion and exact-source POC verification remain open.
- Operator restart apply 20261023-140317 failed: bootstrap raced the old job's
  removal (code 5). Read-only diagnostics now show no Typesense job/process.
  The Ansible handler now unloads conditionally and retries bootstrap for a
  bounded interval. Recovery apply and actual search remain pending.
- Restart apply 20261023-141548 succeeded. Collection GET/list now returns
  absent, while seed sync creation returns HTTP 409. Source Normal Models remain
  present. The only snapshot entry is temp; Typesense 30.2 treats any entry as
  a snapshot and skips initial collection loading, matching the startup log.
  Prepared operator-run snapshot recovery preserving db/meta and the incomplete
  snapshot while retaining the Raft log for native replay. This startup failure
  and the original ingestion/search stall still require separate verification.
- Snapshot recovery check 20261023-151134 and apply 20261023-151706 passed.
  Collection GET now returns 4,180 documents; keyword search succeeded in 7 ms.
  Separate direct live hybrid probes succeeded for relevance and oldest sorting
  in 15 ms and 6 ms. Routed full sync resumed, retaining progress in
  /tmp/chatlas-typesense-sync-recovered-20261023.log. No concurrent search will
  be added during this run; original stall cause and full POC remain open.
- User testing reproduced the stall with the exact natural-language query plus
  side=user. Sync had reached 9,350 sessions and 257,647 documents in this run.
  Engine logs show inflight searches and a queued write with frozen sequence;
  a direct local API request times out after 5 seconds while health takes 10 ms.
  This excludes SSH routing as the immediate cause. Upstream PR #3087 describes
  a v30.2 recursive shared-mutex deadlock during concurrent search/delete that
  closely matches our consumer's workload. Source review confirms the nested
  lock is conditional on enable_curations=true, enabled by default even without
  configured rules. The consumer needs no curated ranking; request false.
- Boundary discipline: the deployed 600s import timeout also applied to searches,
  hiding this failure for ten minutes. Add a short search-specific ceiling and
  an explicit timeout diagnostic; preserve the import allowance. The parameter
  bypass is a supported consumer setting, not a patched Typesense build. Its
  live effectiveness remains unverified until operator recovery/deployment.
- Concurrent external edits are present in the shared Python worktree (test
  restructuring and hooks). Preserve them; use a separate regression test file
  and leave their test_typesense.py changes intact.
- Regression checks failed before the fix: the curation parameter was absent,
  and the real CLI against a stalled HTTP fixture exceeded a 25s outer timeout.
  After the fix both dedicated tests passed in 19.14s. Shared focused testing
  passed seven checks but an existing 401-error CLI case printed its expected
  error and then failed to exit within 20s; this is not a green broader run.
  A detached verification/publication checkout at the deployed a1bad45d revision
  is checking only this repair independently of concurrent uncommitted changes.
- Isolated verification against the deployed a1bad45d baseline passed all 36
  adapter/routing tests in 65.30s with this repair overlaid. Ruff and whitespace
  checks passed. The dedicated regression pair also passes on the shared tree.
  Typesense is not installed locally. Remote recovery and the exact live User
  query still await operator client deployment and service restart.
