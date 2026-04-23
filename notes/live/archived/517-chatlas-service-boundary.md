# Chatlas Service Boundary

## Goal
- Define `Chatlas` as an `agentos` service.
- Clarify that `Chatlas` owns structured chat data, not all chat-related machinery.
- Record the command-surface direction for `agentos chatlas ...`.
- Merge the current chat archive concept into `Chatlas` as the raw-data layer.

## Accepted Direction
- `agentos` is the platform and shared machinery.
- `Chatlas` is a packaged `agentos` service for chat data.
- `Chatlas` owns the maintained chat dataset and its public-facing access surfaces.
- `Chatlas` is not the owner of provider telemetry gathering, account usage refresh, or generic provider operations.
- `agentos chat session` should be treated as one connector/query surface in the broader stack, not as the whole product.

## Core Definition
- `Chatlas` is the public place where chat data is collected and exposed.
- `Chatlas` should be backed by a git repo so the dataset is inspectable, versioned, and easy to consume.
- `Chatlas` should preserve provider-native raw artifacts when they are publishable.
- `Chatlas` should also expose normalized cross-provider records so downstream tools can consume one canonical shape.

## Responsibilities
- Archive raw provider chat artifacts into the Chatlas dataset.
- Maintain a normalized cross-provider surface over chat sessions and messages.
- Materialize clean transcript views.
- Materialize several summary levels over the same underlying chats.
- Expose queryable/public consumption surfaces for other tools and users.
- Keep lineage between raw provider artifacts and normalized/derived outputs.

## Non-Responsibilities
- Provider telemetry gathering.
- Account usage refresh and usage-report collection.
- Provider auth/config management.
- Generic provider diagnostics that are not part of the maintained chat dataset.

## Service Layers
- `raw/`: provider-native archived chat artifacts.
- `normalized/`: canonical cross-provider records.
- `derived/`: transcripts, summaries, indexes, and similar projections.
- `manifests/`: update runs, lineage, schema versions, and source fingerprints.

## Command Surface Direction
- Prefer a dedicated service namespace.
- `agentos chatlas update`
- `agentos chatlas query`
- `agentos chatlas export`
- `agentos chatlas stats`
- Keep `agentos chat ...` available for provider-facing discovery, inspection, extraction, and related connector workflows.
- Use `agentos` shared provider-family/provider-instance machinery underneath both surfaces.

## Update Workflow Direction
- `agentos chatlas update` should run the workflows that pull new provider activity into the Chatlas dataset.
- One update run should include these steps.
- discover new provider activity through `agentos` connectors
- copy or mirror raw publishable artifacts into `raw/`
- normalize them into canonical records in `normalized/`
- materialize transcript and summary outputs in `derived/`
- optionally rebuild local query databases or indexes
- checkpoint the resulting dataset changes in the git-backed Chatlas repo

## Archive Merge Decision
- The current `agentos chat archive` concept should be merged into `Chatlas`.
- Archive is not a sibling service to `Chatlas`; it is the raw-data layer inside `Chatlas`.
- This keeps one service responsible for the full chat-data lifecycle from raw artifacts to normalized and derived surfaces.

## Architecture Notes
- Not all `agentos chat` commands belong to `Chatlas`.
- `Chatlas` should own the maintained chat corpus.
- Other chat-related commands can continue to exist for provider/account/runtime concerns outside the Chatlas boundary.
- Shared provider family / instance modeling remains in `agentos`, since it is common machinery used beyond Chatlas.

## Open Design Follow-Ups
- Define the canonical top-level Chatlas entities.
- Decide the exact normalized schema for session/message/turn/transcript/summary records.
- Decide which raw artifacts are publishable in the public Chatlas repo versus private/local-only.
- Decide whether local query databases are generated artifacts or part of the checked-in dataset.
