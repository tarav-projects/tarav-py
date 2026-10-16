"""Objects contribute triples; a Context Explorer collects and explores them."""

from __future__ import annotations

import pytest

from tarav.l0.kernel import RDF_TYPE, TaravClass, TaravObject, TypeShip, entity
from tarav.l1.context import ContextBuildError, ContextBuilder, ContextEdge, ContextExplorer, ContextHook, ObjectContext
from tarav.l1.poi import POI
from tarav.l3.runtime import create_runtime, get_runtime, set_runtime

AUTHOR = "urn:tarav:test:author"
NAME = "urn:tarav:test:name"


class Person(TaravObject):
    """An object that adds a name and an author to its default triple."""

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("0b6f3f43-57f0-4a5e-9a33-2d1fb7c58e01"),
                          name="Tarav.Test.Context.Person")

    def __init__(self, name: str, author: TaravObject | None = None) -> None:
        super().__init__()
        self.name, self.author = name, author

    class Context(TaravObject.Context):
        def _obj_context_hook(self, cxt):
            super()._obj_context_hook(cxt)
            person = self.obj
            cxt.triplets.append((person, NAME, person.name))
            if person.author is not None:
                cxt.triplets.append((person, AUTHOR, person.author))


def test_an_object_contributes_its_type_by_default() -> None:
    poi_class = entity(POI)
    [(subject, predicate, target)] = POI.context.build().triplets
    assert (subject.id, predicate, target.id) == (poi_class.id, RDF_TYPE, entity(TaravClass).id)

    explorer = POI.context()
    [(own, kind, its_class)] = explorer.context.build().triplets
    assert own is explorer and kind == RDF_TYPE and its_class.name == "Tarav.Context.Explorer"


def test_context_opens_an_explorer_focused_on_the_subject() -> None:
    get_runtime()  # composing the runtime configures `.context()`
    alice = Person("alice")
    explorer = alice.context()

    assert isinstance(explorer, ContextExplorer) and explorer.focus is alice
    edges = explorer.ls()
    assert sorted((edge.direction, edge.predicate) for edge in edges) == [("out", RDF_TYPE), ("out", NAME)]
    assert {edge.predicate: edge.node for edge in edges}[NAME] == "alice"
    assert {edge.predicate: edge.node for edge in edges}[RDF_TYPE].name == "Tarav.Test.Context.Person"


def test_following_opens_the_target_and_the_graph_only_grows() -> None:
    alice = Person("alice")
    bob = Person("bob", author=alice)
    explorer = bob.context()
    assert len(explorer.graph) == 3 and explorer.node(alice) not in explorer.opened

    explorer.follow(ContextEdge("out", AUTHOR, alice))
    assert explorer.focus is alice
    assert len(explorer.graph) == 5  # alice's type and name joined bob's three triples
    assert ContextEdge("in", AUTHOR, bob) in explorer.ls()

    explorer.follow(next(edge for edge in explorer.ls() if edge.predicate == RDF_TYPE))
    assert explorer.focus.name == "Tarav.Test.Context.Person"
    explorer.follow(next(edge for edge in explorer.ls() if edge.direction == "out"))
    assert explorer.focus.name == "Tarav.Class"
    # the class of classes is its own type: following it stays there
    explorer.follow(next(edge for edge in explorer.ls() if edge.direction == "out"))
    assert explorer.focus.name == "Tarav.Class"
    size = len(explorer.graph)

    assert explorer.back().back().focus.name == "Tarav.Test.Context.Person"
    assert explorer.back().focus is alice and explorer.back().focus is bob
    with pytest.raises(IndexError):
        explorer.back()
    assert explorer.forward().focus is alice
    assert len(explorer.graph) == size  # moving the cursor adds and removes nothing

    explorer.follow(ContextEdge("out", AUTHOR, alice))  # a new step drops the old forward path
    with pytest.raises(IndexError):
        explorer.forward()


def test_a_literal_cannot_be_followed_and_bad_triples_are_rejected() -> None:
    explorer = Person("alice").context()
    with pytest.raises(TypeError, match="literal"):
        explorer.follow(next(edge for edge in explorer.ls() if edge.predicate == NAME))

    class Broken(Person):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(target=cls, id=TypeShip("8a0f6a4e-2b8b-4f3c-b2a1-6f0d7e9c3b12"),
                              name="Tarav.Test.Context.Broken")

        class Context(Person.Context):
            def _obj_context_hook(self, cxt):
                super()._obj_context_hook(cxt)
                cxt.triplets.append((self.obj, entity(Person), "x"))

    with pytest.raises(TypeError, match="IRI string"):
        Broken("x").context()


def test_identifiers_open_through_the_resolver() -> None:
    by_id = get_runtime().context("Tarav.POI")
    assert by_id.focus.target is POI
    explorer = get_runtime().context(Person("alice"))
    node = explorer.open("Tarav.POI")
    assert explorer.objects[node].id == entity(POI).id and node in explorer.opened
    assert explorer.focus.name == "alice"  # opening collects; only following moves

    with pytest.raises(KeyError, match="Nothing resolves"):
        ContextExplorer(Person("alice").context.build()).open("Tarav.POI")


def test_queries_run_over_what_is_open_and_open_nothing() -> None:
    alice = Person("alice")
    explorer = Person("bob", author=alice).context()
    select = f"SELECT ?who ?name WHERE {{ ?who <{NAME}> ?name }}"

    assert [row["name"] for row in explorer.query(select)] == ["bob"]
    assert explorer.query(f"ASK {{ ?x <{AUTHOR}> ?y }}") is True
    assert explorer.node(alice) not in explorer.opened

    explorer.open(alice)
    rows = explorer.query(select)
    assert sorted(row["name"] for row in rows) == ["alice", "bob"]
    assert {row["who"].name for row in rows} == {"alice", "bob"}
    assert {row["p"] for row in explorer.query("SELECT ?p WHERE { ?s ?p ?o }")} == {RDF_TYPE, NAME, AUTHOR}
    with pytest.raises(ValueError, match="SELECT and ASK"):
        explorer.query("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }")


@pytest.fixture
def context_runtime():
    previous = get_runtime()
    runtime = create_runtime()
    set_runtime(runtime)
    try:
        yield runtime
    finally:
        set_runtime(previous)


def test_build_passes_one_mutable_result_through_class_instance_and_external_hooks(context_runtime):
    seen = []

    class Document(Person):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("3f286f51-582a-4537-a5b5-af4bd02cfb9c"),
                              name="Tarav.Test.Context.Document")

        class Context(Person.Context):
            def _class_context_hook(self, cxt):
                super()._class_context_hook(cxt)
                seen.append(cxt)
                cxt.hints["stages"] = ["class"]
                cxt.options["label"] += ":class"

            def _obj_context_hook(self, cxt):
                super()._obj_context_hook(cxt)
                seen.append(cxt)
                cxt.hints["stages"].append("instance")
                cxt.options["label"] += ":instance"

    class Annotate(ContextHook):
        def run(self, cxt):
            seen.append(cxt)
            cxt.hints["stages"].append("annotations")
            cxt.triplets[:] = [triple for triple in cxt.triplets if triple[1] != NAME]
            cxt.triplets.append((cxt.subject, NAME, cxt.options["label"]))

    class Finish(ContextHook):
        def run(self, cxt):
            seen.append(cxt)
            cxt.hints["stages"].append("finish")

    context_runtime.contexts.register("annotations", Annotate())
    context_runtime.contexts.register("finish", Finish())
    document = Document("original")
    options = {"label": "requested"}
    cxt = document.context.build(options=options)

    assert isinstance(cxt, ObjectContext) and cxt.subject is document
    assert all(value is cxt for value in seen) and len(seen) == 4
    assert cxt.hints["stages"] == ["class", "instance", "annotations", "finish"]
    assert [(predicate, target) for _, predicate, target in cxt.triplets if predicate == NAME] == [
        (NAME, "requested:class:instance")]
    assert options == {"label": "requested"}
    assert cxt.status == "completed"
    assert [(run.stage, run.name, run.before, run.after) for run in cxt.runs] == [
        ("class", "_class_context_hook", 0, 1), ("instance", "_obj_context_hook", 1, 2),
        ("external", "annotations", 2, 2), ("external", "finish", 2, 2)]
    assert all(run.error is None for run in cxt.runs)
    assert not hasattr(document.context, "triplets")


def test_class_access_runs_the_identity_types_hooks_not_the_represented_types():
    class ClassIdentity(TaravClass):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("ad1ec085-9ff6-4cbe-a0e3-7397ec0fe40d"),
                              name="Tarav.Test.Context.ClassIdentity")

        class Context(TaravClass.Context):
            def _class_context_hook(self, cxt):
                super()._class_context_hook(cxt)
                cxt.hints["stages"] = ["identity-class"]

            def _obj_context_hook(self, cxt):
                super()._obj_context_hook(cxt)
                cxt.hints["stages"].append("identity-instance")
                cxt.triplets.append((self.obj, NAME, self.obj.target.__name__))

    class Document(Person):
        @classmethod
        def class_entity(cls):
            return ClassIdentity(target=cls, id=TypeShip("b0b33879-fbe7-4d69-b61d-d756ce2f6f2e"),
                                 name="Tarav.Test.Context.IdentityDocument")

        class Context(Person.Context):
            def _class_context_hook(self, cxt):
                raise AssertionError("Document's hooks describe Document instances")

    for cxt in (Document.context.build(), entity(Document).context.build()):
        assert isinstance(cxt.subject, ClassIdentity) and cxt.subject.target is Document
        assert cxt.hints["stages"] == ["identity-class", "identity-instance"]
        assert cxt.triplets[0][1] == RDF_TYPE
        assert cxt.triplets[0][2].target is ClassIdentity
        assert cxt.triplets[1] == (cxt.subject, NAME, "Document")


def test_super_composes_both_hook_stages_once_across_a_diamond():
    class Left(TaravObject):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("a3e2b016-699b-4c1a-978f-45e73c0ed578"), name="Test.ContextLeft")

        class Context(TaravObject.Context):
            def _class_context_hook(self, cxt):
                super()._class_context_hook(cxt)
                cxt.hints.setdefault("order", []).append("left-class")

            def _obj_context_hook(self, cxt):
                super()._obj_context_hook(cxt)
                cxt.hints["order"].append("left-instance")

    class Right(TaravObject):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("4bc786e6-76eb-4f0b-9b29-de656bfda283"), name="Test.ContextRight")

        class Context(TaravObject.Context):
            def _class_context_hook(self, cxt):
                super()._class_context_hook(cxt)
                cxt.hints.setdefault("order", []).append("right-class")

            def _obj_context_hook(self, cxt):
                super()._obj_context_hook(cxt)
                cxt.hints["order"].append("right-instance")

    class Both(Left, Right):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("22b942c4-724c-46e5-9d22-4b608d5125e0"), name="Test.ContextBoth")

        class Context(Left.Context, Right.Context):
            pass

    class Derived(Both):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("2e5f3c03-383f-4552-8241-036710481c50"), name="Test.ContextDerived")

    cxt = Derived().context.build()
    assert cxt.hints["order"] == ["right-class", "left-class", "right-instance", "left-instance"]
    assert len(cxt.triplets) == 1 and cxt.triplets[0][2].id == entity(Derived).id


def test_external_registration_is_ordered_snapshotted_and_runtime_local():
    first, second = create_runtime(), create_runtime()

    class Late(ContextHook):
        def run(self, cxt):
            cxt.hints["late"] = True

    class RegisterDuringBuild(ContextHook):
        def __init__(self, builder):
            self.builder = builder

        def run(self, cxt):
            self.builder.register("late", Late())
            self.builder.unregister("first")
            cxt.hints["first"] = True

    first.contexts.register("first", RegisterDuringBuild(first.contexts))
    with pytest.raises(KeyError, match="already registered"):
        first.contexts.register("first", Late())
    person = Person("alice")
    assert first.contexts.build(person).hints == {"first": True}
    assert first.contexts.build(person).hints == {"late": True}
    assert second.contexts.build(person).hints == {}
    first.contexts.unregister("late")
    assert first.contexts.build(person).hints == {}


def test_failed_hooks_preserve_diagnostics_and_do_not_publish_a_partial_graph():
    builder = ContextBuilder()
    alice, bob = Person("alice"), Person("bob")
    context = builder.build(alice)
    explorer = ContextExplorer(context, build=builder.build)
    before = set(explorer.graph)
    cause = ValueError("annotation source unavailable")

    class Fail(ContextHook):
        def run(self, cxt):
            cxt.triplets.append((cxt.subject, AUTHOR, alice))
            raise cause

    builder.register("annotations", Fail())
    with pytest.raises(ContextBuildError) as raised:
        explorer.open(bob)
    failed = raised.value.context
    assert raised.value.cause is cause and raised.value.__cause__ is cause
    assert failed.subject is bob and failed.status == "failed"
    assert failed.runs[-1].error == "ValueError: annotation source unavailable"
    assert (failed.runs[-1].before, failed.runs[-1].after) == (2, 3)
    assert explorer.focus is alice and set(explorer.graph) == before
    assert explorer.node(bob) not in explorer.opened
    builder.unregister("annotations")
    explorer.open(bob)
    assert explorer.contexts[explorer.node(bob)].status == "completed"


def test_explorer_retains_built_results_and_collects_each_subject_once():
    builder, alice = ContextBuilder(), Person("alice")
    calls = []

    class Contribute(ContextHook):
        def run(self, cxt):
            calls.append(cxt.subject)
            cxt.hints["source"] = "external"

    builder.register("contributor", Contribute())
    cxt = builder.build(alice)
    explorer = ContextExplorer(cxt, build=builder.build)
    node = explorer.node(alice)
    assert explorer.contexts[node] is cxt
    assert explorer.contexts[node].hints == {"source": "external"}
    explorer.open(alice)
    assert calls == [alice]
    cxt.triplets.clear()  # the collected graph is a snapshot, not this mutable list
    assert len(explorer.graph) == 2

    # A context is also a Tarav object: asking for its context describes it.
    own = cxt.context()
    assert own.focus is cxt
    assert own.ls()[0].node.target is ObjectContext


def test_invalid_triplets_are_not_partially_collected_and_can_be_retried():
    alice, bob = Person("alice"), Person("bob")
    builder = ContextBuilder()
    explorer = ContextExplorer(builder.build(alice), build=builder.build)
    before = set(explorer.graph)

    class Invalid(ContextHook):
        def run(self, cxt):
            cxt.triplets.append((cxt.subject, NAME, "a valid preceding triple"))
            cxt.triplets.append((cxt.subject, entity(Person), "invalid predicate"))

    builder.register("invalid", Invalid())
    with pytest.raises(TypeError, match="IRI string"):
        explorer.open(bob)
    assert set(explorer.graph) == before
    assert explorer.node(bob) not in explorer.contexts
    assert explorer.node(bob) not in explorer.opened
    builder.unregister("invalid")
    explorer.open(bob)
    assert explorer.contexts[explorer.node(bob)].subject is bob


def test_hook_instances_bundle_dependencies_keep_state_and_choose_subjects(context_runtime):
    class Labels(ContextHook):
        def __init__(self, labels):
            self.labels = labels
            self.used = []

        def run(self, cxt):
            subject = cxt.subject
            if not isinstance(subject, Person) or subject.name not in self.labels:
                return
            self.used.append(subject)
            cxt.triplets.append((subject, "urn:tarav:test:label", self.labels[subject.name]))

    labels = {"alice": "first"}
    hook = Labels(labels)
    context_runtime.contexts.register("labels", hook)
    alice, bob = Person("alice"), Person("bob")
    alice_context = alice.context.build()
    ignored = bob.context.build()
    class_context = Person.context.build()
    labels["bob"] = "second"  # the registered instance retains its supplied dependency
    bob_context = bob.context.build()

    assert hook.used == [alice, bob]
    assert alice_context.triplets[-1] == (alice, "urn:tarav:test:label", "first")
    assert bob_context.triplets[-1] == (bob, "urn:tarav:test:label", "second")
    assert [(p, value) for _, p, value in ignored.triplets if p == NAME] == [(NAME, "bob")]
    assert len(ignored.triplets) == 2 and len(class_context.triplets) == 1
    assert [(run.name, run.before, run.after) for run in ignored.runs[-1:]] == [("labels", 2, 2)]


def test_external_registration_requires_a_concrete_context_hook_instance():
    class Concrete(ContextHook):
        def run(self, cxt):
            cxt.hints["concrete"] = True

    class Duck:
        def run(self, cxt):
            raise AssertionError("Unregistered duck-typed hook ran")

    with pytest.raises(TypeError, match="abstract"):
        ContextHook()
    builder = ContextBuilder()
    for invalid in (lambda cxt: None, Concrete, Duck()):
        with pytest.raises(TypeError, match="ContextHook instance"):
            builder.register("contributor", invalid)
    builder.register("contributor", Concrete())
    assert builder.build(Person("alice")).hints == {"concrete": True}
