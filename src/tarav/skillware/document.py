"""Typed generation source and deterministic whole-document compilation."""
import json
import hashlib
from pathlib import Path

from tarav.harness import FileRecord, TypeShip
from tarav.harness.workflows import Workflow
from tarav.references.workflow import ReferenceWorkflow
from .generation import Argument, Block, Generation, _hash


class DocumentRecord(FileRecord):
    type_name = "Tarav.Skillware.Document"
    type_ship = TypeShip("5ba54fe5-40d0-451f-9d32-74d868ec2011")


class GenerationRecord(FileRecord):
    type_name = "Tarav.Skillware.Generation"
    type_ship = TypeShip("bf3b76ac-9766-45f5-a086-870b54cf8b66")


class LockRecord(FileRecord):
    type_name = "Tarav.Skillware.Lock"
    type_ship = TypeShip("f133b686-7de8-4a0a-9d4a-e61962a980bf")


class SkillwareWorkflow(Workflow):
    name = "skillware"
    record_types = (DocumentRecord, GenerationRecord, LockRecord)


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


class Document:
    """Load a fresh source for each operation. Storage is explicitly single-writer."""

    def __init__(self, source, *, root=None):
        self.source = Path(source).resolve()
        if root is None:
            depot = next((p for p in self.source.parents if p.name == ".skw"), None)
            if depot is None:
                raise ValueError("Source outside .skw needs project root")
            root = depot.parent
        self.root = Path(root).resolve()
        self.key = self.source.relative_to(self.root).as_posix()
        self.data = read(self.source)
        if self.data.get("type") != DocumentRecord.type_name or self.data.get("schema_version") != 1:
            raise ValueError("Expected Skillware document schema 1")
        self.target = self.path(self.data["output"])
        if self.target == self.source or self.target.is_relative_to(self.root / ".skw"):
            raise ValueError("Output must be a product outside .skw")
        self.blocks = {}
        for b in self.data["blocks"]:
            if not isinstance(b.get("id"), str) or not b["id"] or b["id"] in self.blocks:
                raise ValueError("Blocks require unique IDs")
            self.blocks[b["id"]] = b
            if b["kind"] == "literal":
                lines(b["lines"])
            elif b["kind"] == "generation":
                self.definition(b)
                if b.get("output") is not None:
                    lines(b["output"])
            else:
                raise ValueError("Unknown block kind")
        self.lock_path = self.root / ".skw" / "lock.json"

    def path(self, value):
        if not isinstance(value, str) or Path(value).is_absolute():
            raise ValueError("Expected project-relative path")
        path = (self.root / value).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Path escapes project")
        return path

    def definition(self, block):
        return Block(block["id"], "\n".join(lines(block["prompt"])), tuple(
            Argument(name, spec["type"]) for name, spec in block.get("arguments", {}).items()))

    def inputs(self, identity, active=()):
        if identity in active:
            raise ValueError("Cyclic block dependency")
        block = self.blocks[identity]
        values, dependencies = {}, {}
        for name, spec in block.get("arguments", {}).items():
            if len(set(spec) & {"value", "file", "block"}) != 1:
                raise ValueError("Argument requires exactly one value, file, or block")
            if "file" in spec:
                values[name] = self.path(spec["file"]).read_text(encoding="utf-8")
            elif "block" in spec:
                other = self.blocks[spec["block"]]
                if other["kind"] == "generation":
                    dependencies[name] = self.inputs(other["id"], (*active, identity))[1]
                    output = other.get("output")
                else:
                    output = other["lines"]
                if output is None:
                    raise ValueError("Dependency output missing")
                values[name] = "\n".join(output)
            else:
                values[name] = spec["value"]
        state = {"recipe": {k: v for k, v in block.items() if k != "output"},
                 "values": values, "dependencies": dependencies}
        # Reuse the independent typed template validator, not Index mechanics.
        Generation((self.definition(block),)).prepare(identity, values)
        return values, _hash(state)

    def context(self, identity):
        """Resolve ordered maintainer context without recursive expansion or repair."""
        entries = self.blocks[identity].get("context", [])
        if not isinstance(entries, list):
            raise ValueError("Context must be an ordered array")
        resolved = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Context entry must be an object")
            if entry.get("kind") == "prompt":
                if set(entry) != {"kind", "lines"}:
                    raise ValueError("Prompt context requires kind and lines")
                resolved.append({"declaration": entry, "content": "\n".join(lines(entry["lines"]))})
            elif entry.get("kind") == "reference":
                if set(entry) != {"kind", "reference"}:
                    raise ValueError("Context reference requires one typed reference object")
                reference = ReferenceWorkflow().load(entry["reference"])
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
        return resolved

    def observe_context(self, identity):
        """Explicitly baseline context without claiming generation or agent receipt."""
        context = self.context(identity)
        lock = self.lock()
        entry = lock["documents"].setdefault(self.key, {"blocks": {}})
        entry.setdefault("contexts", {})[identity] = _hash(context)
        write(self.lock_path, lock)
        return {"block": identity, "context_hash": _hash(context)}

    def lock(self):
        if not self.lock_path.exists():
            return {"type": LockRecord.type_name, "schema_version": 1, "documents": {}}
        data = read(self.lock_path)
        if data.get("type") != LockRecord.type_name or data.get("schema_version") != 1:
            raise ValueError("Unsupported lock schema")
        return data

    def annotation_path(self, identity):
        if len(identity) != 32 or any(c not in "0123456789abcdef" for c in identity):
            raise ValueError("Invalid generation ID")
        return self.root / ".skw" / "generations" / (identity + ".json")

    def prepare(self, identity, *, chat=None):
        block = self.blocks[identity]
        context = self.context(identity)
        values, fingerprint = self.inputs(identity)
        generation = Generation((self.definition(block),))
        invocation = generation.prepare(identity, values, chat=chat)
        record = {"type": GenerationRecord.type_name, "schema_version": 1,
                  "id": invocation, "source": self.key, "block": identity,
                  "input_hash": fingerprint, "status": "Prepared",
                  "prompt": generation.invocations[invocation]["prompt"],
                  "previous_output": block.get("output"), "chat": chat}
        record.update(context=context, context_hash=_hash(context))
        write(self.annotation_path(invocation), record)
        return record

    def record(self, invocation):
        annotation = read(self.annotation_path(invocation))
        if annotation["source"] != self.key or annotation["status"] != "Prepared":
            raise ValueError("Expected prepared generation for this source")
        block = annotation["block"]
        context_hash = _hash(self.context(block))
        if annotation.get("context_hash") != context_hash:
            raise ValueError("Context changed since preparation")
        if self.inputs(block)[1] != annotation["input_hash"]:
            raise ValueError("Inputs changed since preparation")
        output = self.blocks[block].get("output")
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
        for b in self.data["blocks"]:
            value = b["lines"] if b["kind"] == "literal" else b.get("output")
            if value is None:
                raise ValueError(f"Missing output: {b['id']}")
            result.extend(value)
        return "\n".join(result) + ("\n" if result else "")

    def lint(self):
        findings = []
        def report(kind, block=None, detail=""):
            findings.append({"kind": kind, "block": block, "detail": detail})
        entry = self.lock()["documents"].get(self.key, {})
        for identity, block in self.blocks.items():
            if "context" in block or identity in entry.get("contexts", {}):
                try:
                    context_hash = _hash(self.context(identity))
                except (KeyError, ValueError, TypeError, OSError) as exc:
                    report("context-unresolvable", identity, str(exc))
                else:
                    observed = entry.get("contexts", {}).get(identity)
                    if observed is None:
                        report("context-unobserved", identity)
                    elif observed != context_hash:
                        report("stale-context", identity)
            if block["kind"] != "generation":
                continue
            if block.get("output") is None:
                report("missing-output", identity)
            try:
                fingerprint = self.inputs(identity)[1]
            except (KeyError, ValueError, TypeError, OSError) as exc:
                report("invalid-input", identity, str(exc))
                continue
            baseline = entry.get("blocks", {}).get(identity)
            if baseline is not None:
                if baseline["input_hash"] != fingerprint:
                    report("stale-generation", identity)
                if baseline["output_hash"] != _hash(block.get("output")):
                    report("output-changed", identity)
                try:
                    annotation = read(self.annotation_path(baseline["generation"]))
                    if (annotation.get("source") != self.key or annotation.get("block") != identity
                            or annotation.get("status") != "Recorded"
                            or annotation.get("input_hash") != baseline["input_hash"]
                            or annotation.get("output_hash") != baseline["output_hash"]):
                        raise ValueError("Annotation disagrees with lock")
                except (OSError, ValueError) as exc:
                    report("invalid-annotation", identity, str(exc))
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


def register_commands(subparsers):
    parser = subparsers.add_parser("document", help="Operate typed .skw.json document sources.")
    commands = parser.add_subparsers(dest="document_command", required=True)
    for name in ("lint", "compile", "prepare", "record", "context", "observe-context"):
        command = commands.add_parser(name)
        command.add_argument("source")
        command.add_argument("--root")
        if name in ("prepare", "context", "observe-context"):
            command.add_argument("block")
        if name == "prepare":
            command.add_argument("--chat")
        if name == "record":
            command.add_argument("generation")
        command.set_defaults(handler=_command)


def _command(args):
    try:
        document = Document(args.source, root=args.root)
        if args.document_command == "prepare":
            result = document.prepare(args.block, chat=args.chat)
        elif args.document_command == "record":
            result = document.record(args.generation)
        elif args.document_command in ("context", "observe-context"):
            result = getattr(document, args.document_command.replace("-", "_"))(args.block)
        else:
            result = getattr(document, args.document_command)()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.document_command == "lint":
            return int(bool(result))
        if args.document_command == "compile":
            return int(not result["written"] or bool(result["findings"]))
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
