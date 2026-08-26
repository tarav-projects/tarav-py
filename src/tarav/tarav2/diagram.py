"""Namespace-rooted Tarav2 Diagram mechanics."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from typing import Any
from uuid import UUID, uuid4

from tarav._core.persistence import atomic_write_json
from tarav._core.project import load_project_marker, project_marker_path
from tarav.chatlas.normal_model import (
    provide_normal_model,
    resolve_chat_message_ref,
    resolve_chat_turn_ref,
)

NAMESPACE_CLASS = "Tarav.Diagram.Namespace"
DIAGRAM_CONFIG_CLASS = "Tarav.Diagram.Configuration"
CAPTURE_MANIFEST_CLASS = "Tarav.Diagram.Capture.Manifest"
USER_TOUCHED_CHATLAS_INDEX = "User.Touched.Chatlas.Index"
MODEL_ANNOTATION_TYPE = "Diagram.Model.Annotation"
LINE_ANNOTATION_TYPE = "Diagram.Line.Annotation"
LINE_SUPPORT_ANNOTATION_TYPE = "Diagram.Line.Support.Annotation"
SCHEMA_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
JsonObject = dict[str, Any]


class DiagramError(RuntimeError):
    pass


class DiagramModelError(ValueError):
    pass


class DiagramAnnotationSpecializationError(DiagramError):
    pass


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    path: str
    message: str

    def to_dict(self) -> JsonObject:
        return {
            "class": "Tarav.POI.Instance",
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ChatlasTurnReference:
    session_identity: str
    turn_address: str
    turn_hash: str

    def __post_init__(self) -> None:
        _digest(self.session_identity, field="Chatlas.Reference.session_identity")
        _digest(self.turn_address, field="Chatlas.Reference.turn_address")
        _digest(self.turn_hash, field="Chatlas.Reference.turn_hash")

    def to_dict(self) -> dict[str, str]:
        return {
            "session_identity": self.session_identity,
            "turn_address": self.turn_address,
            "turn_hash": self.turn_hash,
        }

    @classmethod
    def from_dict(cls, value: object) -> ChatlasTurnReference:
        data = _object(value, field="Chatlas.Reference")
        return cls(
            _string(data.get("session_identity"), field="session_identity"),
            _string(data.get("turn_address"), field="turn_address"),
            _string(data.get("turn_hash"), field="turn_hash"),
        )


@dataclass(frozen=True, slots=True)
class SupportMember:
    root: ChatlasTurnReference
    neighborhood: tuple[ChatlasTurnReference, ...] = ()

    def to_dict(self) -> JsonObject:
        return {
            "root": self.root.to_dict(),
            "neighborhood": [item.to_dict() for item in self.neighborhood],
        }

    @classmethod
    def from_dict(cls, value: object) -> SupportMember:
        data = _object(value, field="Support.Member")
        return cls(
            ChatlasTurnReference.from_dict(data.get("root")),
            tuple(
                ChatlasTurnReference.from_dict(item)
                for item in _array(data.get("neighborhood", []), field="neighborhood")
            ),
        )


@dataclass(frozen=True, slots=True)
class SupportSet:
    members: tuple[SupportMember, ...]

    def to_list(self) -> list[JsonObject]:
        return [item.to_dict() for item in self.members]

    @classmethod
    def from_list(cls, value: object) -> SupportSet:
        return cls(
            tuple(
                SupportMember.from_dict(item)
                for item in _array(value, field="Annotation.support")
            )
        )


@dataclass(frozen=True, slots=True)
class DiagramLocation:
    model_ship: str
    block_ship: str
    line_ship: str

    def __post_init__(self) -> None:
        for key, value in self.to_dict().items():
            _uuid(value, field=f"Annotation.location.{key}")

    def to_dict(self) -> dict[str, str]:
        return {
            "model_ship": self.model_ship,
            "block_ship": self.block_ship,
            "line_ship": self.line_ship,
        }

    @classmethod
    def from_dict(cls, value: object) -> DiagramLocation:
        data = _object(value, field="Annotation.location")
        return cls(
            *(
                _string(data.get(key), field=f"Annotation.location.{key}")
                for key in ("model_ship", "block_ship", "line_ship")
            )
        )


@dataclass(frozen=True, slots=True)
class AnnotationDraft:
    id: str
    record: JsonObject

    def __post_init__(self) -> None:
        _uuid(self.id, field="Annotation.id")
        copied = _object(self.record, field="Annotation")
        _string(copied.get("type"), field="Annotation.type")
        object.__setattr__(self, "record", copied)

    def to_dict(self) -> JsonObject:
        return {"id": self.id, **self.record}

    @classmethod
    def from_dict(cls, value: object) -> AnnotationDraft:
        data = _object(value, field="Capture.Annotation")
        annotation_id = data.pop("id", None)
        return cls(_string(annotation_id, field="Annotation.id"), data)


@dataclass(frozen=True, slots=True)
class DiagramAnnotation:
    """Opaque Annotation. Only ``type`` is universal."""

    id: str
    namespace: DiagramNamespace
    record: JsonObject

    def __post_init__(self) -> None:
        _uuid(self.id, field="Annotation.id")
        copied = _object(self.record, field="Annotation.Record")
        _string(copied.get("type"), field="Annotation.type")
        object.__setattr__(self, "record", copied)

    @property
    def type(self) -> str:
        return _string(self.record.get("type"), field="Annotation.type")

    @property
    def standing(self) -> str:
        return "Asserted" if self.record.get("score_vector") else "UnAsserted"

    def assertions(self) -> tuple[JsonObject, ...]:
        return self.namespace.assertions_for(self)

    def score_vector(self) -> JsonObject:
        value = self.record.get("score_vector", {})
        return value if isinstance(value, dict) else {}

    def to_record(self) -> JsonObject:
        return dict(self.record)

    def specialize(self) -> TypedAnnotation:
        return self.namespace.specialize(self)


@dataclass(frozen=True, slots=True)
class TypedAnnotation:
    annotation: DiagramAnnotation

    @property
    def id(self) -> str:
        return self.annotation.id

    @property
    def type(self) -> str:
        return self.annotation.type

    @property
    def record(self) -> JsonObject:
        return self.annotation.record


@dataclass(frozen=True, slots=True)
class ModelAnnotation(TypedAnnotation):
    def __post_init__(self) -> None:
        if self.type != MODEL_ANNOTATION_TYPE:
            raise DiagramModelError(f"not a Model Annotation: {self.type}")
        _uuid(self.record.get("model_ship"), field="Model.Annotation.model_ship")

    @property
    def model_ship(self) -> str:
        return _string(self.record.get("model_ship"), field="model_ship")


@dataclass(frozen=True, slots=True)
class UserTouchedAnnotation(TypedAnnotation):
    @property
    def producer(self) -> ChatlasTurnReference:
        return ChatlasTurnReference.from_dict(self.record.get("producer"))

    @property
    def support(self) -> SupportSet:
        return SupportSet.from_list(self.record.get("support", []))

    def render_support(self, evidence: ChatlasEvidence) -> list[JsonObject]:
        return [evidence.render_member(item) for item in self.support.members]


@dataclass(frozen=True, slots=True)
class LineAnnotation(UserTouchedAnnotation):
    def __post_init__(self) -> None:
        if self.type != LINE_ANNOTATION_TYPE:
            raise DiagramModelError(f"not a Line Annotation: {self.type}")
        DiagramLocation.from_dict(self.record.get("location"))
        _string(
            _object(self.record.get("data", {}), field="data").get("text"),
            field="data.text",
        )

    @property
    def location(self) -> DiagramLocation:
        return DiagramLocation.from_dict(self.record.get("location"))

    @property
    def text(self) -> str:
        return _string(
            _object(self.record.get("data", {}), field="data").get("text"),
            field="data.text",
        )


@dataclass(frozen=True, slots=True)
class LineSupportAnnotation(UserTouchedAnnotation):
    def __post_init__(self) -> None:
        if self.type != LINE_SUPPORT_ANNOTATION_TYPE:
            raise DiagramModelError(f"not a Line Support Annotation: {self.type}")
        DiagramLocation.from_dict(self.record.get("location"))

    @property
    def location(self) -> DiagramLocation:
        return DiagramLocation.from_dict(self.record.get("location"))


@dataclass(frozen=True, slots=True)
class CaptureManifest:
    model_ship: str
    annotations: tuple[AnnotationDraft, ...]

    def __post_init__(self) -> None:
        _uuid(self.model_ship, field="Capture.Manifest.model_ship")

    def to_dict(self) -> JsonObject:
        return {
            "class": CAPTURE_MANIFEST_CLASS,
            "schema_version": SCHEMA_VERSION,
            "model_ship": self.model_ship,
            "annotations": [item.to_dict() for item in self.annotations],
        }

    @classmethod
    def from_dict(cls, value: object) -> CaptureManifest:
        data = _object(value, field="Capture.Manifest")
        if (
            data.get("class") != CAPTURE_MANIFEST_CLASS
            or data.get("schema_version") != SCHEMA_VERSION
        ):
            raise DiagramModelError("unsupported Tarav Diagram Capture.Manifest")
        return cls(
            _string(data.get("model_ship"), field="model_ship"),
            tuple(
                AnnotationDraft.from_dict(item)
                for item in _array(data.get("annotations"), field="annotations")
            ),
        )

    @classmethod
    def read(cls, path: Path) -> CaptureManifest:
        return cls.from_dict(_read_json(path))

    @classmethod
    def template(
        cls,
        *,
        model_ship: str,
        annotation_type: str = LINE_ANNOTATION_TYPE,
        block_ship: str | None = None,
        line_ship: str | None = None,
    ) -> CaptureManifest:
        empty = ChatlasTurnReference("0" * 64, "0" * 64, "0" * 64)
        record = {
            "type": annotation_type,
            "producer": empty.to_dict(),
            "support": [SupportMember(empty).to_dict()],
            "location": DiagramLocation(
                model_ship, block_ship or str(uuid4()), line_ship or str(uuid4())
            ).to_dict(),
            "data": {"text": ""} if annotation_type == LINE_ANNOTATION_TYPE else {},
        }
        return cls(model_ship, (AnnotationDraft(str(uuid4()), record),))

    def check(
        self, namespace: DiagramNamespace, *, evidence: ChatlasEvidence | None = None
    ) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        seen: dict[str, JsonObject] = {}
        for index, draft in enumerate(self.annotations):
            path = f"annotations[{index}]"
            if draft.id in seen:
                findings.append(
                    Finding(
                        "duplicate-annotation-id",
                        f"{path}.id",
                        "Capture.Manifest repeats one Annotation identity.",
                    )
                )
                if seen[draft.id] != draft.record:
                    findings.append(
                        Finding(
                            "annotation-identity-rebound",
                            f"{path}.id",
                            "One Annotation identity names different content.",
                        )
                    )
            seen[draft.id] = draft.record
            annotation = DiagramAnnotation(draft.id, namespace, draft.record)
            findings.extend(
                namespace.findings(annotation, path=path, evidence=evidence)
            )
            location = draft.record.get("location")
            if (
                isinstance(location, dict)
                and location.get("model_ship") != self.model_ship
            ):
                findings.append(
                    Finding(
                        "capture-model-mismatch",
                        f"{path}.location.model_ship",
                        "Annotation is not located in the Capture.Manifest Model.",
                    )
                )
        return tuple(findings)


@dataclass(frozen=True, slots=True)
class CaptureReceipt:
    namespace_id: str
    created: tuple[str, ...]
    existing: tuple[str, ...]
    findings: tuple[Finding, ...]
    commit: str

    def to_dict(self) -> JsonObject:
        return {
            "class": "Tarav.Diagram.Capture.Receipt",
            "namespace_id": self.namespace_id,
            "created": list(self.created),
            "existing": list(self.existing),
            "findings": [item.to_dict() for item in self.findings],
            "commit": self.commit,
        }


class ChatlasEvidence:
    def __init__(
        self,
        *,
        model_loader: Callable[[str], JsonObject] | None = None,
        chatlas_root: Path | None = None,
    ) -> None:
        self.model_loader = model_loader or (
            lambda identity: provide_normal_model(
                identity_hash=identity, chatlas_root=chatlas_root
            )
        )
        self._models: dict[str, JsonObject] = {}

    def model(self, identity: str) -> JsonObject:
        if identity not in self._models:
            model = self.model_loader(identity)
            if not isinstance(model, dict):
                raise DiagramError("Chatlas Normal Model loader returned no object")
            self._models[identity] = model
        return self._models[identity]

    def resolve(self, ref: ChatlasTurnReference) -> JsonObject:
        turns = self.model(ref.session_identity).get("turns")
        if not isinstance(turns, list):
            raise DiagramError("Chatlas Normal Model has no turns collection")
        return resolve_chat_turn_ref(
            turns, {"turn_address": ref.turn_address, "turn_hash": ref.turn_hash}
        )

    def check(self, annotation: UserTouchedAnnotation, *, path: str) -> list[Finding]:
        findings: list[Finding] = []
        producer = self._matched(
            annotation.producer,
            f"{path}.producer",
            "producer-turn-unresolved",
            findings,
        )
        if producer is not None and producer.get("side") != "agent":
            findings.append(
                Finding(
                    "producer-turn-not-agent",
                    f"{path}.producer",
                    "Annotation producer is not an Agent turn.",
                )
            )
        for index, member in enumerate(annotation.support.members):
            root_path = f"{path}.support[{index}].root"
            root = self._matched(
                member.root, root_path, "support-root-unresolved", findings
            )
            if root is not None and root.get("side") != "user":
                findings.append(
                    Finding(
                        "support-root-not-user",
                        root_path,
                        "Support.Member root is not a User turn.",
                    )
                )
        return findings

    def render_member(self, member: SupportMember) -> JsonObject:
        refs = (member.root, *member.neighborhood)
        return {
            "root": member.root.to_dict(),
            "turns": [
                {
                    "reference": ref.to_dict(),
                    "side": self._turn(ref).get("side"),
                    "text": self.turn_text(ref),
                    "root": ref == member.root,
                }
                for ref in refs
            ],
        }

    def turn_text(self, ref: ChatlasTurnReference) -> str:
        turn = self._turn(ref)
        messages = self.model(ref.session_identity).get("messages")
        chunks: list[str] = []
        if isinstance(messages, list):
            for message_ref in turn.get("message_refs", []):
                if isinstance(message_ref, dict):
                    resolved = resolve_chat_message_ref(messages, message_ref)
                    message = resolved.get("message")
                    if (
                        resolved.get("standing") == "MATCHED"
                        and isinstance(message, dict)
                        and isinstance(message.get("text"), str)
                    ):
                        chunks.append(message["text"])
        return "\n".join(chunks)

    def _matched(
        self, ref: ChatlasTurnReference, path: str, code: str, findings: list[Finding]
    ) -> JsonObject | None:
        try:
            resolved = self.resolve(ref)
        except Exception as exc:
            findings.append(Finding(code, path, str(exc)))
            return None
        turn = resolved.get("turn")
        if resolved.get("standing") != "MATCHED" or not isinstance(turn, dict):
            findings.append(
                Finding(
                    code,
                    path,
                    f"Chatlas Turn reference standing is {resolved.get('standing')}.",
                )
            )
            return None
        return turn

    def _turn(self, ref: ChatlasTurnReference) -> JsonObject:
        findings: list[Finding] = []
        turn = self._matched(ref, "reference", "turn-unresolved", findings)
        if turn is None:
            raise DiagramError(findings[0].message)
        return turn


@dataclass(frozen=True, slots=True)
class DiagramNamespace:
    root: Path
    id: str
    name: str
    allowed_types: tuple[str, ...]

    @property
    def annotations_root(self) -> Path:
        return self.root / "annotations"

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        name: str,
        namespace_id: str | None = None,
        allowed_types: Iterable[str] = (),
    ) -> DiagramNamespace:
        resolved = root.expanduser().resolve()
        if resolved.exists() and any(resolved.iterdir()):
            return cls.open(resolved)
        resolved.mkdir(parents=True, exist_ok=True)
        (resolved / "annotations").mkdir()
        _run_git(resolved, "init", "-q")
        atomic_write_json(
            resolved / "namespace.json",
            {
                "class": NAMESPACE_CLASS,
                "schema_version": SCHEMA_VERSION,
                "id": namespace_id or str(uuid4()),
                "name": name,
                "allowed_types": list(allowed_types),
            },
        )
        _commit_paths(
            resolved,
            (Path("namespace.json"),),
            message="diagram(namespace): initialize",
        )
        return cls.open(resolved)

    @classmethod
    def create_user_touched_chatlas_index(cls, root: Path) -> DiagramNamespace:
        return cls.create(
            root,
            name=USER_TOUCHED_CHATLAS_INDEX,
            allowed_types=(
                MODEL_ANNOTATION_TYPE,
                LINE_ANNOTATION_TYPE,
                LINE_SUPPORT_ANNOTATION_TYPE,
            ),
        )

    @classmethod
    def open(cls, root: Path) -> DiagramNamespace:
        resolved = root.expanduser().resolve()
        if not (resolved / ".git").is_dir() or not (resolved / "annotations").is_dir():
            raise DiagramError(f"Diagram Namespace repository is invalid: {resolved}")
        data = _read_json(resolved / "namespace.json")
        if (
            data.get("class") != NAMESPACE_CLASS
            or data.get("schema_version") != SCHEMA_VERSION
        ):
            raise DiagramError(f"Diagram Namespace definition is invalid: {resolved}")
        return cls(
            resolved,
            _uuid(data.get("id"), field="Namespace.id"),
            _string(data.get("name"), field="Namespace.name"),
            tuple(
                _string(item, field="allowed_types[]")
                for item in _array(data.get("allowed_types", []), field="allowed_types")
            ),
        )

    def annotation(self, annotation_id: str) -> DiagramAnnotation:
        annotation_id = _uuid(annotation_id, field="Annotation.id")
        path = self.annotations_root / f"{annotation_id}.json"
        if not path.is_file():
            raise DiagramError(f"Diagram Annotation not found: {annotation_id}")
        return DiagramAnnotation(annotation_id, self, _read_json(path))

    def annotations(self) -> tuple[DiagramAnnotation, ...]:
        return tuple(
            DiagramAnnotation(path.stem, self, _read_json(path))
            for path in sorted(self.annotations_root.glob("*.json"))
        )

    def assertions_for(self, annotation: DiagramAnnotation) -> tuple[JsonObject, ...]:
        if self.name != USER_TOUCHED_CHATLAS_INDEX:
            return ()
        if annotation.type == MODEL_ANNOTATION_TYPE:
            return ({"type": "Model.Derived.Support.Assertion"},)
        assertions: tuple[JsonObject, ...] = (
            {"type": "Annotation.Representation.Assertion"},
            {"type": "User.Touch.Support.Assertion"},
        )
        if annotation.type in (LINE_ANNOTATION_TYPE, LINE_SUPPORT_ANNOTATION_TYPE):
            assertions += tuple(
                {"type": kind}
                for kind in (
                    "Line.Continuity.Assertion",
                    "Block.Context.Assertion",
                    "Model.Scope.Assertion",
                )
            )
        return assertions

    def specialize(self, annotation: DiagramAnnotation) -> TypedAnnotation:
        classes = (
            {
                MODEL_ANNOTATION_TYPE: ModelAnnotation,
                LINE_ANNOTATION_TYPE: LineAnnotation,
                LINE_SUPPORT_ANNOTATION_TYPE: LineSupportAnnotation,
            }
            if self.name == USER_TOUCHED_CHATLAS_INDEX
            else {}
        )
        annotation_class = classes.get(annotation.type)
        if annotation_class is None:
            raise DiagramAnnotationSpecializationError(
                f"Annotation type is not registered in Namespace {self.name}: {annotation.type}"
            )
        try:
            return annotation_class(annotation)
        except DiagramModelError as exc:
            raise DiagramAnnotationSpecializationError(
                f"Annotation {annotation.id} cannot be specialized as {annotation.type}: {exc}"
            ) from exc

    def findings(
        self,
        annotation: DiagramAnnotation,
        *,
        path: str,
        evidence: ChatlasEvidence | None = None,
    ) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        if self.allowed_types and annotation.type not in self.allowed_types:
            findings.append(
                Finding(
                    "annotation-type-not-allowed",
                    f"{path}.type",
                    f"Namespace {self.name} does not allow Annotation type {annotation.type}.",
                )
            )
        try:
            typed = self.specialize(annotation)
        except DiagramAnnotationSpecializationError as exc:
            findings.append(
                Finding(
                    "annotation-specialization-unavailable", f"{path}.type", str(exc)
                )
            )
            return tuple(findings)
        if isinstance(typed, UserTouchedAnnotation):
            if not typed.support.members:
                findings.append(
                    Finding(
                        "empty-support-set",
                        f"{path}.support",
                        "Annotation has no rooted User.Turn support.",
                    )
                )
            if evidence is not None:
                findings.extend(evidence.check(typed, path=path))
        return tuple(findings)

    def append(
        self,
        drafts: Iterable[AnnotationDraft],
        *,
        findings: Iterable[Finding] = (),
        message: str = "diagram: append annotations",
    ) -> CaptureReceipt:
        created: list[str] = []
        existing: list[str] = []
        pending: list[tuple[Path, JsonObject]] = []
        claimed: dict[str, JsonObject] = {}
        for draft in drafts:
            if draft.id in claimed:
                if claimed[draft.id] != draft.record:
                    raise DiagramError(
                        f"Diagram Annotation identity cannot be rebound: {draft.id}"
                    )
                continue
            claimed[draft.id] = draft.record
            path = self.annotations_root / f"{draft.id}.json"
            if path.exists():
                if _semantic_record(_read_json(path)) != _semantic_record(draft.record):
                    raise DiagramError(
                        f"Diagram Annotation identity cannot be rebound: {draft.id}"
                    )
                existing.append(draft.id)
            else:
                pending.append((path, {**draft.record, "recorded_at": _timestamp()}))
        for path, record in pending:
            atomic_write_json(path, record, ensure_ascii=False)
            created.append(path.stem)
        if pending:
            _commit_paths(
                self.root,
                (path.relative_to(self.root) for path, _ in pending),
                message=message,
            )
        return CaptureReceipt(
            self.id,
            tuple(created),
            tuple(existing),
            tuple(findings),
            _run_git(self.root, "rev-parse", "HEAD"),
        )

    def create_model(
        self, *, model_ship: str | None = None, label: str | None = None
    ) -> DiagramModel:
        ship = model_ship or str(uuid4())
        draft = AnnotationDraft(
            str(uuid4()),
            {
                "type": MODEL_ANNOTATION_TYPE,
                "model_ship": ship,
                "data": {"label": label} if label else {},
            },
        )
        self.append((draft,), message="diagram(model): create")
        return DiagramModel(ship, self, draft.id)

    def model(self, model_ship: str) -> DiagramModel:
        ship = _uuid(model_ship, field="Model.ship")
        roots = [
            item
            for item in self.annotations()
            if item.type == MODEL_ANNOTATION_TYPE
            and item.record.get("model_ship") == ship
        ]
        if len(roots) != 1:
            raise DiagramError(
                f"Diagram Model does not resolve uniquely in Namespace {self.name}: {ship}"
            )
        return DiagramModel(ship, self, roots[0].id)

    def apply(
        self, manifest: CaptureManifest, *, evidence: ChatlasEvidence | None = None
    ) -> CaptureReceipt:
        self.model(manifest.model_ship)
        return self.append(
            manifest.annotations,
            findings=manifest.check(self, evidence=evidence),
            message=f"diagram(capture): add {len(manifest.annotations)} annotation(s)",
        )

    def line(self, line_ship: str) -> tuple[TypedAnnotation, ...]:
        ship = _uuid(line_ship, field="Line.ship")
        result: list[TypedAnnotation] = []
        for annotation in self.annotations():
            if annotation.type in (LINE_ANNOTATION_TYPE, LINE_SUPPORT_ANNOTATION_TYPE):
                typed = self.specialize(annotation)
                if (
                    isinstance(typed, (LineAnnotation, LineSupportAnnotation))
                    and typed.location.line_ship == ship
                ):
                    result.append(typed)
        return tuple(result)


@dataclass(frozen=True, slots=True)
class DiagramModel:
    ship: str
    namespace: DiagramNamespace
    root_annotation_id: str

    def annotations(self) -> tuple[DiagramAnnotation, ...]:
        return tuple(
            item
            for item in self.namespace.annotations()
            if isinstance(item.record.get("location"), dict)
            and item.record["location"].get("model_ship") == self.ship
        )


@dataclass(frozen=True, slots=True)
class DiagramConfiguration:
    path: Path
    namespace_locations: tuple[Path, ...]
    default_namespace_id: str | None = None

    @staticmethod
    def default_path() -> Path:
        return (Path.home() / ".tarav" / "diagram.json").resolve()

    @classmethod
    def load(
        cls, path: Path | None = None, *, create: bool = False
    ) -> DiagramConfiguration:
        resolved = (path or cls.default_path()).expanduser().resolve()
        if not resolved.exists():
            if not create:
                raise DiagramError(f"Diagram configuration not found: {resolved}")
            resolved.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                resolved,
                {
                    "class": DIAGRAM_CONFIG_CLASS,
                    "schema_version": SCHEMA_VERSION,
                    "namespace_locations": [],
                    "default_namespace_id": None,
                },
            )
        data = _read_json(resolved)
        if (
            data.get("class") != DIAGRAM_CONFIG_CLASS
            or data.get("schema_version") != SCHEMA_VERSION
        ):
            raise DiagramError(f"Diagram configuration is invalid: {resolved}")
        default = data.get("default_namespace_id")
        return cls(
            resolved,
            tuple(
                Path(_string(item, field="namespace_locations[]"))
                .expanduser()
                .resolve()
                for item in _array(
                    data.get("namespace_locations", []), field="namespace_locations"
                )
            ),
            _uuid(default, field="default_namespace_id")
            if default is not None
            else None,
        )

    def mount(
        self, namespace: DiagramNamespace, *, default: bool = False
    ) -> DiagramConfiguration:
        locations = list(self.namespace_locations)
        if namespace.root not in locations:
            locations.append(namespace.root)
        default_id = namespace.id if default else self.default_namespace_id
        atomic_write_json(
            self.path,
            {
                "class": DIAGRAM_CONFIG_CLASS,
                "schema_version": SCHEMA_VERSION,
                "namespace_locations": [str(item) for item in locations],
                "default_namespace_id": default_id,
            },
        )
        return DiagramConfiguration.load(self.path)

    def diagram(self) -> Diagram:
        return Diagram(
            tuple(DiagramNamespace.open(path) for path in self.namespace_locations),
            self.default_namespace_id,
        )


@dataclass(frozen=True, slots=True)
class Diagram:
    namespaces: tuple[DiagramNamespace, ...]
    default_namespace_id: str | None = None

    def namespace(self, selector: str | None = None) -> DiagramNamespace:
        selector = selector or self.default_namespace_id
        if selector is None and len(self.namespaces) == 1:
            return self.namespaces[0]
        matches = [item for item in self.namespaces if selector in (item.id, item.name)]
        if len(matches) != 1:
            raise DiagramError(
                f"Diagram Namespace does not resolve uniquely: {selector}"
            )
        return matches[0]

    def annotation(
        self, annotation_id: str, *, namespace: str | None = None
    ) -> DiagramAnnotation:
        if namespace:
            return self.namespace(namespace).annotation(annotation_id)
        matches = [
            space.annotation(annotation_id)
            for space in self.namespaces
            if (space.annotations_root / f"{annotation_id}.json").is_file()
        ]
        if not matches:
            raise DiagramError(f"Diagram Annotation not found: {annotation_id}")
        return matches[0]

    def model(self, model_ship: str) -> DiagramModel:
        matches = []
        for space in self.namespaces:
            roots = [
                item
                for item in space.annotations()
                if item.type == MODEL_ANNOTATION_TYPE
                and item.record.get("model_ship") == model_ship
            ]
            matches.extend(DiagramModel(model_ship, space, item.id) for item in roots)
        if len(matches) != 1:
            raise DiagramError(f"Diagram Model does not resolve uniquely: {model_ship}")
        return matches[0]

    def apply(
        self, manifest: CaptureManifest, *, evidence: ChatlasEvidence | None = None
    ) -> CaptureReceipt:
        return self.model(manifest.model_ship).namespace.apply(
            manifest, evidence=evidence
        )

    def line(
        self, line_ship: str, *, namespace: str | None = None
    ) -> tuple[TypedAnnotation, ...]:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        return tuple(item for space in spaces for item in space.line(line_ship))

    def ensure_project_model(self, project_root: Path) -> DiagramModel:
        marker_path = project_marker_path(project_root.expanduser().resolve())
        marker = load_project_marker(marker_path)
        setting = marker.get("diagram")
        if isinstance(setting, dict) and isinstance(setting.get("main_model"), str):
            return self.model(setting["main_model"])
        namespace = (
            self.namespace(USER_TOUCHED_CHATLAS_INDEX)
            if any(item.name == USER_TOUCHED_CHATLAS_INDEX for item in self.namespaces)
            else self.namespace()
        )
        model = namespace.create_model(label=project_root.name)
        marker["diagram"] = {"main_model": model.ship}
        atomic_write_json(marker_path, marker, ensure_ascii=False)
        return model


def _semantic_record(record: Mapping[str, Any]) -> JsonObject:
    return {key: value for key, value in record.items() if key != "recorded_at"}


def _object(value: object, *, field: str) -> JsonObject:
    if not isinstance(value, dict):
        raise DiagramModelError(f"{field} must be an object")
    return dict(value)


def _array(value: object, *, field: str) -> list[object]:
    if not isinstance(value, list):
        raise DiagramModelError(f"{field} must be an array")
    return value


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise DiagramModelError(f"{field} must be a non-empty string")
    return value


def _digest(value: object, *, field: str) -> str:
    text = _string(value, field=field)
    if not _SHA256.fullmatch(text):
        raise DiagramModelError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _uuid(value: object, *, field: str) -> str:
    text = _string(value, field=field)
    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise DiagramModelError(f"{field} must be a UUID") from exc
    if str(parsed) != text:
        raise DiagramModelError(f"{field} must be a canonical lowercase UUID")
    return text


def _read_json(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiagramError(f"cannot read Diagram JSON {path}: {exc}") from exc
    return _object(value, field=str(path))


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repo), *args), capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise DiagramError(
            f"Git failed for {repo}: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def _commit_paths(repo: Path, paths: Iterable[Path], *, message: str) -> None:
    values = tuple(path.as_posix() for path in paths)
    _run_git(repo, "add", "--", *values)
    _run_git(
        repo,
        "-c",
        "user.name=Tarav Diagram",
        "-c",
        "user.email=diagram@tarav.invalid",
        "commit",
        "-q",
        "--only",
        "-m",
        message,
        "--",
        *values,
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    name
    for name in globals()
    if name.startswith("Diagram")
    or name
    in {
        "AnnotationDraft",
        "CaptureManifest",
        "CaptureReceipt",
        "ChatlasEvidence",
        "ChatlasTurnReference",
        "Finding",
        "SupportMember",
        "SupportSet",
        "TypedAnnotation",
        "UserTouchedAnnotation",
        "LineAnnotation",
        "LineSupportAnnotation",
        "ModelAnnotation",
        "LINE_ANNOTATION_TYPE",
        "LINE_SUPPORT_ANNOTATION_TYPE",
        "MODEL_ANNOTATION_TYPE",
        "USER_TOUCHED_CHATLAS_INDEX",
    }
]
