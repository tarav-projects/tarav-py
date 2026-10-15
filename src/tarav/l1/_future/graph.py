"""A progressively populated RDF graph with resolvable Python representations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from rdflib import BNode, Graph, Literal, RDF, RDFS, URIRef
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.util import from_n3

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TaravObject, TaravType, entity
from tarav.l1.context.models import TypePath

from .types import FutureEntity, FutureObject, ModelMember, class_projection


class RDFTerm(FutureObject):
    """Code representation of a vocabulary IRI, including RDF's own terms."""

    @classmethod
    def class_entity(cls):
        return class_projection(cls, "04430209-dc63-4bf5-92f9-9ad3582e67db", "RDFTerm")

    def __init__(self, iri: str, label: str):
        super().__init__()
        self.iri, self.label = iri, label

    def _to_record(self):
        return {**super()._to_record(), "iri": self.iri, "label": self.label}

    @classmethod
    def _from_record(cls, record_data):
        return cls(record_data.iri, record_data.label)

    class RecordInterface(FutureObject.RecordInterface):
        iri: str
        label: str


class RDFValue(FutureObject):
    """An RDF literal's code representation, retaining datatype and language."""

    @classmethod
    def class_entity(cls):
        return class_projection(cls, "41b25b3e-5b29-4c89-8f00-2b731b92735a", "RDFValue")

    def __init__(self, value: Literal):
        super().__init__()
        self.value = value

    @property
    def label(self):
        return str(self.value)

    def _to_record(self):
        return {**super()._to_record(), "lexical": str(self.value),
                "datatype": str(self.value.datatype) if self.value.datatype else None,
                "language": self.value.language}

    @classmethod
    def _from_record(cls, record_data):
        return cls(Literal(record_data.lexical, lang=record_data.language,
                           datatype=record_data.datatype, normalize=False))

    class RecordInterface(FutureObject.RecordInterface):
        lexical: str
        datatype: str | None = None
        language: str | None = None


TYPE = RDFTerm(str(RDF.type), "type")
LABEL = RDFTerm(str(RDFS.label), "label")
STATEMENT = RDFTerm(str(RDF.Statement), "statement")
SUBJECT = RDFTerm(str(RDF.subject), "subject")
PREDICATE = RDFTerm(str(RDF.predicate), "predicate")
OBJECT = RDFTerm(str(RDF.object), "object")
BASE = RDFTerm("urn:tarav:future:pythonBase", "Python base")
MEMBER = RDFTerm("urn:tarav:future:modelMember", "model member")
OWNER = RDFTerm("urn:tarav:future:memberOwner", "member owner")
PATH = RDFTerm("urn:tarav:future:codePath", "current code path")


# tarav.context 473c89a0:a25dc4a4402725c7
class Relation(FutureEntity):
    """One graph-local statement occurrence, inspectable as an object."""

    @classmethod
    def class_entity(cls):
        return class_projection(cls, "f31cc708-a714-41dc-a6ad-715005b646a2", "Relation")

    def __init__(self, diagram, subject, predicate, target, *, id=None):
        super().__init__(id if id is not None else Ship(uuid4()))
        self.diagram, self.subject, self.predicate, self.target = diagram, subject, predicate, target

    def _to_record(self):
        return {**super()._to_record(),
                "subject": self.diagram.ref(self.subject).n3(),
                "predicate": self.diagram.ref(self.predicate).n3(),
                "target": self.diagram.ref(self.target).n3()}

    @classmethod
    def _from_record(cls, record_data):
        raise TypeError("Computed Relation occurrences require their live Diagram")


@dataclass(frozen=True)
class Expansion:
    """An explicitly offered finite contribution; listing does not invoke it."""

    key: str
    label: str
    load: Callable[[Diagram], None]


# tarav.context 473c89a0:2231281cb94571ae
class Diagram:
    """One exploration's graph, object resolver, providers and loading offers.

    Providers receive an object and this graph. They add known relationships
    with relate() and advertise deferred contributions with offer(). Queries
    only read the accumulated graph; they never invoke providers implicitly.
    """

    def __init__(self):
        self._graph = Graph()
        self.objects = {}
        self._runtime = {}
        self._described = set()
        self._classes = {}
        self._providers = []
        self._offers = {}
        self._relations = {}
        self.views = {}
        self._models = {}
        self.revision = 0
        for term in (TYPE, LABEL, STATEMENT, SUBJECT, PREDICATE, OBJECT, BASE, MEMBER, OWNER, PATH):
            self.objects[URIRef(term.iri)] = term

    @property
    def triple_count(self):
        return len(self._graph)

    def register(self, cls: type[TaravObject], provider: Callable):
        """Register trusted contribution code on this Diagram only."""
        if not isinstance(cls, type) or not issubclass(cls, TaravObject):
            raise TypeError("Provider registration requires a TaravObject Type")
        self._providers.append((cls, provider))

    def register_view(self, name, request):
        if name in {"out", "in", "type", "model"} or name in self.views:
            raise ValueError(f"View name is already registered: {name}")
        self.views[name] = request

    def register_model(self, owner, nodes):
        """Contribute model members without editing the represented class."""
        self._models.setdefault(entity(owner).id, []).extend(nodes)
        self.ref(owner)

    def ref(self, obj):
        if isinstance(obj, type) and issubclass(obj, TaravType):
            obj = entity(obj)
        if not isinstance(obj, TaravObject):
            raise TypeError("Graph resources require TaravObject representations")
        term = self._identity(obj)
        previous = self.objects.get(term)
        if previous is not None and previous is not obj:
            if isinstance(previous, Relation) and isinstance(obj, Relation):
                def signature(relation):
                    return (entity(type(relation)).id, *(self._identity(value) for value in (
                        relation.subject, relation.predicate, relation.target,
                    )))
                agrees = signature(previous) == signature(obj)
            else:
                agrees = previous.records.to_record() == obj.records.to_record()
            if not agrees:
                raise ValueError(f"Conflicting object representations for {term}")
            # Prefer a live class projection over its detached Record.
            if isinstance(obj, TaravClass) and obj._target is not None:
                self.objects[term] = obj
        else:
            self.objects[term] = obj
        if isinstance(obj, TaravClass) and obj._target is not None:
            self._classes[obj.id] = obj.target
        if term not in self._described and not isinstance(term, Literal):
            self._described.add(term)
            self._put(term, RDF.type, self.ref(entity(type(obj))))
            self._put(term, RDFS.label, Literal(self.label(obj)))
        return term

    def _identity(self, obj):
        if isinstance(obj, RDFValue):
            term = obj.value
        elif isinstance(obj, RDFTerm):
            term = URIRef(obj.iri)
        elif isinstance(obj, TaravEntity):
            term = URIRef("urn:uuid:" + str(obj.id))
        else:
            term = self._runtime.setdefault(id(obj), BNode())
        return term

    @staticmethod
    def label(obj):
        for name in ("label", "title", "name", "path"):
            value = getattr(obj, name, None)
            if isinstance(value, str):
                return value
        return entity(type(obj)).name.rsplit(".", 1)[-1]

    def resolve(self, identifier):
        if type(identifier) is str:
            if identifier.startswith(("_:", "<", '"', "'")):
                identifier = from_n3(identifier)
            else:
                try:
                    identifier = URIRef("urn:uuid:" + str(Ship(identifier)))
                except ValueError:
                    identifier = URIRef(identifier)
        if isinstance(identifier, Literal) and identifier not in self.objects:
            self.objects[identifier] = RDFValue(identifier)
        try:
            return self.objects[identifier]
        except KeyError:
            raise KeyError(f"Identifier is outside this exploration: {identifier}") from None

    def _put(self, subject, predicate, target):
        triple = subject, predicate, target
        if triple not in self._graph:
            self._graph.add(triple)
            self.revision += 1

    def relate(self, subject, predicate, target):
        """Add a triple and return its reusable graph-local occurrence."""
        if not isinstance(target, TaravObject):
            if type(target) not in (str, int, float, bool):
                raise TypeError("Relation targets must be Tarav objects or scalar values")
            target = RDFValue(Literal(target))
        s, p, o = self.ref(subject), self.ref(predicate), self.ref(target)
        if not isinstance(p, URIRef):
            raise TypeError("RDF predicates must have IRI representations")
        if isinstance(s, Literal):
            raise TypeError("RDF literals cannot be statement subjects")
        triple = s, p, o
        if triple not in self._relations:
            relation = Relation(self, self.resolve(s), self.resolve(p), self.resolve(o))
            self._relations[triple] = relation
            r = self.ref(relation)
            self._put(r, RDF.type, RDF.Statement)
            self._put(r, RDF.subject, s)
            self._put(r, RDF.predicate, p)
            self._put(r, RDF.object, o)
        self._put(s, p, o)
        return self._relations[triple]

    def relation(self, subject, predicate, target):
        """Return a representation even for automatically contributed triples."""
        triple = subject, predicate, target
        if triple not in self._relations:
            self._relations[triple] = Relation(
                self, self.resolve(subject), self.resolve(predicate), self.resolve(target),
            )
        return self._relations[triple]

    def offer(self, subject, key, label, load):
        self._offers.setdefault(self.ref(subject), {})[key] = Expansion(key, label, load)

    def expansions(self, subject):
        return tuple(self._offers.get(self.ref(subject), {}).values())

    def expand(self, subject):
        """Add one object's finite contribution; existing triples remain."""
        subject = self.resolve(self.ref(subject))
        if isinstance(subject, TaravClass):
            try:
                target = subject.target
            except RuntimeError:
                target = None
            if target is not None:
                for base in subject.bases():
                    self.relate(subject, BASE, base)
                members = (*target.Context(target).model_nodes(),
                           *self._models.get(subject.id, ()))
                for member in members:
                    if not isinstance(member, TypePath):
                        raise TypeError("Class models contribute TypePath objects")
                    self.relate(subject, MEMBER, member)
                    self.relate(member, PATH, member.path)
                    self.relate(member, OWNER, subject)
        elif isinstance(subject, ModelMember):
            self.relate(subject, PATH, subject.path)
            owner = self._classes.get(subject.owner)
            if owner is not None:
                self.relate(subject, OWNER, entity(owner))
        elif isinstance(subject, Relation):
            self.relate(subject, SUBJECT, subject.subject)
            self.relate(subject, PREDICATE, subject.predicate)
            self.relate(subject, OBJECT, subject.target)
        for cls, provider in self._providers:
            if isinstance(subject, cls):
                provider(subject, self)
        return subject

    def load(self, subject, key):
        expansion = self._offers[self.ref(subject)][key]
        expansion.load(self)
        del self._offers[self.ref(subject)][key]

    def merge(self, other: Diagram):
        """Import loaded triples and representations, keeping local provider policy.

        Runtime resources are reconciled through their Python objects; blank
        node labels from another exploration are not treated as global IDs.
        """
        if other is self:
            return self
        translated = {}
        occurrences = {relation.id: relation for relation in other._relations.values()}
        occurrences.update({obj.id: obj for obj in other.objects.values() if isinstance(obj, Relation)})
        for term, obj in tuple(other.objects.items()):
            if not isinstance(obj, Relation):
                translated[term] = self.ref(obj)
        local_occurrences = {}
        for identity, relation in occurrences.items():
            term = URIRef("urn:uuid:" + str(identity))
            existing = self.objects.get(term)
            if existing is not None and not isinstance(existing, Relation):
                raise ValueError(f"Conflicting relationship identity: {identity}")
            local_occurrences[identity] = existing or Relation(
                self, relation.subject, relation.predicate, relation.target, id=identity,
            )
            self.objects[term] = local_occurrences[identity]
            translated[term] = term

        def translate(term):
            if term not in translated:
                translated[term] = self.ref(other.resolve(term))
            return translated[term]

        for identity, relation in occurrences.items():
            local = local_occurrences[identity]
            local.subject = self.resolve(translate(other.ref(relation.subject)))
            local.predicate = self.resolve(translate(other.ref(relation.predicate)))
            local.target = self.resolve(translate(other.ref(relation.target)))
            self.ref(local)
        for s, p, o in tuple(other._graph):
            self._put(translate(s), translate(p), translate(o))
        for triple, relation in other._relations.items():
            self._relations.setdefault(tuple(translate(term) for term in triple),
                                       local_occurrences[relation.id])
        return self

    def query(self, sparql, *, bindings=None):
        """Evaluate read queries entirely inside the accumulated RDF dataset."""
        try:
            query = prepareQuery(sparql)
        except Exception as exc:
            raise ValueError(f"Invalid SPARQL query: {exc}") from exc
        def inspect(value):
            if isinstance(value, CompValue):
                if value.name == "ServiceGraphPattern" or (
                    "datasetClause" in value and value["datasetClause"]
                ):
                    raise ValueError("Queries must stay inside the explorer's loaded graph")
                for child in value.values():
                    inspect(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    inspect(child)
        inspect(query.algebra)
        converted = {
            name: self.ref(value) if isinstance(value, (TaravObject, type)) else (
                Literal(value) if type(value) in (str, int, float, bool) else value
            ) for name, value in (bindings or {}).items()
        }
        return self._graph.query(query, initBindings=converted, use_store_provided=False)
