"""Typed generation source and deterministic whole-document compilation."""
from __future__ import annotations

import difflib
import json
import hashlib
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Self
from uuid import uuid4


from tarav.l0.kernel import TaravClass, TypeRegistry, current_records, entity
from tarav.l0.kernel import FileRecord, Ship, TaravEntity, TaravObject, TypeShip
from tarav.l0.kernel.records import _json_object
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l1.skw.identity import SKILLWARE_WORKFLOW_SHIP, SKW_CODE_WORKFLOW_SHIP
from .annotations import (
    BLOCK_OBJECT_TYPES,
    BlockAnnotation,
    GenerationAnnotation,
    ObjectIndexReference,
    typed_record,
)
from .generation import _hash
from .pois import (
    ContextUnobserved, ContextUnresolvable, Finding, InvalidAnnotation, MissingContent,
    OutputChanged, ProductDrift, ProductUnavailable, SourceUncompiled, StaleContext,
    StaleGeneration,
)
from .presentation import (
    add_output_mode,
    emit,
    emit_error,
    render_document_context,
    render_document_result,
)
from tarav.l1.references import Reference
from tarav.l0.kernel import LoadedRecord


class DocumentRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('5ba54fe5-40d0-451f-9d32-74d868ec2011'),
            name='Tarav.Skillware.Document',
            workflow=SKW_CODE_WORKFLOW_SHIP,
        )


class GenerationRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('bf3b76ac-9766-45f5-a086-870b54cf8b66'),
            name='Tarav.Skillware.Generation',
            workflow=SKW_CODE_WORKFLOW_SHIP,
        )


class LockRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('f133b686-7de8-4a0a-9d4a-e61962a980bf'),
            name='Tarav.Skillware.Lock',
            workflow=SKW_CODE_WORKFLOW_SHIP,
        )


class SkillwareWorkflow(TaravWorkflow):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('0ec23e63-f4f5-44e7-b9c0-890e9c63474a'),
            name='Tarav.Workflow.Skillware',
            workflow=SKILLWARE_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return SKILLWARE_WORKFLOW_SHIP
    constitution = "Contain the workflows used to develop and deploy Skillware surfaces."


#: A Project's own Skillware depot; its skills' depots are under `skills/` in it.
DEFAULT_DEPOT = ".tarav/skillware"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")


def lines(value):
    if not isinstance(value, list) or any(not isinstance(v, str) or "\n" in v or "\r" in v for v in value):
        raise ValueError("Expected an array of lines")
    return value


# tarav.breadcrumb 80deda126047
# tarav.breadcrumb 6ddf1dc4e25c
class SkwBlock(TaravEntity, Mapping[str, object]):
    """One actionable block retained inline in a Skillware document."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('6dad5fc0-fcee-4285-b7ac-9dd89802410c'),
            name='Tarav.Skillware.Block',
            workflow=SKW_CODE_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravEntity.RecordInterface):
        label: str
        content: list[str] | None
        objects_index: dict[str, dict] | None = None
        annotations: list[dict] | None = None

    class Records(TaravEntity.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {
                "type": entity(cls).name,
                "id": "6df624aa-d8bb-46fb-a095-d91e2150b9a4",
                "label": "example",
                "content": ["Example."],
            }


    def __init__(self, record: Mapping[str, object]) -> None:
        retired = {
            "output", "prompt", "arguments", "context", "reading",
            "contains", "reading_deps", "links",
        } & record.keys()
        if retired:
            raise ValueError(f"Migrate retired block fields: {sorted(retired)}")
        identity = record.get("id")
        super().__init__(identity if isinstance(identity, Ship) else Ship(identity))
        self._fields = _json_object(record)
        self._registry: TypeRegistry[TaravObject] | None = None
        self._objects_index: dict[str, TaravObject] = {}
        self._annotations: tuple[BlockAnnotation, ...] = ()
        type(self).records.parse_record(self._fields)
        if not isinstance(self._fields.get("label"), str) or not self._fields["label"]:
            raise ValueError("Blocks require non-empty labels")
        if self._fields.get("content") is not None:
            lines(self._fields["content"])

    @classmethod
    def _from_record(cls, loaded: LoadedRecord) -> Self:
        return cls(
            loaded.data.model_dump(mode="json", exclude_unset=True, by_alias=True)
        )

    def _to_record(self) -> dict[str, object]:
        return _json_object(self._fields)

    def __getitem__(self, key: str) -> object:
        return self._fields[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._fields)

    def __len__(self) -> int:
        return len(self._fields)

    @property
    def label(self) -> str:
        return self._fields["label"]  # type: ignore[return-value]

    def bind_registry(self, registry: TypeRegistry[TaravObject]) -> None:
        """Bind and validate every nested typed object through one authority."""

        self._registry = registry
        index = self._fields.get("objects_index", {})
        if not isinstance(index, Mapping):
            raise ValueError("objects_index must be an object")
        loaded = {}
        for name, record in index.items():
            if not isinstance(name, str) or not name:
                raise ValueError("objects_index keys must be non-empty strings")
            loaded[name] = self.load_object(record)
        self._objects_index = loaded

        records = self._fields.get("annotations", [])
        if not isinstance(records, list):
            raise ValueError("annotations must be an array")
        annotations = tuple(self.load_object(record) for record in records)
        if any(not isinstance(value, BlockAnnotation) for value in annotations):
            raise ValueError("annotations require BlockAnnotation objects")
        self._annotations = annotations  # type: ignore[assignment]
        for annotation in self._annotations:
            if isinstance(annotation, GenerationAnnotation):
                annotation.context_objects(self)

    def load_object(self, record: object) -> TaravObject:
        return self._nested_registry().from_record(typed_record(record))

    def _nested_registry(self) -> TypeRegistry[TaravObject]:
        if self._registry is not None:
            return self._registry
        registry = _skw_registry()
        self.bind_registry(registry)
        return registry

    def indexed_object(self, name: str) -> TaravObject:
        self._nested_registry()
        try:
            return self._objects_index[name]
        except KeyError as exc:
            raise KeyError(f"Unknown block object index: {name}") from exc

    def annotations(self, type_: type[TaravObject] | None = None):
        self._nested_registry()
        if type_ is None:
            return self._annotations
        return tuple(value for value in self._annotations if isinstance(value, type_))

    def annotation(self, type_: type[TaravObject]):
        matches = self.annotations(type_)
        if len(matches) > 1:
            raise ValueError(f"Block has multiple {type_.__name__} annotations")
        return matches[0] if matches else None

    def content_lines(self) -> list[str]:
        content = self._fields.get("content")
        if content is None:
            raise ValueError(f"Missing content: {self.label}")
        return lines(content)

    def produce(self, document: Document) -> list[str]:
        raise ValueError(f"{entity(type(self)).name} has no code producer")

    def output_findings(self, document: Document, lock_entry: dict) -> list[Finding]:
        generation = self.annotation(GenerationAnnotation)
        if generation is None:
            return []
        findings = []
        baseline = lock_entry.get("blocks", {}).get(self.label)
        if baseline is not None:
            if baseline["output_hash"] != _hash(self.get("content")):
                findings.append(Finding(OutputChanged, block=self.label))
            try:
                annotation = read(document.annotation_path(baseline["generation"]))
                if (annotation.get("source") != document.key or annotation.get("block") != self.label
                        or annotation.get("status") != "Recorded"
                        or annotation.get("input_hash") != baseline["input_hash"]
                        or annotation.get("output_hash") != baseline["output_hash"]):
                    raise ValueError("Annotation disagrees with lock")
            except (OSError, ValueError) as exc:
                findings.append(Finding(InvalidAnnotation, block=self.label, detail=str(exc)))
        return findings

    def inline_only(self) -> bool:
        return False


SKW_CODE_RECORD_TYPES = (
    DocumentRecord, GenerationRecord, LockRecord, SkwBlock, *BLOCK_OBJECT_TYPES,
)


def _skw_registry() -> TypeRegistry[TaravObject]:
    from tarav.l1.references.workflow import REFERENCE_RECORD_TYPES
    from .code import LINK_PROSE_TYPES, READING_DECLARATION_TYPES, READING_ENTRY_TYPES

    return TypeRegistry(TaravObject, (
        *SKW_CODE_RECORD_TYPES,
        *REFERENCE_RECORD_TYPES,
        *READING_DECLARATION_TYPES,
        *READING_ENTRY_TYPES,
        *LINK_PROSE_TYPES,
    ))


def _block_registry(registry: TypeRegistry[TaravObject] | None) -> TypeRegistry:
    if registry is not None:
        return registry
    try:
        return current_records()
    except RuntimeError as exc:
        if str(exc) != "Current Record registry has not been configured":
            raise
        return _skw_registry()


def _difference(actual: str, expected: str, *, limit: int = 40) -> tuple[int, int, list[str]]:
    """How far two texts are apart: the places that differ, the lines in them, and
    those lines for a reader, `-` for the file and `+` for what its source produces.
    """
    places = lines = 0
    shown: list[str] = []
    have, want = actual.splitlines(), expected.splitlines()
    for tag, a1, a2, b1, b2 in difflib.SequenceMatcher(None, have, want,
                                                      autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        places += 1
        lines += max(a2 - a1, b2 - b1)
        shown.append(f"@@ line {a1 + 1}")
        shown.extend(f"-{line}" for line in have[a1:a2])
        shown.extend(f"+{line}" for line in want[b1:b2])
    if len(shown) > limit:
        shown = [*shown[:limit], f"… {len(shown) - limit} more lines"]
    return places, lines, shown


class Document:
    """Load a fresh source for each operation. Storage is explicitly single-writer."""

    def __init__(self, source, *, root, depot, roles=None, registry=None):
        """`depot` holds the source; `root` is where its product and context resolve."""
        if roles is not None:
            raise TypeError("Context roles were replaced by typed block annotations")
        self.source = Path(source).resolve()
        self.root = Path(root).resolve()
        # tarav.breadcrumb b730537a34b4
        selected_depot = Path(depot)
        if not selected_depot.is_absolute():
            selected_depot = self.root / selected_depot
        self.depot = selected_depot.resolve()
        if not self.source.is_relative_to(self.depot):
            raise ValueError("Source must be inside its Skillware depot")
        # tarav.breadcrumb f3d91ef05572
        # a source is named from its depot; products and context from the root
        self.key = self.source.relative_to(self.depot).as_posix()
        self.data = read(self.source)
        if self.data.get("type") != entity(DocumentRecord).name or self.data.get("schema_version") != 1:
            raise ValueError("Expected Skillware document schema 1")
        self.target = self.path(self.data["output"])
        if self.target == self.source or self.target.is_relative_to(self.depot):
            raise ValueError("Output must be a product outside the Skillware depot")
        # tarav.breadcrumb e1dbc0ae2138
        self.registry = _block_registry(registry)
        self.blocks: dict[str, SkwBlock] = {}
        self.blocks_by_ship: dict[Ship, SkwBlock] = {}
        for index, b in enumerate(self.data["blocks"]):
            block = self.registry.from_record(b)
            if not isinstance(block, SkwBlock):
                raise ValueError(f"Document block is not a SkwBlock: {type(block).__name__}")
            block.bind_registry(self.registry)
            self.data["blocks"][index] = block.records.to_record()
            if block.label in self.blocks or block.id in self.blocks_by_ship:
                raise ValueError("Blocks require unique labels and Ships in one document")
            self.blocks[block.label] = block
            self.blocks_by_ship[block.id] = block
        self.lock_path = self.depot / "lock.json"

    def block(self, selector: str | Ship) -> SkwBlock:
        """Resolve a local label or an exact Ship; ambiguous scopes stay explicit."""
        if isinstance(selector, Ship):
            return self.blocks_by_ship[selector]
        try:
            ship = Ship(selector)
        except ValueError:
            ship = None
        if ship in self.blocks_by_ship:
            return self.blocks_by_ship[ship]
        if selector in self.blocks:
            return self.blocks[selector]
        raise KeyError(selector)

    def path(self, value):
        if not isinstance(value, str) or Path(value).is_absolute():
            raise ValueError("Expected project-relative path")
        path = (self.root / value).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Path escapes project")
        return path

    def definition(self, block: SkwBlock):
        annotation = block.annotation(GenerationAnnotation)
        if annotation is None:
            raise ValueError(f"Block does not define agent generation: {block.label}")
        return annotation

    def generation_fingerprint(self, identity):
        block = self.block(identity)
        annotation = self.definition(block)
        return _hash({"instructions": list(annotation.instructions)})

    def _context_records(self, identity):
        block = self.block(identity)
        annotation = self.definition(block)
        records = annotation.typed.context
        return block, tuple(records)

    def _resolved_context(self, identity, selected=None):
        """Resolve ordered maintainer context without recursive expansion or repair."""
        block, entries = self._context_records(identity)
        resolved = []
        for index, record in enumerate(entries):
            if selected is not None and index != selected:
                continue
            value = block.load_object(record)
            if isinstance(value, ObjectIndexReference):
                result = value.resolve(block=block)
                if not result.ok:
                    raise ValueError(result.message)
                value = result.target
            if not isinstance(value, TaravObject):
                raise TypeError("Generation context must resolve to a TaravObject")
            if isinstance(value, Reference):
                value.source = self.source
                result = value.resolve()
                if not result.ok:
                    raise ValueError(result.message)
                content = result.target
                if isinstance(content, bytes):
                    fingerprint = hashlib.sha256(content).hexdigest()
                    content = content.decode("utf-8")
                else:
                    fingerprint = _hash(content)
            else:
                content = value.records.to_record()
                fingerprint = _hash(content)
            resolved.append({"declaration": record, "content": content,
                             "fingerprint": fingerprint})
        return resolved

    def context(self, identity):
        """List navigation coordinates only. Target content/checks are not evaluated."""
        block, entries = self._context_records(identity)
        listing = []
        for index, record in enumerate(entries):
            item = {"index": index, "source": str(self.source), "block": identity}
            try:
                value = block.load_object(record)
                item["type"] = entity(type(value)).name
                item["record"] = record
                if isinstance(value, ObjectIndexReference):
                    item["object_index"] = value.index
                    result = value.resolve(block=block)
                    if not result.ok:
                        raise ValueError(result.message)
                    value = result.target
                    item["target_type"] = entity(type(value)).name
                if isinstance(value, Reference):
                    value.source = self.source
                    address = getattr(value, "address", None)
                    if address is None:
                        item["status"] = "uninspected"
                    else:
                        item.update(address())
                        if "path" not in item:
                            item["status"] = "uninspected"
                            listing.append(item)
                            continue
                        stat = Path(item["path"]).stat()
                        if not Path(item["path"]).is_file():
                            raise ValueError("Reference target is not a file")
                        item.update(size_bytes=stat.st_size, status="available-unchecked")
                else:
                    item.update(status="inline", record=value.records.to_record())
            except (ValueError, TypeError, KeyError, OSError) as exc:
                item.update(status="unresolvable", finding=str(exc))
            listing.append(item)
        return listing

    def read_context(self, identity, index, *, mode="cat", line_limit=20, char_limit=4000):
        """Read exactly one entry, without expanding any references inside it."""
        _, entries = self._context_records(identity)
        if type(index) is not int or not 0 <= index < len(entries):
            raise ValueError("Context index out of range")
        if mode not in {"cat", "head", "tail"}:
            raise ValueError("Unknown read mode")
        if line_limit < 1 or char_limit < 1:
            raise ValueError("Preview bounds must be positive")
        content = self._resolved_context(identity, selected=index)[0]["content"]
        text = content if isinstance(content, str) else json.dumps(content, indent=2, ensure_ascii=False)
        selected = text
        if mode != "cat":
            rows = text.splitlines(keepends=True)
            selected = "".join(rows[:line_limit] if mode == "head" else rows[-line_limit:])
            selected = selected[:char_limit] if mode == "head" else selected[-char_limit:]
        return {"index": index, "mode": mode, "text": selected,
                "truncated": selected != text}

    def _context_hash(self, context):
        return _hash(context)

    def observe_context(self, identity):
        """Explicitly baseline context without claiming generation or agent receipt."""
        context = self._resolved_context(identity)
        lock = self.lock()
        entry = lock["documents"].setdefault(self.key, {"blocks": {}})
        entry.setdefault("contexts", {})[identity] = self._context_hash(context)
        write(self.lock_path, lock)
        return {"block": identity, "context_hash": self._context_hash(context)}

    def lock(self):
        if not self.lock_path.exists():
            return {"type": entity(LockRecord).name, "schema_version": 1, "documents": {}}
        data = read(self.lock_path)
        if data.get("type") != entity(LockRecord).name or data.get("schema_version") != 1:
            raise ValueError("Unsupported lock schema")
        return data

    def annotation_path(self, identity):
        if len(identity) != 32 or any(c not in "0123456789abcdef" for c in identity):
            raise ValueError("Invalid generation ID")
        return self.depot / "generations" / (identity + ".json")

    def prepare(self, identity, *, chat=None):
        block = self.block(identity)
        generation = self.definition(block)
        context = self._resolved_context(identity)
        fingerprint = self.generation_fingerprint(identity)
        invocation = uuid4().hex
        record = {"type": entity(GenerationRecord).name, "schema_version": 1,
                  "id": invocation, "source": self.key, "block": identity,
                  "input_hash": fingerprint, "status": "Prepared",
                  "instructions": list(generation.instructions),
                  "previous_content": block.get("content"), "chat": chat}
        record.update(context=context, context_hash=self._context_hash(context))
        write(self.annotation_path(invocation), record)
        return {**record, "context": self.context(identity)}

    def record(self, invocation):
        annotation = read(self.annotation_path(invocation))
        if annotation["source"] != self.key or annotation["status"] != "Prepared":
            raise ValueError("Expected prepared generation for this source")
        block = annotation["block"]
        self.definition(self.block(block))
        context_hash = self._context_hash(self._resolved_context(block))
        if annotation.get("context_hash") != context_hash:
            raise ValueError("Context changed since preparation")
        if self.generation_fingerprint(block) != annotation["input_hash"]:
            raise ValueError("Inputs changed since preparation")
        content = self.block(block).get("content")
        if content is None:
            raise ValueError("Fill source content before recording")
        lock = self.lock()
        entry = lock["documents"].setdefault(self.key, {"blocks": {}})
        entry.setdefault("contexts", {})[block] = context_hash
        entry["blocks"][block] = {"input_hash": annotation["input_hash"],
                                   "output_hash": _hash(content), "generation": invocation}
        annotation.update(status="Recorded", output_hash=_hash(content))
        write(self.annotation_path(invocation), annotation)
        write(self.lock_path, lock)
        return annotation

    def text(self):
        result = []
        for block in self.blocks.values():
            if not block.inline_only():
                result.extend(block.content_lines())
        return "\n".join(result) + ("\n" if result else "")

    # tarav.breadcrumb 432b274a6a49
    def produce(self, identity):
        block = self.block(identity)
        content = lines(block.produce(self))
        original = block.records.to_record()
        updated = {**original, "content": content}
        type(block).records.parse_record(updated)
        index = next(i for i, value in enumerate(self.data["blocks"])
                     if value["id"] == str(block.id))
        self.data["blocks"][index] = updated
        write(self.source, self.data)
        return {"block": identity, "content": content}

    # tarav.breadcrumb 5db8fa8e7000
    def block_findings(self, identity, *, freshness=True):
        """What the analysis finds about one block of this document."""
        findings = []
        def report(poi, detail=""):
            findings.append(Finding(poi, block=identity, detail=detail))
        entry = self.lock()["documents"].get(self.key, {})
        block = self.blocks[identity]
        generation = block.annotation(GenerationAnnotation)
        if freshness and generation is not None:
            baseline = entry.get("blocks", {}).get(identity)
            if (isinstance(baseline, dict) and "input_hash" in baseline
                    and baseline["input_hash"] != self.generation_fingerprint(identity)):
                report(StaleGeneration)
        if (freshness and generation is not None
                and (generation.typed.context
                     or identity in entry.get("contexts", {}))):
            try:
                context_hash = self._context_hash(self._resolved_context(identity))
            except (KeyError, ValueError, TypeError, OSError) as exc:
                report(ContextUnresolvable, str(exc))
            else:
                observed = entry.get("contexts", {}).get(identity)
                if observed is None:
                    report(ContextUnobserved)
                elif observed != context_hash:
                    report(StaleContext)
        if block.get("content") is None:
            report(MissingContent)
        findings.extend(block.output_findings(self, entry))
        return findings

    def source_findings(self):
        """What the analysis finds about the source as a whole, apart from its blocks and product."""
        entry = self.lock()["documents"].get(self.key, {})
        if entry.get("source_hash") != _hash(self.data):
            return [Finding(SourceUncompiled, block=None, detail="")]
        return []

    def product_text(self):
        """The compiled file as it is; raises OSError or UnicodeError when it cannot be read."""
        return self.target.read_text(encoding="utf-8")

    def expected_text(self):
        """What the source produces, or None when it cannot be rendered."""
        try:
            return self.text()
        except ValueError:
            return None

    def drift(self, actual, expected):
        """The ProductDrift finding when the compiled file differs from what the source produces."""
        if actual == expected:
            return None
        # tarav.breadcrumb a999689284b9
        places, lines, shown = _difference(actual, expected)
        return Finding(ProductDrift, block=None, detail=f"{places} places, {lines} lines",
                       product=str(self.target), source=str(self.source), actual=_hash(actual),
                       expected=_hash(expected), difference=shown)

    def product_findings(self):
        """What the analysis finds about the compiled file."""
        expected = self.expected_text()
        try:
            actual = self.product_text()
        except (OSError, UnicodeError) as exc:
            return [Finding(ProductUnavailable, block=None, detail=str(exc))]
        found = None if expected is None else self.drift(actual, expected)
        return [] if found is None else [found]

    def lint(self, *, freshness=True):
        findings = [finding for identity in self.blocks
                    for finding in self.block_findings(identity, freshness=freshness)]
        return [*findings, *self.source_findings(), *self.product_findings()]

    def compile(self):
        findings = self.lint()
        try:
            text = self.text()
        except ValueError:
            return {"written": False, "findings": findings}
        lock = self.lock()
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text(text, encoding="utf-8")
        entry = lock["documents"].setdefault(self.key, {"blocks": {}})
        entry.update(source_hash=_hash(self.data), product_hash=_hash(text))
        write(self.lock_path, lock)
        return {"written": True, "findings": self.lint()}


def project_root(project=None, *, depot=DEFAULT_DEPOT):
    """Select an explicit project or discover the nearest ancestor holding the depot."""
    start = Path(project).expanduser().resolve() if project is not None else Path.cwd().resolve()
    candidates = (start,) if project is not None else (start, *start.parents)
    for candidate in candidates:
        depot_path = (candidate / depot).resolve()
        if not depot_path.is_relative_to(candidate):
            raise ValueError("Skillware depot must be inside project root")
        if depot_path.is_dir():
            return candidate
    raise ValueError(f"No {depot} depot found at {start}" if project is not None
                     else f"No {depot} depot found above {start}; supply --project")


def project_document(source, *, project=None, registry=None, depot=DEFAULT_DEPOT):
    root = project_root(project, depot=depot)
    relative = Path(source)
    if relative.is_absolute():
        raise ValueError("--source must be relative to the depot's src directory")
    base = (root / depot / "src").resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base):
        raise ValueError("--source escapes the depot's src directory")
    return Document(path, root=root, depot=root / depot, registry=registry)


def register_commands(subparsers, *, document_factory=project_document):
    parser = subparsers.add_parser("document", help="Operate typed .skw.json document sources.")
    commands = parser.add_subparsers(dest="document_command", required=True)
    for name in ("lint", "compile", "prepare", "record", "produce", "context", "observe-context"):
        command = commands.add_parser(name)
        command.add_argument("--source", required=True, help="Source path relative to the depot's src.")
        command.add_argument("--project", help="The Project; default: discover upward from cwd.")
        command.add_argument("--depot", help=f"Project-relative Skillware depot; default: {DEFAULT_DEPOT}; "
                             "a skill's is .tarav/skillware/skills/<name>.")
        if name in ("prepare", "produce", "context", "observe-context"):
            command.add_argument("--block", required=True)
        if name == "prepare":
            command.add_argument("--chat")
        if name == "context":
            modes = command.add_mutually_exclusive_group()
            modes.add_argument("--ls", action="store_true", help="List entries (default).")
            for mode in ("head", "tail", "cat"):
                modes.add_argument("--" + mode, type=int, metavar="INDEX")
            command.add_argument("--lines", type=int, default=20)
            command.add_argument("--chars", type=int, default=4000)
        if name == "record":
            command.add_argument("--generation", required=True)
        add_output_mode(command)
        command.set_defaults(handler=_command, document_factory=document_factory)


def _printable(result):
    """A command result with its findings as plain data."""
    if isinstance(result, list):
        return [item.to_json() if isinstance(item, Finding) else item for item in result]
    if isinstance(result, dict) and "findings" in result:
        return {**result, "findings": _printable(result["findings"])}
    return result


def _command(args):
    try:
        factory = getattr(args, 'document_factory', project_document)
        options = {"depot": args.depot} if args.depot is not None else {}
        document = factory(args.source, project=args.project, **options)
        if args.document_command == "prepare":
            result = document.prepare(args.block, chat=args.chat)
        elif args.document_command == "record":
            result = document.record(args.generation)
        elif args.document_command == "produce":
            result = document.produce(args.block)
        elif args.document_command == "context":
            mode = next((m for m in ("head", "tail", "cat") if getattr(args, m) is not None), None)
            if mode:
                result = document.read_context(args.block, getattr(args, mode), mode=mode,
                                               line_limit=args.lines, char_limit=args.chars)
                emit(args, result, lambda value: value["text"])
                if args.output_mode == "rendered" and result["truncated"]:
                    import sys
                    print("[preview truncated]", file=sys.stderr)
                return 0
            result = document.context(args.block)
            emit(args, result, render_document_context)
            return 0
        elif args.document_command == "observe-context":
            result = getattr(document, args.document_command.replace("-", "_"))(args.block)
        else:
            result = getattr(document, args.document_command)()
        emit(
            args,
            _printable(result),
            lambda value: render_document_result(args.document_command, value),
        )
        if args.document_command == "lint":
            return int(bool(result))
        if args.document_command == "compile":
            return int(not result["written"] or bool(result["findings"]))
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        emit_error(args, str(exc))
        return 2
