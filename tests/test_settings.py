"""Settings are a capability: declared, checked, and visible in Context."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from tarav.l0.kernel import TaravClass, TaravObject, TaravTypeDeclarationError, TypeShip, entity
from tarav.l1.context import explore
from tarav.l1.settings import (
    SettingsError,
    SettingsProvider,
    SettingsValues,
    SettingsWorkflow,
    contribute_settings,
)
from tarav.l1.settings.testing import SettingsContractTests


class Tracking(TaravObject, SettingsProvider):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5b0d8f0e-3c0b-4d4e-9d52-0a8f6a1f2c11"),
                          name="Tarav.Test.Settings.Tracking")

    class SettingsInterface(BaseModel):
        enabled: bool = Field(True, description="Store raised instances.")
        limit: int = Field(10, description="How many to keep.")

    def __init__(self, *, settings: SettingsValues | None = None) -> None:
        super().__init__()
        self.settings.apply(values=settings)


class Labelled(Tracking):
    """Declares its own partition and explicitly includes its parent's."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6c1e9a1f-4d1c-4e5f-8e63-1b9a7b2a3d22"),
                          name="Tarav.Test.Settings.Labelled")

    settings_include = (Tracking,)

    class SettingsInterface(BaseModel):
        label: str = Field("", description="A display label.")
        limit: int = Field(3, description="A second limit, to exercise ambiguity.")


class Silent(Tracking):
    """Extends a provider but declares and includes nothing."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7d2fab20-5e2d-4f60-9f74-2cab8c3b4e33"),
                          name="Tarav.Test.Settings.Silent")

    def __init__(self) -> None:
        TaravObject.__init__(self)


class TestTrackingSettingsContract(SettingsContractTests):
    def provider(self) -> SettingsProvider:
        return Tracking()


class TestLabelledSettingsContract(SettingsContractTests):
    def provider(self) -> SettingsProvider:
        return Labelled()


# tarav.breadcrumb 77df5a5a02c79ba1787e0adee765c5c75fdaadd570ca51cd7a0af33f1f1cfa9b
def test_values_arrive_at_construction_and_can_be_written_afterwards() -> None:
    obj = Tracking(settings=SettingsValues.of(Tracking, enabled=False))
    assert obj.settings.get("enabled") is False
    assert obj.settings.origin("enabled") == "construction"
    assert obj.settings.get("limit") == 10
    assert obj.settings.origin("limit") == "default"

    obj.settings.set("limit", value=25)
    assert obj.settings.get("limit", partition=Tracking) == 25
    assert obj.settings.origin("limit") == "runtime"
    assert Tracking().settings.get("limit") == 10


def test_the_standard_path_checks_keys_partitions_and_value_types() -> None:
    obj = Tracking()
    with pytest.raises(SettingsError, match="declares no setting 'colour'"):
        obj.settings.set("colour", value="red")
    with pytest.raises(SettingsError, match="rejects 'yes'"):
        obj.settings.set("enabled", value="yes")
    with pytest.raises(SettingsError, match="no settings partition"):
        obj.settings.get("enabled", partition="Tarav.Other")
    with pytest.raises(SettingsError, match="declares no setting 'colour'"):
        Tracking(settings=SettingsValues.of(Tracking, colour="red"))
    assert obj.settings.get("enabled") is True


# tarav.breadcrumb 8e6c32510cfdbb25aa73e32b02352f1914ec905bf5dd42401aaa59eb0dead1bb
def test_a_parent_partition_is_included_only_explicitly() -> None:
    labelled = Labelled()
    assert set(type(labelled).settings_partitions()) == {
        entity(Labelled).name, entity(Tracking).name}
    assert labelled.settings.get("enabled") is True
    with pytest.raises(SettingsError, match="several partitions"):
        labelled.settings.get("limit")
    assert labelled.settings.get("limit", partition=Labelled) == 3
    assert labelled.settings.get("limit", partition=Tracking) == 10

    silent = Silent()
    assert type(silent).settings_partitions() == {}
    assert silent.settings.describe() == {}
    with pytest.raises(SettingsError, match="settings_include"):
        silent.settings.get("enabled", partition=Tracking)


def test_a_setting_without_a_default_is_a_declaration_error() -> None:
    with pytest.raises(TaravTypeDeclarationError, match="need defaults: size"):
        class Broken(TaravObject, SettingsProvider):
            @classmethod
            def class_entity(cls) -> TaravClass:
                return TaravClass(target=cls,
                                  id=TypeShip("8e30bc31-6f3e-4071-a085-3dbc9d4c5f44"),
                                  name="Tarav.Test.Settings.Broken")

            class SettingsInterface(BaseModel):
                size: int


# tarav.breadcrumb 906e2365423e710052436667a3def8f21dd7d7eb8cdd682490868e5f46adb38f
def test_settings_can_be_loaded_from_a_file_through_the_record_machinery(tmp_path: Path) -> None:
    path = tmp_path / "tracking.settings.json"
    path.write_text(json.dumps({"type": "Tarav.Settings.Values",
                                "partitions": {entity(Tracking).name: {"limit": 4}}}))

    values = SettingsValues.from_path(path=path)
    obj = Tracking()
    obj.settings.apply(values=values, origin=f"file:{path}")

    assert obj.settings.get("limit") == 4
    assert obj.settings.origin("limit") == f"file:{path}"
    assert values.records.to_record()["partitions"] == {entity(Tracking).name: {"limit": 4}}


def test_settings_are_visible_in_object_and_type_context() -> None:
    obj = Tracking(settings=SettingsValues.of(Tracking, limit=7))
    view = explore(obj, contributors=(contribute_settings,))
    report = view.get("settings").open().records.to_record()["value"]
    assert report[entity(Tracking).name]["limit"] == {
        "value": 7, "origin": "construction", "type": "int", "default": 10,
        "description": "How many to keep."}

    template = explore(Tracking).get("settings-template").open().records.to_record()["value"]
    assert template[entity(Tracking).name]["enabled"]["description"] == "Store raised instances."
    assert "settings-template" not in [entry.name for entry in explore(Silent).ls()]


def test_the_runtime_registers_the_workflow_and_contributes_settings() -> None:
    from tarav.l3.runtime import create_runtime

    runtime = create_runtime()
    assert runtime.workflows.get("Tarav.Workflow.Settings") is SettingsWorkflow
    names = [entry.name for entry in runtime.context(Tracking()).ls()]
    assert "settings" in names


# tarav.breadcrumb 6fd463b6ff2194bdb4a80e5046b6d3cb143ce867a490c38b270132417860a8e0
def test_the_agents_file_switches_are_settings_read_from_the_marker(tmp_path: Path) -> None:
    from tarav.l1.project import TaravProject

    marker = tmp_path / ".tarav" / "project.json"
    marker.parent.mkdir()
    marker.write_text(json.dumps({
        "class": "agentos.project", "schema_version": 1,
        "project_id": "20c26be7-a8e5-4974-9ec0-0b5a3a125a94",
        "agents": {"main": "AGENTS.md", "tarav_system_prompt": False},
    }))
    agents = TaravProject.from_path(tmp_path).agents.agents_md

    assert agents.tarav_prompt_enabled is False
    assert agents.settings.origin("tarav_system_prompt") == f"file:{marker}"
    assert agents.project_prompt_enabled is True
    assert agents.settings.origin("project_system_prompt") == "default"
    assert str(agents.main) == "AGENTS.md"

    marker.write_text(marker.read_text().replace("false", '"no"'))
    with pytest.raises(ValueError, match="rejects 'no'"):
        TaravProject.from_path(tmp_path).agents.agents_md
