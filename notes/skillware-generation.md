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

Run `tarav skw document prepare .skw/src/explanation.skw.json explain`.
The JSON response supplies the invocation ID, expanded prompt, and previous
output. The agent edits `output` in the source to an array of lines, then runs
`tarav skw document record .skw/src/explanation.skw.json <invocation-id>`.
Recording rejects inputs changed since preparation; it does not judge meaning.
`tarav skw document compile .skw/src/explanation.skw.json` assembles the entire
product and reports findings. `tarav skw document lint <source>` is read-only.
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

`tarav skw document context <source> <block>` returns resolved context in order.
Preparation includes this context and its fingerprint in its annotation;
recording rejects context changed since preparation. For maintained existing
content, `observe-context <source> <block>` explicitly stores a context baseline
without asserting any generation history or agent receipt. Python exposes
`context(block)` and `observe_context(block)` on `Document`.

Lint reports `context-unobserved`, `context-unresolvable`, and `stale-context`.
Changing declarations or referenced content invalidates the observation.
Lint and compile never refresh context baselines; explicit recording or
observation does. An observation says nothing about semantic correctness.

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
