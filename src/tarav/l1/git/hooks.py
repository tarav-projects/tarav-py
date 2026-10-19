"""Git hooks for Projects: Tarav handlers a Project's config selects.

A Project whose root is a Git repository names the handlers it uses in the
`git` section of its `.tarav/config.json`. Install writes one small script
per Git hook those handlers use into `.tarav/git-hooks/`, tracked with the
Project, and points `core.hooksPath` there. A script runs the chained hook,
if any, then `tarav git hook`, which runs the handlers in process. Hooks are
not a guarantee: a missing or failing Tarav warns and lets Git continue, and
the Project checks report what drifted. A handler may stop the Git operation
on purpose, to make whoever commits rethink; naming it in
`TARAV_GIT_HOOKS_OVERRULE` overrules the stop, and the handler records that.
"""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from tarav.l0._core.errors import CliError
from tarav.l0._core.git_repository import GitError, git_result, run_git
from tarav.l0.kernel import TaravClass, TaravObject, TypeShip
from tarav.l0.project import project_id
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite
from tarav.l1.actions.pois import BlessableResolution
from tarav.l1.project.config import ProjectConfig

from .workflow import GIT_WORKFLOW_SHIP

HOOKS_FOLDER = ".tarav/git-hooks"
ATTRIBUTES_FILE = ".gitattributes"
# Git hooks that receive data on standard input; their script passes it to both callees.
STDIN_HOOKS = frozenset({"post-rewrite", "pre-push", "reference-transaction"})
# The exit status of `tarav git hook` when a handler stopped the operation; no other stops Git.
REFUSED_EXIT = 75
OVERRULE_ENV_VAR = "TARAV_GIT_HOOKS_OVERRULE"
# tarav.breadcrumb f89d4fccd8dc
# The handlers a Project whose config names none uses; its checks report them until installed.
DEFAULT_HANDLERS = ("gitleaks",)


# tarav.breadcrumb f7391cbd2d28
class GitHooksConfig(BaseModel):
    """The handlers a Project uses, and a hooks folder whose same-named hooks run first."""

    model_config = ConfigDict(strict=True, extra="forbid")

    handlers: list[str] = []
    chain: str | None = None


class GitConfig(BaseModel):
    """The `git` section of a Project's config, owned by the Git workflow."""

    model_config = ConfigDict(strict=True, extra="forbid")

    hooks: GitHooksConfig | None = None


# tarav.breadcrumb 7336e756890d
class GitHookRefusal(Exception):
    """A handler stops the Git operation; its message says why and how to overrule it."""


@dataclass(frozen=True)
class GitHookCall:
    """One run of a Git hook: its name, Git's arguments, the repository and standard input.

    `overrule` names the handlers whose stops are overruled for this run.
    """

    hook: str
    arguments: tuple[str, ...]
    root: Path
    stdin: str = ""
    overrule: frozenset[str] = frozenset()

    def overrules(self, handler: str) -> bool:
        return handler in self.overrule or "all" in self.overrule


def overrule_from_environment() -> frozenset[str]:
    raw = os.environ.get(OVERRULE_ENV_VAR, "")
    return frozenset(name.strip() for name in raw.split(",") if name.strip())


class GitHookHandler(TaravObject):
    """Tarav code a Git hook runs. A subclass names itself, its hooks and what it needs."""

    name: str = ""
    hooks: frozenset[str] = frozenset()
    attributes: tuple[str, ...] = ()  # `.gitattributes` lines the handler needs

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5e0f2d8a-7c31-4b96-a4e2-9d1c6b3f8a70"),
                          name="Tarav.Git.Hooks.Handler", workflow=GIT_WORKFLOW_SHIP)

    def run(self, call: GitHookCall) -> None:
        raise NotImplementedError

    def check(self, project) -> Check | None:
        """The check that keeps what this handler maintains in the Project; None when none."""
        return None


_HANDLERS: dict[str, GitHookHandler] = {}


def register_git_hook_handler(handler: GitHookHandler) -> None:
    """Make a handler available to Projects under its name; the runtime does the registering."""
    if not isinstance(handler, GitHookHandler) or not handler.name or not handler.hooks:
        raise TypeError("A Git hook handler has a name and the hooks it uses")
    known = _HANDLERS.get(handler.name)
    if known is not None and type(known) is not type(handler):
        raise ValueError(f"Another handler is registered as {handler.name}")
    _HANDLERS[handler.name] = handler


def git_hook_handlers() -> dict[str, GitHookHandler]:
    return dict(_HANDLERS)


def hooks_config(root: Path) -> GitHooksConfig | None:
    """What the Project at ``root`` configures for its Git hooks; None when nothing."""
    git = ProjectConfig(root).section("git", GitConfig)
    return git.hooks if git is not None else None


def hook_script(hook: str, chain: str | None) -> str:
    """The script install writes for ``hook``; the check compares against it."""
    lines = ["#!/bin/sh",
             "# Tarav Git hook, written by `tarav git hooks install`. Do not edit.",
             f"hook={hook}"]
    reads_stdin = hook in STDIN_HOOKS
    if reads_stdin:
        lines.append("input=$(cat)")
    if chain is not None:
        feed = "printf '%s\\n' \"$input\" | " if reads_stdin else ""
        lines.append(f"chained='{chain}/{hook}'")
        lines.append(f'if [ -x "$chained" ]; then {feed}"$chained" "$@" || exit $?; fi')
    lines += ["n=$#",
              'for a do set -- "$@" "--arg=$a"; done',
              'shift "$n"',
              "if command -v tarav >/dev/null 2>&1; then"]
    call = 'tarav git hook --name "$hook" "$@"'
    if reads_stdin:
        call = f"printf '%s\\n' \"$input\" | {call}"
    lines += [f"  {call}",
              "  status=$?",
              f'  if [ "$status" -eq {REFUSED_EXIT} ]; then exit 1; fi',
              '  if [ "$status" -ne 0 ]; then echo "tarav: the $hook hook failed; Git continues" >&2; fi',
              "else",
              '  echo "tarav: not found on PATH; the Tarav $hook hook did nothing" >&2',
              "fi",
              "exit 0",
              ""]
    return "\n".join(lines)


def expected_scripts(config: GitHooksConfig) -> dict[str, str]:
    """Hook name to script, for every hook the configured handlers use."""
    handlers = git_hook_handlers()
    names = {hook for name in config.handlers if name in handlers for hook in handlers[name].hooks}
    return {hook: hook_script(hook, config.chain) for hook in sorted(names)}


def expected_attributes(config: GitHooksConfig) -> tuple[str, ...]:
    handlers = git_hook_handlers()
    lines = (line for name in config.handlers if name in handlers
             for line in handlers[name].attributes)
    return tuple(dict.fromkeys(lines))


def repository_root(path: Path) -> Path | None:
    """The root of the repository ``path`` is in; None outside one."""
    result = git_result(path, "rev-parse", "--show-toplevel")
    return Path(result.stdout.decode().strip()).resolve() if result.returncode == 0 else None


def install(root: Path | str, *, add: Sequence[str] = ()) -> GitHooksConfig:
    """Add ``add`` to the Project's handlers, then make the repository match its config."""
    root = Path(root).expanduser().resolve()
    if repository_root(root) != root:
        raise CliError(f"{root} is not the root of a Git repository")
    handlers = git_hook_handlers()
    unknown = [name for name in add if name not in handlers]
    if unknown:
        raise CliError(f"No Git hook handler is named {', '.join(unknown)}; "
                       f"known: {', '.join(sorted(handlers)) or 'none'}")
    project_config = ProjectConfig(root)
    git = project_config.section("git", GitConfig) or GitConfig()
    config = git.hooks or GitHooksConfig(handlers=list(DEFAULT_HANDLERS))
    config = config.model_copy(update={"handlers": list(dict.fromkeys([*config.handlers, *add]))})
    project_config.write_section("git", git.model_copy(update={"hooks": config}))

    folder = root / HOOKS_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    scripts = expected_scripts(config)
    for path in folder.iterdir():
        if path.name not in scripts:
            path.unlink()
    for hook, text in scripts.items():
        path = folder / hook
        path.write_text(text, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    run_git(root, "config", "core.hooksPath", HOOKS_FOLDER)

    attributes = root / ATTRIBUTES_FILE
    present = attributes.read_text(encoding="utf-8").splitlines() if attributes.exists() else []
    missing = [line for line in expected_attributes(config) if line not in present]
    if missing:
        text = "\n".join([*present, *missing]) + "\n"
        attributes.write_text(text, encoding="utf-8")
    return config


def dispatch(call: GitHookCall) -> tuple[list[str], list[str]]:
    """Run the configured handlers that use ``call.hook``; return warnings and refusals.

    A refusal is a handler stopping the operation on purpose; every other
    failure is only a warning.
    """
    try:
        config = hooks_config(call.root)
    except CliError as exc:
        return [str(exc)], []
    if config is None:
        return [f"{call.root} configures no Tarav Git hooks"], []
    warnings, refusals = [], []
    handlers = git_hook_handlers()
    for name in config.handlers:
        handler = handlers.get(name)
        if handler is None:
            warnings.append(f"No Git hook handler is named {name}")
        elif call.hook in handler.hooks:
            try:
                handler.run(call)
            except GitHookRefusal as exc:
                refusals.append(f"{name} stopped {call.hook}: {exc}")
            except (GitError, OSError, ValueError, RuntimeError) as exc:
                warnings.append(f"{name} failed in {call.hook}: {exc}")
    return warnings, refusals


# tarav.breadcrumb 98cfc9f168e7
def run_hook(hook: str, arguments: Sequence[str]) -> int:
    """The `tarav git hook` entry: one hook run in the current repository."""
    root = repository_root(Path.cwd())
    if root is None:
        print(f"tarav: {hook} ran outside a Git repository", file=sys.stderr)
        return 0
    stdin = sys.stdin.read() if hook in STDIN_HOOKS else ""
    warnings, refusals = dispatch(GitHookCall(hook, tuple(arguments), root, stdin,
                                              overrule_from_environment()))
    for message in (*warnings, *refusals):
        print(f"tarav: {message}", file=sys.stderr)
    return REFUSED_EXIT if refusals else 0


class GitHooksPOI(CheckPOI):
    """Family, never raised: a Project's Git hooks do not match its config."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c3a71e5f-08d4-4b2c-9f6a-e1b7d2c94a38"),
                          name="Tarav.Git.Hooks.POI", workflow=GIT_WORKFLOW_SHIP)


class HooksNotInstalled(GitHooksPOI):
    """The repository does not run the Project's hooks: `core.hooksPath` is elsewhere.

    A Project that wants no hooks blesses it.
    """

    action = "Tarav.Git.Hooks.NotInstalled.Resolution"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7b2e9c40-5d16-4f83-a0e7-3c8f1b6d2e59"),
                          name="Tarav.Git.Hooks.NotInstalled", workflow=GIT_WORKFLOW_SHIP)


class HooksNotInstalledResolution(BlessableResolution):
    """The action of HooksNotInstalled: a Project that wants no hooks blesses it."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("36eb6b87-0afe-4f70-a62c-20b76a8ebcd2"),
                          name="Tarav.Git.Hooks.NotInstalled.Resolution", workflow=GIT_WORKFLOW_SHIP)


class HookStale(GitHooksPOI):
    """A hook script is missing, differs from what install writes, or is not needed."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e9d40b17-6a2c-4e58-b3f1-8c07a5d2e6b4"),
                          name="Tarav.Git.Hooks.Stale", workflow=GIT_WORKFLOW_SHIP)


class UnknownHookHandler(GitHooksPOI):
    """The config names a handler this Tarav does not have."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1f6c8a3d-92e7-4b05-8d4a-b5e2c7f91036"),
                          name="Tarav.Git.Hooks.UnknownHandler", workflow=GIT_WORKFLOW_SHIP)


class HookAttributesMissing(GitHooksPOI):
    """`.gitattributes` lacks a line a configured handler needs."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a4e8d2f6-3b19-4c70-95e1-0d7f6b8c2a43"),
                          name="Tarav.Git.Hooks.AttributesMissing", workflow=GIT_WORKFLOW_SHIP)


# tarav.breadcrumb 3047e0efecce
class GitHooksCheck(Check):
    """Checks that a Project's repository runs the hooks its config selects."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6d1b5f92-e4a8-4c37-b0d6-2f9e8a1c7b54"),
                          name="Tarav.Git.Hooks.Check", workflow=GIT_WORKFLOW_SHIP)

    def __init__(self, project, config: GitHooksConfig) -> None:
        super().__init__()
        self.project, self.config = project, config

    def _poi(self, poi_type: type[GitHooksPOI], message: str, **situation) -> GitHooksPOI:
        return poi_type(self, message, situation={"project": project_id(self.project.root), **situation},
                        details={"root": str(self.project.root)})

    def _run(self) -> CheckResult:
        root = self.project.root
        pois = [self._poi(UnknownHookHandler, f"No Git hook handler is named {name}", handler=name)
                for name in self.config.handlers if name not in git_hook_handlers()]
        if repository_root(root) != root:
            pois.append(self._poi(HooksNotInstalled, f"{root} is not the root of a Git repository"))
            return CheckResult(self, status="completed", pois=pois)
        configured = git_result(root, "config", "--get", "core.hooksPath").stdout.decode().strip()
        if configured != HOOKS_FOLDER:
            pois.append(self._poi(HooksNotInstalled, f"core.hooksPath is {configured or 'unset'}, "
                                  f"not {HOOKS_FOLDER}", hooks_path=configured or None))
        folder = root / HOOKS_FOLDER
        scripts = expected_scripts(self.config)
        present = {path.name for path in folder.iterdir()} if folder.is_dir() else set()
        for hook in sorted(present | set(scripts)):
            path = folder / hook
            if hook not in scripts:
                reason = "is not needed by the configured handlers"
            elif not path.is_file():
                reason = "is missing"
            elif path.read_text(encoding="utf-8") != scripts[hook]:
                reason = "differs from what install writes"
            elif not os.access(path, os.X_OK):
                reason = "is not executable"
            else:
                continue
            pois.append(self._poi(HookStale, f"The {hook} hook script {reason}", hook=hook))
        attributes = root / ATTRIBUTES_FILE
        lines = attributes.read_text(encoding="utf-8").splitlines() if attributes.exists() else []
        for line in expected_attributes(self.config):
            if line not in lines:
                pois.append(self._poi(HookAttributesMissing,
                                      f"{ATTRIBUTES_FILE} lacks the line {line!r}", line=line))
        return CheckResult(self, status="completed", pois=pois)


def git_hook_checks(project) -> Iterable[Check]:
    """The checks of a Project's Git hooks: those its config selects, or the default
    handlers when it selects none and its root is a repository root.

    An invalid `git` section yields nothing here; the Project files check reports it.
    """
    try:
        config = hooks_config(project.root)
    except CliError:
        return ()
    if config is None:
        if repository_root(project.root) != Path(project.root).resolve():
            return ()
        config = GitHooksConfig(handlers=list(DEFAULT_HANDLERS))
    handlers = git_hook_handlers()
    extra = (handlers[name].check(project) for name in config.handlers if name in handlers)
    return (GitHooksCheck(project, config), *(check for check in extra if check is not None))


def git_hooks_suite(project) -> CheckSuite:
    return CheckSuite(lambda _suite: git_hook_checks(project), name="git hooks")


GIT_HOOKS_RECORD_TYPES = (GitHooksPOI, HooksNotInstalled, HookStale, UnknownHookHandler,
                          HookAttributesMissing)

__all__ = [
    "DEFAULT_HANDLERS", "GIT_HOOKS_RECORD_TYPES", "GitConfig", "GitHookCall", "GitHookHandler", "GitHookRefusal",
    "GitHooksCheck", "OVERRULE_ENV_VAR", "REFUSED_EXIT", "overrule_from_environment",
    "GitHooksConfig", "GitHooksPOI", "HOOKS_FOLDER", "HookAttributesMissing", "HookStale",
    "HooksNotInstalled", "UnknownHookHandler", "dispatch", "expected_scripts",
    "git_hook_checks", "git_hook_handlers", "git_hooks_suite", "hook_script", "hooks_config",
    "install", "register_git_hook_handler", "repository_root", "run_hook",
]
