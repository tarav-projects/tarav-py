"""A Project's `.tarav/config.json`: one section per workflow that configures it.

`project.json` is the Project workflow's own file. `config.json` is where other
workflows keep what they configure for a Project, each under a section it
owns and validates with its own model. A workflow registers its section; the
runtime does the registering. Reading a section that is absent gives None.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ValidationError

from tarav.l0._core.errors import CliError
from tarav.l0._core.persistence import atomic_write_json
from tarav.l0.project import load_project_config, project_config_path

_SECTIONS: dict[str, type[BaseModel]] = {}


def register_config_section(name: str, model: type[BaseModel]) -> None:
    """A workflow owns the section `name` of every Project's config, shaped by `model`."""
    if not isinstance(name, str) or not name:
        raise ValueError("A config section has a name")
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise TypeError("A config section is shaped by a pydantic model")
    if _SECTIONS.get(name, model) is not model:
        raise ValueError(f"Another model owns the config section {name}")
    _SECTIONS[name] = model


def config_sections() -> dict[str, type[BaseModel]]:
    return dict(_SECTIONS)


# tarav.breadcrumb e165cab92003978233c30d50a1b5fe7bda4205246ae2994e9043259104682369
class ProjectConfig:
    """The config file of one Project, read and written section by section."""

    def __init__(self, root: Path | str) -> None:
        self.path = project_config_path(Path(root).expanduser().resolve())

    def data(self) -> dict[str, object]:
        return load_project_config(self.path) if self.path.exists() else {}

    def section(self, name: str, model: type[BaseModel]):
        """The section `name` validated by `model`, or None when it is absent."""
        raw = self.data().get(name)
        if raw is None:
            return None
        try:
            return model.model_validate(raw)
        except ValidationError as exc:
            raise CliError(f"{self.path}: config section {name} is invalid: {exc}") from exc

    def write_section(self, name: str, value: BaseModel) -> None:
        data = self.data()
        data[name] = value.model_dump(mode="json", exclude_none=True)
        atomic_write_json(self.path, data, ensure_ascii=False)


__all__ = ["ProjectConfig", "config_sections", "register_config_section"]
