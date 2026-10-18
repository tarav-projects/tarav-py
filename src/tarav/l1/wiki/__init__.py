"""Folder-based Markdown wikis with optional Tarav project integration."""

from datetime import date
from pathlib import Path
import subprocess

from tarav.l0._core.persistence import atomic_write_text
from tarav.l0.kernel import TaravClass, TaravObject, TypeShip, entity
from tarav.l1.surfaces.markdown import MarkdownNormalModel

from .workflow import WIKI_WORKFLOW_SHIP, WikiWorkflow
from tarav.l0.kernel import LoadedRecord


class Wiki(TaravObject):
    """Notes rooted at a folder. Resolving a Wiki never creates files."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("9cc7e1b5-88fc-4c1b-a868-d9e899f1ac12"),
            name="Tarav.Wiki",
            workflow=WIKI_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        root: str

    def __init__(self, root: Path | str):
        super().__init__()
        self.root = Path(root).expanduser().resolve()
        if self.root.exists() and not self.root.is_dir():
            raise NotADirectoryError(self.root)

    @classmethod
    def from_path(cls, root: Path | str):
        return cls(root)

    def get(self, path: Path | str):
        return WikiNote(self, path)

    def daily(self, day: date):
        return self.get(Path("daily") / f"{day.isoformat()}.md")

    def ls(self) -> tuple["WikiNote", ...]:
        """List existing Markdown notes recursively in relative-path order."""
        return tuple(
            self.get(path.relative_to(self.root))
            for path in sorted(self.root.rglob("*.md"))
            if path.is_file()
        )

    def commit(self, message: str) -> str | None:
        """Commit the complete Wiki working state; leave outside staging intact.

        The caller authorizes committing. No repository is created implicitly.
        Returns None when the Wiki has no changes.
        """

        def git(*args):
            return subprocess.run(
                ["git", "-C", str(self.root), *args],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        repository = Path(git("rev-parse", "--show-toplevel")).resolve()
        scope = ":(top,literal)" + self.root.relative_to(repository).as_posix()
        if self.root == repository:
            scope = ":(top)"
        if not git("status", "--porcelain", "--untracked-files=all", "--", scope):
            return None
        git("add", "-A", "--", scope)
        git("commit", "--only", "-m", message, "--", scope)
        return git("rev-parse", "HEAD")

    def _to_record(self):
        return {"type": entity(type(self)).name, "root": str(self.root)}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        return cls(loaded.data.root)

    class Records(TaravObject.Records):
        def record_example(self):
            cls = self._owner
            return {"type": entity(cls).name, "root": "/example/wiki"}



class WikiNote(TaravObject):
    """One Markdown file addressed relative to its Wiki root."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("b68f3a3e-e150-4a7d-847b-b51324f42f51"),
            name="Tarav.Wiki.Note",
            workflow=WIKI_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        root: str
        path: str

    def __init__(self, wiki: Wiki, path: Path | str):
        super().__init__()
        self.wiki = wiki
        self.relative_path = Path(path)
        if self.relative_path.is_absolute() or ".." in self.relative_path.parts:
            raise ValueError("Wiki note paths must remain relative to the Wiki root")
        if self.relative_path.suffix != ".md":
            raise ValueError("Wiki notes must use the .md extension")
        self.path  # Validate now, and again at each I/O boundary.

    @property
    def path(self) -> Path:
        target = (self.wiki.root / self.relative_path).resolve()
        if not target.is_relative_to(self.wiki.root):
            raise ValueError("Wiki note escapes its root")
        return target

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def write(self, text: str) -> None:
        atomic_write_text(self.path, text)

    def parse(self) -> MarkdownNormalModel:
        return MarkdownNormalModel.from_text(self.read())

    def _to_record(self):
        return {
            "type": entity(type(self)).name,
            "root": str(self.wiki.root),
            "path": self.relative_path.as_posix(),
        }

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        return cls(Wiki.from_path(loaded.data.root), loaded.data.path)

    class Records(TaravObject.Records):
        def record_example(self):
            cls = self._owner
            return {"type": entity(cls).name, "root": "/example/wiki", "path": "topic.md"}



__all__ = ["Wiki", "WikiNote", "WikiWorkflow"]
