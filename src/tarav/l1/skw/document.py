"""Typed generation source and deterministic whole-document compilation."""
from __future__ import annotations

import json
import hashlib
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Self

from pydantic import BaseModel

from tarav.l0.kernel import TaravClass, TypeRegistry, current_records, entity
from tarav.l0.kernel import FileRecord, Ship, TaravEntity, TaravObject, TypeShip
from tarav.l0.kernel.records import _json_object
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l1.skw.identity import SKILLWARE_WORKFLOW_SHIP
from tarav.l1.references.workflow import ReferenceService
from .generation import Argument, Block, Generation, _hash
from .context_roles import ContextRoles
from .presentation import (
    add_output_mode,
    emit,
    emit_error,
    render_document_context,
    render_document_result,
)
from tarav.l1.chatlas.references import ChatlasTurnReference


class DocumentRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('5ba54fe5-40d0-451f-9d32-74d868ec2011'),
            name='Tarav.Skillware.Document',
            workflow=SKILLWARE_WORKFLOW_SHIP,
        )


class GenerationRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('bf3b76ac-9766-45f5-a086-870b54cf8b66'),
            name='Tarav.Skillware.Generation',
            workflow=SKILLWARE_WORKFLOW_SHIP,
        )


class LockRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('f133b686-7de8-4a0a-9d4a-e61962a980bf'),
            name='Tarav.Skillware.Lock',
            workflow=SKILLWARE_WORKFLOW_SHIP,
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
    workflow_name = "skillware"
    constitution = "Build and check structured Skillware documents."


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


# tarav.breadcrumb 218840d2e598e238395a44e5e66211f2064dfad13f5f4936839bec2bc3942d13
class SkwBlock(TaravEntity, Mapping[str, object]):
    """One actionable block retained inline in a Skillware document."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('6dad5fc0-fcee-4285-b7ac-9dd89802410c'),
            name='Tarav.Skillware.Block',
            workflow=SKILLWARE_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravEntity.RecordInterface):
        label: str
        output: list[str] | None
        reading: list[dict] | None = None

    def __init__(self, record: Mapping[str, object]) -> None:
        identity = record.get("id")
        super().__init__(identity if isinstance(identity, Ship) else Ship(identity))
        self._record = _json_object(record)
        type(self).validate_record(self._record)
        if not isinstance(self._record.get("label"), str) or not self._record["label"]:
            raise ValueError("Blocks require non-empty labels")
        if self._record.get("output") is not None:
            lines(self._record["output"])

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(
            record_data.model_dump(mode="json", exclude_unset=True, by_alias=True)
        )

    def __getitem__(self, key: str) -> object:
        return self._record[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._record)

    def __len__(self) -> int:
        return len(self._record)

    @property
    def label(self) -> str:
        return self._record["label"]  # type: ignore[return-value]

    def output_lines(self) -> list[str]:
        output = self._record.get("output") if self._record is not None else None
        if output is None:
            raise ValueError(f"Missing output: {self.label}")
        return lines(output)

    def reading_declarations(self):
        from .reading import declaration_from_record

        return tuple(declaration_from_record(value)
                     for value in self._record.get("reading", []) or ())

    def produce(self, document: Document) -> list[str]:
        raise ValueError(f"{entity(type(self)).name} has no code producer")

    def output_findings(self, document: Document, lock_entry: dict) -> list[dict]:
        return []

    def inline_only(self) -> bool:
        return False


class LiteralBlock(SkwBlock):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('311e903d-705a-43dd-9c0b-6300c2f17a79'),
                          name='Tarav.Skillware.LiteralBlock', workflow=SKILLWARE_WORKFLOW_SHIP)

    class RecordInterface(SkwBlock.RecordInterface):
        output: list[str]

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {"type": entity(cls).name, "id": "6df624aa-d8bb-46fb-a095-d91e2150b9a4",
                "label": "example", "output": ["Example."]}


class AgentGenerationBlock(SkwBlock):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('ed3a77cd-f4b6-45b6-bbee-39d1dcf7698c'),
                          name='Tarav.Skillware.AgentGenerationBlock', workflow=SKILLWARE_WORKFLOW_SHIP)

    class RecordInterface(SkwBlock.RecordInterface):
        prompt: list[str]

    def __init__(self, record: Mapping[str, object]) -> None:
        super().__init__(record)
        self.definition()

    def definition(self) -> Block:
        arguments = self._record.get("arguments", {})
        if not isinstance(arguments, Mapping):
            raise ValueError("Block arguments must be an object")
        declared = []
        for name, spec in arguments.items():
            if not isinstance(name, str) or not isinstance(spec, Mapping):
                raise ValueError("Block arguments require named object declarations")
            argument_type = spec.get("type")
            if not isinstance(argument_type, str):
                raise ValueError("Block argument type must be a string")
            declared.append(Argument(name, argument_type))
        return Block(
            self.label,
            "\n".join(lines(self._record.get("prompt"))),
            tuple(declared),
        )

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {
            "type": entity(cls).name,
            "id": "052474e0-9065-49dd-b153-582e495a6379",
            "label": "example",
            "prompt": ["Write an example."],
            "arguments": {},
            "output": None,
        }

    def output_findings(self, document: Document, lock_entry: dict) -> list[dict]:
        findings = []
        try:
            fingerprint = document.inputs(self.label)[1]
        except (KeyError, ValueError, TypeError, OSError) as exc:
            return [{"kind": "invalid-input", "block": self.label, "detail": str(exc)}]
        baseline = lock_entry.get("blocks", {}).get(self.label)
        if baseline is not None:
            if baseline["input_hash"] != fingerprint:
                findings.append({"kind": "stale-generation", "block": self.label})
            if baseline["output_hash"] != _hash(self.get("output")):
                findings.append({"kind": "output-changed", "block": self.label})
            try:
                annotation = read(document.annotation_path(baseline["generation"]))
                if (annotation.get("source") != document.key or annotation.get("block") != self.label
                        or annotation.get("status") != "Recorded"
                        or annotation.get("input_hash") != baseline["input_hash"]
                        or annotation.get("output_hash") != baseline["output_hash"]):
                    raise ValueError("Annotation disagrees with lock")
            except (OSError, ValueError) as exc:
                findings.append({"kind": "invalid-annotation", "block": self.label, "detail": str(exc)})
        return findings


SKILLWARE_RECORD_TYPES = (
    DocumentRecord, GenerationRecord, LockRecord, LiteralBlock, AgentGenerationBlock,
)


def _block_registry(registry: TypeRegistry[TaravObject] | None) -> TypeRegistry:
    if registry is not None:
        return registry
    try:
        return current_records()
    except RuntimeError as exc:
        if str(exc) != "Current Record registry has not been configured":
            raise
        return TypeRegistry(SkwBlock, (LiteralBlock, AgentGenerationBlock))


class Document:
    """Load a fresh source for each operation. Storage is explicitly single-writer."""

    def __init__(self, source, *, root=None, roles=None, registry=None):
        self.roles = roles if roles is not None else ContextRoles()
        self.references = ReferenceService()
        self.references.records.register(ChatlasTurnReference)
        self.source = Path(source).resolve()
        if root is None:
            depot = next((p for p in self.source.parents if p.name == ".skw"), None)
            if depot is None:
                raise ValueError("Source outside .skw needs project root")
            root = depot.parent
        self.root = Path(root).resolve()
        self.key = self.source.relative_to(self.root).as_posix()
        self.data = read(self.source)
        if self.data.get("type") != entity(DocumentRecord).name or self.data.get("schema_version") != 1:
            raise ValueError("Expected Skillware document schema 1")
        self.target = self.path(self.data["output"])
        if self.target == self.source or self.target.is_relative_to(self.root / ".skw"):
            raise ValueError("Output must be a product outside .skw")
        # tarav.breadcrumb e1dbc0ae21389449d35926a5dcf9fe717168db8afacbe4ff94f80ae4009325ce
        self.registry = _block_registry(registry)
        self.blocks: dict[str, SkwBlock] = {}
        self.blocks_by_ship: dict[Ship, SkwBlock] = {}
        for index, b in enumerate(self.data["blocks"]):
            block = self.registry.from_record(b)
            if not isinstance(block, SkwBlock):
                raise ValueError(f"Document block is not a SkwBlock: {type(block).__name__}")
            if block._record is None:
                raise RuntimeError("Loaded Skillware block has no retained Record")
            self.data["blocks"][index] = block._record
            if block.label in self.blocks or block.id in self.blocks_by_ship:
                raise ValueError("Blocks require unique labels and Ships in one document")
            self.blocks[block.label] = block
            self.blocks_by_ship[block.id] = block
        self.lock_path = self.root / ".skw" / "lock.json"

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
        if not isinstance(block, AgentGenerationBlock):
            raise ValueError(f"Block does not define agent generation: {block.label}")
        return block.definition()

    def inputs(self, identity, active=()):
        if identity in active:
            raise ValueError("Cyclic block dependency")
        block = self.block(identity)
        values, dependencies = {}, {}
        for name, spec in block.get("arguments", {}).items():
            if len(set(spec) & {"value", "file", "block"}) != 1:
                raise ValueError("Argument requires exactly one value, file, or block")
            if "file" in spec:
                values[name] = self.path(spec["file"]).read_text(encoding="utf-8")
            elif "block" in spec:
                other = self.block(spec["block"])
                if isinstance(other, AgentGenerationBlock):
                    dependencies[name] = self.inputs(other.label, (*active, identity))[1]
                values[name] = "\n".join(other.output_lines())
            else:
                values[name] = spec["value"]
        recipe = {k: v for k, v in block.items() if k != "output"}
        migration_path = self.root / ".skw" / "block-identity-migration.json"
        if migration_path.is_file():
            migration = read(migration_path)
            old = migration.get("documents", {}).get(self.key, {}).get(block.label)
            if old is not None:
                if recipe["id"] != old["ship"]:
                    raise ValueError("Block identity disagrees with explicit migration")
                # Historical generation evidence fingerprints the authored
                # recipe, not its later identity and reading-path annotations.
                recipe["id"] = old["label"]
                recipe.pop("label", None)
                recipe.pop("reading", None)
        state = {"recipe": recipe,
                 "values": values, "dependencies": dependencies}
        # Reuse the independent typed template validator, not Index mechanics.
        Generation((self.definition(block),)).prepare(identity, values)
        return values, _hash(state)

    def _resolved_context(self, identity, selected=None):
        """Resolve ordered maintainer context without recursive expansion or repair."""
        entries = self.block(identity).get("context", [])
        if not isinstance(entries, list):
            raise ValueError("Context must be an ordered array")
        resolved = []
        for index, entry in enumerate(entries):
            if selected is not None and index != selected:
                continue
            if not isinstance(entry, dict):
                raise ValueError("Context entry must be an object")
            roles = self.roles.select(entry)
            if entry.get("kind") == "prompt":
                if set(entry) - {"roles"} != {"kind", "lines"}:
                    raise ValueError("Prompt context requires kind and lines")
                resolved.append({"declaration": entry, "content": "\n".join(lines(entry["lines"]))})
            elif entry.get("kind") == "reference":
                if set(entry) - {"roles"} != {"kind", "reference"}:
                    raise ValueError("Context reference requires one typed reference object")
                reference = self.references.load(entry["reference"])
                reference.source = self.source
                result = reference.resolve()
                if not result.ok:
                    raise ValueError(result.message)
                content = result.target
                if isinstance(content, bytes):
                    fingerprint = hashlib.sha256(content).hexdigest()
                    content = content.decode("utf-8")
                else:
                    fingerprint = _hash(content)
                resolved.append({"declaration": entry, "content": content,
                                 "fingerprint": fingerprint})
            else:
                raise ValueError("Unknown context entry kind")
            for role in roles:
                finding = role.check(resolved[-1]["content"])
                if finding:
                    raise ValueError(finding)
        return resolved

    def context(self, identity):
        """List navigation coordinates only. Target content/checks are not evaluated."""
        entries = self.block(identity).get("context", [])
        if not isinstance(entries, list):
            raise ValueError("Context must be an ordered array")
        listing = []
        for index, entry in enumerate(entries):
            item = {"index": index, "source": str(self.source), "block": identity}
            try:
                if not isinstance(entry, dict):
                    raise ValueError("Context entry must be an object")
                self.roles.select(entry)
                item["roles"] = entry.get("roles", [])
                item["kind"] = entry.get("kind")
                if entry.get("kind") == "prompt":
                    if set(entry) - {"roles"} != {"kind", "lines"}:
                        raise ValueError("Prompt context requires kind and lines")
                    item.update(line_count=len(lines(entry["lines"])), status="inline")
                elif entry.get("kind") == "reference":
                    if set(entry) - {"roles"} != {"kind", "reference"}:
                        raise ValueError("Context reference requires one typed reference object")
                    item["reference"] = entry["reference"]
                    reference = self.references.load(entry["reference"])
                    reference.source = self.source
                    address = getattr(reference, "address", None)
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
                    raise ValueError("Unknown context entry kind")
            except (ValueError, TypeError, KeyError, OSError) as exc:
                item.update(status="unresolvable", finding=str(exc))
            listing.append(item)
        return listing

    def read_context(self, identity, index, *, mode="cat", line_limit=20, char_limit=4000):
        """Read exactly one entry, without expanding any references inside it."""
        entries = self.block(identity).get("context", [])
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
        return _hash([item if any(role.tracks_changes for role in self.roles.select(item["declaration"]))
                      else {"declaration": item["declaration"]} for item in context])

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
        return self.root / ".skw" / "generations" / (identity + ".json")

    def prepare(self, identity, *, chat=None):
        block = self.block(identity)
        if not isinstance(block, AgentGenerationBlock):
            raise ValueError(f"Block does not define agent generation: {identity}")
        context = self._resolved_context(identity)
        values, fingerprint = self.inputs(identity)
        generation = Generation((self.definition(block),))
        invocation = generation.prepare(identity, values, chat=chat)
        record = {"type": entity(GenerationRecord).name, "schema_version": 1,
                  "id": invocation, "source": self.key, "block": identity,
                  "input_hash": fingerprint, "status": "Prepared",
                  "prompt": generation.invocations[invocation]["prompt"],
                  "previous_output": block.get("output"), "chat": chat}
        record.update(context=context, context_hash=self._context_hash(context))
        write(self.annotation_path(invocation), record)
        return {**record, "context": self.context(identity)}

    def record(self, invocation):
        annotation = read(self.annotation_path(invocation))
        if annotation["source"] != self.key or annotation["status"] != "Prepared":
            raise ValueError("Expected prepared generation for this source")
        block = annotation["block"]
        if not isinstance(self.block(block), AgentGenerationBlock):
            raise ValueError(f"Block does not define agent generation: {block}")
        context_hash = self._context_hash(self._resolved_context(block))
        if annotation.get("context_hash") != context_hash:
            raise ValueError("Context changed since preparation")
        if self.inputs(block)[1] != annotation["input_hash"]:
            raise ValueError("Inputs changed since preparation")
        output = self.block(block).get("output")
        if output is None:
            raise ValueError("Fill source output before recording")
        lock = self.lock()
        entry = lock["documents"].setdefault(self.key, {"blocks": {}})
        entry.setdefault("contexts", {})[block] = context_hash
        entry["blocks"][block] = {"input_hash": annotation["input_hash"],
                                   "output_hash": _hash(output), "generation": invocation}
        annotation.update(status="Recorded", output_hash=_hash(output))
        write(self.annotation_path(invocation), annotation)
        write(self.lock_path, lock)
        return annotation

    def text(self):
        result = []
        for block in self.blocks.values():
            if not block.inline_only():
                result.extend(block.output_lines())
        return "\n".join(result) + ("\n" if result else "")

    # tarav.breadcrumb 432b274a6a49d11a9a31d381a8bad064b544a44d210397fdec9450d6d9bdea97
    def produce(self, identity):
        block = self.block(identity)
        output = lines(block.produce(self))
        original = block.to_record()
        updated = {**original, "output": output}
        type(block).validate_record(updated)
        index = next(i for i, value in enumerate(self.data["blocks"])
                     if value["id"] == str(block.id))
        self.data["blocks"][index] = updated
        write(self.source, self.data)
        return {"block": identity, "output": output}

    def lint(self):
        findings = []
        def report(kind, block=None, detail=""):
            findings.append({"kind": kind, "block": block, "detail": detail})
        entry = self.lock()["documents"].get(self.key, {})
        for identity, block in self.blocks.items():
            if "context" in block or identity in entry.get("contexts", {}):
                try:
                    context_hash = self._context_hash(self._resolved_context(identity))
                except (KeyError, ValueError, TypeError, OSError) as exc:
                    report("context-unresolvable", identity, str(exc))
                else:
                    observed = entry.get("contexts", {}).get(identity)
                    if observed is None:
                        report("context-unobserved", identity)
                    elif observed != context_hash:
                        report("stale-context", identity)
            if block.get("output") is None:
                report("missing-output", identity)
            findings.extend(block.output_findings(self, entry))
        if entry.get("source_hash") != _hash(self.data):
            report("source-uncompiled")
        try:
            expected = self.text()
        except ValueError:
            expected = None
        try:
            actual = self.target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            report("product-unavailable", detail=str(exc))
        else:
            if expected is not None and actual != expected:
                report("product-drift")
        return findings

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


def project_root(project=None):
    """Select an explicit project or discover the nearest .skw ancestor."""
    start = Path(project).expanduser().resolve() if project is not None else Path.cwd().resolve()
    candidates = (start,) if project is not None else (start, *start.parents)
    for candidate in candidates:
        if (candidate / ".skw").is_dir():
            return candidate
    raise ValueError(f"No .skw project found at {start}" if project is not None
                     else f"No .skw project found above {start}; supply --project")


def project_document(source, *, project=None, registry=None):
    root = project_root(project)
    relative = Path(source)
    if relative.is_absolute():
        raise ValueError("--source must be relative to .skw/src")
    base = (root / ".skw" / "src").resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base):
        raise ValueError("--source escapes .skw/src")
    return Document(path, root=root, registry=registry)


def register_commands(subparsers, *, document_factory=project_document):
    parser = subparsers.add_parser("document", help="Operate typed .skw.json document sources.")
    commands = parser.add_subparsers(dest="document_command", required=True)
    for name in ("lint", "compile", "prepare", "record", "produce", "context", "observe-context"):
        command = commands.add_parser(name)
        command.add_argument("--source", required=True, help="Source path relative to .skw/src.")
        command.add_argument("--project", help="Directory containing .skw; default: discover upward from cwd.")
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


def _command(args):
    try:
        factory = getattr(args, 'document_factory', project_document)
        document = factory(args.source, project=args.project)
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
            result,
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
