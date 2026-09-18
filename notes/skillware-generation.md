# Independent Skillware generation MVP

## Document-source workflow

The document workflow is `tarav.skillware.document.Document`. Sources default
to `.skw/src/<product-name>.skw.json`; generation annotations live under
`.skw/generations/`, and `.skw/lock.json` retains per-document baselines.
The whole product is derived from literal lines and generated output lines.

```json
{
  "type": "Tarav.Skillware.Document",
  "schema_version": 1,
  "output": "explanation.md",
  "blocks": [
    {"id": "title", "kind": "literal", "lines": ["# Calculator", ""]},
    {
      "id": "explain",
      "kind": "generation",
      "prompt": ["Explain this code: ${code}"],
      "arguments": {"code": {"type": "text", "file": "calculator.py"}},
      "output": null
    }
  ]
}
```

Run `tarav skw document prepare --source explanation.skw.json --block explain`.
The JSON response supplies the invocation ID, expanded prompt, and previous
output. The agent edits `output` in the source to an array of lines, then runs
`tarav skw document record --source explanation.skw.json --generation <invocation-id>`.
Recording rejects inputs changed since preparation; it does not judge meaning.
`tarav skw document compile --source explanation.skw.json` assembles the entire
product and reports findings. `tarav skw document lint --source <source>` is read-only.
These commands require no persistent scripts or prompt file.

Arguments select exactly one `value`, project-relative `file`, or local `block`
ID. Blocks are joined in source order with newline separators and one final
newline for nonempty documents. Empty output arrays are valid; null means
unfinished. Missing outputs prevent assembly, while stale generation findings
remain visible even when the product can be compiled. Compile updates only
the product/source baseline, never generation baselines. Editing generated
product files is detected as drift; explicit compilation replaces them.

Use `Document(source).prepare(block)`, reload after agent edits, then
`.record(invocation)`, `.compile()`, and `.lint()` from Python. Paths cannot
escape the project. Sources outside `.skw/` require an explicit root.
Prepared prompts are evidence of preparation, not proof of agent receipt.
Sources, annotations, and locks have registered Tarav Record classes.
Storage is single-writer; semantic scoring and cross-document block addressing
are future work. The independent generation helpers below remain implementation
building blocks; the document source is the main authoring surface.

## Low-level generation helpers

### Maintainer context

Every context object may carry a `roles` array (absent means no roles):
`maintenance` presents guidance, `dependency` tracks target changes, and
`user-grounding` requires an exact Chatlas User Turn. Roles compose; unknown
or duplicate roles produce findings. Context declarations themselves remain
tracked; only dependency-role targets contribute changing content to baselines.
Missing references remain resolution findings regardless of roles.

```json
{
  "kind": "reference",
  "roles": ["maintenance", "user-grounding"],
  "reference": {
    "type": "Tarav.Chatlas.Reference.Turn",
    "locator": {
      "session_identity": "<full session identity hash>",
      "turn_address": "<full turn address>",
      "turn_hash": "<full turn hash>"
    }
  }
}
```

Chatlas owns resolution and returns exact messages without summaries. Missing
or amended turns are findings, not replacements. Listings expose coordinates
without loading chats; selected reads resolve only the selected reference.
Grounding indicates relevant user evidence, not approval or proof of fidelity.
Trusted callers may register `ContextRole` implementations with `ContextRoles`
and supply that registry to `Document(..., roles=registry)`; records never load
arbitrary code. Runtime also registers the Turn reference for other consumers.

Existing Hugentics contexts were explicitly migrated to maintenance/dependency
roles and their baselines re-observed, preserving prior tracking semantics.

Blocks may declare an ordered `context` array:

```json
[
  {"kind": "prompt", "lines": ["Preserve the workflow boundaries."]},
  {"kind": "reference", "reference": {"type": "Tarav.Reference.StructuredFile", "locator": {"path": "./workflows.skw.json", "pointer": "/blocks/0"}}},
  {"kind": "reference", "reference": {"type": "Tarav.Reference.StructuredFile", "locator": {"path": "../../CONSTITUTION.md"}}}
]
```

Context references resolve relative to the containing source's directory,
including paths outside its project. They are intentionally unstable: no
Archive, search, or automatic repair. File references fingerprint exact bytes;
JSON Pointer references fingerprint the selected value; selecting a whole block includes instructions,
context declarations, and output. References do not recursively load context.
Files presented as context must be UTF-8 text. Prompt context is literal text,
not argument-template syntax.

`tarav skw document context --source <source> --block <block>` lists context entries in order,
without reading target payloads. Listings include zero-based indices, declared
references, absolute paths and JSON pointers where supported, file sizes, and
address findings. `available-unchecked` means the file exists, not that its
pointer or identity check has been validated. Other reference types without
address inspection remain explicitly `uninspected`.

Select one entry explicitly:

```sh
tarav skw document context --source <source> --block <block> --head 0 --lines 10 --chars 2000
tarav skw document context --source <source> --block <block> --tail 0
tarav skw document context --source <source> --block <block> --cat 0
```

Previews default to 20 lines and 4000 characters, with truncation reported on
stderr. Full reads are explicit; selected reads do not resolve sibling entries.
JSON values are pretty-printed, and file text is emitted directly. Agents can
also use listed absolute paths and pointers with their native tools. To navigate
onward, inspect a referenced source/block and list its context with the same
command; nested references are never automatically expanded.

`Document.context(block)` lists entries; `read_context(block, index, mode=...)`
returns selected text and truncation metadata. Preparation returns a compact
listing but retains resolved context and its fingerprint in its annotation;
recording rejects context changed since preparation. For maintained existing
content, `observe-context --source <source> --block <block>` explicitly stores a context baseline
without asserting any generation history or agent receipt. Python exposes
`context(block)` and `observe_context(block)` on `Document`.

Lint reports `context-unobserved`, `context-unresolvable`, and `stale-context`.
Changing declarations or referenced content invalidates the observation.
Lint and compile never refresh context baselines; explicit recording or
observation does. An observation says nothing about semantic correctness.

Fingerprinting and explicit reads may read whole targets internally, including
JSON documents needed for pointer selection. Preview bounds limit presentation,
not storage I/O. Listing uses address/stat inspection only.

Existing content does not require a generation annotation. A block may retain
its output with an empty prompt and incrementally developed context. Lint
checks the declarations and baselines actually present; absent generation
history is not itself a finding. Missing output remains a finding. Once a
generation is explicitly recorded, its recipe/output baseline is checked.

`tarav.skillware.generation` provides a Python-first generation workflow.
It does not resolve Index concepts, query Diagram, launch agents, or acquire
context. The caller supplies context explicitly as arguments or prompt text.

```python
from tarav.skillware.generation import Argument, Block, Generation, Output

skw = Generation((
    Block("explain", "Explain this code: ${code}", (Argument("code"),)),
    Block("review", "Review this explanation: ${text}", (Argument("text"),)),
))
invocation = skw.prepare("explain", {"code": "def add(a, b): return a + b"})
prompt = skw.invocations[invocation]["prompt"]  # Supply this to the agent.
# Record the actual result returned by the agent:
skw.finish(invocation, "The function returns the sum of its two arguments.")
review = skw.prepare("review", {"text": Output(invocation)})
skw.save("generation.json")
findings = skw.check()  # The review has no output yet.
```

Templates use `${name}` and `$$` for a literal dollar. Arguments are required;
supported types are text, integer, number, boolean, and JSON. Substitution is
literal and never executes the argument text. An `Output` argument consumes
another invocation's text and records its identity and content fingerprint.

Each invocation retains a block fingerprint, input snapshot, expanded prompt,
optional chat locator supplied by the caller, and output. This records the
prepared prompt, not proof that an agent received or used it. A supplied output
file must already match the recorded text; recording never writes that file.

Checks report missing outputs, changed definitions, unavailable or changed
files, missing or changed dependencies, and downstream review needs. They do
not assess semantic correctness or regenerate anything. Definitions can be
replaced explicitly in `blocks`; new invocations preserve distinct histories.

State persistence is explicit and single-writer. This first version handles
text outputs and whole-file checks; arbitrary fragment selectors, a source-file
grammar, semantic scoring, and contextualization integrations are not included.
The existing `.skw` compiler remains a separate consumer; this API does not
translate its sources or import its dependency semantics.

Context uses only typed reference objects; the old path/block entry form is rejected.
`check` and `hints` are optional and omitted when empty. A pointer may select
any JSON value, including shared context in the same source. Resolution returns
that value without recursively expanding references. Relative paths use the
containing source directory; the reference layer owns resolution and checks,
while Skillware owns observations and stale-context findings.

CLI project selection: pass `--project <directory-containing-.skw>` or run
inside the project and let the CLI discover the nearest `.skw/` upward.
`--source` is relative to `.skw/src/`; absolute and escaping source paths are
rejected. Output paths remain project-relative, and context reference paths
remain relative to their containing source. All CLI inputs use named flags.
# Skill-package specialization

## Declared consumer loading model

An optional manifest `loading` path (for example `.skw/loading.json`) selects
static instruction-context analysis. A package without it has no declared
block-level context analysis; file/dependency checks alone do not establish
consumer-context completeness. A loading record has this shape:

```json
{
  "type": "Tarav.Skillware.SkillLoading",
  "schema_version": 1,
  "blocks": [
    {
      "id": "entry",
      "reference": {
        "type": "Tarav.Reference.StructuredFile",
        "locator": {"path": "src/SKILL.skw.json", "pointer": "/blocks/0"}
      },
      "links": [{"target": "vocabulary", "slot": "read", "label": "Vocabulary"}]
    },
    {
      "id": "vocabulary",
      "reference": {
        "type": "Tarav.Reference.StructuredFile",
        "locator": {"path": "src/SKILL.skw.json", "pointer": "/blocks/1"}
      }
    },
    {
      "id": "use",
      "reference": {
        "type": "Tarav.Reference.StructuredFile",
        "locator": {"path": "src/SKILL.skw.json", "pointer": "/blocks/2"}
      },
      "parents": ["entry", "vocabulary"],
      "requires": [{"target": "vocabulary", "delivery": "inlined"}]
    }
  ]
}
```

IDs are local declaration identities, bound to actual SKW source blocks using
ordinary typed references. References resolve relative to the loading Record.
Every managed source block must be bound exactly once. The default root is
the first block producing the package entrypoint (normally `SKILL.md`). An
explicit `root` can select another declared entry block. `parents` overrides
the default predecessor within a file; `[]` declares no parent. First blocks
of other files need explicit attachments. Parent edges are not inferred from
links. Multiple parents represent alternative incoming paths.

The example's entry output contains `{{skw:read}}`, replaced deterministically
by a link. Non-first-block links use generated `skw-<id>` anchors; links to a
file's first block address the file. `includes` uses the same `target` and
`slot` fields, without a label, to insert another block's rendered content.
Each declared slot must occur exactly once; undeclared slots are errors. Nested
inclusions rebase links to the destination file. Inclusion cycles cannot render.

At each point the analyzer accumulates block IDs, declared links, and inline
inclusions. Requirements accept `referenced`, `inlined`, or `either` (default).
Referenced does not imply inlined; inlined alone does not imply a link exists.
A block's own declared primitives contribute to its context contract. No code
infers what the agent learns from the content. Inclusions also form contextual
visits and their own requirements are assessed at the inclusion site.

Findings cover undeclared/unreachable blocks, invalid references/parents,
attachment and inclusion cycles, missing context, and path-dependent coverage.
The analyzer bounds path traversal at 10,000 visits and reports incomplete
analysis rather than claiming success if that limit is reached. The first
implementation binds package-owned source blocks; external skill context is
not silently imported. Inline Markdown links lacking primitive declarations
produce `unannotated-output-link` conformance findings but never become edges.

Use `SkillPackage(root).loading().analyze()` or `.inspect(block, limit=5)` in
Python. `tarav skw skills context --project <root> --block <id> --limit 2` shows
one declaration, its parents, bounded path examples and findings. Package
`check` runs static analysis; `build` compiles primitives and retains findings.
The loading declaration hash is recorded in each document's existing lock
entry. Changing declarations makes compilation stale without accepting
generation/context baselines. Runtime composes the specialized document
factory into `tarav skw document` too, so existing commands preserve primitives.

`tarav-hugentics` is the first adoption: 97 bound blocks and 33 declared internal
links. Its cross-file parents were explicitly authored, its existing compiled
Markdown stayed byte-identical, and the mechanical source migration's context
baselines were explicitly observed. Three external `tarav-pkg` links remain
visible conformance findings pending explicit external block modeling.


`tarav.skw.skills.SkillPackage(root)` composes document sources into a skill.
Its typed `.skw/skill.json` manifest declares `type`:
`Tarav.Skillware.SkillPackage`, `schema_version`: 1, `entrypoint`, `sources`,
`files`, and `dependencies`. Sources and deployed files are package-relative
paths. Dependencies have `kind` (`skill` or developer-only `file`), a relative
`path`, and `purposes` containing `developer`, `consumer`, or both. Purposes
are separate from context roles. Document context remains maintenance input;
declaring a consumer dependency never dumps that context into compiled text.

Library operations are `check()`, `build()`, and `deploy(destination)`.
CLI equivalents use `tarav skw skills check|build|deploy --project <root>`;
deploy additionally requires `--destination <new-directory>`.
Build compiles all declared documents without accepting context baselines.
Deploy copies only declared consumer files to a fresh directory, preserving
file modes, and returns external consumer skill requirements plus findings.
It does not install those other skills or recursively copy their sources.
Findings remain visible without gating publication; missing files still
prevent a faithful copy. Existing destinations are never overwritten.

Checks cover document lint, duplicate outputs, missing deployed files,
dependency availability, and inline Markdown file-link coverage. Fragment
anchors, reference-style links, prose mentions, and semantic completeness are
not assessed by this first checker. Diagram-to-Markdown publication remains
a separate publication capability described below.

## Diagram.Model publication

Add `publications` to `.skw/skill.json`: an array of package-relative source
paths, for example `[".skw/src/model.publication.json"]`. Add its output to
the manifest's `files` so it ships to consumers. A publication source is:

```json
{
  "type": "Tarav.Skillware.ModelPublication",
  "schema_version": 1,
  "namespace": "../../../../diagram-namespace",
  "model": "MODEL-SHIP-UUID",
  "blocks": ["BLOCK-SHIP-UUID"],
  "output": "references/model.md"
}
```

Replace the example path and identities with actual Diagram coordinates.
Namespace paths resolve relative to the publication source; output paths
resolve relative to the skill package. Blocks are selected explicitly from
the Model's primary projection and rendered in declaration order. There is
no implicit dependency expansion, inference, or generation. Collection-only
content is not selected through this first publication route.

`tarav skw skills build --project <package>` publishes model outputs before
compiling document sources. `check` detects stale publications and product
drift without writing; `deploy` copies the resulting Markdown along with the
other declared consumer files. Consumers need no Diagram to read the export.

The Python API is `tarav.skw.publication.ModelPublication(source, root=...)`,
with `render()`, `check()`, and `compile()`. It reuses `Kernel.Writing.Block`,
including its assessment markers and findings; it does not invent scores or
claim reviewed wording. No Chatlas evidence is loaded automatically, so some
assessments can remain unassessable. Findings do not block publication.

`.skw/publications.lock.json` is a typed development Record containing hashes
of the declaration, Model ships/annotations, and compiled product. This first
version conservatively fingerprints the whole Model: unrelated changes may
request republication. Markdown comments retain namespace and Block Ship
coordinates. Modeling always happens in Diagram; compiled Markdown is never
an independent authoring surface. Check failures never repair it silently.
