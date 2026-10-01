"""Independent, library-first generation blocks. No agent execution or repair.

Templates use ``${argument}`` placeholders (``$$`` escapes a dollar). An
Output input explicitly consumes another invocation's retained text. Checks
report changed evidence; they never regenerate, bless, or rewrite anything.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from string import Template
from typing import Mapping
from uuid import uuid4

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.poi import IdentifiedPOI
from tarav.l1.skw.identity import SKILLWARE_WORKFLOW_SHIP


def _hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class Argument:
    name: str
    kind: str = "text"


@dataclass(frozen=True)
class Block:
    name: str
    prompt: str
    arguments: tuple[Argument, ...] = ()

    def __post_init__(self) -> None:
        names = [arg.name for arg in self.arguments]
        if not self.name or len(names) != len(set(names)):
            raise ValueError("Block needs a name and unique arguments")
        for arg in self.arguments:
            if not arg.name.isidentifier() or arg.kind not in {
                "text", "integer", "number", "boolean", "json"
            }:
                raise ValueError(f"Invalid argument: {arg}")
        template = Template(self.prompt)
        if not template.is_valid():
            raise ValueError("Invalid template syntax")
        unknown = set(template.get_identifiers()) - set(names)
        if unknown:
            raise ValueError(f"Undeclared template arguments: {sorted(unknown)}")

    @property
    def fingerprint(self) -> str:
        return _hash(asdict(self))


@dataclass(frozen=True)
class Output:
    invocation: str


class GenerationPOI(IdentifiedPOI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("07610436-2388-4bfc-8be8-d8b83b8cb6b6"),
            name="Tarav.Skillware.Generation.POI",
            workflow=SKILLWARE_WORKFLOW_SHIP,
        )

    def __init__(self, kind: str, invocation: str, detail: str):
        self.kind = kind
        self.invocation = invocation
        self.detail = detail
        super().__init__(
            kind,
            detail,
            subject={"invocation": invocation, "kind": kind},
            evidence={"detail": detail},
        )


class Generation:
    """An explicitly owned JSON state store, independent of Index and Diagram.

    ``prepare`` expands a prompt for an external agent. ``finish`` records
    its output; ``check`` independently reports missing or stale evidence.
    Persistence is explicit through save/load. Store instances are single-writer.
    """

    def __init__(self, blocks: tuple[Block, ...] = ()) -> None:
        self.blocks: dict[str, Block] = {}
        self.invocations: dict[str, dict] = {}
        for block in blocks:
            if block.name in self.blocks:
                raise ValueError(f"Duplicate block: {block.name}")
            self.blocks[block.name] = block

    def prepare(self, block: str, arguments: Mapping[str, object], *,
                chat: str | None = None) -> str:
        definition = self.blocks[block]
        expected = {arg.name: arg.kind for arg in definition.arguments}
        if set(arguments) != set(expected):
            raise ValueError("Supplied arguments must exactly match declarations")
        values: dict[str, object] = {}
        dependencies = {}
        for name, value in arguments.items():
            if isinstance(value, Output):
                source = self.invocations[value.invocation]
                if source["output"] is None:
                    raise ValueError(f"Dependency has no output: {value.invocation}")
                dependencies[name] = {
                    "invocation": value.invocation,
                    "hash": _hash(source["output"]),
                }
                value = source["output"]
            kind = expected[name]
            valid = {
                "text": isinstance(value, str),
                "integer": type(value) is int,
                "number": type(value) in (int, float),
                "boolean": type(value) is bool,
                "json": True,
            }[kind]
            if not valid:
                raise TypeError(f"Argument {name} requires {kind}")
            # Snapshot inputs and reject non-JSON data or non-finite numbers.
            values[name] = json.loads(json.dumps(value, allow_nan=False))
        rendered = Template(definition.prompt).substitute({
            name: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            for name, value in values.items()
        })
        identity = uuid4().hex
        self.invocations[identity] = {
            "block": block, "block_hash": definition.fingerprint,
            "arguments": values, "dependencies": dependencies,
            "prompt": rendered, "chat": chat, "output": None,
            "output_path": None,
        }
        return identity

    def finish(self, invocation: str, output: str, *, path: str | Path | None = None) -> None:
        if not isinstance(output, str):
            raise TypeError("Generation output must be text")
        target = Path(path).resolve() if path is not None else None
        if target is not None and target.read_text() != output:
            raise ValueError("Output does not match the supplied file")
        record = self.invocations[invocation]
        record["output"] = output
        record["output_path"] = str(target) if target is not None else None

    def check(self) -> tuple[GenerationPOI, ...]:
        findings: list[GenerationPOI] = []
        stale: set[str] = set()
        for identity, record in self.invocations.items():
            def report(kind: str, detail: str) -> None:
                findings.append(GenerationPOI(kind, identity, detail))
                stale.add(identity)

            block = self.blocks.get(record["block"])
            if block is None:
                report("missing-block", record["block"])
            elif block.fingerprint != record["block_hash"]:
                report("block-changed", block.name)
            if record["output"] is None:
                report("missing-output", "Invocation has no recorded output")
            if record["output_path"] is not None:
                try:
                    current = Path(record["output_path"]).read_text()
                except (OSError, UnicodeError) as exc:
                    report("output-unavailable", str(exc))
                else:
                    if current != record["output"]:
                        report("output-changed", record["output_path"])
            for name, dependency in record["dependencies"].items():
                source = self.invocations.get(dependency["invocation"])
                if source is None:
                    report("missing-dependency", name)
                elif _hash(source["output"]) != dependency["hash"]:
                    report("dependency-changed", name)
        # Propagate review standing even when downstream bytes are unchanged.
        while True:
            affected = {
                identity for identity, record in self.invocations.items()
                if identity not in stale and any(
                    dep["invocation"] in stale for dep in record["dependencies"].values()
                )
            }
            if not affected:
                break
            for identity in sorted(affected):
                findings.append(GenerationPOI("dependency-needs-review", identity,
                                              "An upstream invocation has POIs"))
            stale.update(affected)
        return tuple(findings)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({
            "schema": 1, "blocks": [asdict(block) for block in self.blocks.values()],
            "invocations": self.invocations,
        }, indent=2, ensure_ascii=False, allow_nan=False) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> Generation:
        data = json.loads(Path(path).read_text())
        if data["schema"] != 1:
            raise ValueError("Unsupported generation schema")
        result = cls(tuple(Block(row["name"], row["prompt"], tuple(
            Argument(**arg) for arg in row["arguments"]
        )) for row in data["blocks"]))
        result.invocations = data["invocations"]
        return result
