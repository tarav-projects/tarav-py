"""Singleton Workflow entities and their implementation-class directory."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
from threading import RLock
from typing import ClassVar

from .identity import KERNEL_WORKFLOW_SHIP, TYPE_WORKFLOW_SHIP, TypeShip, WorkflowShip
from .records import (
    TaravClass,
    TaravEntity,
)

TARAV_WORKFLOW_SHIP = WorkflowShip("7873fdd4-27d3-41e7-a6b4-92acfe4ceaa7")


class WorkflowDeclarationError(TypeError):
    """A Workflow class does not declare its required identities."""


class TaravWorkflow(TaravEntity):
    """One workflow entity per concrete implementation class.

    Class identity belongs to class_entity(); workflow identity is independently
    declared by _workflow_id(). Runtime-local configuration belongs in services.
    """

    _instances: ClassVar[dict[type, TaravWorkflow]] = {}
    _instance_lock: ClassVar[RLock] = RLock()

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('f67713b1-fa70-4f41-9d2e-de512ce7c2ce'),
            name='Tarav.Workflow',
            workflow=TARAV_WORKFLOW_SHIP,
        )

    workflow_name: ClassVar[str] = "tarav"
    constitution: ClassVar[str] = "Contain and organize Tarav workflows."

    @classmethod
    def _workflow_id(cls) -> WorkflowShip:
        return TARAV_WORKFLOW_SHIP

    @property
    def workflow(self) -> TaravWorkflow | None:
        """Root has no parent; ordinary workflows default to the umbrella."""
        return None if type(self) is TaravWorkflow else TaravWorkflow()

    def __new__(cls):
        with TaravWorkflow._instance_lock:
            if cls not in TaravWorkflow._instances:
                identity = cls._workflow_id()
                if not isinstance(identity, WorkflowShip):
                    raise TypeError("Workflow identity must be a WorkflowShip")
                instance = super().__new__(cls)
                TaravEntity.__init__(instance, identity)
                TaravWorkflow._instances[cls] = instance
            return TaravWorkflow._instances[cls]

    def __init__(self) -> None:
        # Python calls __init__ on every construction, including cached returns.
        pass

    @classmethod
    def _from_record(cls, record_data):
        if record_data.id != cls._workflow_id():
            raise ValueError("Record does not identify this workflow")
        return cls()

    @classmethod
    def provider(cls, root: Path, records: object):
        raise NotImplementedError(
            f"{cls.workflow_name} does not provide navigation"
        )

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        workflow_name = cls.__dict__.get("workflow_name")
        if not isinstance(workflow_name, str) or not workflow_name:
            raise WorkflowDeclarationError(
                f"{cls.__name__} must declare a class-local workflow_name"
            )
        constitution = cls.__dict__.get("constitution")
        if not isinstance(constitution, str) or not constitution.strip():
            raise WorkflowDeclarationError(
                f"{cls.__name__} must declare a class-local constitution"
            )
        if not isinstance(cls.__dict__.get("_workflow_id"), classmethod):
            raise WorkflowDeclarationError(
                f"{cls.__name__} must declare a class-local _workflow_id()"
            )


class KernelWorkflow(TaravWorkflow):
    """Bootstrap Workflow owning Tarav's foundational Types and mechanics."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('216850ea-1f04-4ea7-8153-1e0101a55a1a'),
            name='Tarav.Workflow.Kernel',
            workflow=KERNEL_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return KERNEL_WORKFLOW_SHIP

    workflow_name = "kernel"
    constitution = (
        "Provide Tarav's foundational Types, identities, Records, and "
        "navigation mechanics for other Workflows."
    )


class TypeWorkflow(TaravWorkflow):
    """Own class representations and Python-derived type relationships."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("e77bd95f-1180-4908-a3c2-03775d383bc3"),
            name="Tarav.Workflow.Type",
            workflow=TYPE_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return TYPE_WORKFLOW_SHIP

    workflow_name = "type"
    constitution = (
        "Represent Tarav Python classes and expose their declared relationships "
        "without replacing Python's executable authority or represented ownership."
    )


class WorkflowRegistry:
    """Runtime directory from Workflow name or established Ship to its class."""

    def __init__(self) -> None:
        self.workflows: dict[str, type[TaravWorkflow]] = {}
        self._ships: dict[WorkflowShip, type[TaravWorkflow]] = {}

    def get(self, identity: str | WorkflowShip) -> type[TaravWorkflow]:
        """Return one registered Workflow class by name or exact Ship."""

        if isinstance(identity, WorkflowShip):
            return self._ships[identity]
        if isinstance(identity, str) and identity:
            return self.workflows[identity]
        raise TypeError("Workflow identity must be a name or WorkflowShip")

    def register(self, workflow: type[TaravWorkflow]) -> None:
        if not isinstance(workflow, type) or not issubclass(workflow, TaravWorkflow):
            raise TypeError("Expected a TaravWorkflow class")
        name = workflow.workflow_name
        ship = workflow().id
        if not isinstance(ship, WorkflowShip):
            raise TypeError("Workflow Entity id must be a WorkflowShip")
        if name in self.workflows:
            raise ValueError(f"Duplicate Workflow name: {name}")
        if ship in self._ships:
            raise ValueError(f"Duplicate Workflow Ship: {ship}")
        self.workflows[name] = workflow
        self._ships[ship] = workflow

    def load(self, path: str | Path, *, entrypoint: str = "register") -> None:
        """Execute an explicitly selected trusted file's registration function."""

        source = Path(path).expanduser().resolve(strict=True)
        name = "_tarav_workflow_" + hashlib.sha256(str(source).encode()).hexdigest()
        spec = importlib.util.spec_from_file_location(name, source)
        if spec is None or spec.loader is None:
            raise ValueError(f"Cannot load workflow code: {source}")
        module = importlib.util.module_from_spec(spec)
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

    def _trial(self) -> WorkflowRegistry:
        trial = WorkflowRegistry()
        trial.workflows.update(self.workflows)
        trial._ships.update(self._ships)
        return trial

    def _accept(self, trial: WorkflowRegistry) -> None:
        self.workflows.update(trial.workflows)
        self._ships.update(trial._ships)
