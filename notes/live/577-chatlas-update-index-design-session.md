# Chatlas Update Index - design-session

## Session.Abstract

Design session for the new `agentos chatlas update` system, starting with the first phase: `index-only`.

The current design target is a clean first pipeline step that copies provider raw session sources into Chatlas-controlled storage and produces/updates the session index from that copied substrate. The phase is designed from scratch, using v1 as reference only.

## Session.Index

### Chatlas.Update.IndexOnly

`index-only` is the first Chatlas update phase. It is responsible for producing/updating the session index and the copied raw source substrate needed to support that index.

It does not know about later phases.

### Provider.Model.Boundary

Chatlas must use existing Agentos `<Provider>.Agent` and `<Provider>.Session` abstractions. Chatlas must not invent a parallel Chatlas-only provider model.

Providers own raw-session interpretation. Chatlas owns orchestration, source-copy boundaries, index rows, cache/reporting, and phase boundaries.

### Raw.Copy.Index.Flow

`index-only` copies provider raw session sources into Chatlas-controlled storage, then discovers and indexes sessions only from that copied substrate.

The pipeline must not index directly from live provider homes after copying, because that can hide stale, missing, corrupted, or broken artifacts.

### Ref.First.Load.Control

Provider session discovery should produce lightweight refs first. Index production should avoid eager full-session/raw loading.

Any expensive raw or full `Provider.Session` load must be explicit, cacheable, and justified by a required index field.

### Chatlas.Delta.Scan

`Chatlas.Delta.Scan` is the first scan/update implementation strategy for `index-only`.

Design summary: [578-chatlas-delta-scan-design-summary.md](578-chatlas-delta-scan-design-summary.md)

Implementation request: [579-chatlas-delta-scan-impl-req.md](579-chatlas-delta-scan-impl-req.md)

Core invariant: delta detection is native-based; index derivation is Chatlas-raw-based.

## Session.Docs

The copied raw sources are a real Chatlas-owned source substrate, not merely a hidden cache. The session index is the only productized/queryable artifact promised by the first phase.

The first phase may touch raw copy state because that state supports safe index production, but it must not include query/export/stats behavior, broad raw archive lifecycle policy, or git finalization policy.

`Chatlas.Delta.Scan` is captured as a dedicated design-summary artifact because the design has enough authority and implementation detail to guide later work.

## Session.Notes

Next high-leverage question: define the provider/home partition layout for `session-index-derivations` and session index files, including bucket keys, upsert behavior, and how large provider histories are split.

## Session.Log

- 2026-05-11: Upgraded in-chat design discussion to artifact-backed session and captured first settled decisions.
- 2026-05-11: Captured `Chatlas.Delta.Scan` as a dedicated design summary and linked it from `Session.Index`.
- 2026-05-12: Produced `Chatlas.Delta.Scan` implementation request and linked it from `Session.Index`.
