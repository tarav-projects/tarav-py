"""Gitleaks: secrets that gitleaks finds, kept in a depot and handed to Projects.

Gitleaks detects; Tarav does not. Each gitleaks run, a history scan on
request or a scan of the staged changes in the pre-commit hook, leaves its
report in a depot outside the repository, exactly as gitleaks wrote it, with
a Record of the run beside it. A repository's `GitleaksSuite` revisits the
latest report: each finding is a situation, and an atomic Check says whether
it is still in the repository, raising a POI that opens an action.
`.gitleaksignore`, shared with gitleaks, is where accepted findings are
written. This is the template for an external tool: run it natively, keep its
report, and let a Suite find the situations in it.
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
from tarav.l0.project import load_project_marker, project_marker_name
from tarav.l1.actions.blessing import BLESSED
from tarav.l1.actions.pois import BlessableResolution
from tarav.l1.checks import CheckPOI, CheckResult, CheckSuite, SituationCheck
from tarav.l1.checks.chains import SituationChain, chain_type_name

from .hooks import OVERRULE_ENV_VAR, GitHookCall, GitHookHandler, GitHookRefusal
from .workflow import GIT_WORKFLOW_SHIP
from tarav.l0.kernel import LoadedRecord

DEPOT_ENV_VAR = "TARAV_GITLEAKS_ROOT"
IGNORE_FILE = ".gitleaksignore"

# tarav.breadcrumb bdb845c98d11
#: The chains of a repository's gitleaks reports; each names its Types after itself.
BINARY_CHAIN = "Tarav.Git.Gitleaks.Binary"
SCAN_CHAIN = "Tarav.Git.Gitleaks.Scan"
FINDING_CHAIN = "Tarav.Git.Gitleaks.Finding"
STAGED_CHAIN = "Tarav.Git.Gitleaks.Staged"

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
    def _from_record(cls, loaded: LoadedRecord):
        return cls(loaded.data.id, repository=loaded.data.repository, key=loaded.data.key,
                   kind=loaded.data.kind, head=loaded.data.head, version=loaded.data.version,
                   at=loaded.data.at, report=loaded.data.report, findings=loaded.data.findings)

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


def ignored(root: Path) -> set[str]:
    """The fingerprints the repository's `.gitleaksignore` accepts."""
    path = Path(root) / IGNORE_FILE
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def _line_counts(root: Path, objects: list[str]) -> dict[str, int | None]:
    """Line counts of ``commit:file`` objects, read in one `git cat-file --batch`; None if absent."""
    if not objects:
        return {}
    finished = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"],
                              input="\n".join(objects).encode() + b"\n", capture_output=True)
    data, counts, at = finished.stdout, {}, 0
    for name in objects:
        end = data.index(b"\n", at)
        header = data[at:end].split()
        at = end + 1
        if len(header) != 3:
            counts[name] = None  # "<name> missing" or ambiguous
            continue
        size = int(header[2])
        content = data[at:at + size]
        at += size + 1
        counts[name] = content.count(b"\n") + (1 if content and not content.endswith(b"\n") else 0)
    return counts


class GitleaksPOI(CheckPOI):
    """Family, never raised: what gitleaks reported, as Tarav found it in the repository."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("bd15f672-2127-4396-8e87-e2c65b285c1b"),
                          name="Tarav.Git.Gitleaks.POI", workflow=GIT_WORKFLOW_SHIP)


# tarav.breadcrumb 5cf11550e760
class GitleaksFinding(GitleaksPOI):
    """A finding of the latest history report that is still in the repository's history.

    Blessing its action appends its fingerprint to `.gitleaksignore`.
    """

    action = chain_type_name(FINDING_CHAIN, "Action", "Reported")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("68470027-d0c6-48d6-8222-ad9bb2f9d837"),
                          name=chain_type_name(FINDING_CHAIN, "POI", "Reported"), workflow=GIT_WORKFLOW_SHIP)


class GitleaksStaged(GitleaksPOI):
    """The pre-commit hook found secrets in the changes being committed; closed by hand."""

    action = chain_type_name(STAGED_CHAIN, "Action", "Reported")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("89113778-ee00-4879-af26-e899a63882a9"),
                          name=chain_type_name(STAGED_CHAIN, "POI", "Reported"), workflow=GIT_WORKFLOW_SHIP)


class GitleaksNeverScanned(GitleaksPOI):
    """No history scan of the repository is in the depot: `tarav git gitleaks scan` runs one."""

    action = chain_type_name(SCAN_CHAIN, "Action", "NeverScanned")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("11949f2c-848c-4e59-bd6f-8224a6ad9608"),
                          name=chain_type_name(SCAN_CHAIN, "POI", "NeverScanned"), workflow=GIT_WORKFLOW_SHIP)


class GitleaksMissing(GitleaksPOI):
    """The gitleaks binary is not on PATH, so neither the hook nor a scan can run."""

    action = chain_type_name(BINARY_CHAIN, "Action", "Missing")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("587f7bb3-7e22-4a48-bcdf-bd39b2178db8"),
                          name=chain_type_name(BINARY_CHAIN, "POI", "Missing"), workflow=GIT_WORKFLOW_SHIP)


# tarav.breadcrumb 87e22e00cff6
class GitleaksFindingResolution(BlessableResolution):
    """The action of a finding. Its blessing is appending the fingerprint to `.gitleaksignore`."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("35ee9601-3c61-414d-a088-6b3c3353a7c0"),
                          name=chain_type_name(FINDING_CHAIN, "Action", "Reported"), workflow=GIT_WORKFLOW_SHIP)

    def output(self, name, run, context) -> dict:
        if name != BLESSED:
            return super().output(name, run, context)
        poi = run.data["event"]["poi"]
        fingerprint = poi["situation"]["fingerprint"]
        root = Path(poi["details"]["path"])
        if fingerprint not in ignored(root):
            path = root / IGNORE_FILE
            prior = path.read_text(encoding="utf-8") if path.is_file() else ""
            separator = "" if not prior or prior.endswith("\n") else "\n"
            path.write_text(prior + separator + fingerprint + "\n", encoding="utf-8")
        return {"ignored": fingerprint, "file": str(root / IGNORE_FILE)}


class GitleaksStagedResolution(BlessableResolution):
    """The action of a staged report, closed by hand: it may be blessed."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("df19e3d6-615c-4b72-a77a-c47e8b922d5d"),
                          name=chain_type_name(STAGED_CHAIN, "Action", "Reported"), workflow=GIT_WORKFLOW_SHIP)


class GitleaksNeverScannedResolution(BlessableResolution):
    """The action of a repository never scanned: it may be blessed."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("aae0bf0b-25b6-4b08-8db8-275f9f516272"),
                          name=chain_type_name(SCAN_CHAIN, "Action", "NeverScanned"), workflow=GIT_WORKFLOW_SHIP)


class GitleaksMissingResolution(BlessableResolution):
    """The action of a missing gitleaks binary: it may be blessed."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b4ee350f-2905-4b12-900d-1fe4289999c7"),
                          name=chain_type_name(BINARY_CHAIN, "Action", "Missing"), workflow=GIT_WORKFLOW_SHIP)


class GitleaksHistory:
    """What a repository's history holds of a report's findings, read once for all their checks."""

    def __init__(self, root: Path, findings: list[dict]) -> None:
        reachable = (set(git_result(root, "rev-list", "--all").stdout.decode().split())
                     if findings else set())
        self._reachable = reachable
        self._lines = _line_counts(root, sorted({f"{item['Commit']}:{item['File']}"
                                                 for item in findings if item["Commit"] in reachable}))

    def holds(self, item: dict) -> bool:
        """Its commit is reachable from a ref and its file and lines exist in that commit.

        Git addresses content by hash, so that commit holds exactly what
        gitleaks scanned.
        """
        lines = self._lines.get(f"{item['Commit']}:{item['File']}")
        return item["Commit"] in self._reachable and lines is not None and item["EndLine"] <= lines


class GitleaksBinaryCheck(SituationCheck):
    """Is the gitleaks binary on PATH, for the hook and the scans of a repository?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c6fdb80b-ad27-43dd-8585-c98e759b9bf1"),
                          name=chain_type_name(BINARY_CHAIN, "Check"), workflow=GIT_WORKFLOW_SHIP)

    def __init__(self, *, situation, root: Path) -> None:
        super().__init__(situation=situation)
        self.root = root

    def _run(self) -> CheckResult:
        if gitleaks_binary() is not None:
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed", pois=[self.poi(
            GitleaksMissing, message="gitleaks is not on PATH", details={"path": str(self.root)})])


class GitleaksScanCheck(SituationCheck):
    """Has the repository a history scan in the depot?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a7deb3be-3559-4319-87e4-31b2c2cb030a"),
                          name=chain_type_name(SCAN_CHAIN, "Check"), workflow=GIT_WORKFLOW_SHIP)

    def __init__(self, *, situation, root: Path, depot: GitleaksDepot) -> None:
        super().__init__(situation=situation)
        self.root, self.depot = root, depot

    def _run(self) -> CheckResult:
        if self.depot.latest(self.situation["repository"]) is not None:
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed", pois=[self.poi(
            GitleaksNeverScanned,
            message=f"No gitleaks history scan of {self.root}; run `tarav git gitleaks scan`",
            details={"path": str(self.root)})])


# tarav.breadcrumb 6dcc746ab864
class GitleaksFindingCheck(SituationCheck):
    """Is one finding of the latest history report still in the repository's history?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("dbb1b7cf-26fe-4248-ad86-7e7243abe5bc"),
                          name=chain_type_name(FINDING_CHAIN, "Check"), workflow=GIT_WORKFLOW_SHIP)

    def __init__(self, *, situation, root: Path, finding: dict, history: GitleaksHistory,
                 run: str) -> None:
        super().__init__(situation=situation)
        self.root, self.finding, self.history, self.run_report = root, finding, history, run

    def _run(self) -> CheckResult:
        item = self.finding
        if not self.history.holds(item):
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed", pois=[self.poi(
            GitleaksFinding,
            message=f"gitleaks: {item['RuleID']} in {item['File']}:{item['StartLine']} "
                    f"at {item['Commit'][:7]}",
            details={"path": str(self.root), "rule": item["RuleID"], "file": item["File"],
                     "start_line": item["StartLine"], "end_line": item["EndLine"],
                     "commit": item["Commit"], "date": item["Date"], "run": self.run_report})])


class GitleaksStagedCheck(SituationCheck):
    """Raises the hook's Staged POI for one staged report. It never runs in a Project's
    suite, so its action stays open until closed by hand."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("4bb94504-da07-4a10-b933-b5d6f4dd383a"),
                          name=chain_type_name(STAGED_CHAIN, "Check"), workflow=GIT_WORKFLOW_SHIP)

    def __init__(self, *, situation, root: Path, run: GitleaksRun, overruled: bool) -> None:
        super().__init__(situation=situation)
        self.root, self.staged, self.overruled = root, run, overruled

    def _run(self) -> CheckResult:
        findings = [{"rule": item["RuleID"], "file": item["File"], "line": item["StartLine"]}
                    for item in GitleaksDepot().report(self.staged)]
        return CheckResult(self, status="completed", pois=[self.poi(
            GitleaksStaged,
            message=f"gitleaks found {self.staged.findings} secrets in changes staged in "
                    f"{self.root}" + (", committed by overrule" if self.overruled
                                      else ", and stopped the commit"),
            details={"path": str(self.root), "findings": findings, "overruled": self.overruled})])


# tarav.breadcrumb 99de98d10221
class GitleaksBinaryChain(SituationChain):
    """A repository whose hook and scans need the gitleaks binary."""

    Check = GitleaksBinaryCheck
    POIs = (GitleaksMissing,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("72c4e7e8-3b76-444b-bed0-4101046373ba"),
                          name=chain_type_name(BINARY_CHAIN, "Chain"), workflow=GIT_WORKFLOW_SHIP)


class GitleaksScanChain(SituationChain):
    """A repository whose history gitleaks should have scanned."""

    Check = GitleaksScanCheck
    POIs = (GitleaksNeverScanned,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("0cef175a-17a2-4763-971e-dc89516ed597"),
                          name=chain_type_name(SCAN_CHAIN, "Chain"), workflow=GIT_WORKFLOW_SHIP)


class GitleaksFindingChain(SituationChain):
    """One finding of a repository's latest history report, by its gitleaks fingerprint."""

    Check = GitleaksFindingCheck
    POIs = (GitleaksFinding,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b2b2aa9f-68f0-465b-98c9-fc9dabf5c73b"),
                          name=chain_type_name(FINDING_CHAIN, "Chain"), workflow=GIT_WORKFLOW_SHIP)


class GitleaksStagedChain(SituationChain):
    """One staged report of a repository, by the report's name."""

    Check = GitleaksStagedCheck
    POIs = (GitleaksStaged,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2b1be100-9fdc-4c66-ae0d-f8c0b4f00b40"),
                          name=chain_type_name(STAGED_CHAIN, "Chain"), workflow=GIT_WORKFLOW_SHIP)


# tarav.breadcrumb 404e179f3f15
class GitleaksSuite(CheckSuite):
    """A repository's Gitleaks checks: it finds the situations in the latest history report.

    It yields the binary and scan checks of the repository, then one atomic
    finding check for each reported finding its `.gitleaksignore` does not
    accept, all reading the history once. Its key is the repository's, so it
    is the detector that says a finding is gone.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a767d688-fedf-4852-b34c-f5348bcdc14b"),
                          name="Tarav.Git.Gitleaks.Suite", workflow=GIT_WORKFLOW_SHIP)

    def __init__(self, root: Path | str, depot: GitleaksDepot | None = None) -> None:
        self.root = Path(root).resolve()
        self.depot = depot or GitleaksDepot()
        super().__init__(name="gitleaks", key=repository_key(self.root))

    def produce(self):
        key, root = self.key, self.root
        if key is None:
            return
        yield GitleaksBinaryChain({"repository": key}).check(root=root)
        yield GitleaksScanChain({"repository": key}).check(root=root, depot=self.depot)
        run = self.depot.latest(key)
        if run is None:
            return
        accepted = ignored(root)
        findings = [item for item in self.depot.report(run) if item["Fingerprint"] not in accepted]
        history = GitleaksHistory(root, findings)
        for item in findings:
            yield GitleaksFindingChain({"repository": key, "fingerprint": item["Fingerprint"]}).check(
                root=root, finding=item, history=history, run=run.report)


# tarav.breadcrumb 91ec1d57d64a
def register_staged(root: Path | str, run: GitleaksRun, *, overruled: bool) -> dict:
    """Open the action of a staged report on the repository's owner."""
    # tarav.breadcrumb 10c4e1fcba48
    from tarav.l1.project.actions import ActionManager

    root = Path(root).resolve()
    check = GitleaksStagedChain({"repository": run.key, "run": run.report}).check(
        root=root, run=run, overruled=overruled)
    suite = CheckSuite([check], name="gitleaks hook").run()
    return ActionManager.for_owner(owner_of(root)).register(suite)


# tarav.breadcrumb 88f957d5a028
# tarav.breadcrumb 732bc027224b
class Gitleaks(GitHookHandler):
    """Scans the staged changes before each commit and stops it when gitleaks finds secrets."""

    name = "gitleaks"
    hooks = frozenset({"pre-commit"})

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8ac1296c-0150-4af1-973f-5a4afe26f26d"),
                          name="Tarav.Git.Gitleaks", workflow=GIT_WORKFLOW_SHIP)

    def run(self, call: GitHookCall) -> None:
        if gitleaks_binary() is None:
            raise RuntimeError("gitleaks is not on PATH; the staged changes were not scanned")
        run = run_gitleaks(call.root, kind=STAGED)
        if not run.findings:
            return
        overruled = call.overrules(self.name)
        note = ""
        try:
            register_staged(call.root, run, overruled=overruled)
        except Exception as exc:  # the stop must not depend on the action registry
            note = f" The Project action could not be registered: {exc}."
        if overruled:
            return
        files = sorted({item["File"] for item in GitleaksDepot().report(run)})
        shown = ", ".join(files[:3]) + (", ..." if len(files) > 3 else "")
        raise GitHookRefusal(
            f"{run.findings} secrets in the staged changes ({shown}). Remove them, add the "
            f"reviewed fingerprints to {IGNORE_FILE}, or commit again with "
            f"{OVERRULE_ENV_VAR}={self.name}; either way the report is an action of the "
            f"Project.{note}")

    def check(self, project) -> CheckSuite:
        return GitleaksSuite(project.root)


def system_project_root() -> Path:
    """Where the System Project lives; the fallback owner of repositories no Project owns."""
    return default_tarav_data_root() / "system"


def _project(root: Path) -> dict:
    marker = load_project_marker(root / ".tarav" / "project.json")
    return {"id": str(marker["project_id"]), "name": project_marker_name(marker) or root.name,
            "root": str(root)}


# tarav.breadcrumb 150f22c8d66d
def owner_of(root: Path | str, *, system: Path | None = None) -> dict:
    """The Project whose actions a repository's findings become: the nearest Project marker
    at or above its root, else the System Project."""
    root = Path(root).resolve()
    for folder in (root, *root.parents):
        if (folder / ".tarav" / "project.json").is_file():
            return _project(folder)
    return _project(Path(system or system_project_root()).resolve())


def register_run(root: Path | str, run: GitleaksRun, *, system: Path | None = None,
                 runs=None) -> dict:
    """Register the actions of what the repository's check raises now on its owner."""
    from tarav.l1.project.actions import ActionManager

    suite = CheckSuite([GitleaksSuite(root)], name="gitleaks scan").run()
    return ActionManager.for_owner(owner_of(root, system=system), runs).register(suite)


def unowned_suites(depot: GitleaksDepot | None = None) -> list[GitleaksSuite]:
    """Suites of the scanned repositories no Project owns, for the System Project's suite."""
    depot = depot or GitleaksDepot()
    suites = []
    for key in depot.keys():
        run = depot.latest(key)
        path = Path(run.repository) if run else None
        if path is None or not path.is_dir() or repository_key(path) != key:
            continue
        if any((folder / ".tarav" / "project.json").is_file() for folder in (path, *path.parents)):
            continue
        suites.append(GitleaksSuite(path, depot))
    return suites


GIT_GITLEAKS_RECORD_TYPES = (GitleaksRun, GitleaksPOI, GitleaksFinding, GitleaksStaged,
                             GitleaksNeverScanned, GitleaksMissing)

__all__ = ["DEPOT_ENV_VAR", "GIT_GITLEAKS_RECORD_TYPES", "Gitleaks", "GitleaksBinaryChain",
           "GitleaksBinaryCheck", "GitleaksDepot", "GitleaksFinding", "GitleaksFindingChain",
           "GitleaksFindingCheck", "GitleaksFindingResolution", "GitleaksHistory", "GitleaksMissing",
           "GitleaksMissingResolution", "GitleaksNeverScanned", "GitleaksNeverScannedResolution",
           "GitleaksPOI", "GitleaksRun", "GitleaksScanChain", "GitleaksScanCheck", "GitleaksStaged",
           "GitleaksStagedChain", "GitleaksStagedCheck", "GitleaksStagedResolution",
           "GitleaksSuite", "register_staged",
           "GitleaksUnavailable", "HISTORY", "IGNORE_FILE", "STAGED", "gitleaks_binary",
           "ignored", "owner_of", "register_run", "repository_key", "run_gitleaks",
           "system_project_root", "unowned_suites"]
