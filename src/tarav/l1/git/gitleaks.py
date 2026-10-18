"""Gitleaks: secrets that gitleaks finds, kept in a depot and handed to Projects.

Gitleaks detects; Tarav does not. Each gitleaks run, a history scan on
request or a scan of the staged changes in the pre-commit hook, leaves its
report in a depot outside the repository, exactly as gitleaks wrote it, with
a Record of the run beside it. Project checks double-check the latest
report: a finding still in the repository is the situation that raises a
POI and opens an action. `.gitleaksignore`, shared with gitleaks, is where
accepted findings are written.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict

from tarav.l0._core.data_root import default_tarav_data_root
from tarav.l0._core.git_repository import git_result
from tarav.l0._core.persistence import atomic_write_json
from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypeShip, entity

from .workflow import GIT_WORKFLOW_SHIP

DEPOT_ENV_VAR = "TARAV_GITLEAKS_ROOT"
IGNORE_FILE = ".gitleaksignore"
HISTORY, STAGED = "history", "staged"


# tarav.breadcrumb 9a6072c18208
class GitleaksUnavailable(RuntimeError):
    """The gitleaks binary is not on PATH."""


def gitleaks_binary() -> str | None:
    return shutil.which("gitleaks")


def repository_key(root: Path | str) -> str | None:
    """The depot's key for a repository: its root commit; None before the first commit.

    A repository with several root commits takes the smallest hash, so the
    key does not depend on the order Git lists them in.
    """
    result = git_result(Path(root), "rev-list", "--max-parents=0", "HEAD")
    roots = result.stdout.decode().split() if result.returncode == 0 else []
    return min(roots) if roots else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GitleaksRun(TaravEntity):
    """One gitleaks run over one repository, and the report it left in the depot."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e73383ad-7c18-48e4-a2ba-2dda028f519b"),
                          name="Tarav.Git.Gitleaks.Run", workflow=GIT_WORKFLOW_SHIP)

    class RecordInterface(TaravEntity.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Tarav.Git.Gitleaks.Run"]
        repository: str
        key: str
        kind: Literal["history", "staged"]
        head: str | None
        version: str
        at: str
        report: str
        findings: int

    def __init__(self, id: Ship, *, repository: str, key: str, kind: str, head: str | None,
                 version: str, at: str, report: str, findings: int) -> None:
        super().__init__(id)
        self.repository, self.key, self.kind, self.head = repository, key, kind, head
        self.version, self.at, self.report, self.findings = version, at, report, findings

    @classmethod
    def _from_record(cls, record_data):
        return cls(record_data.id, repository=record_data.repository, key=record_data.key,
                   kind=record_data.kind, head=record_data.head, version=record_data.version,
                   at=record_data.at, report=record_data.report, findings=record_data.findings)

    def _to_record(self):
        return {**super()._to_record(), "repository": self.repository, "key": self.key,
                "kind": self.kind, "head": self.head, "version": self.version, "at": self.at,
                "report": self.report, "findings": self.findings}

    class Records(TaravEntity.Records):
        def record_example(self) -> dict[str, object]:
            return {"type": entity(self._owner).name, "id": "2c3b985f-8982-4a9e-a6e6-7bde1414ab94",
                    "repository": "/example/repo", "key": "0c6a7501c6caace13e15a00add8d0995d52ff1e6",
                    "kind": HISTORY, "head": "0c6a7501c6caace13e15a00add8d0995d52ff1e6",
                    "version": "8.30.1", "at": "2026-10-18T00:00:00+00:00",
                    "report": "20261018T000000000000Z.json", "findings": 0}


# tarav.breadcrumb 7d5905ffcc51
class GitleaksDepot:
    """Gitleaks reports and the Records of their runs, one folder per repository key."""

    def __init__(self, root: Path | str | None = None) -> None:
        chosen = root if root is not None else (os.environ.get(DEPOT_ENV_VAR)
                                                or default_tarav_data_root() / "gitleaks")
        self.root = Path(chosen).expanduser().resolve()

    def report_path(self, key: str, name: str) -> Path:
        return self.root / key / "reports" / name

    def put(self, run: GitleaksRun) -> None:
        path = self.root / run.key / "runs" / run.report
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, run.records.to_record(), ensure_ascii=False)

    def keys(self) -> list[str]:
        return sorted(path.name for path in self.root.iterdir()
                      if (path / "runs").is_dir()) if self.root.is_dir() else []

    def runs(self, key: str) -> list[GitleaksRun]:
        """The runs of one repository, oldest first."""
        folder = self.root / key / "runs"
        paths = sorted(folder.glob("*.json")) if folder.is_dir() else []
        return [GitleaksRun.records.from_record(json.loads(path.read_text(encoding="utf-8")))
                for path in paths]

    def latest(self, key: str, kind: str = HISTORY) -> GitleaksRun | None:
        found = [run for run in self.runs(key) if run.kind == kind]
        return found[-1] if found else None

    def report(self, run: GitleaksRun) -> list[dict]:
        return json.loads(self.report_path(run.key, run.report).read_text(encoding="utf-8"))


def run_gitleaks(root: Path | str, *, kind: str = HISTORY,
                 depot: GitleaksDepot | None = None) -> GitleaksRun:
    """Run gitleaks over the repository at ``root`` and keep its report in the depot.

    `history` scans every commit; `staged` scans the changes being committed,
    as the pre-commit hook does. Fingerprints in the repository's
    `.gitleaksignore` are not reported.
    """
    binary = gitleaks_binary()
    if binary is None:
        raise GitleaksUnavailable("gitleaks is not on PATH; install it, e.g. `brew install gitleaks`")
    root = Path(root).resolve()
    key = repository_key(root)
    if key is None:
        raise ValueError(f"{root} has no commits for gitleaks to scan")
    depot = depot or GitleaksDepot()
    at = _now()
    name = datetime.fromisoformat(at).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    report = depot.report_path(key, name)
    report.parent.mkdir(parents=True, exist_ok=True)
    command = [binary, "git", ".", "--redact", "--no-banner", "--log-level", "error",
               "--exit-code", "0", "--report-format", "json", "--report-path", str(report),
               "--gitleaks-ignore-path", str(root)]
    if kind == STAGED:
        command += ["--pre-commit", "--staged"]
    elif kind != HISTORY:
        raise ValueError(f"A gitleaks run is {HISTORY} or {STAGED}, not {kind!r}")
    finished = subprocess.run(command, cwd=root, capture_output=True, text=True)
    if finished.returncode != 0 or not report.is_file():
        raise RuntimeError(f"gitleaks failed on {root}: {finished.stderr.strip()}")
    findings = json.loads(report.read_text(encoding="utf-8"))
    version = subprocess.run([binary, "version"], capture_output=True, text=True).stdout.strip()
    head = git_result(root, "rev-parse", "HEAD").stdout.decode().strip() or None
    run = GitleaksRun(Ship(str(uuid.uuid4())), repository=str(root), key=key, kind=kind,
                      head=head, version=version, at=at, report=name, findings=len(findings))
    depot.put(run)
    return run


GIT_GITLEAKS_RECORD_TYPES = (GitleaksRun,)

__all__ = ["DEPOT_ENV_VAR", "GIT_GITLEAKS_RECORD_TYPES", "GitleaksDepot", "GitleaksRun",
           "GitleaksUnavailable", "HISTORY", "IGNORE_FILE", "STAGED", "gitleaks_binary",
           "repository_key", "run_gitleaks"]
