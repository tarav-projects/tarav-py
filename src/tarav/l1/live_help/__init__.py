"""Small, demand-driven help sections for agent-facing subjects."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
import shlex

from tarav.l0.kernel import TaravClass, TaravType, TypeShip, WorkflowShip
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l1.usage import UsageRegistry, UsageTrace


LIVE_HELP_WORKFLOW_SHIP = WorkflowShip("259a5d90-44a9-4dad-a8fa-8fcb704ed6c1")


# tarav.breadcrumb a81b81424414448e696f428f87a1cf998e05674cc337d204ea17582132908cfe
class LiveHelpWorkflow(TaravWorkflow):
    workflow_name = "live-help"
    constitution = "Offer mechanically sourced code and recent-usage leads when help is requested."

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("e7cde2f0-d86c-484a-aab2-e1be7418a7cd"),
            name="Tarav.Workflow.LiveHelp",
            workflow=LIVE_HELP_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls) -> WorkflowShip:
        return LIVE_HELP_WORKFLOW_SHIP


class LiveHelpProvider(TaravType):
    """A subject that can supply leads for a reactive help section."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("1ce34661-bf70-47eb-a792-357977218186"),
            name="Tarav.LiveHelp.Provider",
            workflow=LIVE_HELP_WORKFLOW_SHIP,
        )

    @property
    def help_subject(self) -> str:
        raise NotImplementedError

    @property
    def help_workflow(self) -> type[TaravWorkflow]:
        raise NotImplementedError

    @property
    def help_trace_type(self) -> type[UsageTrace]:
        raise NotImplementedError

    @property
    def help_heading(self) -> str:
        raise NotImplementedError

    @property
    def source_location(self) -> tuple[Path, int] | None:
        raise NotImplementedError

    def help_hints(self) -> Sequence[str]:
        return ()


class LiveHelpArgumentParser(argparse.ArgumentParser):
    """Argparse's built-in help action calls format_help before it exits."""

    live_help: Callable[[], str] | None = None

    def format_help(self) -> str:
        base = super().format_help()
        extra = self.live_help() if self.live_help is not None else ""
        return base + ("\n" + extra.rstrip() + "\n" if extra else "")


def _git_history_hint(path: Path, line: int) -> str | None:
    for root in (path.parent, *path.parents):
        if not (root / ".git").exists():
            continue
        try:
            relative = path.relative_to(root)
            end = min(line + 20, len(path.read_text(encoding="utf-8").splitlines()))
        except ValueError:
            return None
        except OSError:
            return None
        span = f"-L{line},{max(line, end)}:{relative.as_posix()}"
        return "git -C " + shlex.quote(str(root)) + " log -5 " + shlex.quote(span)
    return None


def render_live_help(
    provider: LiveHelpProvider,
    registry: UsageRegistry,
    *,
    recent_limit: int = 3,
) -> str:
    """Render leads; missing history stays an honest absence."""
    lines = [f"{provider.help_heading}:  {provider.help_subject}"]
    source = provider.source_location
    if source is not None:
        path, line = source
        lines.append(f"source:   {path}:{line}")
    try:
        # tarav.breadcrumb 5217c2e01194ba4df73a01a761799164d5926d2a4e12423d2d4c1b6dee0abe18
        uses = registry.query(
            workflow=provider.help_workflow,
            subject=provider.help_subject,
            trace_type=provider.help_trace_type,
        )
    except OSError:
        uses = ()
    lines.append(f"recent uses ({min(recent_limit, len(uses))} of {len(uses)}):")
    for use in uses[:recent_limit]:
        lines.extend(provider.help_trace_type.render_trace(use))
    if source is not None:
        hint = _git_history_hint(*source)
        if hint is not None:
            lines.append(f"history:  {hint}")
    lines.extend(provider.help_hints())
    return "\n".join(lines)


__all__ = ["LiveHelpWorkflow", "LiveHelpProvider", "LiveHelpArgumentParser", "render_live_help"]
