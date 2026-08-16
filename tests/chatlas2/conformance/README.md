# Chatlas2 Conformance Corpus

This is a hermetic corpus of immutable, best-effort anonymized provider artifacts.
One rich script may have many accepted captures for each provider and
`Raw.Model.Version`; every compatible normalizer is tested against those fixed specimens.

The corpus currently contains 21 accepted historical captures: 10 Codex
`codex.rollout.5f98` specimens and 11 Claude `claude.transcript.1ecc` specimens. The
supported but not yet corpus-registered Claude legacy family is
`claude.transcript.b17b`. These opaque suffixes identify compatible mapping partitions;
they do not express succession. The four historical scripts are preserved under `scripts/legacy/`.
`scripts/chatlas2-conformance.v1.md` is the consolidated script for new captures.

## Layout

- `captures.jsonl` — append-only accepted-capture registry
- `artifacts/sha256/` — deterministic gzip blobs addressed by anonymized content digest
- `specifications/` — exact user-message contracts and capture requirements
- `scripts/` — operator-facing scripts; these are documentation, while JSON is executable

## Hermetic checks

From the `tarav-py` repository:

```sh
tarav chatlas2 corpus verify --corpus tests/chatlas2/conformance
tarav chatlas2 corpus check --corpus tests/chatlas2/conformance
uv run pytest -q tests/chatlas2/test_conformance_corpus.py
```

`verify` checks registry, compression, size, and digests. `check` materializes every
artifact in a temporary directory, reruns Raw.Model.Version recognition, dispatches only
compatible normalizers, and checks exact user messages plus basic event-tape/reference
invariants. It does not read the live Chatlas archive.

## Registering a new artifact

Registration is intentionally interactive and only needed when adding a specimen. First
run the script and let current Chatlas archive the complete provider session. Add or review
its JSON specification, then prepare into a private temporary directory:

```sh
tarav chatlas2 corpus ingest prepare \
  --corpus tests/chatlas2/conformance \
  --stage /tmp/chatlas2-candidate \
  --script tests/chatlas2/conformance/specifications/SCRIPT.json \
  --provider PROVIDER \
  --session-id SESSION_ID \
  --captured-at YYYY-MM-DD \
  --json
```

Preparation reviews every retained transcript artifact. Its model-independent text pass
replaces obvious credentials, home paths, emails, and UUIDs. For a recognized format, the
outer workflow requires this preservation loop:

```text
source artifact -> Versioner -> Raw.Model.Version
       | text anonymizer
       v
candidate artifact -> Versioner -> same Raw.Model.Version
```

Codex preparation additionally compares normalized topology and the script's exact user
messages. Inspect the candidate report and staged anonymous text. Anonymization is best
effort, so a human must decide whether the artifact is safe to include. No daemon, test, or
background task performs registration.

After review, register the exact candidate explicitly:

```sh
tarav chatlas2 corpus ingest register \
  --corpus tests/chatlas2/conformance \
  --candidate /tmp/chatlas2-candidate/candidate-CAPTURE_ID.json \
  --json
```

Then run `corpus verify`, `corpus check`, and the Chatlas2 tests. Repeating the same
candidate is idempotent; a conflicting capture identifier or content-address collision is
rejected. Source artifacts stay in Chatlas, while only anonymous compressed artifacts and
hashed session/identity references enter this repository.
