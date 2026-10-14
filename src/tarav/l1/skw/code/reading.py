"""Typed claims about the context supplied by a declared skill reading path."""

from urllib.parse import unquote

from markdown_it import MarkdownIt

from tarav.l0.kernel import Ship, TaravClass, TaravObject, TypeRegistry, TypeShip, entity

from ..annotations import BlockAnnotation
from ..identity import SKW_CODE_WORKFLOW_SHIP
from ..pois import Finding, MissingMarkdownLink


# tarav.breadcrumb effa713807d1ea29a6b5be34a2603c55ef4c72643a9b9f129d7c2e6a35520365
# tarav.breadcrumb c97cc9fa0b5eb251d2f2dc91036f5294d75e5c3cc8bb06e5f62b6db045c290c1
class ReadingDeclaration(BlockAnnotation):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c45b568f-7057-4a38-a75d-d6fbb61013d2"),
                          name="Tarav.SKW.Reading.Declaration",
                          workflow=SKW_CODE_WORKFLOW_SHIP)

    class RecordInterface(BlockAnnotation.RecordInterface):
        target: str

    class Records(BlockAnnotation.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
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
                          name="Tarav.SKW.Reading.Entry", workflow=SKW_CODE_WORKFLOW_SHIP)


class BlockEntry(ReadingEntry):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e9df2037-05cf-41c8-93a8-c232661c03e5"),
                          name="Tarav.SKW.Reading.BlockEntry",
                          workflow=SKW_CODE_WORKFLOW_SHIP)

    class RecordInterface(ReadingEntry.RecordInterface):
        node: str

    class Records(ReadingEntry.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {"type": entity(cls).name, "node": "example"}



class FileEntry(ReadingEntry):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("06bb35ac-0eb7-44fa-92fb-e7af869591bc"),
                          name="Tarav.SKW.Reading.FileEntry",
                          workflow=SKW_CODE_WORKFLOW_SHIP)

    class RecordInterface(ReadingEntry.RecordInterface):
        source: str

    class Records(ReadingEntry.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {"type": entity(cls).name, "source": "SKILL.md"}



# tarav.breadcrumb 7a8dc39912a8499d231b58a1b0532d3eb8ad195d19c6b5b0c9012e5f16ce897a
class Contains(BlockAnnotation):
    # tarav.breadcrumb 2d50f5b52886ca9a118de057c82531820bc2821854395253e767b0922c81bd13
    """Claim content is co-loaded; expand annotations of contained SKW blocks."""

    class RecordInterface(BlockAnnotation.RecordInterface):
        target: str

    @property
    def target(self) -> str:
        if self._record is None:
            raise RuntimeError("Content declaration has no Record")
        return str(self._record["target"])

    class Records(BlockAnnotation.Records):
        def record_example(self):
            cls = self._owner
            return {"type": entity(cls).name,
                    "target": "27ad5113-56b1-4994-a6ea-013eddd422aa"}


    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8ff9e46a-9673-4494-b169-0ff1c55d62c5"),
                          name="Tarav.SKW.Reading.Contains",
                          workflow=SKW_CODE_WORKFLOW_SHIP)


# tarav.breadcrumb cc5ae810d7c36b9115f0e8341df7977a974903db6cab59151f8665fa8609b71a
# tarav.breadcrumb 5d4e0d6cc8a3f9b5952622540e4050b146a5526ddfe70805bdd15cf6c5d43e5d
class LinkProse(TaravObject):
    """How a declared link appears in the text of its block.

    The reading graph trusts the declaration and never reads the text; a
    prose part is what checks the text, for the maintainers. This base checks
    nothing.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3251688c-1883-46f0-b418-aa1a5ec2f2ff"),
                          name="Tarav.SKW.Reading.LinkProse", workflow=SKW_CODE_WORKFLOW_SHIP)

    def findings(self, text: str, href: str) -> list[Finding]:
        """What is wrong with how `text` holds the link to `href`."""
        return []


class MarkdownProse(LinkProse):
    """The text of the block holds a Markdown link to the declared target."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1a339fcb-acc3-47b4-8b7c-d2c747531a43"),
                          name="Tarav.SKW.Reading.MarkdownProse",
                          workflow=SKW_CODE_WORKFLOW_SHIP)

    def findings(self, text: str, href: str) -> list[Finding]:
        written = {unquote(child.attrGet("href") or "")
                   for token in MarkdownIt().parse(text)
                   for child in token.children or () if child.type == "link_open"}
        return [] if unquote(href) in written else [Finding(MissingMarkdownLink, href=href)]


# tarav.breadcrumb bb711d9c3ade0dd1b7b6e6d8ed8eb1d3b44236371c63595d7f90d157ed4892d3
class ReadingLink(ReadingDeclaration):
    """A reference to an entity, with a separately declared reading entry.

    The declaration does not write the link: the block's text holds it, and
    the optional `prose` part says how, and checks it.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3a125e14-e7ad-49b4-9b8f-757753b92b8c"),
                          name="Tarav.SKW.Reading.Link",
                          workflow=SKW_CODE_WORKFLOW_SHIP)

    class RecordInterface(ReadingDeclaration.RecordInterface):
        entry: dict | None = None
        prose: dict | None = None

    @property
    def entry(self) -> dict | None:
        if self._record is None:
            raise RuntimeError("Reading link has no Record")
        value = self._record.get("entry")
        return dict(value) if isinstance(value, dict) else None

    # tarav.breadcrumb cd646a3168c40dec240403b69648b58d59a443811d5a5074bf42befa1d2991fc
    @property
    def prose(self) -> LinkProse | None:
        if self._record is None:
            raise RuntimeError("Reading link has no Record")
        value = self._record.get("prose")
        return None if value is None else _PROSE.from_record(value)


class ExpectedLink(ReadingLink):
    """An expected reading action, not proof its target has been loaded."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d0f065db-b468-4843-b602-a135a2c2d9b5"),
                          name="Tarav.SKW.Reading.ExpectedLink",
                          workflow=SKW_CODE_WORKFLOW_SHIP)

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
                          workflow=SKW_CODE_WORKFLOW_SHIP)


class IncludesBlock(Contains):
    """Containment with optional rendering-slot composition, not a link."""

    class RecordInterface(Contains.RecordInterface):
        entry: dict | None = None
        slot: str | None = None

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ca3bf83d-299a-4087-87f3-f8b9110e73e3"),
                          name="Tarav.SKW.Reading.IncludesBlock",
                          workflow=SKW_CODE_WORKFLOW_SHIP)

    def destination(self):
        entry = self._record.get("entry") if self._record else None
        if entry is None:
            raise ValueError("IncludesBlock requires a reading entry")
        return entry_from_record(entry)


class ReadingDependency(ReadingDeclaration):
    """A prerequisite checked against incoming context before this block."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8ae49c46-71b7-443d-a4fb-6855c1eea214"),
                          name="Tarav.SKW.Reading.Dependency",
                          workflow=SKW_CODE_WORKFLOW_SHIP)

    def satisfied(self, target: Ship, inline: set[Ship], referenced: set[Ship]) -> bool:
        raise NotImplementedError

    @property
    def delivery(self) -> str:
        raise NotImplementedError


class InlineDependency(ReadingDependency):
    """Require content (including containment), rather than a reference alone."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("00a46453-d716-4b3d-ab1f-84ad7f4c7cee"),
                          name="Tarav.SKW.Reading.InlineDependency",
                          workflow=SKW_CODE_WORKFLOW_SHIP)

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
                          workflow=SKW_CODE_WORKFLOW_SHIP)

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
                          workflow=SKW_CODE_WORKFLOW_SHIP)

    def satisfied(self, target: Ship, inline: set[Ship], referenced: set[Ship]) -> bool:
        return target in inline or target in referenced

    @property
    def delivery(self) -> str:
        return "either"


READING_DECLARATION_TYPES = (
    Contains, ReadingLink, ExpectedLink, ConsultationLink, IncludesBlock,
    ReadingDependency, InlineDependency, ReferenceDependency, EitherDependency,
)
READING_ENTRY_TYPES = (ReadingEntry, BlockEntry, FileEntry)
LINK_PROSE_TYPES = (LinkProse, MarkdownProse)

_DECLARATIONS = TypeRegistry(TaravObject,
                             (ReadingDeclaration, *READING_DECLARATION_TYPES))
_ENTRIES = TypeRegistry(ReadingEntry, READING_ENTRY_TYPES)
_PROSE = TypeRegistry(LinkProse, LINK_PROSE_TYPES)


def declaration_from_record(record: dict) -> TaravObject:
    return _DECLARATIONS.from_record(record)


def entry_from_record(record: dict) -> ReadingEntry:
    return _ENTRIES.from_record(record)
