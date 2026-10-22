"""Explicit consumers composing Archive declarations and local Git mechanics."""
# tarav.breadcrumb ae45623930d0

from dataclasses import dataclass
from pathlib import Path
import socket

from tarav.l0._core.git_repository import GitError, git_result, run_git
from tarav.l0.kernel import entity
from tarav.l1.archive.model import LocalLocator, RepositoryDOI
from tarav.l1.archive import Archive
from tarav.l1.archive.references import DOIReference, RepositoryReference
from tarav.l1.git.change import TaravChangeCheck, find, ids_at, owner_root
from tarav.l1.references import ReferenceResult
from tarav.l1.references.git import git_file
from tarav.l1.git.hooks import GitConfig, install, repository_root
from tarav.l1.project.config import ProjectConfig
from tarav.l0._core.data_root import default_tarav_data_root
from tarav.l1.checks import CheckSuite, SuiteCheckpoint
from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.git.workflow import GIT_WORKFLOW_SHIP


def capture_repository(repository: DOIReference, location, *, commit="HEAD", path=None):
    """Capture from a caller-selected location; never infer or register identity."""
    declaration = repository.resolve()
    if not declaration.ok or not isinstance(declaration.target, RepositoryDOI):
        raise ValueError("Capture needs a readable Repository DOI declaration")
    root = Path(location).expanduser().resolve()
    known = [Path(item.path).resolve() for item in declaration.target.locators
             if isinstance(item, LocalLocator) and item.host == socket.gethostname()]
    if root not in known:
        raise ValueError("Capture location is not declared for this repository DOI")
    exact = run_git(root, "rev-parse", "--verify", "--end-of-options",
                    f"{commit}^{{commit}}").stdout.decode().strip()
    tree = run_git(root, "rev-parse", f"{exact}^{{tree}}").stdout.decode().strip()
    ids = ids_at(root, exact)
    locator = {**repository.locator, "commit": exact, "tree": tree}
    if ids:
        locator["change_id"] = ids[-1]
    if path is not None:
        git_file(root, exact, path)
        locator["path"] = path
    result = RepositoryReference({"type": entity(RepositoryReference).name, "locator": locator})
    result._records = getattr(repository, "_records", None)
    return result


@dataclass(frozen=True)
class RepositoryGitTarget:
    repository: Path
    commit: str
    tree: str
    recovered: bool
    path: str | None = None
    git_oid: str | None = None
    content: bytes | None = None


def resolve_repository(reference: RepositoryReference):
    """Verify local candidates. No fetches, semantic equivalence or silent ambiguity."""
    if not isinstance(reference, RepositoryReference):
        raise TypeError("Expected a RepositoryReference")
    declaration = reference.resolve()
    if not declaration.ok:
        return declaration
    coordinate = declaration.target.coordinate
    roots = [Path(item.path) for item in declaration.target.repository.locators
             if isinstance(item, LocalLocator) and item.host == socket.gethostname()]
    available = []

    def target(root, commit, recovered):
        oid, content = (git_file(root, commit, coordinate.path)
                        if coordinate.path is not None else (None, None))
        return ReferenceResult(RepositoryGitTarget(root, commit, coordinate.tree, recovered,
                                                   coordinate.path, oid, content), "resolved")

    def tree(root, commit):
        result = git_result(root, "rev-parse", "--verify", f"{commit}^{{tree}}")
        return result.stdout.decode().strip() if result.returncode == 0 else None

    try:
        for root in roots:
            original = tree(root, coordinate.commit)
            if original is not None:
                if original != coordinate.tree:
                    return ReferenceResult(None, "mismatch", "Original commit does not match captured tree")
                return target(root, coordinate.commit, False)
            if git_result(root, "rev-parse", "--git-dir").returncode == 0:
                available.append(root)
        candidates = {}
        rejected = []
        if coordinate.change_id is not None:
            for root in available:
                for commit in find(root, coordinate.change_id):
                    if tree(root, commit) == coordinate.tree:
                        candidates.setdefault(commit, root)
                    else:
                        rejected.append(commit)
        if len(candidates) == 1:
            commit, root = next(iter(candidates.items()))
            return target(root, commit, True)
        if len(candidates) > 1:
            return ReferenceResult(None, "unresolvable", "Ambiguous Change-ID candidates",
                                   hints={"commits": sorted(candidates)})
        return ReferenceResult(None, "mismatch" if rejected else "unresolvable",
                               "No candidate matches the captured repository state",
                               hints={"rejected_commits": sorted(set(rejected))})
    except (GitError, OSError, ValueError) as exc:
        return ReferenceResult(None, "unresolvable", str(exc))


def bind_repository(root, *, archive=None, repository_id=None, owner=None):
    """An explicit maintainer operation; never identify a repository by similarity."""
    from tarav.l1.archive.model import RepositoryHints

    root = Path(root).expanduser().resolve()
    if repository_root(root) != root:
        raise ValueError("Binding requires a Git working-tree root")
    config_store = ProjectConfig(root)
    config = config_store.section("git", GitConfig) or GitConfig()
    chosen = repository_id or config.repository
    if archive is None:
        archive = Archive(config.repository_registry) if config.repository_registry else Archive()
    owner = (Path(owner).expanduser().resolve() if owner is not None else
             Path(config.owner) if config.owner else
             root if (root / ".tarav/project.json").is_file() else
             default_tarav_data_root() / "system")
    if not (owner / ".tarav/project.json").is_file():
        raise ValueError("Choose an owning Project for repository hook actions")
    if chosen is not None:
        declaration = archive.read(chosen)
        if not isinstance(declaration, RepositoryDOI):
            raise ValueError("Hook binding requires a Repository DOI")
        known = [Path(item.path).resolve() for item in declaration.locators
                 if isinstance(item, LocalLocator) and item.host == socket.gethostname()]
        if root not in known:
            raise ValueError("Declare this location on the repository DOI before binding it")
    else:
        archive.store.create()
        has_head = git_result(root, "rev-parse", "--verify", "HEAD").returncode == 0
        declaration = archive.register(RepositoryDOI(
            label=root.name, locators=[LocalLocator(root)],
            hints=RepositoryHints.collect(root) if has_head else None))
        archive.store.commit((declaration.id,), "Register repository for tarav-change")
    config_store.write_section("git", config.model_copy(update={
        "repository": declaration.id, "repository_registry": str(archive.root),
        "owner": str(owner) if owner != root else None}))
    return declaration


def install_repository_hooks(root, *, add=(), archive=None, repository_id=None, owner=None):
    """Compose explicit DOI binding with the existing hook installer."""
    root = Path(root).expanduser().resolve()
    config = ProjectConfig(root).section("git", GitConfig)
    selected = {*add, *(config.hooks.handlers if config and config.hooks else ())}
    if "tarav-change" in selected:
        bind_repository(root, archive=archive, repository_id=repository_id, owner=owner)
    return install(root, add=add)


class OwnedRepositorySuite(CheckSuite):
    """Recheck DOI-bound external repositories owned by one featured Project."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("250e93a9-7e42-42c0-b8c7-efb45220cc75"),
                          name="Tarav.Git.OwnedRepositories.Suite", workflow=GIT_WORKFLOW_SHIP)

    def __init__(self, project, *, archive=None):
        self.project = project
        self.archive = archive if archive is not None else Archive()
        super().__init__(name="Owned repository Change-IDs", key=str(project.root),
                         checkpoint_types={"repositories": (TaravChangeCheck,)})

    def produce(self):
        if not self.archive.store.marker.exists():
            return
        complete = True
        visited = set()
        for identity in self.archive.ids():
            doi = self.archive.read(identity)
            if not isinstance(doi, RepositoryDOI):
                continue
            for locator in doi.locators:
                if not isinstance(locator, LocalLocator) or locator.host != socket.gethostname():
                    continue
                root = Path(locator.path).resolve()
                if root in visited or root == self.project.root:
                    continue
                visited.add(root)
                if repository_root(root) != root:
                    complete = False
                    continue
                config = ProjectConfig(root).section("git", GitConfig)
                if (config and config.repository == doi.id and config.hooks and
                        "tarav-change" in config.hooks.handlers and
                        owner_root(root) == self.project.root):
                    yield TaravChangeCheck(root)
        if complete:
            yield SuiteCheckpoint("repositories")
        else:
            self._refused += 1
