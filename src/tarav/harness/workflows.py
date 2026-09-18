"""Explicit trusted workflow registration, usable directly from Python.

This module does not execute an action graph. Workflows expose ordinary Python
operations. A configured entry point registers code; Record data never does.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

from .types import TaravRecord, TypeRegistry


class Workflow:
    name: str
    record_types: tuple[type[TaravRecord], ...] = ()

    def register(self, registry: WorkflowRegistry) -> None:
        """Register this workflow's Record authorities."""
        for record_type in self.record_types:
            registry.records.register(record_type)

    def provider(self, root: Path, records: TypeRegistry[TaravRecord]):
        raise NotImplementedError(f"{self.name} does not provide navigation")


class WorkflowRegistry:
    def __init__(self, records: TypeRegistry[TaravRecord] | None = None) -> None:
        self.records = records if records is not None else TypeRegistry(TaravRecord)
        self.workflows: dict[str, Workflow] = {}

    def register(self, workflow: Workflow) -> None:
        if not isinstance(workflow, Workflow):
            raise TypeError("Expected a Workflow instance")
        if (
            not isinstance(workflow.name, str)
            or not workflow.name
            or workflow.name in self.workflows
        ):
            raise ValueError(f"Invalid or duplicate workflow: {workflow.name}")
        # Register into a trial registry so conflicts cannot half-register types.
        trial = self._trial()
        workflow.register(trial)
        if workflow.name in trial.workflows:
            raise ValueError(f"Workflow registered its own name: {workflow.name}")
        trial.workflows[workflow.name] = workflow
        self._accept(trial)

    def _trial(self) -> WorkflowRegistry:
        trial = WorkflowRegistry(TypeRegistry(TaravRecord, self.records.record_types))
        trial.workflows.update(self.workflows)
        return trial

    def _accept(self, trial: WorkflowRegistry) -> None:
        # Preserve registry identity: mounted providers may already hold it.
        existing = set(self.records.record_types)
        for record_type in trial.records.record_types:
            if record_type not in existing:
                self.records.register(record_type)
        self.workflows.update(trial.workflows)

    def load(self, path: str | Path, *, entrypoint: str = "register") -> None:
        """Execute an explicitly selected trusted file's registration function."""
        source = Path(path).expanduser().resolve(strict=True)
        name = "_tarav_workflow_" + hashlib.sha256(str(source).encode()).hexdigest()
        spec = importlib.util.spec_from_file_location(name, source)
        if spec is None or spec.loader is None:
            raise ValueError(f"Cannot load workflow code: {source}")
        module = importlib.util.module_from_spec(spec)
        # Python's normal module identity is required by dataclasses and imports.
        previous = sys.modules.get(name)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
            callback = getattr(module, entrypoint)
            trial = self._trial()
            callback(trial)
            self._accept(trial)
        except Exception:
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
            raise
