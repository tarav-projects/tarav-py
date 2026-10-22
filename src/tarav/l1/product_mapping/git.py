"""Read only Git objects; byte ranges never refer to working-directory files."""

from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import subprocess

from tarav.l1.git.repository import GitRepository, git_bytes, git_text


@dataclass(frozen=True)
class Surface:
    path: str
    mode: str
    oid: str


# tarav.breadcrumb 4a82e90af9c9
class CommittedProduct:
    def __init__(self, repository: str | Path):
        self.repository = GitRepository(repository)
        self.root = self.repository.root
        self._batch = None

    def exact(self, revision):
        return self.repository.exact_commit(revision)

    def tree(self, commit):
        return git_text(self.root, "rev-parse", f"{self.exact(commit)}^{{tree}}")

    def inventory(self, commit):
        raw = git_bytes(self.root, "ls-tree", "-rz", "--full-tree", self.exact(commit))
        result = {}
        for entry in raw.split(b"\0"):
            if entry:
                meta, name = entry.split(b"\t", 1)
                mode, _kind, oid = meta.decode("ascii").split()
                path = name.decode("utf-8", errors="surrogateescape")
                result[path] = Surface(path, mode, oid)
        return result

    @contextmanager
    def batch(self):
        """One bounded object-reader process per operation, with a small blob cache."""
        if self._batch is not None:
            yield self
            return
        proc = subprocess.Popen(["git", "-C", str(self.root), "cat-file", "--batch"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        self._batch = proc
        try:
            yield self
        finally:
            self._batch = None
            proc.stdin.close()
            proc.stdout.close()
            proc.wait()
            self.blob.cache_clear()

    @lru_cache(maxsize=128)
    def blob(self, oid):
        if self._batch is None:
            return git_bytes(self.root, "cat-file", "blob", oid)
        self._batch.stdin.write((oid + "\n").encode("ascii"))
        self._batch.stdin.flush()
        header = self._batch.stdout.readline().split()
        if len(header) != 3 or header[1] != b"blob":
            raise ValueError(f"Not an available Git blob: {oid}")
        size = int(header[2])
        content = self._batch.stdout.read(size)
        if len(content) != size or self._batch.stdout.read(1) != b"\n":
            raise ValueError("Incomplete Git blob read")
        return content

    def checkpoints(self, target="HEAD", *, every=10, after=None):
        # tarav.breadcrumb ab232e912341
        if type(every) is not int or every < 1:
            raise ValueError("Checkpoint interval must be a positive integer")
        history = git_text(self.root, "rev-list", "--first-parent", "--reverse",
                           self.exact(target)).splitlines()
        if after is not None:
            base = self.exact(after)
            if base not in history:
                raise ValueError("Base is outside target's first-parent history")
            pending = history[history.index(base) + 1:]
            selected = pending[every - 1::every]
        else:
            selected = history[::every]
        if history and (not selected or selected[-1] != history[-1]):
            if after is None or history[-1] != self.exact(after):
                selected.append(history[-1])
        return tuple(selected)
