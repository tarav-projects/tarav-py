"""Unsorted legacy context selections over retained semantic records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from typing import Any, ClassVar, Literal, TypeVar, cast
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
    model_validator,
)

from tarav._core.data_root import default_tarav_data_root
from tarav._core.persistence import atomic_write_json
from tarav.unsorted.identity import UNSORTED_WORKFLOW_SHIP
from tarav.kernel import TaravClass, entity
from tarav.kernel import TaravObject, TypeRegistry, TypeShip

from tarav.unsorted.evidence import ChatlasEvidence
from tarav.unsorted.storage import Diagram
from tarav.lines.block import DiagramBlock
from tarav.unsorted.primitives import DiagramError
from tarav.lines.line import DiagramLineShip
from tarav.lines.model import DiagramModel
from tarav.unsorted.contracts import Finding
from tarav.unsorted.records import UserTouchedAnnotation


VIEW_REPOSITORY_TYPE = "Tarav.Diagram.View.Repository"
VIEW_MANIFEST_TYPE = "Diagram.View.Manifest"
VIEW_STATE_TYPE = "Tarav.Diagram.View"
VIEW_ABOUT_TYPE = "Tarav.Diagram.View.About"
DIAGRAM_VIEW_TYPE = "Diagram.View"
SESSION_DIAGRAM_VIEW_TYPE = "Session.Diagram.View"
PROJECT_DIAGRAM_VIEW_TYPE = "Project.Diagram.View"
VIEW_CONFIGURATION_TYPE = "Tarav.Diagram.View.Configuration"
VIEW_SCHEMA_VERSION = 2
VIEW_REPOSITORY_FILENAME = "repository.json"
DISCLOSURE_LEVELS = ("collapsed", "lines", "support", "deep-support")
JsonObject = dict[str, Any]


class DiagramViewError(DiagramError):
    pass


def default_diagram_views_root() -> Path:
    return default_tarav_data_root() / "diagram" / "views"


class DiagramViewScopeInterface(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    type: Literal["Diagram.Model", "Diagram.Block"]
    namespace_id: str
    model_ship: str
    block_ship: str | None = None

    @field_validator("namespace_id", "model_ship")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        return _uuid(value, field="View.Scope")

    @model_validator(mode="after")
    def validate_scope(self) -> DiagramViewScopeInterface:
        if self.type == "Diagram.Block":
            _uuid(self.block_ship, field="View.Scope.block_ship")
        elif self.block_ship is not None:
            raise DiagramViewError("Model View.Scope cannot retain block_ship")
        return self


class DiagramViewManifest(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('1c9a9e7e-76a9-4cf0-b823-79fc5032884d'),
            name=VIEW_MANIFEST_TYPE,
            workflow=UNSORTED_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        id: str
        schema_version: Literal[VIEW_SCHEMA_VERSION]
        type: Literal[VIEW_MANIFEST_TYPE]
        view_ship: str
        view_type: Literal[
            "Diagram.View", "Session.Diagram.View", "Project.Diagram.View"
        ]

        @field_validator("id", "view_ship")
        @classmethod
        def validate_uuid(cls, value: str) -> str:
            return _uuid(value, field="View.Manifest")

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> DiagramViewManifest:
        result = super()._from_record(record_data)
        result._view_type = record_data.view_type
        return result

    @property
    def view_type(self) -> str:
        return self._view_type


class DiagramViewConfiguration(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('1c70b581-641e-429a-9305-d4ee65c78ad1'),
            name=VIEW_CONFIGURATION_TYPE,
            workflow=UNSORTED_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal[VIEW_CONFIGURATION_TYPE]
        schema_version: Literal[VIEW_SCHEMA_VERSION]
        bootstrap_visible_lines: int
        max_visible_lines: int
        renderer: Literal["Kernel.Writing.View"]

        @model_validator(mode="after")
        def validate_limits(self) -> DiagramViewConfiguration.RecordInterface:
            if self.bootstrap_visible_lines < 0:
                raise DiagramViewError("bootstrap_visible_lines cannot be negative")
            if self.max_visible_lines < 1:
                raise DiagramViewError("max_visible_lines must be positive")
            return self

    @classmethod
    def create(
        cls, bootstrap_visible_lines: int = 4, max_visible_lines: int = 120
    ) -> DiagramViewConfiguration:
        return cls.from_record(
            {
                "type": entity(cls).name,
                "schema_version": VIEW_SCHEMA_VERSION,
                "bootstrap_visible_lines": bootstrap_visible_lines,
                "max_visible_lines": max_visible_lines,
                "renderer": "Kernel.Writing.View",
            }
        )

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> DiagramViewConfiguration:
        result = super()._from_record(record_data)
        result._bootstrap_visible_lines = record_data.bootstrap_visible_lines
        result._max_visible_lines = record_data.max_visible_lines
        return result

    @property
    def bootstrap_visible_lines(self) -> int:
        return self._bootstrap_visible_lines

    @property
    def max_visible_lines(self) -> int:
        return self._max_visible_lines


class DiagramViewState(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('ff3f638a-43e4-4df2-99d7-3295a485f9df'),
            name=VIEW_STATE_TYPE,
            workflow=UNSORTED_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal[VIEW_STATE_TYPE]
        schema_version: Literal[VIEW_SCHEMA_VERSION]
        view_ship: str
        source_editions: dict[str, str]
        scope: list[DiagramViewScopeInterface]
        blocks: list[JsonObject]

        @field_validator("view_ship")
        @classmethod
        def validate_view_ship(cls, value: str) -> str:
            return _uuid(value, field="View.view_ship")


class DiagramViewAbout(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('20d90137-05cd-4fe8-8926-999fc47e3e16'),
            name=VIEW_ABOUT_TYPE,
            workflow=UNSORTED_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal[VIEW_ABOUT_TYPE]
        data: JsonObject

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> DiagramViewAbout:
        result = super()._from_record(record_data)
        result._data = dict(record_data.data)
        return result

    @property
    def data(self) -> JsonObject:
        return dict(self._data)


class DiagramViewRepositoryRecord(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('f2decb1e-3727-4a1c-8196-c8bf4ca59448'),
            name=VIEW_REPOSITORY_TYPE,
            workflow=UNSORTED_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal[VIEW_REPOSITORY_TYPE]
        schema_version: Literal[VIEW_SCHEMA_VERSION]


ViewRecordT = TypeVar("ViewRecordT", bound=TaravObject)


def _view_record(path: Path, expected: type[ViewRecordT]) -> ViewRecordT:
    data = _read_json(path)
    registry = TypeRegistry(
        TaravObject,
        (
            DiagramViewManifest,
            DiagramViewConfiguration,
            DiagramViewState,
            DiagramViewAbout,
            DiagramViewRepositoryRecord,
        ),
    )
    authority = registry.resolve(data)
    if authority is not expected:
        raise DiagramViewError(f"Unexpected Diagram.View Record Type: {path}")
    result = authority.from_record(data)
    result.source = path
    return cast(ViewRecordT, result)


@dataclass(frozen=True, slots=True)
class DiagramViewChange:
    operation: str
    target: str
    detail: str

    def to_dict(self) -> JsonObject:
        return {
            "operation": self.operation,
            "target": self.target,
            "detail": self.detail,
        }

    def render(self) -> str:
        marker = {"add": "+", "remove": "-", "change": "~"}.get(self.operation, " ")
        return f"{marker} {_short_identifier(self.target)}  {self.detail}"


@dataclass(frozen=True, slots=True)
class DiagramViewMutation:
    view: DiagramView
    changes: tuple[DiagramViewChange, ...]
    commit: str

    def to_dict(self) -> JsonObject:
        return {
            "view_ship": self.view.ship,
            "commit": self.commit,
            "changes": [item.to_dict() for item in self.changes],
            "findings": [item.to_dict() for item in self.view.check()],
        }


@dataclass(frozen=True, slots=True)
class DiagramView:
    type_id: ClassVar[str] = DIAGRAM_VIEW_TYPE
    root: Path

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @property
    def about_path(self) -> Path:
        return self.root / "about.json"

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    @property
    def state_path(self) -> Path:
        return self.root / "view.json"

    @property
    def manifest(self) -> JsonObject:
        return self.manifest_record.to_record()

    @property
    def manifest_record(self) -> DiagramViewManifest:
        return _view_record(self.manifest_path, DiagramViewManifest)

    @property
    def about(self) -> JsonObject:
        return self.about_record.data

    @property
    def about_record(self) -> DiagramViewAbout:
        return _view_record(self.about_path, DiagramViewAbout)

    @property
    def configuration(self) -> DiagramViewConfiguration:
        return _view_record(self.config_path, DiagramViewConfiguration)

    @property
    def state(self) -> JsonObject:
        return self.state_record.to_record()

    @property
    def state_record(self) -> DiagramViewState:
        return _view_record(self.state_path, DiagramViewState)

    @property
    def ship(self) -> str:
        return _uuid(self.manifest.get("view_ship"), field="View.view_ship")

    @property
    def manifest_id(self) -> str:
        return _uuid(self.manifest.get("id"), field="View.id")

    @property
    def view_type(self) -> str:
        return _string(self.manifest.get("view_type"), field="View.view_type")

    @property
    def scopes(self) -> tuple[DiagramViewScopeInterface, ...]:
        return tuple(
            DiagramViewScopeInterface.model_validate(item)
            for item in _array(self.state.get("scope"), field="View.scope")
        )

    def edition(self) -> JsonObject:
        """Return the exact retained View edition in the shared Views repository."""

        repository = self.root.parent
        return {
            "repository": str(repository),
            "commit": _git(repository, "rev-parse", "HEAD"),
            "path": f"{self.root.name}/view.json",
        }

    def check(
        self,
        diagram: Diagram | None = None,
        *,
        evidence: ChatlasEvidence | None = None,
    ) -> tuple[Finding, ...]:
        del evidence
        findings: list[Finding] = []
        try:
            _validate_manifest(
                self.manifest,
                expected_ship=self.root.name,
                expected_type=self.type_id,
            )
            state = self.state
            if state.get("view_ship") != self.ship:
                raise DiagramViewError("view.json does not identify this Diagram.View")
            self.configuration
            self.scopes
        except (DiagramError, ValidationError) as exc:
            return (Finding("diagram-view-invalid", str(self.root), str(exc)),)

        blocks = _array(state.get("blocks"), field="View.blocks")
        identities: set[tuple[str, str]] = set()
        visible_lines = 0
        for index, value in enumerate(blocks):
            block = _object(value, field=f"View.blocks[{index}]")
            namespace_id = _uuid(
                block.get("namespace_id"), field=f"View.blocks[{index}].namespace_id"
            )
            block_ship = _uuid(
                block.get("block_ship"), field=f"View.blocks[{index}].block_ship"
            )
            identity = (namespace_id, block_ship)
            if identity in identities:
                findings.append(
                    Finding(
                        "diagram-view-block-duplicate",
                        f"view.blocks[{index}]",
                        f"Block occurs more than once in the View: {block_ship}.",
                    )
                )
            identities.add(identity)
            level = _integer(
                block.get("disclosure_level"),
                field=f"View.blocks[{index}].disclosure_level",
            )
            if not 0 <= level < len(DISCLOSURE_LEVELS):
                findings.append(
                    Finding(
                        "diagram-view-disclosure-level-invalid",
                        f"view.blocks[{index}].disclosure_level",
                        f"Disclosure level is outside the supported ladder: {level}.",
                    )
                )
            selected = [
                _uuid(item, field=f"View.blocks[{index}].selected_line_ships[]")
                for item in _array(
                    block.get("selected_line_ships", []),
                    field=f"View.blocks[{index}].selected_line_ships",
                )
            ]
            if len(selected) != len(set(selected)):
                findings.append(
                    Finding(
                        "diagram-view-line-selection-duplicate",
                        f"view.blocks[{index}].selected_line_ships",
                        "A Line ship occurs more than once in one Block selection.",
                    )
                )
            if level >= 1:
                rendered = _array(
                    _object(
                        block.get("disclosure", {}),
                        field=f"View.blocks[{index}].disclosure",
                    ).get("lines", []),
                    field=f"View.blocks[{index}].disclosure.lines",
                )
                visible_lines += len(rendered)
                materialized = [
                    _uuid(
                        _object(item, field="View.Line").get("line_ship"),
                        field="View.Line.line_ship",
                    )
                    for item in rendered
                ]
                if materialized != selected:
                    findings.append(
                        Finding(
                            "diagram-view-line-materialization-mismatch",
                            f"view.blocks[{index}].disclosure.lines",
                            "Visible Line material does not match the retained Line selection.",
                        )
                    )
                for line_index, line_value in enumerate(rendered):
                    line = _object(line_value, field="View.Line")
                    for edition_index, edition_value in enumerate(
                        _array(line.get("editions", []), field="View.Line.editions")
                    ):
                        edition = _object(edition_value, field="View.Line.Edition")
                        _uuid(
                            edition.get("edition_id"),
                            field=(
                                f"View.blocks[{index}].disclosure.lines[{line_index}]"
                                f".editions[{edition_index}].edition_id"
                            ),
                        )
                    for raw_finding in _array(
                        line.get("materialization_findings", []),
                        field="materialization_findings",
                    ):
                        retained = _object(raw_finding, field="Finding")
                        findings.append(
                            Finding(
                                str(
                                    retained.get(
                                        "code", "diagram-view-materialization-poi"
                                    )
                                ),
                                f"view.blocks[{index}].disclosure.lines[{line_index}]",
                                str(
                                    retained.get("message", "View materialization POI.")
                                ),
                            )
                        )
            for dependency_index, dependency_value in enumerate(
                _array(block.get("dependencies", []), field="dependencies")
            ):
                dependency = _object(dependency_value, field="dependency")
                if dependency.get("status") == "ambiguous":
                    findings.append(
                        Finding(
                            "diagram-view-dependency-ambiguous",
                            f"view.blocks[{index}].dependencies[{dependency_index}]",
                            f"Dependency label resolves to several Blocks: {dependency.get('label')}.",
                        )
                    )

        maximum = self.configuration.max_visible_lines
        if visible_lines > maximum:
            findings.append(
                Finding(
                    "diagram-view-visible-line-budget-exceeded",
                    "view.blocks",
                    f"View contains {visible_lines} visible Lines; configured maximum is {maximum}.",
                )
            )

        if diagram is not None:
            for namespace_id, edition in _source_editions(state).items():
                try:
                    namespace = diagram.namespace(namespace_id)
                    current = _git(namespace.root, "rev-parse", "HEAD")
                except DiagramError as exc:
                    findings.append(
                        Finding(
                            "diagram-view-source-unresolved",
                            f"view.source_editions.{namespace_id}",
                            str(exc),
                        )
                    )
                    continue
                if current != edition:
                    findings.append(
                        Finding(
                            "diagram-view-source-stale",
                            f"view.source_editions.{namespace_id}",
                            f"View retains {edition}; Namespace HEAD is {current}.",
                        )
                    )
        return tuple(findings)

    def render(self) -> str:
        state = self.state
        lines = [f"# Diagram.View `{_short_identifier(self.ship)}`", ""]
        rendered_support_roots: set[str] = set()
        if self.about:
            lines.extend(
                (
                    "## About",
                    "",
                    "```json",
                    json.dumps(
                        _compact_identifiers(self.about),
                        indent=2,
                        ensure_ascii=False,
                    ),
                    "```",
                    "",
                )
            )
        for value in _array(state.get("blocks"), field="View.blocks"):
            lines.extend(
                _render_block(
                    _object(value, field="View.Block"),
                    seen_support_roots=rendered_support_roots,
                )
            )
        return "\n".join(lines).rstrip() + "\n"

    def render_blocks(self, block_ships: Iterable[str]) -> str:
        """Render complete current materializations for selected View Blocks."""

        blocks = _array(self.state.get("blocks"), field="View.blocks")
        selected = tuple(dict.fromkeys(block_ships))
        rendered_support_roots: set[str] = set()
        lines: list[str] = []
        for block_ship in selected:
            try:
                block = _one_block(blocks, block_ship)
            except DiagramViewError:
                continue
            lines.extend(
                _render_block(block, seen_support_roots=rendered_support_roots)
            )
        return "\n".join(lines).rstrip() + ("\n" if lines else "")


@dataclass(frozen=True, slots=True)
class SessionDiagramView(DiagramView):
    type_id: ClassVar[str] = SESSION_DIAGRAM_VIEW_TYPE

    @property
    def session_identity(self) -> str | None:
        value = self.about.get("chatlas_session_identity")
        return value if isinstance(value, str) and value else None

    @property
    def project_id(self) -> str | None:
        value = self.about.get("project_id")
        return value if isinstance(value, str) and value else None

    def mentions(
        self, diagram: Diagram, evidence: ChatlasEvidence
    ) -> tuple[JsonObject, ...]:
        identity = self.session_identity
        if identity is None:
            raise DiagramViewError(
                "Session.Diagram.View has no Chatlas session identity"
            )
        model = evidence.model(identity)
        texts = tuple(
            str(message.get("text") or "")
            for value in _array(model.get("messages", []), field="Chatlas.messages")
            for message in (_object(value, field="Chatlas.Message"),)
            if message.get("side") in ("user", "agent")
        )
        visible_blocks = {
            (
                _uuid(block.get("namespace_id"), field="View.Block.namespace_id"),
                _uuid(block.get("block_ship"), field="View.Block.block_ship"),
            )
            for value in _array(self.state.get("blocks"), field="View.blocks")
            for block in (_object(value, field="View.Block"),)
        }
        candidates: dict[tuple[str, str], JsonObject] = {}
        labels: dict[str, list[tuple[str, str]]] = {}
        for diagram_model in diagram.models():
            for block in diagram_model.project().blocks:
                identity_key = (diagram_model.namespace.id, block.ship)
                label = block.labels[-1] if block.labels else None
                candidates[identity_key] = {
                    "namespace_id": diagram_model.namespace.id,
                    "model_ship": diagram_model.ship,
                    "block_ship": block.ship,
                    "label": label,
                }
                if label:
                    labels.setdefault(label, []).append(identity_key)

        matches: list[JsonObject] = []
        combined_text = "\n".join(texts)
        for identity_key, candidate in candidates.items():
            match_kinds: list[str] = []
            count = 0
            label = candidate["label"]
            if isinstance(label, str) and len(labels[label]) == 1:
                label_count = _exact_mention_count(combined_text, label)
                if label_count:
                    match_kinds.append("label")
                    count += label_count
            ship = _string(candidate["block_ship"], field="Block.ship")
            ship_count = combined_text.count(ship)
            prefix_count = 0 if ship_count else combined_text.count(ship[:12])
            if ship_count or prefix_count:
                match_kinds.append("ship")
                count += ship_count + prefix_count
            if not match_kinds:
                continue
            matches.append(
                {
                    **candidate,
                    "mention_count": count,
                    "matched_by": match_kinds,
                    "present_in_view": identity_key in visible_blocks,
                }
            )
        return tuple(
            sorted(
                matches,
                key=lambda item: (
                    bool(item["present_in_view"]),
                    -int(item["mention_count"]),
                    str(item["label"] or item["block_ship"]),
                ),
            )
        )

    def check(
        self,
        diagram: Diagram | None = None,
        *,
        evidence: ChatlasEvidence | None = None,
    ) -> tuple[Finding, ...]:
        findings = list(DiagramView.check(self, diagram, evidence=evidence))
        if self.session_identity is None:
            findings.append(
                Finding(
                    "diagram-view-session-identity-missing",
                    "about.chatlas_session_identity",
                    "Session.Diagram.View has no Chatlas session identity.",
                )
            )
        elif diagram is not None and evidence is not None:
            try:
                mentions = self.mentions(diagram, evidence)
            except DiagramError as exc:
                findings.append(
                    Finding(
                        "diagram-view-mention-check-unassessable",
                        "about.chatlas_session_identity",
                        str(exc),
                    )
                )
            else:
                findings.extend(
                    Finding(
                        "diagram-view-mentioned-block-absent",
                        f"mentions.{mention['block_ship']}",
                        f"Session mentions Block {mention['label'] or mention['block_ship']}, but it is outside this View.",
                    )
                    for mention in mentions
                    if not mention["present_in_view"]
                )
        return tuple(findings)


@dataclass(frozen=True, slots=True)
class ProjectDiagramView(DiagramView):
    type_id: ClassVar[str] = PROJECT_DIAGRAM_VIEW_TYPE


VIEW_TYPES: dict[str, type[DiagramView]] = {
    item.type_id: item for item in (DiagramView, SessionDiagramView, ProjectDiagramView)
}


@dataclass(frozen=True, slots=True)
class DiagramViewRepository:
    root: Path

    @classmethod
    def create(cls, root: Path | None = None) -> DiagramViewRepository:
        resolved = (root or default_diagram_views_root()).expanduser().resolve()
        definition = resolved / VIEW_REPOSITORY_FILENAME
        if definition.is_file():
            return cls.open(resolved)
        if resolved.exists() and any(resolved.iterdir()):
            raise DiagramViewError(
                f"Diagram.View repository root is non-empty but uninitialized: {resolved}"
            )
        resolved.mkdir(parents=True, exist_ok=True)
        _git(resolved, "init", "-q")
        atomic_write_json(
            definition,
            {
                "type": VIEW_REPOSITORY_TYPE,
                "schema_version": VIEW_SCHEMA_VERSION,
            },
        )
        _commit(
            resolved,
            (Path(VIEW_REPOSITORY_FILENAME),),
            "diagram(view): initialize repository",
        )
        return cls.open(resolved)

    @classmethod
    def open(cls, root: Path | None = None) -> DiagramViewRepository:
        resolved = (root or default_diagram_views_root()).expanduser().resolve()
        if not (resolved / ".git").is_dir():
            raise DiagramViewError(
                f"Diagram.View repository is not initialized: {resolved}"
            )
        try:
            _view_record(
                resolved / VIEW_REPOSITORY_FILENAME, DiagramViewRepositoryRecord
            )
        except (TypeError, ValueError) as exc:
            raise DiagramViewError(
                f"Unsupported Diagram.View repository: {resolved}"
            ) from exc
        return cls(resolved)

    def views(self) -> tuple[DiagramView, ...]:
        return tuple(
            _load_view(path)
            for path in sorted(self.root.iterdir())
            if path.is_dir() and (path / "manifest.json").is_file()
        )

    def view(self, selector: str) -> DiagramView:
        exact = self.root / selector
        if exact.is_dir():
            return _load_view(exact)
        matches = tuple(item for item in self.views() if item.ship.startswith(selector))
        if len(matches) != 1:
            raise DiagramViewError(
                f"Diagram.View does not resolve uniquely: {selector}"
            )
        return matches[0]

    def session_peer_hints(self, selector: str) -> tuple[JsonObject, ...]:
        view = self.view(selector)
        if not isinstance(view, SessionDiagramView):
            raise DiagramViewError(
                "Peer attention hints require a Session.Diagram.View"
            )
        model_ships = {scope.model_ship for scope in view.scopes}
        hints: list[JsonObject] = []
        for candidate in self.views():
            if candidate.ship == view.ship or not isinstance(
                candidate, SessionDiagramView
            ):
                continue
            shared_models = sorted(
                model_ships.intersection(scope.model_ship for scope in candidate.scopes)
            )
            shared_project = bool(
                view.project_id
                and candidate.project_id
                and view.project_id == candidate.project_id
            )
            if not shared_models and not shared_project:
                continue
            selected_blocks = []
            for value in _array(candidate.state.get("blocks"), field="View.blocks"):
                block = _object(value, field="View.Block")
                selected_lines = _array(
                    block.get("selected_line_ships", []),
                    field="View.Block.selected_line_ships",
                )
                if not selected_lines:
                    continue
                selected_blocks.append(
                    {
                        "block_ship": _uuid(
                            block.get("block_ship"), field="View.Block.block_ship"
                        ),
                        "label": _string(block.get("label"), field="View.Block.label"),
                        "disclosure": _string(
                            block.get("disclosure_name"),
                            field="View.Block.disclosure_name",
                        ),
                        "selected_line_count": len(selected_lines),
                    }
                )
            hints.append(
                {
                    "view_ship": candidate.ship,
                    "session_identity": candidate.session_identity,
                    "shared_project": shared_project,
                    "shared_models": shared_models,
                    "selected_blocks": selected_blocks,
                    "edition": candidate.edition(),
                }
            )
        return tuple(hints)

    def create_view(
        self,
        diagram: Diagram,
        *,
        model_ships: Iterable[str] = (),
        block_ships: Iterable[str] = (),
        view_type: str = DIAGRAM_VIEW_TYPE,
        about: Mapping[str, Any] | None = None,
        configuration: DiagramViewConfiguration | None = None,
        evidence: ChatlasEvidence | None = None,
    ) -> DiagramViewMutation:
        scopes = _resolve_scopes(diagram, model_ships, block_ships)
        if not scopes:
            raise DiagramViewError(
                "Diagram.View requires at least one Model or Block scope"
            )
        view_class = _view_class(view_type)
        ship = str(uuid4())
        root = self.root / ship
        root.mkdir()
        config = configuration or DiagramViewConfiguration.create()
        atomic_write_json(
            root / "manifest.json",
            DiagramViewManifest.from_record(
                {
                    "id": str(uuid4()),
                    "type": VIEW_MANIFEST_TYPE,
                    "view_type": view_type,
                    "schema_version": VIEW_SCHEMA_VERSION,
                    "view_ship": ship,
                }
            ).to_record(),
            ensure_ascii=False,
        )
        atomic_write_json(
            root / "about.json",
            DiagramViewAbout.from_record(
                {"type": VIEW_ABOUT_TYPE, "data": dict(about or {})}
            ).to_record(),
            ensure_ascii=False,
        )
        atomic_write_json(
            root / "config.json",
            config.to_record(),
            ensure_ascii=False,
        )
        state = _materialize(
            diagram,
            scopes,
            config,
            previous=None,
            evidence=evidence,
        )
        state["view_ship"] = ship
        atomic_write_json(
            root / "view.json",
            DiagramViewState.from_record(state).to_record(),
            ensure_ascii=False,
        )
        paths = tuple(path.relative_to(self.root) for path in sorted(root.iterdir()))
        commit = _commit(self.root, paths, f"diagram(view): create {ship}")
        view = view_class(root)
        return DiagramViewMutation(
            view,
            tuple(
                DiagramViewChange(
                    "add",
                    _string(block.get("block_ship"), field="View.Block.block_ship"),
                    _string(block.get("label"), field="View.Block.label"),
                )
                for value in _array(state.get("blocks"), field="View.blocks")
                for block in (_object(value, field="View.Block"),)
            ),
            commit,
        )

    def synchronize(
        self,
        selector: str,
        diagram: Diagram,
        *,
        evidence: ChatlasEvidence | None = None,
    ) -> DiagramViewMutation:
        view = self.view(selector)
        before = view.state
        state = _materialize(
            diagram,
            view.scopes,
            view.configuration,
            previous=before,
            evidence=evidence,
        )
        state["view_ship"] = view.ship
        changes = _state_changes(before, state)
        if not changes:
            return DiagramViewMutation(view, (), _git(self.root, "rev-parse", "HEAD"))
        atomic_write_json(view.state_path, state, ensure_ascii=False)
        commit = _commit(
            self.root,
            (view.state_path.relative_to(self.root),),
            f"diagram(view): synchronize {view.ship}",
        )
        return DiagramViewMutation(view, changes, commit)

    def disclose(
        self,
        selector: str,
        diagram: Diagram,
        *,
        block_ship: str,
        steps: int,
        full: bool = False,
        evidence: ChatlasEvidence | None = None,
    ) -> DiagramViewMutation:
        view = self.view(selector)
        state = view.state
        blocks = _array(state.get("blocks"), field="View.blocks")
        target = _one_block(blocks, block_ship)
        block_ship = _string(target.get("block_ship"), field="View.Block.block_ship")
        old_level = _integer(target.get("disclosure_level"), field="disclosure_level")
        _, projected_block = _resolve_block(diagram, block_ship)
        ladder = projected_block.disclosure_ladder()
        new_level = min(max(old_level + steps, 0), len(ladder) - 1)
        if new_level == old_level:
            return DiagramViewMutation(view, (), _git(self.root, "rev-parse", "HEAD"))
        target["disclosure_level"] = new_level
        if full and steps > 0:
            target["selected_line_ships"] = [
                line.ship for line in projected_block.lines
            ]
        refreshed = _materialize(
            diagram,
            view.scopes,
            view.configuration,
            previous=state,
            evidence=evidence,
        )
        refreshed["view_ship"] = view.ship
        atomic_write_json(view.state_path, refreshed, ensure_ascii=False)
        change = DiagramViewChange(
            "change",
            block_ship,
            f"{ladder[old_level]} -> {ladder[new_level]}",
        )
        commit = _commit(
            self.root,
            (view.state_path.relative_to(self.root),),
            f"diagram(view): disclose {block_ship[:12]}",
        )
        return DiagramViewMutation(view, (change,), commit)

    def select_line(
        self,
        selector: str,
        diagram: Diagram,
        *,
        block_ship: str,
        line_ship: str,
        selected: bool,
        evidence: ChatlasEvidence | None = None,
    ) -> DiagramViewMutation:
        view = self.view(selector)
        state = view.state
        target = _one_block(
            _array(state.get("blocks"), field="View.blocks"), block_ship
        )
        block_ship = _string(target.get("block_ship"), field="View.Block.block_ship")
        _, projected_block = _resolve_block(diagram, block_ship)
        line_ship = _resolve_identifier(
            line_ship,
            (line.ship for line in projected_block.lines),
            kind=f"Line in View Block {block_ship}",
        )
        selection = list(
            _array(target.get("selected_line_ships", []), field="selected_line_ships")
        )
        if selected and line_ship not in selection:
            selection.append(line_ship)
        elif not selected and line_ship in selection:
            selection.remove(line_ship)
        else:
            return DiagramViewMutation(view, (), _git(self.root, "rev-parse", "HEAD"))
        target["selected_line_ships"] = selection
        if selected and int(target.get("disclosure_level", 0)) == 0:
            target["disclosure_level"] = 1
        refreshed = _materialize(
            diagram,
            view.scopes,
            view.configuration,
            previous=state,
            evidence=evidence,
        )
        refreshed["view_ship"] = view.ship
        atomic_write_json(view.state_path, refreshed, ensure_ascii=False)
        change = DiagramViewChange(
            "change",
            block_ship,
            f"{'included' if selected else 'excluded'} Line {line_ship[:12]}",
        )
        commit = _commit(
            self.root,
            (view.state_path.relative_to(self.root),),
            f"diagram(view): {'include' if selected else 'exclude'} line {line_ship[:12]}",
        )
        return DiagramViewMutation(view, (change,), commit)


def _resolve_scopes(
    diagram: Diagram,
    model_ships: Iterable[str],
    block_ships: Iterable[str],
) -> tuple[DiagramViewScopeInterface, ...]:
    scopes: list[DiagramViewScopeInterface] = []
    for ship in model_ships:
        model = diagram.model(ship)
        scopes.append(
            DiagramViewScopeInterface(
                type="Diagram.Model",
                namespace_id=model.namespace.id,
                model_ship=model.ship,
            )
        )
    for ship in block_ships:
        model, _ = _resolve_block(diagram, ship)
        scopes.append(
            DiagramViewScopeInterface(
                type="Diagram.Block",
                namespace_id=model.namespace.id,
                model_ship=model.ship,
                block_ship=ship,
            )
        )
    return tuple(dict.fromkeys(scopes))


def _resolve_block(
    diagram: Diagram, block_ship: str
) -> tuple[DiagramModel, DiagramBlock]:
    matches: list[tuple[DiagramModel, DiagramBlock]] = []
    for model in diagram.models():
        matches.extend(
            (model, block)
            for block in model.project().blocks
            if block.ship.startswith(block_ship)
        )
    if len(matches) != 1:
        raise DiagramViewError(f"Diagram Block does not resolve uniquely: {block_ship}")
    return matches[0]


def _materialize(
    diagram: Diagram,
    scopes: Iterable[DiagramViewScopeInterface],
    configuration: DiagramViewConfiguration,
    *,
    previous: Mapping[str, Any] | None,
    evidence: ChatlasEvidence | None,
) -> JsonObject:
    scoped: list[tuple[DiagramModel, DiagramBlock]] = []
    for scope in scopes:
        model = diagram.model(scope.model_ship)
        if model.namespace.id != scope.namespace_id:
            raise DiagramViewError(
                f"View Scope Namespace no longer owns Model {scope.model_ship}"
            )
        projection = model.project()
        blocks = (
            projection.blocks
            if scope.type == "Diagram.Model"
            else (projection.block(_string(scope.block_ship, field="block_ship")),)
        )
        scoped.extend((model, block) for block in blocks)
    unique: dict[tuple[str, str], tuple[DiagramModel, DiagramBlock]] = {}
    for model, block in scoped:
        unique[(model.namespace.id, block.ship)] = (model, block)

    label_index: dict[str, list[tuple[str, str]]] = {}
    for candidate_model in diagram.models():
        for candidate_block in candidate_model.project().blocks:
            for label in candidate_block.labels:
                label_index.setdefault(label, []).append(
                    (candidate_model.namespace.id, candidate_block.ship)
                )

    prior_blocks: dict[tuple[str, str], JsonObject] = {}
    if previous is not None:
        for value in _array(previous.get("blocks", []), field="View.blocks"):
            item = _object(value, field="View.Block")
            prior_blocks[
                (str(item.get("namespace_id")), str(item.get("block_ship")))
            ] = item

    blocks: list[JsonObject] = []
    for identity, (model, block) in unique.items():
        prior = prior_blocks.get(identity)
        ranked = _rank_lines(diagram, model, block, evidence=evidence)
        selected = (
            [
                str(item)
                for item in _array(
                    prior.get("selected_line_ships", []), field="selected_line_ships"
                )
            ]
            if prior is not None
            else [line.ship for line in ranked[: configuration.bootstrap_visible_lines]]
        )
        valid_ships = {line.ship for line in block.lines}
        selected_set = {ship for ship in selected if ship in valid_ships}
        selected = [line.ship for line in block.lines if line.ship in selected_set]
        level = (
            int(prior.get("disclosure_level", 1 if selected else 0))
            if prior
            else (1 if selected else 0)
        )
        entry = _block_entry(
            diagram,
            model,
            block,
            label_index,
            selected,
            level,
            evidence=evidence,
        )
        blocks.append(entry)

    namespace_ids = tuple(
        dict.fromkeys(model.namespace.id for model, _ in unique.values())
    )
    return {
        "type": VIEW_STATE_TYPE,
        "schema_version": VIEW_SCHEMA_VERSION,
        "view_ship": previous.get("view_ship") if previous else None,
        "source_editions": {
            namespace_id: _git(
                diagram.namespace(namespace_id).root, "rev-parse", "HEAD"
            )
            for namespace_id in namespace_ids
        },
        "scope": [item.model_dump(mode="json", exclude_none=True) for item in scopes],
        "blocks": blocks,
    }


def _block_entry(
    diagram: Diagram,
    model: DiagramModel,
    block: DiagramBlock,
    label_index: Mapping[str, list[tuple[str, str]]],
    selected: list[str],
    level: int,
    *,
    evidence: ChatlasEvidence | None,
) -> JsonObject:
    ladder = block.disclosure_ladder()
    level = min(max(level, 0), len(ladder) - 1)
    dependencies = _block_dependencies(block, label_index)
    reviewed = 0
    support_members = 0
    selected_set = set(selected)
    rendered_lines: list[JsonObject] = []
    reviewed_lines = {
        line.ship: _is_reviewed(diagram, model, line, evidence=evidence)
        for line in block.lines
    }
    line_types = model.namespace.object_types()
    for line in block.lines:
        support_members += _support_count(line)
        if reviewed_lines[line.ship]:
            reviewed += 1
        if level >= 1 and line.ship in selected_set:
            line_type = (
                line_types.line_type(line.object_type)
                if line.object_type is not None
                else None
            )
            rendered_lines.append(
                _line_entry(
                    line,
                    level=level,
                    evidence=evidence,
                    reviewed=reviewed_lines[line.ship],
                    line_type_code=line_type.short_code if line_type else None,
                )
            )
    label = block.labels[-1] if block.labels else f"Block.{block.ship[:12]}"
    return {
        "namespace_id": model.namespace.id,
        "model_ship": model.ship,
        "block_ship": block.ship,
        "label": label,
        "block_type": block.object_type,
        "dependencies": dependencies,
        "stats": {
            "line_count": len(block.lines),
            "selected_line_count": len(selected),
            "reviewed_line_count": reviewed,
            "support_member_count": support_members,
            "finding_count": len(block.findings)
            + sum(len(line.findings) for line in block.lines),
        },
        "disclosure_level": level,
        "disclosure_name": ladder[level],
        "selected_line_ships": selected,
        "disclosure": {"lines": rendered_lines},
    }


def _line_entry(
    line: DiagramLineShip,
    *,
    level: int,
    evidence: ChatlasEvidence | None,
    reviewed: bool,
    line_type_code: str | None,
) -> JsonObject:
    editions: list[JsonObject] = []
    support_content: list[JsonObject] = []
    support_findings: list[JsonObject] = []
    for item in line.editions:
        annotation = item.annotation
        editions.append({"edition_id": annotation.id, "text": item.text})
    if level >= 3 and evidence is not None:
        for typed in line.annotations:
            if isinstance(typed, UserTouchedAnnotation):
                try:
                    members = typed.render_support(evidence)
                except DiagramError as exc:
                    support_findings.append(
                        Finding(
                            "diagram-view-deep-support-unresolved",
                            f"annotation.{typed.id}.support",
                            str(exc),
                        ).to_dict()
                    )
                else:
                    support_content.extend(
                        _compact_support_member(item) for item in members
                    )
    result: JsonObject = {
        "line_ship": line.ship,
        "line_type": line.object_type,
        "editions": editions,
        "stats": {
            "edition_count": len(editions),
            "finding_count": len(line.findings),
        },
    }
    if line_type_code is not None:
        result["line_type_code"] = line_type_code
    if level >= 2:
        support_roots, support_turns = _support_stats(line)
        result["stats"].update(
            {
                "support_root_count": support_roots,
                "support_turn_count": support_turns,
                "reviewed": reviewed,
            }
        )
    if level >= 3:
        result["support_content"] = support_content
        if evidence is None:
            result["materialization_findings"] = [
                Finding(
                    "diagram-view-deep-support-unassessable",
                    f"line.{line.ship}",
                    "Deep support disclosure requires Chatlas evidence.",
                ).to_dict()
            ]
        else:
            result["materialization_findings"] = support_findings
    return result


def _rank_lines(
    diagram: Diagram,
    model: DiagramModel,
    block: DiagramBlock,
    *,
    evidence: ChatlasEvidence | None,
) -> tuple[DiagramLineShip, ...]:
    order = {line.ship: index for index, line in enumerate(block.lines)}
    return tuple(
        sorted(
            block.lines,
            key=lambda line: (
                -int(_is_reviewed(diagram, model, line, evidence=evidence)),
                -_support_count(line),
                order[line.ship],
            ),
        )
    )


def _is_reviewed(
    diagram: Diagram,
    model: DiagramModel,
    line: DiagramLineShip,
    *,
    evidence: ChatlasEvidence | None,
) -> bool:
    if evidence is None:
        return False
    try:
        return (
            diagram.line_review(
                line.ship,
                namespace=model.namespace.id,
                evidence=evidence,
            ).standing
            == "Reviewed"
        )
    except DiagramError:
        return False


def _support_count(line: DiagramLineShip) -> int:
    return _support_stats(line)[0]


def _support_stats(line: DiagramLineShip) -> tuple[int, int]:
    roots: set[tuple[str, str, str]] = set()
    turns: set[tuple[str, str, str]] = set()
    for annotation in line.annotations:
        if not isinstance(annotation, UserTouchedAnnotation):
            continue
        for member in annotation.support:
            root = (
                member.root.session_identity,
                member.root.turn_address,
                member.root.turn_hash,
            )
            roots.add(root)
            turns.add(root)
            turns.update(
                (
                    reference.session_identity,
                    reference.turn_address,
                    reference.turn_hash,
                )
                for reference in member.neighborhood
            )
    return len(roots), len(turns)


def _render_block(
    block: Mapping[str, Any], *, seen_support_roots: set[str]
) -> list[str]:
    label = _string(block.get("label"), field="View.Block.label")
    block_type = block.get("block_type") or "Diagram.Block"
    level = _integer(block.get("disclosure_level"), field="View.Block.disclosure_level")
    stats = _object(block.get("stats", {}), field="View.Block.stats")
    lines = [
        f"## {label}",
        "",
        f"`{str(block_type)}` · "
        f"`{_short_identifier(str(block['block_ship']))}` · "
        f"{block.get('disclosure_name', DISCLOSURE_LEVELS[level])} · "
        f"{stats.get('line_count', 0)} lines · "
        f"{stats.get('reviewed_line_count', 0)} reviewed · "
        f"{stats.get('finding_count', 0)} POIs",
    ]
    dependencies = _array(block.get("dependencies", []), field="dependencies")
    if dependencies:
        rendered = ", ".join(
            f"`{_object(item, field='dependency').get('label')}`"
            for item in dependencies
        )
        lines.extend(("", f"Dependencies: {rendered}"))
    disclosure = _object(block.get("disclosure", {}), field="disclosure")
    for line in _array(disclosure.get("lines", []), field="disclosure.lines"):
        item = _object(line, field="View.Line")
        line_type = (
            item.get("line_type_code") or item.get("line_type") or "Diagram.Line"
        )
        line_ship = _short_identifier(
            _string(item.get("line_ship"), field="View.Line.line_ship")
        )
        for edition in _array(item.get("editions", []), field="editions"):
            wording = _object(edition, field="edition")
            lines.extend(
                (
                    "",
                    f"- [{line_type}] {wording.get('text', '')} [`{line_ship}`]",
                )
            )
        if level >= 2:
            lines.append(f"  - {_line_stats(item)}")
        if level >= 3:
            lines.extend(_support_content_lines(item, seen=seen_support_roots))
    lines.append("")
    return lines


def _line_stats(line: Mapping[str, Any]) -> str:
    stats = _object(line.get("stats", {}), field="View.Line.stats")
    root_count = int(stats.get("support_root_count", 0))
    turn_count = int(stats.get("support_turn_count", 0))
    finding_count = int(stats.get("finding_count", 0))
    review = "reviewed" if stats.get("reviewed") else "unreviewed"
    return " · ".join(
        (
            review,
            f"{root_count} support root{'s' if root_count != 1 else ''}",
            f"{turn_count} support turn{'s' if turn_count != 1 else ''}",
            f"{finding_count} POI{'s' if finding_count != 1 else ''}",
        )
    )


def _support_content_lines(line: Mapping[str, Any], *, seen: set[str]) -> list[str]:
    rendered: list[str] = []
    for member_value in _array(
        line.get("support_content", []), field="View.Line.support_content"
    ):
        member = _object(member_value, field="View.Support.Member")
        source = _string(member.get("source"), field="View.Support.Member.source")
        if source in seen:
            continue
        seen.add(source)
        rendered.append(f"  - Support `{source}`")
        for turn_value in _array(
            member.get("turns", []), field="View.Support.Member.turns"
        ):
            support_turn = _object(turn_value, field="View.Support.Turn")
            side = str(support_turn.get("side") or "turn").title()
            marker = " (root)" if support_turn.get("root") else ""
            rendered.append(f"    - **{side}{marker}:**")
            text = str(support_turn.get("text") or "")
            rendered.extend(_fenced_verbatim_lines(text, indent="      "))
    return rendered


def _fenced_verbatim_lines(text: str, *, indent: str) -> list[str]:
    longest_run = 0
    current_run = 0
    for character in text:
        if character == "`":
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    fence = "`" * max(5, longest_run + 1)
    return [
        f"{indent}{fence}text",
        *(f"{indent}{part}" for part in text.splitlines() or ("",)),
        f"{indent}{fence}",
    ]


def _compact_support_member(value: object) -> JsonObject:
    member = _object(value, field="Support.Member")
    root = _object(member.get("root", {}), field="Support.Member.root")
    source = "/".join(
        (
            _short_identifier(str(root.get("session_identity", "unknown"))),
            _short_identifier(str(root.get("turn_address", "unknown"))),
        )
    )
    return {
        "source": source,
        "turns": [
            {
                "side": turn.get("side"),
                "text": turn.get("text"),
                "root": bool(turn.get("root")),
            }
            for turn_value in _array(
                member.get("turns", []), field="Support.Member.turns"
            )
            for turn in (_object(turn_value, field="Support.Turn"),)
        ],
    }


def _short_identifier(value: str) -> str:
    compact = value.replace("-", "")
    if len(compact) >= 32 and all(
        character in "0123456789abcdefABCDEF" for character in compact
    ):
        return value[:12]
    return value


def _exact_mention_count(text: str, value: str) -> int:
    pattern = (
        rf"(?<![A-Za-z0-9_.-]){re.escape(value)}"
        rf"(?![A-Za-z0-9_-]|\.[A-Za-z0-9_])"
    )
    return len(re.findall(pattern, text))


def _compact_identifiers(value: object) -> object:
    if isinstance(value, str):
        return _short_identifier(value)
    if isinstance(value, list):
        return [_compact_identifiers(item) for item in value]
    if isinstance(value, dict):
        return {key: _compact_identifiers(item) for key, item in value.items()}
    return value


def _resolve_identifier(selector: str, candidates: Iterable[str], *, kind: str) -> str:
    matches = tuple(
        candidate for candidate in candidates if candidate.startswith(selector)
    )
    if len(matches) != 1:
        raise DiagramViewError(f"{kind} does not resolve uniquely: {selector}")
    return matches[0]


def _block_dependencies(
    block: DiagramBlock,
    label_index: Mapping[str, list[tuple[str, str]]],
) -> list[JsonObject]:
    result: list[JsonObject] = []
    for label in block.inlined_dependencies(label_index):
        candidates = label_index[label]
        target_ships = tuple(ship for _, ship in candidates)
        if block.ship in target_ships:
            continue
        result.append(
            {
                "label": label,
                "status": "resolved" if len(candidates) == 1 else "ambiguous",
                "targets": [
                    {"namespace_id": namespace_id, "block_ship": ship}
                    for namespace_id, ship in candidates
                ],
            }
        )
    return result


def _state_changes(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> tuple[DiagramViewChange, ...]:
    old = {
        (str(item.get("namespace_id")), str(item.get("block_ship"))): item
        for value in _array(before.get("blocks", []), field="View.blocks")
        for item in (_object(value, field="View.Block"),)
    }
    new = {
        (str(item.get("namespace_id")), str(item.get("block_ship"))): item
        for value in _array(after.get("blocks", []), field="View.blocks")
        for item in (_object(value, field="View.Block"),)
    }
    changes: list[DiagramViewChange] = []
    for identity in new.keys() - old.keys():
        changes.append(
            DiagramViewChange("add", identity[1], str(new[identity].get("label")))
        )
    for identity in old.keys() - new.keys():
        changes.append(
            DiagramViewChange("remove", identity[1], str(old[identity].get("label")))
        )
    for identity in new.keys() & old.keys():
        if new[identity] != old[identity]:
            changes.append(
                DiagramViewChange(
                    "change", identity[1], str(new[identity].get("label"))
                )
            )
    return tuple(changes)


def _source_editions(state: Mapping[str, Any]) -> dict[str, str]:
    return {
        _uuid(key, field="source_editions.namespace_id"): _string(
            value, field="source_editions.commit"
        )
        for key, value in _object(
            state.get("source_editions", {}), field="source_editions"
        ).items()
    }


def _one_block(blocks: list[object], block_ship: str) -> JsonObject:
    matches: list[JsonObject] = []
    for item in blocks:
        if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
            raise DiagramViewError("View.Block must be a JSON object")
        if str(item.get("block_ship", "")).startswith(block_ship):
            matches.append(item)
    if len(matches) != 1:
        raise DiagramViewError(f"View Block does not resolve uniquely: {block_ship}")
    return matches[0]


def _view_class(view_type: str) -> type[DiagramView]:
    try:
        return VIEW_TYPES[view_type]
    except KeyError as exc:
        raise DiagramViewError(f"Unsupported Diagram.View Type: {view_type}") from exc


def _load_view(root: Path) -> DiagramView:
    manifest = _view_record(root / "manifest.json", DiagramViewManifest)
    return _view_class(manifest.view_type)(root)


def _validate_manifest(
    data: Mapping[str, Any], *, expected_ship: str, expected_type: str
) -> None:
    if (
        data.get("type") != VIEW_MANIFEST_TYPE
        or data.get("view_type") != expected_type
        or data.get("schema_version") != VIEW_SCHEMA_VERSION
        or data.get("view_ship") != expected_ship
    ):
        raise DiagramViewError("Unsupported Diagram.View manifest")
    _uuid(data.get("id"), field="View.id")
    _uuid(data.get("view_ship"), field="View.view_ship")


def _read_json(path: Path) -> JsonObject:
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), field=str(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiagramViewError(f"Cannot read Diagram.View JSON {path}: {exc}") from exc


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repo), *args),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise DiagramViewError(
            f"Git failed for {repo}: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def _commit(repo: Path, paths: Iterable[Path], message: str) -> str:
    values = tuple(path.as_posix() for path in paths)
    _git(repo, "add", "--", *values)
    staged = subprocess.run(
        ("git", "-C", str(repo), "diff", "--cached", "--quiet", "--", *values),
        capture_output=True,
        text=True,
        check=False,
    )
    if staged.returncode == 0:
        return _git(repo, "rev-parse", "HEAD")
    if staged.returncode != 1:
        raise DiagramViewError(
            f"Git failed for {repo}: {staged.stderr.strip() or staged.stdout.strip()}"
        )
    _git(
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
    return _git(repo, "rev-parse", "HEAD")


def _object(value: object, *, field: str) -> JsonObject:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DiagramViewError(f"{field} must be a JSON object")
    return dict(value)


def _array(value: object, *, field: str) -> list[object]:
    if not isinstance(value, list):
        raise DiagramViewError(f"{field} must be a JSON array")
    return list(value)


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise DiagramViewError(f"{field} must be a non-empty string")
    return value


def _optional_string(value: object, *, field: str) -> str | None:
    return None if value is None else _string(value, field=field)


def _integer(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DiagramViewError(f"{field} must be an integer")
    return value


def _uuid(value: object, *, field: str) -> str:
    text = _string(value, field=field)
    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise DiagramViewError(f"{field} must be a UUID") from exc
    if str(parsed) != text:
        raise DiagramViewError(f"{field} must be a canonical lowercase UUID")
    return text


__all__ = [
    "DISCLOSURE_LEVELS",
    "DiagramView",
    "DiagramViewChange",
    "DiagramViewConfiguration",
    "DiagramViewError",
    "DiagramViewMutation",
    "DiagramViewRepository",
    "DiagramViewScopeInterface",
    "VIEW_STATE_TYPE",
    "VIEW_MANIFEST_TYPE",
    "default_diagram_views_root",
]
