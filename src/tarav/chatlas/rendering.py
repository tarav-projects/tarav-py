"""Named renderers for structured Chatlas Query findings."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import re
from typing import Any

from tarav.chatlas.query import ChatlasQueryResult


JsonObject = dict[str, Any]
DEFAULT_CHATLAS_RENDERER = "Chatlas.Query.Default.Renderer"
INLINED_CAPTURE_MARKDOWN_RENDERER = "Inlined.Capture.Markdown.Reference.Renderer"
RenderOptions = Mapping[str, str]
RenderHandler = Callable[[ChatlasQueryResult, RenderOptions], str]
_FULL_HASH = re.compile(r"[0-9a-f]{64}")
_SESSION_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


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


def _inlined_capture_markdown_renderer(
    result: ChatlasQueryResult,
    options: RenderOptions,
) -> str:
    unknown = set(options) - {"session-alias"}
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ChatlasRenderError(
            f"{INLINED_CAPTURE_MARKDOWN_RENDERER} does not accept options: {names}"
        )
    alias = options.get("session-alias")
    if alias is None:
        raise ChatlasRenderError(
            f"{INLINED_CAPTURE_MARKDOWN_RENDERER} requires session-alias"
        )
    if _SESSION_ALIAS.fullmatch(alias) is None or "--" in alias:
        raise ChatlasRenderError("Markdown session alias is not safe to embed")

    references: list[str] = []
    for finding in result.findings:
        if finding.turn.get("side") != "user":
            raise ChatlasRenderError(
                "Inlined.Capture references must resolve to User Turns"
            )
        turn_hash = finding.turn.get("turn_hash")
        if not isinstance(turn_hash, str) or _FULL_HASH.fullmatch(turn_hash) is None:
            raise ChatlasRenderError("Chat.Turn has no renderable hash")
        prefix_length = max(16, len(finding.prefix))
        references.append(
            f"<!-- tarav.context {alias}:{turn_hash[:prefix_length]} -->"
        )
    return "\n".join(references)


_REGISTRY = ChatlasRendererRegistry()
_REGISTRY.register(
    ChatlasRenderer(
        DEFAULT_CHATLAS_RENDERER,
        "text/markdown",
        "Readable projection of resolved Chatlas Turn findings and their Messages.",
        _default_renderer,
    )
)
_REGISTRY.register(
    ChatlasRenderer(
        INLINED_CAPTURE_MARKDOWN_RENDERER,
        "text/markdown",
        "Markdown references from a Product.Surface to selected User Turns.",
        _inlined_capture_markdown_renderer,
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
    "INLINED_CAPTURE_MARKDOWN_RENDERER",
    "register_renderer",
    "renderer",
    "renderers",
]
