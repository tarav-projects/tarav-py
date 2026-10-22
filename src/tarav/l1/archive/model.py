"""Typed maintenance contracts, locators and small repository recognition hints."""
# tarav.breadcrumb 02a176a67f12
# tarav.breadcrumb e5c511640cd8

import re
import secrets
import socket
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from tarav.l0._core.git_repository import run_git
from tarav.l0.kernel import TaravClass, TaravObject, TypeShip, entity
from .identity import ARCHIVE_WORKFLOW_SHIP


class LocalLocator(TaravObject):
    """A maintained absolute path on a named host; not an availability claim."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("7f337ec3-c97e-4ff6-bd48-0ee602a66afe"),
                          name="Tarav.Archive.Locator.Local", workflow=ARCHIVE_WORKFLOW_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        path: str = Field(min_length=1)
        host: str = Field(min_length=1)

        @model_validator(mode="after")
        def absolute_path(self):
            if not Path(self.path).is_absolute() or "\0" in self.path:
                raise ValueError("Local locator needs an absolute path")
            return self

    def __init__(self, path, *, host=None):
        super().__init__()
        self.path = str(Path(path).expanduser().absolute())
        self.host = socket.gethostname() if host is None else host
        type(self).RecordInterface.model_validate(self._to_record())

    def _to_record(self):
        return {"type": entity(type(self)).name, "path": self.path, "host": self.host}

    @classmethod
    def _from_record(cls, loaded):
        return cls(loaded.data.path, host=loaded.data.host)

    class Records(TaravObject.Records):
        def record_example(self):
            return {"type": entity(self._owner).name, "path": "/example/repo", "host": "example"}


class RemoteLocator(TaravObject):
    """A URI declaration, interpreted by its consumers."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("2b32439a-1f40-4713-8499-9c25b986df48"),
                          name="Tarav.Archive.Locator.Remote", workflow=ARCHIVE_WORKFLOW_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        uri: str = Field(min_length=1)

        @model_validator(mode="after")
        def valid_uri(self):
            if not urlsplit(self.uri).scheme or any(c.isspace() or ord(c) < 32 for c in self.uri):
                raise ValueError("Remote locator needs a URI without whitespace")
            return self

    def __init__(self, uri: str):
        super().__init__()
        self.uri = uri
        type(self).RecordInterface.model_validate(self._to_record())

    def _to_record(self):
        return {"type": entity(type(self)).name, "uri": self.uri}

    @classmethod
    def _from_record(cls, loaded):
        return cls(loaded.data.uri)

    class Records(TaravObject.Records):
        def record_example(self):
            return {"type": entity(self._owner).name, "uri": "https://example.org/repo.git"}


class RepositoryHints(TaravObject):
    """A bounded commit sample; evidence of shared history, not canonical identity."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("25561c0f-4c6e-45c1-bafb-6b0982763d72"),
                          name="Tarav.Archive.Repository.Hints", workflow=ARCHIVE_WORKFLOW_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        object_format: Literal["sha1", "sha256"]
        commits: list[str] = Field(max_length=10)

        @model_validator(mode="after")
        def hash_format(self):
            size = 40 if self.object_format == "sha1" else 64
            if len(set(self.commits)) != len(self.commits) or any(
                re.fullmatch(r"[0-9a-f]{%d}" % size, commit) is None for commit in self.commits
            ):
                raise ValueError("Repository hints need distinct hashes matching the object format")
            return self

    def __init__(self, *, object_format: str, commits=()):
        super().__init__()
        self.object_format, self.commits = object_format, list(commits)
        type(self).RecordInterface.model_validate(self._to_record())

    @classmethod
    def collect(cls, repository, *, revision="HEAD"):
        root = Path(repository)
        tip = run_git(root, "rev-parse", "--verify", "--end-of-options",
                      f"{revision}^{{commit}}").stdout.decode().strip()
        commits = run_git(root, "rev-list", "--reverse", "--topo-order", tip).stdout.decode().split()
        if len(commits) > 10:
            commits = [commits[i * (len(commits) - 1) // 9] for i in range(10)]
        return cls(object_format=run_git(root, "rev-parse", "--show-object-format").stdout.decode().strip(),
                   commits=commits)

    def _to_record(self):
        return {"type": entity(type(self)).name, "object_format": self.object_format,
                "commits": list(self.commits)}

    @classmethod
    def _from_record(cls, loaded):
        return cls(object_format=loaded.data.object_format, commits=loaded.data.commits)

    class Records(TaravObject.Records):
        def record_example(self):
            return {"type": entity(self._owner).name, "object_format": "sha1", "commits": ["a" * 40]}


class DOI(TaravObject):
    """A continuing resource identity whose contract is declared by its Type."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("d37d8e09-1c61-43d9-a343-94673e59437c"),
                          name="Tarav.Archive.DOI", workflow=ARCHIVE_WORKFLOW_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        id: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
        label: str | None = None
        locators: list[LocalLocator.RecordInterface | RemoteLocator.RecordInterface] = []

    @staticmethod
    def validate_id(identity):
        if not isinstance(identity, str) or re.fullmatch(r"[0-9a-f]{64}", identity) is None:
            raise ValueError("Lookup requires an exact DOI: 64 lowercase hexadecimal characters")

    def __init__(self, *, id=None, label=None, locators=()):
        super().__init__()
        self.id = secrets.token_hex(32) if id is None else id
        self.validate_id(self.id)
        self.label = label
        self.locators = list(locators)
        if any(not isinstance(item, (LocalLocator, RemoteLocator)) for item in self.locators):
            raise TypeError("DOI locators must be typed locator objects")

    def _to_record(self):
        return {"type": entity(type(self)).name, "id": self.id, "label": self.label,
                "locators": [item.records.to_record() for item in self.locators]}

    @classmethod
    def _from_record(cls, loaded):
        return cls(id=loaded.data.id, label=loaded.data.label,
                   locators=[_load_locator(item) for item in loaded.data.locators])

    class Records(TaravObject.Records):
        def record_example(self):
            return {"type": entity(self._owner).name, "id": "a" * 64, "label": None, "locators": []}


class RepositoryDOI(DOI):
    """The same repository across evolving checkouts and maintained locations."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("216e89b0-9edb-4566-814e-ff3aa64b55ed"),
                          name="Tarav.Archive.DOI.Repository", workflow=ARCHIVE_WORKFLOW_SHIP)

    class RecordInterface(DOI.RecordInterface):
        hints: RepositoryHints.RecordInterface | None = None

    def __init__(self, *, hints=None, **kwargs):
        super().__init__(**kwargs)
        if hints is not None and not isinstance(hints, RepositoryHints):
            raise TypeError("Repository hints must be typed")
        self.hints = hints

    def _to_record(self):
        return {**super()._to_record(),
                "hints": None if self.hints is None else self.hints.records.to_record()}

    @classmethod
    def _from_record(cls, loaded):
        return cls(id=loaded.data.id, label=loaded.data.label,
                   locators=[_load_locator(item) for item in loaded.data.locators],
                   hints=None if loaded.data.hints is None else
                   RepositoryHints.records.from_record(loaded.data.hints.model_dump(mode="json")))

    class Records(DOI.Records):
        def record_example(self):
            return {**super().record_example(), "hints": None}


DOI_RECORD_TYPES = (DOI, RepositoryDOI, LocalLocator, RemoteLocator, RepositoryHints)


def _load_locator(record):
    cls = LocalLocator if isinstance(record, LocalLocator.RecordInterface) else RemoteLocator
    return cls.records.from_record(record.model_dump(mode="json"))
