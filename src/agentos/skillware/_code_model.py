# $kw: ^skw-code-model --from Skw.Backend --from POI.Linter --note [DF] language-neutral floor model and backend contract for configured code surfaces ^c20260811-66u
"""Language-neutral model and backend protocol for Skw code surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from .model import SkwSource
from .poi import SkillwarePOIInstance


@dataclass(frozen=True)
class SourceComment:
    text: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass(frozen=True)
class CodeSurfaceModel:
    annotations: SkwSource
    comments: tuple[SourceComment, ...]
    scanner_error: str | None = None


class CodeLanguageBackend(Protocol):
    name: str
    suffixes: tuple[str, ...]

    def model(self, text: str) -> CodeSurfaceModel: ...


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
