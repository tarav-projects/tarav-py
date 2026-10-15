"""Typed SPARQL views and navigation over one progressively growing Diagram."""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import RDF

from tarav.l0.kernel import TaravClass, entity

from .graph import Diagram, MEMBER
from .types import FutureObject, class_projection


class UnsupportedView(TypeError):
    pass


# tarav.context 473c89a0:2231281cb94571ae
class ViewRequest(FutureObject):
    """A typed, explicit transformation of a current SPARQL selection."""

    @classmethod
    def class_entity(cls):
        return class_projection(cls, "eeedc931-e87a-468b-b748-be87dc022b7a", "ViewRequest")

    def accepts(self, current):
        return False

    def apply(self, current):
        raise UnsupportedView(type(self).__name__)


class Along(ViewRequest):
    """Select outgoing targets through one represented predicate."""

    @classmethod
    def class_entity(cls):
        return class_projection(cls, "455d84a8-29fb-49a2-bc69-04dff2c0e93f", "Along")

    def __init__(self, predicate):
        super().__init__()
        self.predicate = predicate

    def accepts(self, current):
        return not current.qualifications

    def apply(self, current):
        predicate = current.diagram.ref(self.predicate).n3()
        return f"?focus {predicate} ?target . BIND({predicate} AS ?predicate)", {}


class Where(ViewRequest):
    """Add a predicate/value condition on the selected target."""

    @classmethod
    def class_entity(cls):
        return class_projection(cls, "45488cc8-f37a-45d4-9062-b06aa79b40f7", "Where")

    def __init__(self, predicate, value):
        super().__init__()
        if value is None:
            raise TypeError("Where requires a bound RDF value")
        self.predicate, self.value = predicate, value

    def accepts(self, current):
        return bool(current.pattern) and not any(
            isinstance(previous, Where) and
            current.diagram.ref(previous.predicate) == current.diagram.ref(self.predicate)
            and previous.value == self.value for previous in current.qualifications
        )

    def apply(self, current):
        predicate = current.diagram.ref(self.predicate).n3()
        name = "filter" + str(len(current.qualifications))
        return f"{current.pattern}\n?target {predicate} ?{name} .", {name: self.value}


@dataclass(frozen=True)
class Location:
    subject: object
    pattern: str = ""
    bindings: tuple = ()
    qualifications: tuple = ()


class ContextEntry(FutureObject):
    @classmethod
    def class_entity(cls):
        return class_projection(cls, "61458b54-a647-42ec-8921-2292b46b193b", "ContextEntry")

    def __init__(self, key, target, *, predicate=None, relation=None, label=None):
        super().__init__()
        self.key, self.target = key, target
        self.predicate, self.relation = predicate, relation
        self.label = label or key

    @property
    def name(self):
        return self.key

    def open(self):
        return self.target


class ContextView(FutureObject):
    @classmethod
    def class_entity(cls):
        return class_projection(cls, "45f8a742-8849-42e1-b96b-b85df8dcdb3a", "ContextView")

    def __init__(self, diagram, location):
        super().__init__()
        self.diagram, self.location = diagram, location

    @property
    def subject(self):
        return self.location.subject

    @property
    def qualifications(self):
        return self.location.qualifications

    @property
    def pattern(self):
        return self.location.pattern

    @property
    def bindings(self):
        return {"focus": self.subject, **dict(self.location.bindings)}

    @property
    def sparql(self):
        if not self.pattern:
            return ""
        return "SELECT DISTINCT ?source ?predicate ?target WHERE {\n" + self.pattern + "\n}"

    def refine(self, *, views=()):
        current = self
        for request in views:
            if not isinstance(request, ViewRequest) or not request.accepts(current):
                raise UnsupportedView(f"Unsupported qualification: {type(request).__name__}")
            pattern, bindings = request.apply(current)
            combined = {**dict(current.location.bindings), **bindings}
            current = ContextView(self.diagram, Location(
                self.subject, pattern, tuple(combined.items()),
                (*current.qualifications, request),
            ))
        return current

    def ls(self):
        if not self.pattern:
            return tuple(ContextViewEntry(self, name) for name in self.available_views())
        result = []
        for row in self.diagram.query(self.sparql, bindings=self.bindings):
            target = self.diagram.resolve(row.target)
            predicate = self.diagram.resolve(row.predicate)
            incoming = self.qualifications[0] == "in"
            s, o = (row.target, self.diagram.ref(self.subject)) if incoming else (
                row.source if row.source is not None else self.diagram.ref(self.subject), row.target,
            )
            relation = self.diagram.relation(s, row.predicate, o)
            result.append(ContextEntry(
                str(relation.id), target, predicate=predicate, relation=relation,
                label=self.diagram.label(predicate) + " → " + self.diagram.label(target),
            ))
        return (*sorted(result, key=lambda entry: (entry.label, entry.key)),
                *(ContextViewEntry(self, name) for name in self.available_views()))

    def available_views(self):
        builtins = ("out", "in", "type", "model") if not self.pattern else ()
        return (*builtins, *(name for name, request in self.diagram.views.items()
                             if request.accepts(self)))

    def get(self, key):
        for entry in self.ls():
            if entry.key == key:
                return entry
        raise KeyError(key)

    def open(self, key):
        if key in self.diagram.views:
            return self.refine(views=(self.diagram.views[key],))
        if not self.pattern:
            if key == "out":
                pattern = "?focus ?predicate ?target ."
            elif key == "in":
                pattern = "?target ?predicate ?focus ."
            elif key == "type":
                pattern = f"?focus <{RDF.type}> ?target . BIND(<{RDF.type}> AS ?predicate)"
            elif key == "model":
                owner = self.subject if isinstance(self.subject, TaravClass) else entity(type(self.subject))
                self.diagram.expand(owner)
                predicate = self.diagram.ref(MEMBER).n3()
                source = self.diagram.ref(owner).n3()
                pattern = f"{source} {predicate} ?target . BIND({predicate} AS ?predicate) BIND({source} AS ?source)"
            else:
                raise KeyError(key)
            return ContextView(self.diagram, Location(self.subject, pattern, (), (key,)))
        return self.get(key).open()


class ContextViewEntry(ContextEntry):
    @classmethod
    def class_entity(cls):
        return class_projection(cls, "1ac09605-85c0-4438-a414-31d03c9d0a9a", "ContextViewEntry")

    def __init__(self, view, key):
        super().__init__(key, None)
        self.view = view

    def open(self):
        return self.view.open(self.key)


# tarav.context 473c89a0:2231281cb94571ae
class ContextExplorer:
    """History changes focus/query; the shared Diagram retains loaded triples."""

    def __init__(self, diagram: Diagram, subject):
        self.diagram = diagram
        subject = diagram.expand(subject)
        self._history = [ContextView(diagram, Location(subject))]
        self._position = 0

    @property
    def view(self):
        return self._history[self._position]

    @property
    def subject(self):
        return self.view.subject

    def _enter(self, view):
        self._history[self._position + 1:] = [view]
        self._position += 1
        return self

    def ls(self):
        return self.view.ls()

    def open(self, key):
        return self.view.open(key)

    def select(self, key):
        root = ContextView(self.diagram, Location(self.subject))
        view = root if key in root.available_views() else self.view
        selected = view.open(key)
        if not isinstance(selected, ContextView):
            raise TypeError("select() requires a view; use follow() for an object")
        return self._enter(selected)

    def refine(self, *, views=()):
        return self._enter(self.view.refine(views=views))

    def follow(self, obj):
        if isinstance(obj, ContextEntry):
            obj = obj.open()
        if isinstance(obj, ContextView):
            if obj.diagram is not self.diagram:
                raise ValueError("A view belongs to a different explorer graph")
            return self._enter(obj)
        return self._enter(ContextView(self.diagram, Location(self.diagram.expand(obj))))

    def expand(self, key):
        self.diagram.load(self.subject, key)
        return self

    def expansions(self):
        return self.diagram.expansions(self.subject)

    def back(self):
        if self._position:
            self._position -= 1
        return self

    def forward(self):
        if self._position + 1 < len(self._history):
            self._position += 1
        return self

    def query(self, sparql, *, bindings=None):
        return self.diagram.query(sparql, bindings={"focus": self.subject, **(bindings or {})})
