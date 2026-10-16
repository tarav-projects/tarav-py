"""Run with `tarav run -- examples/object_context.py` from tarav-py."""

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip, entity
from tarav.l1.context import ContextExplorer, ContextHook
from tarav.l3.runtime import get_runtime


TITLE = "urn:example:context:title"
LENGTH = "urn:example:context:title-length"


class Document(TaravObject):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("9ff8811a-2146-4e04-8131-ec7a2e04ec51"),
                          name="Tarav.Example.ContextDocument")

    def __init__(self, title):
        super().__init__()
        self.title = title

    class Context(TaravObject.Context):
        def _class_context_hook(self, cxt):
            super()._class_context_hook(cxt)  # inherited type triple
            cxt.options.setdefault("include_title", True)

        def _obj_context_hook(self, cxt):
            super()._obj_context_hook(cxt)
            if cxt.options["include_title"]:
                cxt.triplets.append((self.obj, TITLE, self.obj.title))


class TitleLengthHook(ContextHook):
    def __init__(self, predicate):
        self.predicate = predicate

    def run(self, cxt):
        if isinstance(cxt.subject, Document):
            cxt.triplets.append((cxt.subject, self.predicate, len(cxt.subject.title)))
            cxt.hints["title-length"] = "computed from the instance title"


def main():
    runtime = get_runtime()
    runtime.contexts.register("example.title-length", TitleLengthHook(LENGTH))
    try:
        document = Document("Shared context")
        cxt = document.context.build()
        assert cxt.subject is document and cxt.status == "completed"
        assert [run.stage for run in cxt.runs] == ["class", "instance", "external"]

        explorer = ContextExplorer(cxt)
        assert explorer.contexts[explorer.node(document)] is cxt
        rows = explorer.query(f"""
            SELECT ?title ?length WHERE {{
                ?document <{TITLE}> ?title ; <{LENGTH}> ?length .
            }}
        """)
        assert rows == [{"title": "Shared context", "length": 14}]

        class_context = Document.context.build()
        assert isinstance(class_context.subject, TaravClass)
        assert class_context.subject.id == entity(Document).id
        assert len(class_context.triplets) == 1  # Document's instance hooks did not run

        print("stages:", ", ".join(run.stage for run in cxt.runs))
        print("triples:", len(explorer.graph))
        print("query:", rows)
        print("class context:", class_context.subject.name)
    finally:
        runtime.contexts.unregister("example.title-length")


if __name__ == "__main__":
    main()
