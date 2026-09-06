<!-- tarav.sessions
4571385e = codex:01a06bed-b554-7770-86e3-cce2e5729994 @4571385eb2c5457a615e836d943acad00147fda45a10dbad26848faf81e2bfe1
-->

# Inlined.Capture tooling evaluation

## Status

- **Type:** live design evaluation
- **Date:** 2026-09-04
- **Implementation status:** no changes proposed here are implemented
- **Source:** practical use during the PhD documentation workflow
<!-- tarav.context 4571385e:f8afd4b4130b5f6e -->

## Executive conclusion

The current Inlined.Capture design is conceptually sound, but its operational surface is too manual beyond the intended one-document-at-a-time rhythm. The largest friction is not writing the Markdown comment. It is discovering the exact User Turn that the Agent has already identified semantically, then safely attaching and validating the rendered reference on the product surface.
<!-- tarav.context 4571385e:893153adb60d4832 -->

The semantic decisions should remain Agent work. The surrounding discovery, insertion, and validation ceremony is mechanical and should become cheaper. This distinction preserves the workflow's minimality while strengthening the connection between product surfaces and their conversational neighborhoods.
<!-- tarav.context 4571385e:a25968e7175d135f -->

## Observed workflow

A retrospective capture pass over the PhD project resulted in 276 inline references across 33 Markdown files, pointing to 65 distinct User Turns in one Chatlas session. The pass required the Agent to:

1. refresh the Chatlas session;
2. materialize the Normal Model;
3. construct a custom projection joining Turns, Events, and Messages to obtain a readable hash-and-text ledger;
4. select relevant Turns and map them to Markdown blocks;
5. call the named Renderer in batches;
6. insert the comments through ordinary surface editing;
7. build a separate shell audit for declarations, syntax, resolution, and User-Turn validity.

The final references resolved cleanly, but the amount of ad hoc orchestration shows where the public primitives stop short of the complete natural workflow.

## Friction assessment

### 1. User-Turn discovery — largest friction

Chatlas Query and Render accept Turn-hash prefixes once they are known. The Normal Model contains the necessary data, but an operator seeking a Turn by remembered content must currently join separate Turn, Event, and Message projections or already possess a prefix.

This is not semantic selection: exposing candidate User Turns as a compact ledger remains a deterministic data-access operation. Requiring each Agent to reconstruct that projection is unjustified friction.

### 2. Surface attachment

The Renderer correctly owns only reference syntax. The workflow still requires the Agent to insert each rendered comment after the intended Markdown block, preserve or add the document-local session declaration, and avoid accidental attachment to a neighboring block.

This is manageable on a clean note. It becomes fragile across many files or hard-wrapped paper transcripts, where exact-text patches may fail and the practical Markdown block boundary may be unclear. The Agent should continue choosing the semantic attachment; a tool can safely perform a declared attachment.

### 3. Reference audit

There is no first-class command that reads a product surface, resolves its `tarav.sessions` declarations, collects `tarav.context` references, and reports malformed syntax, unknown aliases, missing or ambiguous Turns, non-User Turns, and suspicious attachment positions.

All these checks are mechanical and directly protect the workflow's core promise. Their absence is unjustified, even while POIs remain nonblocking.

### 4. Retrospective multi-surface capture

The explicit workflow is intentionally bounded to one selected surface. That is appropriate for the normal rhythm:

```text
Discuss → settle a decision → update one document → Inlined.Capture → continue
```

A large catch-up pass is exceptional, but it is also a legitimate recovery workflow. Repeating the same refresh, rendering, insertion, and audit ceremony across many selected surfaces adds cost without improving semantic judgment.

## Justified friction

The following responsibilities should remain Agent-operated:

- deciding which User Turns are relevant;
- deciding whether a Turn contextualizes a surface fragment at all;
- selecting the smallest useful Markdown block or neighborhood;
- distinguishing conversational rationale from documentary evidence;
- avoiding references that imply stronger provenance than the conversation provides.

Automatic semantic matching is therefore not the immediate solution. The reference means that the annotating Agent selected a Turn as useful context; tooling must not silently make that claim on the Agent's behalf.

## Recommended tooling increments

### Priority 1 — compact User-Turn ledger and search

Provide a Chatlas projection that emits, at minimum:

```text
turn-hash-prefix    timestamp    User-Turn text
```

It should support one exact session plus bounded text, time, or recent-Turn filtering. This remains structural retrieval: the Agent interprets the candidates and selects the relevant Turns.

### Priority 2 — inline-reference audit

Provide a read-only audit over one Markdown surface or an explicitly selected set. It should validate:

- session declaration syntax and alias uniqueness;
- context-reference syntax and ordinary 16-character prefixes;
- exact resolution within the declared session;
- User-Turn side;
- zero-match and collision POIs;
- references lacking a plausible preceding Markdown block.

The audit should report POIs without blocking editing or capture.

### Priority 3 — manifest-based application

Let the Agent declare a small mapping such as:

```text
surface + block locator + session alias + selected Turn hashes
```

A surface-aware applicator can then validate the declaration, render the references, insert them at the requested attachment point, and preserve ordinary Markdown. The manifest is coordination data, not a new semantic registry.

The block locator should be designed only after testing real files. A source span plus a small content fingerprint is a candidate, but the interface should not be frozen prematurely.

### Priority 4 — bounded batch orchestration

Allow the same manifest and audit mechanics to operate over multiple explicitly selected surfaces. Batch mode should reduce repeated mechanical work without performing automatic semantic selection.

## Ownership boundary

- **Chatlas** should own compact User-Turn retrieval and exact resolution.
- **The Renderer** should continue to own only the reference representation.
- **Inlined.Capture/Hugentics** should own session declarations, attachment policy, capture manifests, application, and audit behavior.
- **Native Markdown surfaces** should expose only the syntax and source spans demonstrated necessary by consumers; Inlined.Capture policy should not leak into the base normal model.

## Explicitly deferred

The observed friction does not yet justify:

- automatic semantic annotation;
- an alias registry;
- Git-history reconstruction;
- Diagram capture or Assertion scoring for every breadcrumb;
- a generalized product-surface impact map;
- a universal fragment-addressing grammar.

Those may become useful if later workflows require them. They are not prerequisites for making the current breadcrumb workflow substantially easier and safer.

## Proposed next design question

Define the smallest User-Turn ledger and inline-reference audit that would eliminate the custom `jq` and `rg` orchestration observed in the PhD capture pass, while leaving Turn selection and semantic block attachment explicitly under Agent control.
<!-- tarav.context 4571385e:893153adb60d4832 -->
