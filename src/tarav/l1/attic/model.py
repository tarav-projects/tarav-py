"""Path handlers and the small, self-declared deposit manifest."""

from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from tarav.l0._core.data_root import default_tarav_data_root
from tarav.l0.kernel import LoadedRecord, TaravClass, TaravObject, TypeShip, entity
from tarav.l1.checks import CheckProvider

from .workflow import ATTIC_WORKFLOW_SHIP

Nonblank = Annotated[str, StringConstraints(pattern=r"\S")]


# tarav.breadcrumb e80b6b05e648
class DepositManifest(BaseModel):
    """Format only. Extra depositor hints are opaque; no claim is verified."""

    model_config = ConfigDict(strict=True, extra="allow")

    kind: Literal["tarav.attic.deposit"] = Field(alias="class")
    schema_version: Literal[1]
    uuid: str
    deposited_at: str
    sources: list[Nonblank] = Field(min_length=1)
    material: Nonblank
    reason: Nonblank
    dependency_status: Literal["disconnected"]

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("schema_version must be an integer")
        return value

    @field_validator("uuid")
    @classmethod
    def uuid_format(cls, value):
        UUID(value)
        return value

    @field_validator("deposited_at")
    @classmethod
    def utc_timestamp(cls, value):
        timestamp = datetime.fromisoformat(value)
        if timestamp.utcoffset() != timedelta(0):
            raise ValueError("deposited_at must be a UTC timestamp")
        return value

    @field_validator("material")
    @classmethod
    def local_path(cls, value):
        path = PurePosixPath(value)
        if (path.is_absolute() or not path.parts or ".." in path.parts or
                "\\" in value or "\0" in value or path.parts[0] == "deposit.json"):
            raise ValueError("material must name a relative path within the deposit")
        return value


class Deposit(TaravObject):
    """A deposit directory; its UUID is a declaration, not an Artifact identity."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("651f064e-cbf3-41b2-9f02-1963211a7ac2"),
                          name="Tarav.Attic.Deposit", workflow=ATTIC_WORKFLOW_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        path: str

    def __init__(self, path: Path | str):
        super().__init__()
        self.path = Path(path).expanduser().absolute()

    @property
    def manifest_path(self) -> Path:
        return self.path / "deposit.json"

    def read_manifest(self) -> DepositManifest:
        return DepositManifest.model_validate_json(self.manifest_path.read_text(encoding="utf-8"))

    def _to_record(self):
        return {"type": entity(type(self)).name, "path": str(self.path)}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        return cls(loaded.data.path)

    class Records(TaravObject.Records):
        def record_example(self):
            return {"type": entity(self._owner).name, "path": "/example/attic/deposits/one"}


class Attic(TaravObject, CheckProvider):
    """A depot whose discovery never opens retained material or creates files."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("0278ec20-b2e8-4be1-81bc-5137f4b5271f"),
                          name="Tarav.Attic", workflow=ATTIC_WORKFLOW_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        root: str

    def __init__(self, root: Path | str | None = None):
        super().__init__()
        self.root = (Path(root).expanduser().resolve() if root is not None
                     else default_tarav_data_root() / "attic")

    def deposits(self) -> tuple[Deposit, ...]:
        try:
            entries = sorted((self.root / "deposits").iterdir())
        except FileNotFoundError:
            return ()
        return tuple(Deposit(path) for path in entries if path.is_dir())

    class Checks(CheckProvider.Checks):
        def suite(self):
            from .checks import AtticSuite

            return AtticSuite(self.obj)

    def _to_record(self):
        return {"type": entity(type(self)).name, "root": str(self.root)}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        return cls(loaded.data.root)

    class Records(TaravObject.Records):
        def record_example(self):
            return {"type": entity(self._owner).name, "root": "/example/attic"}
