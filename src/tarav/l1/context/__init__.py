"""The Context graph: objects contribute triples, an Explorer collects them.

Every object answers ``obj.context.triplets()`` with what it contributes
about itself. ``ContextExplorer`` holds the RDF graph collected from the
objects it opened. The graph only grows; the focus moves, with a history.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal as Direction

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.term import Node

from tarav.l0.kernel.identity import TypeShip, WorkflowShip
from tarav.l0.kernel.records import TaravClass, TaravEntity, TaravObject, TaravType, entity


CONTEXT_WORKFLOW_SHIP = WorkflowShip("ae6fb02b-b82f-4f64-82e8-67f28a76d179")

LITERALS = (str, int, float, bool)

Subject = TaravType | type[TaravType]
Value = Subject | str | int | float | bool


@dataclass(frozen=True, slots=True)
class ContextEdge:
    """One triple seen from the focus: ``out`` when the focus is its subject."""

    direction: Direction["out", "in"]
    predicate: str
    node: Value


# tarav.breadcrumb 63241207e6c1a0bd61f15732e7700233170cbfcb77fa5794e223dd6aec67e0c4
# tarav.breadcrumb 8a8e2940fa0b92fbc9e9931c67a88bd697bae775d8c46708659aedb52ad40eb0
# tarav.breadcrumb 2a5f824db625f173d446751f2a61ad1e17f802631ea5cc3fd27b91fc341b5010
class ContextExplorer(TaravObject):
    """The graph collected from opened objects, a focus, and its history."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f3e47a44-5182-47d5-b6d5-cad8a674b7df"),
                          name="Tarav.Context.Explorer", workflow=CONTEXT_WORKFLOW_SHIP)

    def __init__(self, subject: Subject, *, resolve: Callable[[str], Subject] | None = None) -> None:
        super().__init__()
        self.graph = Graph()
        self.objects: dict[Node, object] = {}
        self.opened: set[Node] = set()
        self._resolve = resolve
        self._blank: dict[int, BNode] = {}
        start = self.open(subject)
        self.history: list[Node] = [start]
        self.position = 0

    @property
    def focus(self) -> object:
        return self.objects[self.history[self.position]]

    def open(self, target: Subject | str) -> Node:
        """Collect the triples an object contributes, once; return its node."""
        if isinstance(target, str):
            if self._resolve is None:
                raise KeyError(f"Nothing resolves identifiers in this Explorer: {target!r}")
            target = self._resolve(target)
        node = self._node(target)
        if node not in self.opened:
            self.opened.add(node)
            for triple in self.objects[node].context.triplets():
                self._add(triple)
        return node

    def ls(self) -> tuple[ContextEdge, ...]:
        """The edges at the focus among the triples collected so far."""
        here = self.history[self.position]
        edges = [ContextEdge("out", str(p), self._value(o)) for p, o in self.graph.predicate_objects(here)]
        edges += [ContextEdge("in", str(p), self.objects[s]) for s, p in self.graph.subject_predicates(here)]
        return tuple(edges)

    def follow(self, edge: ContextEdge | int) -> ContextExplorer:
        """Move the focus along an edge and open what it reaches."""
        if isinstance(edge, int):
            edge = self.ls()[edge]
        if isinstance(edge.node, LITERALS):
            raise TypeError(f"A literal cannot be followed: {edge.node!r}")
        node = self.open(edge.node)
        del self.history[self.position + 1:]
        self.history.append(node)
        self.position += 1
        return self

    def back(self) -> ContextExplorer:
        if self.position == 0:
            raise IndexError("Nothing to go back to")
        self.position -= 1
        return self

    def forward(self) -> ContextExplorer:
        if self.position == len(self.history) - 1:
            raise IndexError("Nothing to go forward to")
        self.position += 1
        return self

    def query(self, sparql: str) -> bool | list[dict[str, Value | None]]:
        """Run SPARQL over the graph collected so far; nothing is opened."""
        result = self.graph.query(sparql)
        if result.type == "ASK":
            return bool(result.askAnswer)
        if result.type != "SELECT":
            raise ValueError(f"Only SELECT and ASK queries are supported, not {result.type}")
        names = [str(name) for name in result.vars]
        return [{name: None if term is None else self._value(term) for name, term in zip(names, row)}
                for row in result]

    def node(self, value: Value) -> Node:
        """The graph term of an object or literal, as this Explorer names it."""
        return Literal(value) if isinstance(value, LITERALS) else self._node(value)

    def _node(self, value: Subject) -> Node:
        if isinstance(value, type):
            value = entity(value)
        if not isinstance(value, TaravType):
            raise TypeError(f"Context triples hold Tarav objects or literals, not {type(value).__name__}")
        if isinstance(value, TaravEntity):
            node = URIRef(f"urn:uuid:{value.id}")
        else:
            node = self._blank.setdefault(id(value), BNode())
        self.objects.setdefault(node, value)
        return node

    def _add(self, triple: tuple) -> None:
        subject, predicate, target = triple
        if not isinstance(predicate, str) or not predicate:
            raise TypeError(f"A Context predicate is an IRI string, not {predicate!r}")
        self.graph.add((self._node(subject), URIRef(predicate), self.node(target)))

    def _value(self, term: Node) -> Value:
        if isinstance(term, Literal):
            return term.toPython()
        if term not in self.objects and isinstance(term, URIRef):
            return str(term)  # a predicate, as triples write it
        return self.objects[term]


__all__ = ["CONTEXT_WORKFLOW_SHIP", "ContextEdge", "ContextExplorer"]
