# Chatlas search with Typesense

This is a client of a separately installed Typesense 30.2 service. Importing or
installing Tarav never installs Typesense, downloads an embedding model or starts
a search service. All embedding generation runs in Typesense. Deployment and
host selection belong to the operator and the separate CLI router.
<!-- tarav.breadcrumb 30be7ad81d66 -->
<!-- tarav.breadcrumb 74fe5fd492b4 -->

## Input and source contract

Sync reads only `normal-model/<identity>/main.json`, `messages.jsonl`,
`turns.jsonl` and `events.jsonl` through the Normal Model's public readers. It
does not read raw artifacts, the Session Index, loaded contexts or cache.json.
It never captures providers, normalizes a chat or repairs an input. Old,
incompatible, missing or corrupt models are reported as session errors.
<!-- tarav.breadcrumb 7846914460fe -->

One search document is one message chunk, with exact character offsets into its
original Message. It retains the session identity, provider, native session ID,
speaker, stored Event time and exact Message/Event/Turn references. Header paths
are retained as hints, never opened. The current header has no project metadata:
this initial adapter provides no project filter and does not infer one from paths.

The default model is Typesense's built-in `ts/all-MiniLM-L12-v2`, primarily an
English baseline. Typesense downloads and runs it. The 800-character chunks with
80-character overlap are a simple initial mapping, not a guarantee about the
model's token window. Test relevance on real chat questions before claiming
multilingual or long-passage quality. Model choice remains ordinary configuration.

## Configuration

Create `~/.tarav/chatlas-typesense.json` on the machine executing these commands:

```json
{
  "url": "http://127.0.0.1:8108",
  "api_key_file": "/absolute/private/typesense-api-key",
  "collection": "chatlas_messages_v1",
  "normal_model_root": "/absolute/chatlas/normal-model",
  "embedding_model": "ts/all-MiniLM-L12-v2"
}
```

The Normal Model root defaults to the default Chatlas depot's `normal-model/`.
`--config PATH` and `--normal-model-root PATH` are available on each leaf.
Optional JSON controls are `chunk_chars` (800), `chunk_overlap` (80),
`batch_size` (100) and HTTP `timeout` seconds (120). The first import can require
longer while Typesense downloads its embedding model; increase timeout in that
machine's configuration if necessary.

The environment can supply `TARAV_TYPESENSE_URL`, `TARAV_TYPESENSE_API_KEY_FILE`
or `TARAV_TYPESENSE_API_KEY`. Keep keys in private files or the environment,
never command arguments, public repositories or CLI routing rules. Configuration
has no host-routing or remote-execution fields.

## Commands

```sh
tarav chatlas typesense status
tarav chatlas typesense sync --limit-sessions 1
tarav chatlas typesense sync
tarav chatlas typesense search 'why did we add command routing?'
tarav chatlas typesense search 'normal model' --side user --provider codex \
  --since 2026-10-01 --limit 5 --json
```

Status reports service health, collection existence/document count, source model
directories and completed session checkpoints. Status/search do not create an
index. Sync creates a dedicated collection with a configured auto-embedding field
and then performs bulk upserts. Existing collections with incompatible adapter
metadata/model settings are rejected: choose another collection name explicitly.

Sync checkpoints each successfully imported session in the executing machine's
Tarav cache, bound to the source root, endpoint, collection and collection index
identity. Unchanged inputs are skipped; `--force` resends them. Losing this cache
only causes reindexing. After a session succeeds, its superseded chunks are
deleted. A failed import preserves earlier data and is retried on the next run.
There is no transaction over all imports: partially imported new chunks may be
searchable after an interrupted run. Repeating sync converges that session.
Disappearing source directories never trigger global index deletion.

Sync progress goes to stderr; its final JSON report goes to stdout. Any session
error gives exit 1 and keeps the error in that report. The command does not spawn
background workers; a caller may run it in its own terminal/job runner.

Search delegates hybrid matching and ranking to Typesense. JSON hits contain
the full source selector; text output shows the Message and available Turn hashes.
For exact Turn expansion, use the returned provider, session ID and Turn hash:

```sh
tarav chatlas query --provider <provider> --session-id <session-id> \
  --turn-hash-prefix <turn-hash>
```

The normal Chatlas query command has its own freshness policy and may read raw
data. This Typesense adapter itself does not use that path. Message-only hits
can be located directly in their stored Normal Model using the returned exact
message address/hash and offsets.

## Routing

Configure the existing global CLI router independently. Its rule may match
`["chatlas", "typesense"]` and invoke any external command. The adapter knows only
the service URL and input root; it has no SSH or machine-specific behavior.
<!-- tarav.breadcrumb a698ce375cb3 -->

Local tests use an HTTP contract fixture, not an installed Typesense engine.
They verify mapping, requests, errors and resumption; real engine compatibility,
embedding speed and retrieval quality require a deployed service.
