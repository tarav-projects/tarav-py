"""Run with ``uv run --extra future tarav run -- examples/future_diagram.py``."""

from pathlib import Path
from tempfile import TemporaryDirectory

from tarav.l1._future.context import ContextViewEntry
from tarav.l2._future.demo import Demo


# tarav.context 473c89a0:8944495a171e5499
with TemporaryDirectory(prefix="tarav-future-example-") as directory:
    demo = Demo(Path(directory)).seed()
    explorer = demo.open().select("messages").select("by-alice")

    def messages():
        return [entry.open().read_text() for entry in explorer.ls()
                if not isinstance(entry, ContextViewEntry)]

    print("Stored Alice messages:", messages())
    explorer.expand("runtime-turn")
    print("After loading runtime context:", messages())
    print("SPARQL:", explorer.view.sparql)
    print("Loaded triples:", explorer.diagram.triple_count)
