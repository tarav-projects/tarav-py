# $kw: ^skw-surface-model --from Skw.Backend --from Floor.Model --note [DF] common carrier model consumed by shared Skillware parsing ^c20260812-0u
"""The common Skillware carrier model produced by native-surface adapters."""

from __future__ import annotations

from dataclasses import dataclass

from tarav.surfaces.model import SourceDiagnostic, SourceSpan


@dataclass(frozen=True)
class SkwSurfaceAnnotation:
    """A host annotation classified for shared downstream policy."""

    text: str
    span: SourceSpan
    classification: str
    external_kind: str | None = None


@dataclass(frozen=True)
class SkwSurfaceLine:
    """One source line with host syntax reduced to Skillware carrier facts."""

    text: str
    open_content: str | None = None
    close_content: str | None = None
    flag_content: str | None = None
    fence: bool = False
    boundary_name: str | None = None


@dataclass(frozen=True)
class SkwSurfaceModel:
    """A host-independent input to the shared Skillware parser."""

    carrier: str
    lines: tuple[SkwSurfaceLine, ...]
    boundary_label: str = "boundary"
    annotations: tuple[SkwSurfaceAnnotation, ...] = ()
    diagnostics: tuple[SourceDiagnostic, ...] = ()


__all__ = ["SkwSurfaceAnnotation", "SkwSurfaceLine", "SkwSurfaceModel"]
