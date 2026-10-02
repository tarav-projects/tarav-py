# 836 — Typed annotated SKW blocks

<!-- tarav.sessions
1f561f5d = codex:01a0b984-4664-7871-934a-89cf92595b64 @1f561f5d8db849a3a445b83a91a5e94acbb80927f9c332d45322ac70f8705a74
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: implemented.

Make `SkwBlock` the concrete neutral block Type. Its common Record consists of
stable identity, a local label, retained content, an optional typed
`objects_index`, and typed workflow-owned annotations. Remove the generation-
specific block Type and its prompt-template argument expansion. Generation,
reading dependencies, containment, and links participate through annotations
on the same block.
<!-- tarav.context 1f561f5d:60d4d034d5e0e584 -->
<!-- tarav.context 1f561f5d:b797b3be7d0a82e5 -->
<!-- tarav.context 1f561f5d:19bbdfd778ba3641 -->

Migrate the maintained SKW source Records explicitly. Do not add compatibility
readers for `LiteralBlock`, `AgentGenerationBlock`, `output`, `prompt`,
`arguments`, `context`, `contains`, `reading_deps`, or `links` in their former
top-level positions.

Non-goals: redesigning the standalone templated `Generation` utility; defining
one universal relationship vocabulary; changing compiled skill text; claiming
that declared generation context was supplied to a particular historical
agent; or designing persistence for arbitrary external annotation Types.

## Design narrative

### Neutral block substrate

The common shape is:

```text
SkwBlock
├── id
├── label
├── objects_index     optional locally named typed objects
├── annotations       typed objects whose workflows own their meanings
└── content           retained block content
```

`content` is neutral: it may be literal, agent-produced, code-produced, or
assessed by another workflow. Generation is therefore participation expressed
by an annotation, rather than the identity of the block itself. Specialized
block subtypes remain valid when their representation or executable behavior
really differs, as with `SkillLink`.
<!-- tarav.context 1f561f5d:19bbdfd778ba3641 -->

All retained objects are typed. The document Record remains the top dynamic
dispatch boundary, while nested objects also carry Types when they have their
own semantics or behavior. Plain structural values inside one typed object's
schema need no independent Type.
<!-- tarav.context 1f561f5d:0b1b0473a31afaa7 -->
<!-- tarav.context 1f561f5d:19bbdfd778ba3641 -->

### Local objects and mixed values

`objects_index` is a block-local object table. Its string keys are local
identifiers, not Ships. Values are typed TaravObject Records. A retained Entity
inside the index keeps its own stable Ship independently of its local name.
Annotations may inline typed objects directly or use a typed
`ObjectIndexReference` when local reuse is useful; indexing is never required.
<!-- tarav.context 1f561f5d:b974c6c7f7064562 -->
<!-- tarav.context 1f561f5d:0b1b0473a31afaa7 -->

`ObjectIndexReference` is a Reference whose resolution needs the containing
block. It returns the indexed TaravObject. A consuming workflow decides whether
to use that object directly or, when it is another Reference, resolve it again.
The index supplies local storage and addressing only; annotations supply
meaning.

### Workflow annotations

Introduce a minimal `BlockAnnotation` base. `GenerationAnnotation` owns ordered
instructions and an ordered mixed list of typed context objects. Reading
declarations become BlockAnnotation subtypes and move into the block's common
`annotations` array. The same indexed object may be used from multiple
annotations without imposing one shared semantic role.
<!-- tarav.context 1f561f5d:b797b3be7d0a82e5 -->

The SKW generation path gives the agent the complete block. It does not perform
`${name}` interpolation or maintain a special argument-binding language.
Generation preparation renders the annotation's instructions and separately
resolves its declared context objects. Its generation fingerprint covers the
generation instructions; context has its own independently captured
fingerprint. This removes the present accidental coupling where changing a
context declaration changes the generation-input fingerprint.
<!-- tarav.context 1f561f5d:60d4d034d5e0e584 -->

### Current implementation and migration boundary

Current `document.py` makes `LiteralBlock` and `AgentGenerationBlock` concrete
Types. The latter converts `prompt` and `arguments` into the independent
templated `Generation` utility. Context entries use untyped wrapper dictionaries
with `kind` and string roles. Reading declarations are typed internally but
are separated across three top-level block fields. `output` retains content.

Current package evaluation also performs generation/context freshness work in
document lint before discarding those findings and constructing SituationChecks.
The migration must give package evaluation one freshness path: structural lint
does not resolve freshness inputs, while freshness SituationChecks snapshot
them once. Direct document lint may adapt from that same snapshot path rather
than independently repeating detection.

The maintained `tarav-md` skill sources contain 114 blocks across 37 documents:
16 literal blocks, 97 generation blocks, and one `SkillLink`. Their generation
prompts are empty; their 231 context entries are typed StructuredFile References.
The migration can therefore preserve all compiled text while moving those
References directly into `GenerationAnnotation.context`. Existing reading
declarations move unchanged into `annotations`.

## Impl.Req.Wiki

Product: `tarav-py`. Documentation owner/root: `tarav-md/notes/wiki`.
Relevant topical Note: `skillware.md`. Mandatory daily destination:
`daily/2026-10-02.md`. Supporting Chatlas session:
`codex:01a0b984-4664-7871-934a-89cf92595b64`.

The current session was refreshed through an isolated writable Chatlas root
because the sandbox cannot update `~/Documents/tarav`. The resulting identity
matches the established `1f561f5d` session declaration. Breadcrumb submission
to the canonical retained store remains subject to that same sandbox boundary.

## Execution.Plan

1. Add the typed block-object/annotation primitives and register them in the
   runtime. Make `SkwBlock` concrete with `content`, `objects_index`, and
   `annotations`; preserve trusted dispatch for nested objects.
2. Move generation preparation, context navigation, recording, compilation,
   and freshness snapshots onto `GenerationAnnotation`. Remove SKW template
   arguments and the generation-specific block classes.
3. Make reading declarations BlockAnnotations and update Loading to select
   typed annotations. Migrate `SkillLink` and presentation from `output` to
   `content`.
4. Explicitly migrate all maintained `tarav-md` SKW Records. Rebuild both
   maintained skills and verify their compiled Markdown is unchanged.
5. Keep one broad SKW contract test covering direct and indexed mixed context,
   annotation selection, retained content, compilation, and independent
   generation/context freshness. Update the architecture contract and run the
   maintained foundational suite plus Ruff.
6. Capture justified Product.Surface Breadcrumbs, update the Skillware Wiki and
   daily narrative, audit what the sandbox permits, then close scoped evidence
   commits in both repositories.

### Acceptance checks

- Every block and nested semantic object in a maintained SKW source has a
  registered Type; unknown or unregistered nested Types fail at loading.
- `objects_index` accepts typed TaravObjects and rejects duplicate/invalid local
  identifiers. `ObjectIndexReference` resolves only against its containing
  block and fails for an absent key.
- Generation context accepts both direct typed objects and typed index
  references. It contains no untyped `kind` wrapper requirement.
- A block may carry generation, reading, and content-related annotations at the
  same time; each consumer selects only annotation Types it understands.
- SKW generation performs no placeholder interpolation or argument binding.
- Changing only declared context does not change the generation fingerprint;
  it may change the context fingerprint and its independently identified POI.
- Package evaluation resolves each freshness concern once.
- Maintained skill builds reproduce their current Markdown text.
- No compatibility reader accepts the former block Types or field layout.

## Impl.Log

2026-10-02 — Design inspected current SKW code, retained skill Records, prior
Skillware Wiki decisions, and the accepted in-chat block model. Scoped start
checkpoints preserve existing overlapping work: `tarav-py` `f93f8f3` and
`tarav-md` `e1c58e7`.

2026-10-02 — Implemented the neutral `SkwBlock`, typed local object index,
typed block annotations, generation annotation, indexed-object Reference, and
reading-declaration annotations. Removed the generation-specific SKW block
Types, prompt interpolation, argument binding, and old context-role wrappers.
Package evaluation now leaves freshness to its bound SituationChecks.

Explicitly migrated 114 blocks in 37 maintained source documents and rebuilt
both maintained skills. All compiled Markdown remained byte-identical. Five
valid generation baselines and 83 valid context baselines were translated;
14 context baselines that were already stale remain stale. The maintained
suite passes with 150 tests in 19.26 seconds, and the focused Ruff check passes.

Product and Wiki surfaces retain provisional exact-turn markers because the
managed sandbox cannot write the canonical Breadcrumb store under
`~/Documents/tarav`. The session identity and turn prefixes remain explicit so
canonical submission can be completed without reconstructing the discussion.
