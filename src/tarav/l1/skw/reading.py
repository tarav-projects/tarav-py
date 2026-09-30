"""Typed claims about the context supplied by a declared skill reading path."""

from tarav.l0.kernel import Ship, TaravClass, TaravObject, TypeRegistry, TypeShip, entity

from .identity import SKW_SKILLS_WORKFLOW_SHIP


# tarav.breadcrumb c97cc9fa0b5eb251d2f2dc91036f5294d75e5c3cc8bb06e5f62b6db045c290c1
class ReadingDeclaration(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c45b568f-7057-4a38-a75d-d6fbb61013d2"),
                          name="Tarav.SKW.Reading.Declaration",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        target: str

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {"type": entity(cls).name,
                "target": "27ad5113-56b1-4994-a6ea-013eddd422aa"}

    @property
    def target(self) -> str:
        if self._record is None:
            raise RuntimeError("Reading declaration has no Record")
        return str(self._record["target"])


class ReadingEntry(TaravObject):
    """The point at which following a link resumes reading."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ead86f2b-1dc6-4fc0-a990-e0a7f1fca690"),
                          name="Tarav.SKW.Reading.Entry", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class BlockEntry(ReadingEntry):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e9df2037-05cf-41c8-93a8-c232661c03e5"),
                          name="Tarav.SKW.Reading.BlockEntry",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    class RecordInterface(ReadingEntry.RecordInterface):
        node: str

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {"type": entity(cls).name, "node": "example"}


class FileEntry(ReadingEntry):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("06bb35ac-0eb7-44fa-92fb-e7af869591bc"),
                          name="Tarav.SKW.Reading.FileEntry",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    class RecordInterface(ReadingEntry.RecordInterface):
        source: str

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {"type": entity(cls).name, "source": "SKILL.md"}


class ProvidesEntity(ReadingDeclaration):
    """Claim that the block's content provides an entity to its reader."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e92ee1f7-57ca-4fe4-b9ce-d4ba121540f4"),
                          name="Tarav.SKW.Reading.ProvidesEntity",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)


class InlinesEntity(ReadingDeclaration):
    """Claim that the block embeds an entity's content."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("59d4745a-45e0-4451-9d3e-1f66fc68386a"),
                          name="Tarav.SKW.Reading.InlinesEntity",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)


class ReadingLink(ReadingDeclaration):
    """A reference to an entity, with a separately declared reading entry."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3a125e14-e7ad-49b4-9b8f-757753b92b8c"),
                          name="Tarav.SKW.Reading.Link",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    class RecordInterface(ReadingDeclaration.RecordInterface):
        entry: dict | None = None
        slot: str | None = None
        caption: str | None = None

    @property
    def entry(self) -> dict | None:
        if self._record is None:
            raise RuntimeError("Reading link has no Record")
        value = self._record.get("entry")
        return dict(value) if isinstance(value, dict) else None


class ExpectedLink(ReadingLink):
    """A link the declared route expects the reader to follow."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d0f065db-b468-4843-b602-a135a2c2d9b5"),
                          name="Tarav.SKW.Reading.ExpectedLink",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def destination(self):
        if self.entry is None:
            raise ValueError("ExpectedLink requires a reading entry")
        return entry_from_record(self.entry)


class ConsultationLink(ReadingLink):
    """An optional reference; it does not put target content on every path."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("82206514-59e7-4922-91d3-b260f626b75e"),
                          name="Tarav.SKW.Reading.ConsultationLink",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)


class IncludesBlock(ReadingLink):
    """Inline the destination block at the declared rendering slot."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ca3bf83d-299a-4087-87f3-f8b9110e73e3"),
                          name="Tarav.SKW.Reading.IncludesBlock",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def destination(self):
        if self.entry is None:
            raise ValueError("IncludesBlock requires a reading entry")
        return entry_from_record(self.entry)


class ReadingDependency(ReadingDeclaration):
    """A prerequisite checked against incoming context before this block."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8ae49c46-71b7-443d-a4fb-6855c1eea214"),
                          name="Tarav.SKW.Reading.Dependency",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def satisfied(self, target: Ship, inline: set[Ship], referenced: set[Ship]) -> bool:
        raise NotImplementedError

    @property
    def delivery(self) -> str:
        raise NotImplementedError


class InlineDependency(ReadingDependency):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("00a46453-d716-4b3d-ab1f-84ad7f4c7cee"),
                          name="Tarav.SKW.Reading.InlineDependency",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def satisfied(self, target: Ship, inline: set[Ship], referenced: set[Ship]) -> bool:
        return target in inline

    @property
    def delivery(self) -> str:
        return "inlined"


class ReferenceDependency(ReadingDependency):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e6e08473-bf32-41cc-9e27-1eb0d8fd961b"),
                          name="Tarav.SKW.Reading.ReferenceDependency",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def satisfied(self, target: Ship, inline: set[Ship], referenced: set[Ship]) -> bool:
        return target in referenced

    @property
    def delivery(self) -> str:
        return "referenced"


class EitherDependency(ReadingDependency):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8217652c-3fa4-4fa7-ac1a-9b3d88b4b297"),
                          name="Tarav.SKW.Reading.EitherDependency",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def satisfied(self, target: Ship, inline: set[Ship], referenced: set[Ship]) -> bool:
        return target in inline or target in referenced

    @property
    def delivery(self) -> str:
        return "either"


READING_DECLARATION_TYPES = (
    ProvidesEntity, InlinesEntity, ReadingLink, ExpectedLink, ConsultationLink, IncludesBlock,
    ReadingDependency, InlineDependency, ReferenceDependency, EitherDependency,
)
READING_ENTRY_TYPES = (ReadingEntry, BlockEntry, FileEntry)

_DECLARATIONS = TypeRegistry(ReadingDeclaration,
                             (ReadingDeclaration, *READING_DECLARATION_TYPES))
_ENTRIES = TypeRegistry(ReadingEntry, READING_ENTRY_TYPES)


def declaration_from_record(record: dict) -> ReadingDeclaration:
    return _DECLARATIONS.from_record(record)


def entry_from_record(record: dict) -> ReadingEntry:
    return _ENTRIES.from_record(record)
