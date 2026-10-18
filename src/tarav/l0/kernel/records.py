"""Record objects, interfaces, JSON boundaries, and retained storage roles."""

from __future__ import annotations

import inspect
import json
import math
from pathlib import Path
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, BinaryIO, Self, TextIO, TypeVar

from pydantic import BaseModel, ConfigDict

from .namespaces import NamespaceBase, check_namespace_composition
from .identity import (
    KERNEL_WORKFLOW_SHIP,
    TYPE_WORKFLOW_SHIP,
    Ship,
    TypeShip,
    WorkflowShip,
)

if TYPE_CHECKING:
    from .workflows import TaravWorkflow
    from .types import RecordTypeReference, TypeRegistry


class TaravTypeDeclarationError(TypeError):
    """A Tarav Type does not declare the class identity Tarav requires."""


class InvalidRecordJSON(ValueError):
    """Loaded JSON is not a root Record object."""


class RecordTypeMismatch(TypeError):
    """A Record identifies a different Type than the requested concrete class."""


JsonFile = TextIO | BinaryIO

_workflow_resolver: Callable[[WorkflowShip], TaravWorkflow] | None = None
_context_opener: Callable | None = None
_context_builder: Callable | None = None

# The predicate of the one triple every object contributes by default.
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def configure_context_opener(opener: Callable) -> None:
    """Supply the Context Explorer without an upward Kernel import."""
    global _context_opener
    _context_opener = opener


def configure_context_builder(builder: Callable) -> None:
    """Supply Context construction without an upward Kernel import."""
    global _context_builder
    _context_builder = builder


def configure_workflow_resolver(resolver: Callable[[WorkflowShip], TaravWorkflow]) -> None:
    """Let library composition supply workflow resolution without domain imports."""
    global _workflow_resolver
    _workflow_resolver = resolver


def resolve_workflow(ship: WorkflowShip) -> TaravWorkflow:
    if _workflow_resolver is None:
        raise RuntimeError("Workflow resolution has not been configured")
    return _workflow_resolver(ship)


class _ContextDescriptor:
    """Classes enter through their identity object's own namespace."""

    def __get__(self, instance: TaravType | None, owner: type[TaravType]):
        if instance is None:
            return entity(owner).context
        return owner.Context(instance)


class TaravType:
    """Class-level participation in Tarav's executable ontology."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("0e942bdd-8e3b-4b19-89b3-329dc7384b29"),
            name="Tarav.Type",
            workflow=KERNEL_WORKFLOW_SHIP,
        )

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Require every Tarav Type to define its own ontology projection."""

        super().__init_subclass__(**kwargs)
        if not isinstance(cls.__dict__.get("class_entity"), classmethod):
            raise TaravTypeDeclarationError(
                f"{cls.__name__} must define a class-local class_entity()"
            )
        check_namespace_composition(cls)

    # tarav.breadcrumb 0989202cb613
    # tarav.breadcrumb 057f6334bd2a
    class Context(NamespaceBase["TaravType"]):
        """Build an object's context, or open an Explorer over it.

        Construction calls the class hook, the instance hook, then external
        hooks with one result. Override hooks cooperatively with ``super()``.
        """

        def build(self, *, options: Mapping[str, object] | None = None):
            """Return the ObjectContext assembled by the configured builder."""
            if _context_builder is None:
                raise RuntimeError("Context construction has not been configured")
            return _context_builder(self.obj, options=options)

        def _class_context_hook(self, cxt) -> None:
            """The inherited class contribution, by default the subject's type."""
            cxt.triplets.append((self.obj, RDF_TYPE, entity(type(self.obj))))

        def _obj_context_hook(self, cxt) -> None:
            """The instance contribution, empty by default."""

        def __call__(self):
            """Open a Context Explorer focused on the subject."""
            if _context_opener is None:
                raise RuntimeError("Context has not been configured")
            return _context_opener(self.obj)

    context = _ContextDescriptor()

    @classmethod
    def help(cls) -> dict[str, object]:
        """Return mechanically sourced context for this Python class."""

        result: dict[str, object] = {
            "class": f"{cls.__module__}.{cls.__qualname__}",
            "source_path": None,
            "source_line": None,
            "hints": {},
        }
        unavailable: dict[str, str] = {}
        result["hints"] = {"unavailable": unavailable}
        try:
            filename = inspect.getsourcefile(cls)
            if filename is None:
                raise OSError("Python could not locate a source file")
            path = Path(filename).resolve(strict=True)
            if not path.is_file():
                raise OSError("Source path is not a file")
            result["source_path"] = str(path)
        except (OSError, TypeError, ValueError) as exc:
            unavailable["source_path"] = str(exc)
            unavailable["source_line"] = "Source file unavailable"
            return result
        try:
            _, line = inspect.getsourcelines(cls)
            result["source_line"] = line
        except (OSError, TypeError, ValueError) as exc:
            unavailable["source_line"] = str(exc)
        if not unavailable:
            result["hints"] = {}
        return result


# tarav.breadcrumb 925bef28324b
class _RecordsDescriptor:
    """Bind one selected Record namespace to an object or its concrete class."""

    def __get__(
        self, instance: TaravObject | None, owner: type[TaravObject]
    ) -> TaravObject.Records:
        return owner.Records(owner if instance is None else instance)


class TaravObject(TaravType):
    """Semantic Python object with a class-owned Record projection.

    Every subclass, including intermediate bases, projects its Python class to
    a distinct ``TaravClass`` Entity through ``class_entity()``.

    The object's state is its source of truth. Every construction path fills
    it; ``_record`` only keeps what ``records.from_record()`` was given, and
    ``records.to_record()`` projects the state.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("cb2ff088-9d30-44e9-8208-c0b4cbd1572d"),
            name="Tarav.Object",
        )

    class RecordInterface(BaseModel):
        """Minimal open record contract; subclasses declare their own fields."""

        model_config = ConfigDict(strict=True, extra="allow")

    class Records(NamespaceBase["TaravObject | type[TaravObject]"]):
        """Record projection and loading for one object or concrete class."""
        # tarav.breadcrumb 515f09866971
        # tarav.breadcrumb 3798a3aa52c9

        @property
        def _owner(self) -> type[TaravObject]:
            return self.obj if isinstance(self.obj, type) else type(self.obj)

        # tarav.breadcrumb 2c1992f27b7e
        # tarav.breadcrumb 442d0d53638d
        # tarav.breadcrumb dd22e0b42afb
        def parse_record(self, value: object) -> BaseModel:
            """Parse a Record into the Type's typed data, or reject it.

            One strict pass of the RecordInterface over the given dict; the
            dict itself is neither copied nor changed.
            """
            if not isinstance(value, Mapping):
                raise InvalidRecordJSON("Tarav JSON root must be an object")
            return self._owner.RecordInterface.model_validate(value, strict=True)

        # tarav.breadcrumb 195ac6bd926a
        def record_example(self) -> dict[str, object]:
            """Return a minimal storage-independent example for the bound Type."""
            return {"type": entity(self._owner).name}

        def to_record(self) -> dict[str, object]:
            if isinstance(self.obj, type):
                raise TypeError("Record projection requires an object instance")
            record = _json_object(self.obj._to_record())
            type(self.obj)._check_record_type(record)
            self.parse_record(record)
            return record

        # tarav.breadcrumb fe4ebb28de64
        def from_record(self, value: object) -> TaravObject:
            """Construct the bound Type through its hook and retain the Record."""

            owner = self._owner
            if owner is TaravObject:
                raise TypeError("TaravObject is not an opaque JSON wrapper")
            record = _json_object(value)
            owner._check_record_type(record)
            record_data = self.parse_record(record)
            result = owner._from_record(record_data)
            if type(result) is not owner:
                raise TypeError(f"{owner.__name__}._from_record() must return exact class")
            result._record = record
            return result

    records = _RecordsDescriptor()

    @property
    def workflow(self) -> TaravWorkflow:
        """Return this object's containing workflow."""
        return entity(type(self)).workflow

    @classmethod
    def preserves_parent_record_interface(cls) -> bool:
        """Whether all direct Tarav parents' interfaces are inherited."""
        return all(
            isrecordsubclass(cls, parent)
            for parent in cls.__bases__
            if issubclass(parent, TaravObject)
        )

    def __init__(self) -> None:
        if type(self) is TaravObject:
            raise TypeError("TaravObject is not an opaque JSON wrapper")
        self._record: dict[str, object] | None = None
        self.source: Path | None = None

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        """Build an instance; subclasses override when represented data is state."""

        result = cls.__new__(cls)
        TaravObject.__init__(result)
        return result

    @classmethod
    def _check_record_type(cls, record: Mapping[str, object]) -> None:
        """Reject a present Type reference that names another concrete class."""

        from .types import RecordTypeReference, locate_record_type

        location = locate_record_type(record)
        if location is None:
            return
        reference = RecordTypeReference.parse(location.value)
        if not cls.matches(reference):
            raise RecordTypeMismatch(
                f"Record {location.field} identifies {reference.describe()}, "
                f"expected exact Type {entity(cls).name}"
            )

    def _to_record(self) -> Mapping[str, object]:
        """Project the object's state as its Record.

        Returning ``_record`` serves only Types not yet migrated to state.
        """

        if self._record is not None:
            return self._record
        return {"type": entity(type(self)).name}

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        direct_record_api = {"from_record", "to_record", "parse_record", "record_example"}
        misplaced = direct_record_api.intersection(cls.__dict__)
        if misplaced:
            name = sorted(misplaced)[0]
            raise TaravTypeDeclarationError(
                f"{name}() belongs in the selected Records namespace"
            )
        if not isinstance(cls.RecordInterface, type) or not issubclass(
            cls.RecordInterface, BaseModel
        ):
            raise TaravTypeDeclarationError(
                "RecordInterface must be a Pydantic BaseModel class"
            )

    @classmethod
    def matches(cls, reference: RecordTypeReference) -> bool:
        """Whether one retained Type reference designates this class.

        The Ship decides when it is present, so a Record whose label drifted
        still specializes as the Type its Ship identifies.
        """

        class_entity = entity(cls)
        if reference.ship is not None:
            return reference.ship == class_entity.id
        return reference.label == class_entity.name

    def ships(self) -> tuple[Ship, ...]:
        """Return the Ships this Record semantically recognizes.

        The default exposes only the Record Type Ship. A subclass extends the
        projection with the Ships its own semantics recognize, returning
        concrete ``Ship`` instances; Kernel never infers a Ship by scanning
        UUID-shaped values, and the projection exposes no serialized paths.
        """

        return (entity(type(self)).id,)


class TaravEntity(TaravObject):
    """TaravObject with one stable Ship identity in its Record."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("be0d1257-9ba3-46dc-8350-5b85bc683ec6"),
            name="Tarav.Entity",
        )

    # tarav.breadcrumb c9406d280c0e
    class RecordInterface(TaravObject.RecordInterface):
        id: Ship

    def __init__(self, id: Ship) -> None:
        if not isinstance(id, Ship):
            raise TypeError("id must be a Ship")
        super().__init__()
        self._id = id

    @property
    def id(self) -> Ship:
        """Return this Entity's stable typed identity."""

        return self._id

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(id=record_data.id)

    def _to_record(self) -> Mapping[str, object]:
        return {**super()._to_record(), "id": str(self.id)}

    # tarav.breadcrumb 7bee6ef26e75
    def ships(self) -> tuple[Ship, ...]:
        return (*super().ships(), self.id)


class TaravClass(TaravEntity):
    """Runtime TaravObject representation of one Python ``TaravType`` class."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("0c4fdf7e-8fdf-4855-baf7-63ad66dbfa52"),
            name="Tarav.Class",
            workflow=TYPE_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravEntity.RecordInterface):
        id: TypeShip
        python_class: str
        name: str
        workflow: WorkflowShip

    def __init__(
        self,
        *,
        target: type[TaravType],
        id: TypeShip,
        name: str,
        workflow: WorkflowShip | None = None,
    ) -> None:
        if not isinstance(target, type) or not issubclass(target, TaravType):
            raise TypeError("target must be a TaravType class")
        if not isinstance(id, TypeShip):
            raise TypeError("id must be a TypeShip")
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")
        selected_workflow = workflow or _inherited_workflow(target)
        if not isinstance(selected_workflow, WorkflowShip):
            raise TypeError("workflow must be a WorkflowShip")
        super().__init__(id)
        self._target = target
        self._python_class = f"{target.__module__}.{target.__qualname__}"
        self._name = name
        self._workflow = selected_workflow

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        result = cls.__new__(cls)
        TaravEntity.__init__(result, record_data.id)
        result._target = None
        result._python_class = record_data.python_class
        result._name = record_data.name
        result._workflow = record_data.workflow
        return result

    class Records(TaravEntity.Records):
        def record_example(self) -> dict[str, object]:
            """Use ``TaravType`` itself as the minimal concrete class subject."""

            return entity(TaravType).records.to_record()

    def _to_record(self) -> Mapping[str, object]:
        return {
            **super()._to_record(),
            "type": "Tarav.Class",
            "python_class": self._python_class,
            "name": self._name,
            "workflow": str(self._workflow),
        }

    @property
    def id(self) -> TypeShip:
        identity = super().id
        if not isinstance(identity, TypeShip):
            raise TypeError("TaravClass identity must be a TypeShip")
        return identity

    @property
    def name(self) -> str:
        return self._name

    @property
    def workflow_ship(self) -> WorkflowShip:
        return self._workflow

    @property
    def workflow(self) -> TaravWorkflow:
        return resolve_workflow(self._workflow)

    @property
    def target(self) -> type[TaravType]:
        """Return the live Python class represented by this runtime Entity."""

        if self._target is None:
            raise RuntimeError("TaravClass was not reified from a live Python class")
        return self._target

    def bases(self) -> tuple[TaravClass, ...]:
        """Project direct Tarav bases in Python declaration order.

        Non-Tarav mixins have no class entity. Detached Records cannot supply
        live inheritance and deliberately fail through the target boundary.
        """
        return tuple(
            entity(base)
            for base in self.target.__bases__
            if issubclass(base, TaravType)
        )


def entity(target: type[TaravType]) -> TaravClass:
    """Project one Tarav Python class into the Diagram ontology."""

    if not isinstance(target, type) or not issubclass(target, TaravType):
        raise TypeError("target must be a TaravType class")
    result = target.class_entity()
    if not isinstance(result, TaravClass):
        raise TaravTypeDeclarationError(
            f"{target.__name__}.class_entity() must return a TaravClass"
        )
    if result.target is not target:
        raise TaravTypeDeclarationError(
            f"{target.__name__}.class_entity() must represent that exact class"
        )
    return result


def _inherited_workflow(target: type[TaravType]) -> WorkflowShip:
    for parent in target.__mro__[1:]:
        if issubclass(parent, TaravType):
            return entity(parent).workflow_ship
    raise TaravTypeDeclarationError(
        f"{target.__name__}.class_entity() must declare a WorkflowShip"
    )


class TaravSystem(TaravEntity):
    """The root Entity representing Tarav as one semantic system."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("65bb3af5-2f5c-4ada-8e2f-1ab45f6ec4da"),
            name="Tarav.System",
        )

    class RecordInterface(TaravEntity.RecordInterface):
        name: str

    def __init__(self) -> None:
        super().__init__(Ship("e5ff87ed-c382-49c8-855e-e04191dcf4c8"))

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        retained = _record_model_json(record_data)
        if retained != cls._canonical_record():
            raise InvalidRecordJSON("TaravSystem Record does not match Tarav identity")
        return cls()

    class Records(TaravEntity.Records):
        def record_example(self) -> dict[str, object]:
            return self._owner._canonical_record()

    def _to_record(self) -> Mapping[str, object]:
        return type(self)._canonical_record()

    @classmethod
    def _canonical_record(cls) -> dict[str, object]:
        return {
            "type": entity(cls).name,
            "id": "e5ff87ed-c382-49c8-855e-e04191dcf4c8",
            "name": "tarav",
        }


def _tarav_object_class(value: object, *, argument: str) -> type[TaravObject]:
    if not isinstance(value, type) or not issubclass(value, TaravObject):
        raise TypeError(f"{argument} must be a TaravObject class")
    return value


def issubrecord(subtype: object, supertype: object) -> bool:
    """Whether two Tarav classes have the declared RecordInterface relationship."""

    sub_class = _tarav_object_class(subtype, argument="subtype")
    super_class = _tarav_object_class(supertype, argument="supertype")
    return issubclass(
        sub_class.RecordInterface,
        super_class.RecordInterface,
    )


def isrecordsubclass(subtype: object, supertype: object) -> bool:
    """Whether behavioral and RecordInterface inheritance both hold."""

    sub_class = _tarav_object_class(subtype, argument="subtype")
    super_class = _tarav_object_class(supertype, argument="supertype")
    return issubclass(sub_class, super_class) and issubrecord(sub_class, super_class)


class TaravAssertion(TaravType):
    """Semantic role for an auditable Tarav Assertion."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("26687ca9-e0e4-4172-a322-498d1eaa5d09"),
            name="Tarav.Assertion",
        )


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise InvalidRecordJSON("Tarav JSON root must be an object")

    def copy_json(item):
        if item is None or type(item) in (str, bool, int):
            return item
        if type(item) is float and math.isfinite(item):
            return item
        if isinstance(item, Mapping):
            if any(not isinstance(key, str) for key in item):
                raise InvalidRecordJSON("JSON object keys must be strings")
            return {key: copy_json(child) for key, child in item.items()}
        if type(item) is list:
            return [copy_json(child) for child in item]
        raise InvalidRecordJSON(f"Not a JSON value: {type(item).__name__}")

    try:
        return copy_json(value)
    except RecursionError as exc:
        raise InvalidRecordJSON("JSON representation must not contain cycles") from exc


def _record_model_json(model: BaseModel) -> dict[str, object]:
    return _json_object(
        model.model_dump(mode="json", exclude_unset=True, by_alias=True)
    )


def _json_load_record(file: JsonFile) -> dict[str, object]:
    value = json.load(file)
    if not isinstance(value, Mapping):
        raise InvalidRecordJSON("Tarav JSON root must be an object")
    return _json_object(value)


DIRECTORY_ENTRY_PATH = (
    "__tarav.json",
    "main.json",
    "type.json",
)


class FileRecord(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("fca80371-e492-497b-bf43-044ab2c10220"),
            name="Tarav.FileRecord",
        )


class DirectoryRecord(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("1e07c649-a55f-4805-915e-464a8e9b2de1"),
            name="Tarav.DirectoryRecord",
        )

    @property
    def directory(self) -> Path:
        if self.source is None:
            raise ValueError("DirectoryRecord has no retained source")
        return self.source.parent


def entry_file(
    path: str | Path, *, candidates: tuple[str, ...] | None = None
) -> Path:
    """Select one entry without opening payload files or searching recursively."""
    source = Path(path).expanduser().absolute()
    if candidates is not None:
        if not isinstance(candidates, tuple):
            raise TypeError("Record entry paths must be a tuple")
        for name in candidates:
            if (
                not isinstance(name, str)
                or not name
                or Path(name).is_absolute()
                or any(part == ".." for part in Path(name).parts)
                or Path(name) == Path(".")
            ):
                raise ValueError(f"Invalid relative Record entry path: {name!r}")
    if source.is_dir():
        for name in DIRECTORY_ENTRY_PATH if candidates is None else candidates:
            candidate = source / name
            if candidate.exists() or candidate.is_symlink():
                return candidate
        paths = DIRECTORY_ENTRY_PATH if candidates is None else candidates
        raise FileNotFoundError(f"No Record entry in {source}: {paths}")
    return source


RecordT = TypeVar("RecordT", bound=TaravObject)


def _load_record(
    path: str | Path,
    *,
    registry: TypeRegistry[RecordT],
    expected_type: type[RecordT] | None = None,
    entry_paths: tuple[str, ...] | None = None,
) -> RecordT:
    source = entry_file(path, candidates=entry_paths)
    with source.open(encoding="utf-8") as stream:
        payload = _json_load_record(stream)
    authority = registry.resolve(payload)
    if expected_type is not None:
        if not isinstance(expected_type, type) or not issubclass(
            expected_type, TaravObject
        ):
            raise TypeError("expected_type must be a TaravObject class")
        if authority is not expected_type:
            raise RecordTypeMismatch(
                f"Record resolves to {authority.__name__}, expected exact Type "
                f"{expected_type.__name__}"
            )
    if (
        entry_paths is None
        and Path(path).expanduser().is_dir()
        and not issubclass(authority, DirectoryRecord)
    ):
        raise RecordTypeMismatch(f"{source} does not declare a DirectoryRecord")
    result = registry._construct(payload, authority)
    result.source = source
    return result


TARAV = TaravSystem()
