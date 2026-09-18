# Independent Skillware generation MVP

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
