# $kw: ^skw-code-model --from Skw.Backend --from POI.Linter --note [DF] language-neutral floor model and backend contract for configured code surfaces ^c20260811-66u
"""Language-neutral model and backend protocol for Skw code surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from .model import SkwSource
from .poi import SkillwarePOIInstance
from .surface_model import SkwSurfaceModel


@dataclass(frozen=True)
class CodeSurfaceModel:
    surface: SkwSurfaceModel
    annotations: SkwSource


class CodeLanguageBackend(Protocol):
    name: str
    suffixes: tuple[str, ...]

    def model(self, text: str) -> CodeSurfaceModel: ...


class CodeDependencyResolver(Protocol):
    def resolve(self, names: set[str]) -> dict[str, str]: ...

    def collisions(self, names: set[str]) -> dict[str, list[Path]]: ...


class CodeBackendRegistry:
    def __init__(self, backends: tuple[CodeLanguageBackend, ...]) -> None:
        entries = {backend.name: backend for backend in backends}
        if len(entries) != len(backends):
            raise ValueError("duplicate code language backend name")
        self._entries = MappingProxyType(entries)

    def get(self, language: str) -> CodeLanguageBackend | None:
        return self._entries.get(language)

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))


@dataclass(frozen=True)
class CodeSurfaceTarget:
    language: str
    path: Path


@dataclass(frozen=True)
class CodeCheckReport:
    targets: tuple[CodeSurfaceTarget, ...]
    pois: tuple[SkillwarePOIInstance, ...]


@dataclass(frozen=True)
class CodeBlessRecord:
    target: Path
    key: str | None
    poi_hash: str
