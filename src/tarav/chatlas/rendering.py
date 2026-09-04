"""Named renderers for structured Chatlas Query findings."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from tarav.chatlas.query import ChatlasQueryResult


JsonObject = dict[str, Any]
DEFAULT_CHATLAS_RENDERER = "Chatlas.Query.Default.Renderer"
RenderOptions = Mapping[str, str]
RenderHandler = Callable[[ChatlasQueryResult, RenderOptions], str]


class ChatlasRenderError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ChatlasRenderer:
    name: str
    media_type: str
    description: str
    handler: RenderHandler

    def __post_init__(self) -> None:
        if not self.name:
            raise ChatlasRenderError("Chatlas Renderer name must not be empty")
        if not self.media_type:
            raise ChatlasRenderError("Chatlas Renderer media type must not be empty")

    def render(
        self,
        result: ChatlasQueryResult,
        *,
        options: RenderOptions | None = None,
    ) -> ChatlasRenderResult:
        content = self.handler(result, options or {})
        if not isinstance(content, str):
            raise ChatlasRenderError(
                f"Chatlas Renderer {self.name} did not return a string"
            )
        return ChatlasRenderResult(self, result, content)


@dataclass(frozen=True, slots=True)
class ChatlasRenderResult:
    renderer: ChatlasRenderer
    query_result: ChatlasQueryResult
    content: str

    @property
    def media_type(self) -> str:
        return self.renderer.media_type

    def to_dict(self) -> JsonObject:
        return {
            "status": "ok",
            "renderer": self.renderer.name,
            "media_type": self.renderer.media_type,
            "content": self.content,
            "query_result": self.query_result.to_dict(),
        }


@dataclass(slots=True)
class ChatlasRendererRegistry:
    _renderers: dict[str, ChatlasRenderer] = field(default_factory=dict)

    def register(self, value: ChatlasRenderer) -> None:
        if value.name in self._renderers:
            raise ChatlasRenderError(
                f"Chatlas Renderer is already registered: {value.name}"
            )
        self._renderers[value.name] = value

    def renderer(self, name: str) -> ChatlasRenderer:
        try:
            return self._renderers[name]
        except KeyError as exc:
            raise ChatlasRenderError(f"Chatlas Renderer not found: {name}") from exc

    def renderers(self) -> tuple[ChatlasRenderer, ...]:
        return tuple(self._renderers.values())


def _default_renderer(result: ChatlasQueryResult, options: RenderOptions) -> str:
    if options:
        names = ", ".join(sorted(options))
        raise ChatlasRenderError(
            f"{DEFAULT_CHATLAS_RENDERER} accepts no Renderer options: {names}"
        )
    rendered: list[str] = []
    for finding in result.findings:
        side = finding.turn.get("side")
        if side not in {"user", "agent"}:
            raise ChatlasRenderError("Chat.Turn has no renderable side")
        title = "User" if side == "user" else "Agent"
        sections = [f"## {title} Turn `{finding.prefix}`"]
        for message in finding.messages:
            text = message.get("text")
            if not isinstance(text, str):
                raise ChatlasRenderError("Chat.Message has no renderable text")
            sections.append(text)
        rendered.append("\n\n".join(sections))
    return "\n\n".join(rendered)


_REGISTRY = ChatlasRendererRegistry()
_REGISTRY.register(
    ChatlasRenderer(
        DEFAULT_CHATLAS_RENDERER,
        "text/markdown",
        "Readable projection of resolved Chatlas Turn findings and their Messages.",
        _default_renderer,
    )
)


def register_renderer(value: ChatlasRenderer) -> None:
    _REGISTRY.register(value)


def renderer(name: str) -> ChatlasRenderer:
    return _REGISTRY.renderer(name)


def renderers() -> tuple[ChatlasRenderer, ...]:
    return _REGISTRY.renderers()


__all__ = [
    "ChatlasRenderer",
    "ChatlasRendererRegistry",
    "ChatlasRenderError",
    "ChatlasRenderResult",
    "DEFAULT_CHATLAS_RENDERER",
    "register_renderer",
    "renderer",
    "renderers",
]
