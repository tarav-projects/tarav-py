"""One mutable context passed through class, instance and external hooks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from tarav.l0.kernel import TaravClass, TaravObject, TaravType, TypeShip, WorkflowShip, entity


CONTEXT_WORKFLOW_SHIP = WorkflowShip("ae6fb02b-b82f-4f64-82e8-67f28a76d179")

Subject = TaravType | type[TaravType]
Value = Subject | str | int | float | bool
Triple = tuple[Subject, str, Value]


@dataclass(frozen=True, slots=True)
class ContextHookRun:
    """Observed execution of one stage entry point, including any failure."""

    stage: Literal["class", "instance", "external"]
    name: str
    elapsed_seconds: float
    before: int
    after: int
    error: str | None = None


class ObjectContext(TaravObject):
    """The complete mutable result of constructing one object's context.

    Hooks share this object. ``hints`` is opaque contributor-owned data;
    ``runs`` describes stage entry points, not each call along a super chain.
    The result is runtime data; no persistence or replay is implied.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b7a3e13f-422d-402a-8e2e-c912f6408b06"),
                          name="Tarav.Context.Object", workflow=CONTEXT_WORKFLOW_SHIP)

    def __init__(self, subject: TaravType, *, options: Mapping[str, object] | None = None) -> None:
        super().__init__()
        if not isinstance(subject, TaravType):
            raise TypeError("An ObjectContext subject must be a Tarav instance")
        self.subject = subject
        self.triplets: list[Triple] = []
        self.options = dict(options) if options is not None else {}
        self.hints: dict[str, object] = {}
        self.runs: list[ContextHookRun] = []
        self.status: Literal["building", "completed", "failed"] = "building"


class ContextBuildError(RuntimeError):
    """A failed hook, retaining its partial context for inspection."""

    def __init__(self, context: ObjectContext, name: str, cause: Exception) -> None:
        self.context = context
        self.cause = cause
        super().__init__(f"Context hook {name!r} failed: {type(cause).__name__}: {cause}")


class ContextHook(ABC):
    """An external contributor, with dependencies supplied by its constructor.

    The registered instance is reused across builds. Each hook decides
    whether the current subject concerns it and may simply return unchanged.
    """

    @abstractmethod
    def run(self, cxt: ObjectContext) -> None:
        """Inspect the subject and contribute to this shared context."""


class ContextBuilder(TaravType):
    """Build contexts with an ordered, runtime-local external hook registry."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5da01b71-2c7e-4659-8475-3f0c0cde33d6"),
                          name="Tarav.Context.Builder", workflow=CONTEXT_WORKFLOW_SHIP)

    def __init__(self) -> None:
        self._hooks: dict[str, ContextHook] = {}

    def register(self, name: str, hook: ContextHook) -> None:
        """Append an external contributor; names cannot silently replace hooks."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A Context hook needs a nonempty name")
        if not isinstance(hook, ContextHook):
            raise TypeError("A Context hook must be a ContextHook instance")
        if name in self._hooks:
            raise KeyError(f"Context hook {name!r} is already registered")
        self._hooks[name] = hook

    def unregister(self, name: str) -> None:
        del self._hooks[name]

    def build(self, subject: Subject, *, options: Mapping[str, object] | None = None) -> ObjectContext:
        """Run class → instance → external hooks with the same context."""
        if isinstance(subject, type):
            subject = entity(subject)
        cxt = ObjectContext(subject, options=options)
        external = tuple(self._hooks.items())
        namespace = subject.context
        self._run(cxt, "class", "_class_context_hook", namespace._class_context_hook)
        self._run(cxt, "instance", "_obj_context_hook", namespace._obj_context_hook)
        for name, hook in external:
            self._run(cxt, "external", name, hook.run)
        cxt.status = "completed"
        return cxt

    @staticmethod
    def _run(cxt: ObjectContext, stage, name: str, hook: Callable[[ObjectContext], None]) -> None:
        before, start, error = len(cxt.triplets), perf_counter(), None
        try:
            hook(cxt)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            cxt.status = "failed"
            raise ContextBuildError(cxt, name, exc) from exc
        finally:
            cxt.runs.append(ContextHookRun(stage, name, perf_counter() - start,
                                           before, len(cxt.triplets), error))
