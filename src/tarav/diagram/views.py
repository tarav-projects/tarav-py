"""Retained, Agent-readable context selections over Tarav.Diagram."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any
from uuid import UUID, uuid4

from tarav._core.data_root import default_tarav_data_root
from tarav._core.persistence import atomic_write_json

from . import (
    ChatlasEvidence,
    Diagram,
    DiagramBlock,
    DiagramError,
    DiagramLineShip,
    DiagramModel,
    Finding,
    UserTouchedAnnotation,
)


VIEW_REPOSITORY_CLASS = "Tarav.Diagram.View.Repository"
VIEW_MANIFEST_TYPE = "Diagram.View.Annotation"
VIEW_CLASS = "Tarav.Diagram.View"
VIEW_CONFIGURATION_CLASS = "Tarav.Diagram.View.Configuration"
VIEW_SCHEMA_VERSION = 1
VIEW_REPOSITORY_FILENAME = "repository.json"
DISCLOSURE_LEVELS = ("collapsed", "lines", "support", "deep-support")
JsonObject = dict[str, Any]


class DiagramViewError(DiagramError):
    pass


def default_diagram_views_root() -> Path:
    return default_tarav_data_root() / "diagram" / "views"


@dataclass(frozen=True, slots=True)
class DiagramViewScope:
    kind: str
    namespace_id: str
    model_ship: str
    block_ship: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("Diagram.Model", "Diagram.Block"):
            raise DiagramViewError(f"Unsupported Diagram.View Scope kind: {self.kind}")
        _uuid(self.namespace_id, field="View.Scope.namespace_id")
        _uuid(self.model_ship, field="View.Scope.model_ship")
        if self.kind == "Diagram.Block":
            _uuid(self.block_ship, field="View.Scope.block_ship")
        elif self.block_ship is not None:
            raise DiagramViewError("Model View.Scope cannot retain block_ship")

    def to_dict(self) -> JsonObject:
        result: JsonObject = {
            "type": self.kind,
            "namespace_id": self.namespace_id,
            "model_ship": self.model_ship,
        }
        if self.block_ship is not None:
            result["block_ship"] = self.block_ship
        return result

    @classmethod
    def from_dict(cls, value: object) -> DiagramViewScope:
        data = _object(value, field="View.Scope")
        return cls(
            _string(data.get("type"), field="View.Scope.type"),
            _string(data.get("namespace_id"), field="View.Scope.namespace_id"),
            _string(data.get("model_ship"), field="View.Scope.model_ship"),
            _optional_string(data.get("block_ship"), field="View.Scope.block_ship"),
        )


@dataclass(frozen=True, slots=True)
class DiagramViewConfiguration:
    bootstrap_visible_lines: int = 4
    max_visible_lines: int = 120

    def __post_init__(self) -> None:
        if self.bootstrap_visible_lines < 0:
            raise DiagramViewError("bootstrap_visible_lines cannot be negative")
        if self.max_visible_lines < 1:
            raise DiagramViewError("max_visible_lines must be positive")

    def to_dict(self) -> JsonObject:
        return {
            "class": VIEW_CONFIGURATION_CLASS,
            "schema_version": VIEW_SCHEMA_VERSION,
            "bootstrap_visible_lines": self.bootstrap_visible_lines,
            "max_visible_lines": self.max_visible_lines,
            "renderer": "Kernel.Writing.View",
        }

    @classmethod
    def from_dict(cls, value: object) -> DiagramViewConfiguration:
        data = _object(value, field="Diagram.View.Configuration")
        if (
            data.get("class") != VIEW_CONFIGURATION_CLASS
            or data.get("schema_version") != VIEW_SCHEMA_VERSION
        ):
            raise DiagramViewError("Unsupported Diagram.View Configuration")
        return cls(
            _integer(
                data.get("bootstrap_visible_lines"),
                field="bootstrap_visible_lines",
            ),
            _integer(data.get("max_visible_lines"), field="max_visible_lines"),
        )


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
        marker = {"add": "+", "remove": "-", "change": "~"}.get(
            self.operation, " "
        )
        return f"{marker} {self.target}  {self.detail}"


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
        return _read_json(self.manifest_path)

    @property
    def about(self) -> JsonObject:
        return _read_json(self.about_path)

    @property
    def configuration(self) -> DiagramViewConfiguration:
        return DiagramViewConfiguration.from_dict(_read_json(self.config_path))

    @property
    def state(self) -> JsonObject:
        return _read_json(self.state_path)

    @property
    def ship(self) -> str:
        return _uuid(self.manifest.get("view_ship"), field="View.view_ship")

    @property
    def annotation_id(self) -> str:
        return _uuid(self.manifest.get("id"), field="View.id")

    @property
    def scopes(self) -> tuple[DiagramViewScope, ...]:
        return tuple(
            DiagramViewScope.from_dict(item)
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

    def check(self, diagram: Diagram | None = None) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        try:
            _validate_manifest(self.manifest, expected_ship=self.root.name)
            state = self.state
            if (
                state.get("class") != VIEW_CLASS
                or state.get("schema_version") != VIEW_SCHEMA_VERSION
                or state.get("view_ship") != self.ship
            ):
                raise DiagramViewError("view.json does not identify this Diagram.View")
            self.configuration
            self.scopes
        except DiagramError as exc:
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
                    for raw_finding in _array(
                        line.get("materialization_findings", []),
                        field="materialization_findings",
                    ):
                        retained = _object(raw_finding, field="Finding")
                        findings.append(
                            Finding(
                                str(retained.get("code", "diagram-view-materialization-poi")),
                                f"view.blocks[{index}].disclosure.lines[{line_index}]",
                                str(retained.get("message", "View materialization POI.")),
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
        lines = [f"# Diagram.View `{self.ship}`", ""]
        if self.about:
            lines.extend(("## About", "", "```json", json.dumps(self.about, indent=2, ensure_ascii=False), "```", ""))
        for value in _array(state.get("blocks"), field="View.blocks"):
            block = _object(value, field="View.Block")
            label = _string(block.get("label"), field="View.Block.label")
            block_type = block.get("block_type") or "Diagram.Block"
            lines.append(f"## {label}")
            lines.append("")
            lines.append(
                f"`{str(block_type)}` · `{str(block['block_ship'])[:12]}` · "
                f"{block.get('disclosure_name', DISCLOSURE_LEVELS[int(block['disclosure_level'])])}"
            )
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
                line_type = item.get("line_type") or "Diagram.Line"
                for edition in _array(item.get("editions", []), field="editions"):
                    wording = _object(edition, field="edition")
                    lines.extend(("", f"- [{line_type}] {wording.get('text', '')}"))
                if "support" in item:
                    lines.append(
                        f"  - Support: {json.dumps(item['support'], ensure_ascii=False)}"
                    )
                if "support_content" in item:
                    lines.append(
                        f"  - Support.Content: {json.dumps(item['support_content'], ensure_ascii=False)}"
                    )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


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
                "class": VIEW_REPOSITORY_CLASS,
                "schema_version": VIEW_SCHEMA_VERSION,
            },
        )
        _commit(resolved, (Path(VIEW_REPOSITORY_FILENAME),), "diagram(view): initialize repository")
        return cls.open(resolved)

    @classmethod
    def open(cls, root: Path | None = None) -> DiagramViewRepository:
        resolved = (root or default_diagram_views_root()).expanduser().resolve()
        if not (resolved / ".git").is_dir():
            raise DiagramViewError(f"Diagram.View repository is not initialized: {resolved}")
        definition = _read_json(resolved / VIEW_REPOSITORY_FILENAME)
        if definition != {
            "class": VIEW_REPOSITORY_CLASS,
            "schema_version": VIEW_SCHEMA_VERSION,
        }:
            raise DiagramViewError(f"Unsupported Diagram.View repository: {resolved}")
        return cls(resolved)

    def views(self) -> tuple[DiagramView, ...]:
        return tuple(
            DiagramView(path)
            for path in sorted(self.root.iterdir())
            if path.is_dir() and (path / "manifest.json").is_file()
        )

    def view(self, selector: str) -> DiagramView:
        exact = self.root / selector
        if exact.is_dir():
            return DiagramView(exact)
        matches = tuple(item for item in self.views() if item.ship.startswith(selector))
        if len(matches) != 1:
            raise DiagramViewError(f"Diagram.View does not resolve uniquely: {selector}")
        return matches[0]

    def create_view(
        self,
        diagram: Diagram,
        *,
        model_ships: Iterable[str] = (),
        block_ships: Iterable[str] = (),
        about: Mapping[str, Any] | None = None,
        configuration: DiagramViewConfiguration | None = None,
        evidence: ChatlasEvidence | None = None,
    ) -> DiagramViewMutation:
        scopes = _resolve_scopes(diagram, model_ships, block_ships)
        if not scopes:
            raise DiagramViewError("Diagram.View requires at least one Model or Block scope")
        ship = str(uuid4())
        root = self.root / ship
        root.mkdir()
        config = configuration or DiagramViewConfiguration()
        atomic_write_json(
            root / "manifest.json",
            {
                "id": str(uuid4()),
                "type": VIEW_MANIFEST_TYPE,
                "schema_version": VIEW_SCHEMA_VERSION,
                "view_ship": ship,
            },
            ensure_ascii=False,
        )
        atomic_write_json(root / "about.json", dict(about or {}), ensure_ascii=False)
        atomic_write_json(root / "config.json", config.to_dict(), ensure_ascii=False)
        state = _materialize(
            diagram,
            scopes,
            config,
            previous=None,
            evidence=evidence,
        )
        state["view_ship"] = ship
        atomic_write_json(root / "view.json", state, ensure_ascii=False)
        paths = tuple(path.relative_to(self.root) for path in sorted(root.iterdir()))
        commit = _commit(self.root, paths, f"diagram(view): create {ship}")
        view = DiagramView(root)
        return DiagramViewMutation(
            view,
            (DiagramViewChange("add", ship, f"{len(state['blocks'])} scoped Blocks"),),
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
        target = _one_block(_array(state.get("blocks"), field="View.blocks"), block_ship)
        _, projected_block = _resolve_block(diagram, block_ship)
        if line_ship not in {line.ship for line in projected_block.lines}:
            raise DiagramViewError(
                f"Line {line_ship} does not belong to View Block {block_ship}"
            )
        selection = list(
            _array(target.get("selected_line_ships", []), field="selected_line_ships")
        )
        if selected and line_ship not in selection:
            selection.append(line_ship)
            operation = "add"
        elif not selected and line_ship in selection:
            selection.remove(line_ship)
            operation = "remove"
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
        change = DiagramViewChange(operation, line_ship, f"Block {block_ship[:12]}")
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
) -> tuple[DiagramViewScope, ...]:
    scopes: list[DiagramViewScope] = []
    for ship in model_ships:
        model = diagram.model(ship)
        scopes.append(DiagramViewScope("Diagram.Model", model.namespace.id, model.ship))
    for ship in block_ships:
        model, _ = _resolve_block(diagram, ship)
        scopes.append(
            DiagramViewScope("Diagram.Block", model.namespace.id, model.ship, ship)
        )
    return tuple(dict.fromkeys(scopes))


def _resolve_block(diagram: Diagram, block_ship: str) -> tuple[DiagramModel, DiagramBlock]:
    matches: list[tuple[DiagramModel, DiagramBlock]] = []
    for model in diagram.models():
        try:
            matches.append((model, model.project().block(block_ship)))
        except DiagramError:
            pass
    if len(matches) != 1:
        raise DiagramViewError(f"Diagram Block does not resolve uniquely: {block_ship}")
    return matches[0]


def _materialize(
    diagram: Diagram,
    scopes: Iterable[DiagramViewScope],
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
            if scope.kind == "Diagram.Model"
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
            prior_blocks[(str(item.get("namespace_id")), str(item.get("block_ship")))] = item

    blocks: list[JsonObject] = []
    for identity, (model, block) in unique.items():
        prior = prior_blocks.get(identity)
        ranked = _rank_lines(diagram, model, block, evidence=evidence)
        selected = (
            [str(item) for item in _array(prior.get("selected_line_ships", []), field="selected_line_ships")]
            if prior is not None
            else [line.ship for line in ranked[: configuration.bootstrap_visible_lines]]
        )
        valid_ships = {line.ship for line in block.lines}
        selected_set = {ship for ship in selected if ship in valid_ships}
        selected = [line.ship for line in block.lines if line.ship in selected_set]
        level = int(prior.get("disclosure_level", 1 if selected else 0)) if prior else (1 if selected else 0)
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

    namespace_ids = tuple(dict.fromkeys(model.namespace.id for model, _ in unique.values()))
    return {
        "class": VIEW_CLASS,
        "schema_version": VIEW_SCHEMA_VERSION,
        "view_ship": previous.get("view_ship") if previous else None,
        "source_editions": {
            namespace_id: _git(diagram.namespace(namespace_id).root, "rev-parse", "HEAD")
            for namespace_id in namespace_ids
        },
        "scope": [item.to_dict() for item in scopes],
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
    for line in block.lines:
        support_members += _support_count(line)
        if _is_reviewed(diagram, model, line, evidence=evidence):
            reviewed += 1
        if level >= 1 and line.ship in selected_set:
            rendered_lines.append(_line_entry(line, level=level, evidence=evidence))
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
) -> JsonObject:
    editions: list[JsonObject] = []
    support: list[JsonObject] = []
    support_content: list[JsonObject] = []
    for item in line.editions:
        annotation = item.annotation
        editions.append({"annotation_id": annotation.id, "text": item.text})
    if level >= 2:
        for typed in line.annotations:
            if isinstance(typed, UserTouchedAnnotation):
                support.append(
                    {
                        "annotation_id": typed.id,
                        "producer": typed.producer.to_dict(),
                        "members": typed.support.to_list(),
                    }
                )
    if level >= 3 and evidence is not None:
        for typed in line.annotations:
            if isinstance(typed, UserTouchedAnnotation):
                try:
                    members = typed.render_support(evidence)
                except DiagramError as exc:
                    support_content.append(
                        {
                            "annotation_id": typed.id,
                            "members": [],
                            "finding": Finding(
                                "diagram-view-deep-support-unresolved",
                                f"annotation.{typed.id}.support",
                                str(exc),
                            ).to_dict(),
                        }
                    )
                else:
                    support_content.append(
                        {"annotation_id": typed.id, "members": members}
                    )
    result: JsonObject = {
        "line_ship": line.ship,
        "line_type": line.object_type,
        "editions": editions,
        "stats": {
            "edition_count": len(editions),
            "support_member_count": _support_count(line),
            "finding_count": len(line.findings),
        },
    }
    if level >= 2:
        result["support"] = support
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
            result["materialization_findings"] = [
                item["finding"]
                for item in support_content
                if isinstance(item.get("finding"), dict)
            ]
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
    roots = {
        (
            member.root.session_identity,
            member.root.turn_address,
            member.root.turn_hash,
        )
        for annotation in line.annotations
        if isinstance(annotation, UserTouchedAnnotation)
        for member in annotation.support.members
    }
    return len(roots)


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
        changes.append(DiagramViewChange("add", identity[1], str(new[identity].get("label"))))
    for identity in old.keys() - new.keys():
        changes.append(DiagramViewChange("remove", identity[1], str(old[identity].get("label"))))
    for identity in new.keys() & old.keys():
        if new[identity] != old[identity]:
            changes.append(DiagramViewChange("change", identity[1], str(new[identity].get("label"))))
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
        if not isinstance(item, dict) or not all(
            isinstance(key, str) for key in item
        ):
            raise DiagramViewError("View.Block must be a JSON object")
        if item.get("block_ship") == block_ship:
            matches.append(item)
    if len(matches) != 1:
        raise DiagramViewError(f"View Block does not resolve uniquely: {block_ship}")
    return matches[0]


def _validate_manifest(data: Mapping[str, Any], *, expected_ship: str) -> None:
    if (
        data.get("type") != VIEW_MANIFEST_TYPE
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
    "DiagramViewScope",
    "VIEW_CLASS",
    "VIEW_MANIFEST_TYPE",
    "default_diagram_views_root",
]
