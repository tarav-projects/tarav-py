"""Typed configuration for explicit Python process execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
import sys

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip

from .workflow import PYTHON_WORKFLOW_SHIP


class PythonObject(TaravObject):
    """Base Record object owned by the Python Workflow."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("1cac978b-f418-461f-a678-ab85c9e7c3b2"),
            name="Tarav.Python.Object",
            workflow=PYTHON_WORKFLOW_SHIP,
        )


class RunnerConfiguration(PythonObject):
    """Resolved interpreter and process location consumed by the runner."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("24601388-2c16-469b-bbe3-cb3ea6dbb558"),
            name="Tarav.Python.RunnerConfiguration",
            workflow=PYTHON_WORKFLOW_SHIP,
        )

    class RecordInterface(PythonObject.RecordInterface):
        interpreter: str
        cwd: str | None = None

    def __init__(self, *, interpreter: Path | str, cwd: Path | str | None = None):
        super().__init__()
        # Preserve a virtual environment's interpreter path. Resolving its
        # symlink would select the base executable and lose that environment.
        self.interpreter = Path(interpreter).expanduser().absolute()
        self.cwd = None if cwd is None else Path(cwd).expanduser().resolve()

    @classmethod
    def _from_record(cls, record_data):
        return cls(interpreter=record_data.interpreter, cwd=record_data.cwd)

    def _to_record(self):
        return {
            **super()._to_record(),
            "interpreter": str(self.interpreter),
            "cwd": None if self.cwd is None else str(self.cwd),
        }

    @classmethod
    def record_example(cls):
        return cls(interpreter=sys.executable).to_record()


class RunnerConfigurator(PythonObject, ABC):
    """Behavioral contract for selecting one Python runner configuration."""
    # tarav.breadcrumb 8930a4c61accc47dc1236cde58f7616d34c0c375ce53e5678289a4cb65f0b423

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("d407ba38-19d9-4333-a1ea-9279f7867333"),
            name="Tarav.Python.RunnerConfigurator",
            workflow=PYTHON_WORKFLOW_SHIP,
        )

    @abstractmethod
    def configure(self) -> RunnerConfiguration:
        raise NotImplementedError


class CurrentRunnerConfigurator(RunnerConfigurator):
    """Select the interpreter and cwd of the current Tarav process."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("06db8609-3cc4-4325-9883-6a82eee021fd"),
            name="Tarav.Python.CurrentRunnerConfigurator",
            workflow=PYTHON_WORKFLOW_SHIP,
        )

    def __init__(self) -> None:
        super().__init__()

    def configure(self) -> RunnerConfiguration:
        return RunnerConfiguration(interpreter=sys.executable)


PYTHON_RECORD_TYPES = (
    RunnerConfiguration,
    CurrentRunnerConfigurator,
)


__all__ = [
    "CurrentRunnerConfigurator",
    "PYTHON_RECORD_TYPES",
    "PythonObject",
    "RunnerConfiguration",
    "RunnerConfigurator",
]
