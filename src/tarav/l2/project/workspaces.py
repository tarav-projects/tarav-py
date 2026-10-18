"""A featured Project's explicit view onto independent Workspaces."""

from __future__ import annotations

import os
from pathlib import Path

from tarav.l1.git.repository import GitRepository
from tarav.l1.workspaces import (
    RepositoryWorktree, WorkspaceDepot, WorkspaceManifest,
)


# tarav.breadcrumb 60a7e544f019
class ProjectWorkspaces:
    def __init__(self, project, *, depot: WorkspaceDepot | None = None):
        self.project = project
        self.depot = depot or WorkspaceDepot()

    def list(self, *, status: str | None = None):
        return self.depot.list(project_id=self.project.id, status=status)

    def create(self, *, label: str, repositories: list[Path] | None = None):
        """Use exact current commits; callers can override repository discovery."""
        roots = repositories if repositories is not None else self.repositories()
        if not roots:
            raise ValueError("Project has no discovered Git repositories")
        entries = []
        for root in roots:
            repository = GitRepository(root)
            relative = repository.root.relative_to(self.project.root)
            location = "repositories/_root" if relative == Path(".") else (
                "repositories/" + relative.as_posix()
            )
            entries.append(RepositoryWorktree(
                path=location, repository=str(repository.root),
                commit=repository.exact_commit("HEAD"),
            ))
        manifest = WorkspaceManifest.new(
            label=label, entries=entries, project_ids=[self.project.id]
        )
        return self.depot.create(manifest)

    def repositories(self) -> list[Path]:
        """Find Git roots beneath the Project, without entering Git internals."""
        result = []
        for directory, children, files in os.walk(self.project.root):
            children[:] = [name for name in children
                           if name not in {".tarav", ".venv", "env", "node_modules", ".git"}]
            if ".git" in files or (Path(directory) / ".git").is_dir():
                repository = GitRepository(directory)
                if repository.root == Path(directory).resolve():
                    result.append(repository.root)
        return sorted(set(result))


__all__ = ["ProjectWorkspaces"]
