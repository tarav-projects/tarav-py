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
from tarav.l1.poi import SituationPOI
from tarav.l1.skw.identity import SKW_CODE_WORKFLOW_SHIP


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


# tarav.breadcrumb 4b43d55059fb05aa7715826b8ba7ff6dd20358261d63637de0766aef86c39765
# tarav.breadcrumb 761a547484e330286e3bc9e3cbab88e035e8700c14e8a03f0837c2c137bae58e
class GenerationPOI(SituationPOI):
    """Family, never raised: a recorded generation no longer matches its inputs or output."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("07610436-2388-4bfc-8be8-d8b83b8cb6b6"),
            name="Tarav.Skillware.Generation.POI",
            workflow=SKW_CODE_WORKFLOW_SHIP,
        )

    def __init__(self, invocation: str, detail: str):
        self.invocation = invocation
        self.detail = detail
        super().__init__(detail, situation={"invocation": invocation})


class GenerationBlockMissing(GenerationPOI):
    """An invocation's generation block no longer exists."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6903c605-92b0-4549-a51b-f374233e7a8b"),
                          name="Tarav.Skillware.Generation.POI.BlockMissing", workflow=SKW_CODE_WORKFLOW_SHIP)


class GenerationBlockChanged(GenerationPOI):
    """An invocation's generation block changed since it was recorded."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("630cfb35-58d4-46b2-a232-3e3ad5a0d97a"),
                          name="Tarav.Skillware.Generation.POI.BlockChanged", workflow=SKW_CODE_WORKFLOW_SHIP)


class GenerationOutputMissing(GenerationPOI):
    """An invocation has no recorded output."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b4a55172-aa7b-465f-a1c4-7533958b18a5"),
                          name="Tarav.Skillware.Generation.POI.OutputMissing", workflow=SKW_CODE_WORKFLOW_SHIP)


class GenerationOutputUnavailable(GenerationPOI):
    """An invocation's output file cannot be read."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9134f086-8f88-4100-9b23-7713d7084c19"),
                          name="Tarav.Skillware.Generation.POI.OutputUnavailable", workflow=SKW_CODE_WORKFLOW_SHIP)


class GenerationOutputChanged(GenerationPOI):
    """An invocation's output file differs from its recorded output."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("da7e7187-1407-4811-ad73-9f77eeacbe0d"),
                          name="Tarav.Skillware.Generation.POI.OutputChanged", workflow=SKW_CODE_WORKFLOW_SHIP)


class GenerationDependencyMissing(GenerationPOI):
    """An invocation depends on an invocation that no longer exists."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("178e8397-3d9a-40f1-b5a3-e37c72fc581e"),
                          name="Tarav.Skillware.Generation.POI.DependencyMissing", workflow=SKW_CODE_WORKFLOW_SHIP)


class GenerationDependencyChanged(GenerationPOI):
    """An invocation's dependency produced different output since it was recorded."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a9a0c920-3cee-4db6-9de8-75518db9684e"),
                          name="Tarav.Skillware.Generation.POI.DependencyChanged", workflow=SKW_CODE_WORKFLOW_SHIP)


class GenerationDependencyNeedsReview(GenerationPOI):
    """An upstream invocation has POIs, so this invocation needs review."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("aef5e66f-5b1c-44cf-bf45-d74a1b1ab4f0"),
                          name="Tarav.Skillware.Generation.POI.DependencyNeedsReview", workflow=SKW_CODE_WORKFLOW_SHIP)


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
            def report(case: type[GenerationPOI], detail: str) -> None:
                findings.append(case(identity, detail))
                stale.add(identity)

            block = self.blocks.get(record["block"])
            if block is None:
                report(GenerationBlockMissing, record["block"])
            elif block.fingerprint != record["block_hash"]:
                report(GenerationBlockChanged, block.name)
            if record["output"] is None:
                report(GenerationOutputMissing, "Invocation has no recorded output")
            if record["output_path"] is not None:
                try:
                    current = Path(record["output_path"]).read_text()
                except (OSError, UnicodeError) as exc:
                    report(GenerationOutputUnavailable, str(exc))
                else:
                    if current != record["output"]:
                        report(GenerationOutputChanged, record["output_path"])
            for name, dependency in record["dependencies"].items():
                source = self.invocations.get(dependency["invocation"])
                if source is None:
                    report(GenerationDependencyMissing, name)
                elif _hash(source["output"]) != dependency["hash"]:
                    report(GenerationDependencyChanged, name)
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
                findings.append(GenerationDependencyNeedsReview(identity,
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
