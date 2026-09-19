# 800 — TaravObject and JSON representation — implementation request

<!-- tarav.sessions
5626cd5f = codex:01a0af61-72e2-7bd2-94a3-26529d6914ec @5626cd5f7db74c4f2e3838250516b5e300cc9387ac254eb65a0816a5f30555a1
-->

## Impl.Abstract

Make `TaravObject` the semantic root of Tarav's object hierarchy. A record is
an object's serialized representation, particularly in storage. Loading is one
behavior of an object; serialization alone does not require another base class.
<!-- tarav.context 5626cd5f:a9e2ecce8eb580b5 -->

This request records the implementation scope using inline wiki-style
grounding. Status: executing.
<!-- tarav.context 5626cd5f:10acac359a1759d9 -->

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index` —
  `1c99092c-ba46-4006-adc3-9ada50c00abd`
- **Project Model:** `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **Semantic Block:** `Tarav.Record` —
  `e63beedb-3007-4391-b339-215dea550cff`
- **Impl.Req.Collection:** `800.Impl.Req` —
  `559c0b47-8c2f-4bc4-881d-554ca5de4b84` (`Open`)
- **Diagram.Draft:** `026011c6-1675-4f23-b903-79f2a04b97b7` —
  `/Users/pereiro/Documents/tarav/diagram/drafts/026011c6-1675-4f23-b903-79f2a04b97b7.json`
- **Authorization Gate:** pending current-session capture.

## Requirements

Preserve common semantic mechanics: class type identity, Type Ship UUID, and
`help()`. They apply independently of file, directory, or inline placement.
An actionable `SkwBlock` can remain serialized inside its document.
<!-- tarav.context 5626cd5f:40aaf63a879481b3 -->

Classes and producing workflows own writing to storage. Tarav resolves a
representation into its declared registered class. Do not introduce a universal
storage writer or a separate record superclass solely for serialization.
<!-- tarav.context 5626cd5f:a9e2ecce8eb580b5 -->

Add `from_json(value)` alongside `json_load(file)`, retaining an explicit
in-memory construction entry point.
<!-- tarav.context 5626cd5f:f7163a36d8e7eaec -->

Provide `to_json()` for the JSON-compatible in-memory representation and a
static `json_example()` for concrete registered classes. The example is usable
by agents as documentation and describes the object independently of storage.
<!-- tarav.context 5626cd5f:d13375746bf42765 -->

Provide a minimum default test across registered classes:
example JSON → object → JSON → object → JSON. Verify that conversion succeeds
and information is retained across the round trip.
<!-- tarav.context 5626cd5f:d13375746bf42765 -->
<!-- tarav.context 5626cd5f:f7163a36d8e7eaec -->

## Execution.Plan

Proposed implementation steps derived from those requirements:

1. Inspect the current hierarchy, registration, constructors, and loaders.
   Rename `TaravRecord` to `TaravObject`; migrate maintained imports,
   subclasses, examples, and documentation without compatibility aliases.
   Preserve existing serialized type identities unless a concrete change
   requires an explicit code-and-data migration.
2. Route registry-selected construction, file loading, and directory-entry
   loading through the selected class's `from_json`. Preserve source-location
   attachment and class-owned validation; readers never repair records.
3. Implement the common JSON representation methods and explicit examples for
   concrete registered classes. Keep storage persistence with its owners.
4. Run the default round-trip test over runtime registrations, with failures
   identifying the responsible class. Verify ordinary loading, type dispatch,
   source metadata, and contextual help continue to work.
5. In a following bounded slice, introduce an actionable `SkwBlock` using the
   common contract. Keep blocks inline in their SKW document and migrate
   relevant callers. Verify compilation preserves the product and existing
   context/dependency behavior.
6. Update affected guidance and run focused checks, then the broader suite
   appropriate to the common-root migration.

## Scope boundary

This request covers the semantic root, JSON contract, and its application to
`SkwBlock`. Context.Path behavior is a separate implementation slice. No new
storage framework or universal semantic correctness gate is proposed.

Design context: [Tarav objects and JSON representation](../../../tarav-md/notes/wiki/record-framework.md#tarav-objects-and-json-representation).

## Impl.Log

Written as an implementation request only. Grounding is inline; no Diagram
Collection or Draft is created. No implementation execution is recorded.
