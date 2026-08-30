# Internal interval checkpointing for an existing Git repository.
"""Interval checkpoint commits for a git-tracked depot.

Two rules shape everything here.

**record depot never runs `git init`.** A depot either sits inside a repo that already
tracks it or names one that already exists. Creating a repository is the operator's act:
inventing one under a depot is how a nested `.git/` appears inside a project and quietly
detaches the records from the history that was supposed to review them.

**A git failure never fails a write.** The record is already on disk by the time a
checkpoint is attempted. Raising here would turn a durable write into a reported error
and invite a caller to retry a write that already succeeded.

The last-checkpoint time is asked of git rather than stored beside the depot. Git already
knows when it last committed these paths; a second copy of that fact is a cache with no
reader but us, and the only thing it can do is disagree.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

#: Long enough that a burst of writes produces one commit, short enough that a session's
#: work is durable before it ends. Configurable per depot.
DEFAULT_INTERVAL_SECONDS = 900


@dataclass(frozen=True)
class GitCheckpoint:
    """One depot's git tracking: a repo that exists, and how often to commit into it."""

    repo: Path
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS

    @classmethod
    def resolve(cls, meta_path: Path, configured: object, interval: object) -> "GitCheckpoint | None":
        """Read the depot's git configuration. A path is relative to `meta.json`."""
        if configured is None:
            return None
        if not isinstance(configured, str) or not configured:
            raise ValueError(f"depot git configuration must be a path: {configured!r}")
        repo = Path(configured).expanduser()
        if not repo.is_absolute():
            repo = (meta_path.parent / repo).resolve()
        seconds = DEFAULT_INTERVAL_SECONDS if interval is None else int(interval)
        return cls(repo=repo, interval_seconds=seconds)

    def checkpoint(self, depot_root: Path) -> str | None:
        """Commit the depot if the interval has elapsed. Returns the commit, or None."""
        try:
            if not (self.repo / ".git").exists():
                return None
            if self._seconds_since_last(depot_root) < self.interval_seconds:
                return None
            self._run("add", "--", str(depot_root))
            if not self._run("diff", "--cached", "--quiet", "--", str(depot_root)).returncode:
                return None
            self._run(
                "commit",
                "-q",
                "-m",
                f"chore(record-depot): checkpoint {depot_root.name}",
            )
            return self._run("rev-parse", "HEAD").stdout.strip() or None
        except (OSError, subprocess.SubprocessError, ValueError):
            return None

    def _seconds_since_last(self, depot_root: Path) -> float:
        result = self._run("log", "-1", "--format=%ct", "--", str(depot_root))
        stamp = result.stdout.strip()
        if not stamp:
            # Never committed: the first write is already overdue.
            return float("inf")
        return time.time() - float(stamp)

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ("git", "-C", str(self.repo), *args),
            capture_output=True,
            text=True,
            check=False,
        )


__all__ = ["DEFAULT_INTERVAL_SECONDS", "GitCheckpoint"]
