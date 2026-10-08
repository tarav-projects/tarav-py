"""Reusable Settings contract checks for Tarav and external providers.

A concrete pytest class inherits the contract tests and supplies one object.
No production Settings operation depends on this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pytest

from . import SettingsError, SettingsProvider


class SettingsContractTests(ABC):
    """Subclass as TestSomething; pytest discovers the inherited test methods."""

    @abstractmethod
    def provider(self) -> SettingsProvider:
        """A fresh object of the Type under test."""

    def test_every_declared_setting_is_described_with_its_default(self) -> None:
        obj = self.provider()
        described = obj.settings.describe()
        assert set(described) == set(type(obj).settings_partitions())
        for partition, interface in type(obj).settings_partitions().items():
            assert set(described[partition]) == set(interface.model_fields)
            for key, field in interface.model_fields.items():
                assert obj.settings.get(key, partition=partition) == field.default
                assert obj.settings.origin(key, partition=partition) == "default"
                assert described[partition][key]["description"], (
                    f"{partition}.{key} needs a one-line description")

    def test_a_written_default_round_trips_as_a_runtime_value(self) -> None:
        obj = self.provider()
        for partition, interface in type(obj).settings_partitions().items():
            for key, field in interface.model_fields.items():
                obj.settings.set(key, value=field.default, partition=partition)
                assert obj.settings.get(key, partition=partition) == field.default
                assert obj.settings.origin(key, partition=partition) == "runtime"

    def test_unknown_keys_and_partitions_are_rejected(self) -> None:
        obj = self.provider()
        with pytest.raises(SettingsError):
            obj.settings.get("no-such-setting")
        with pytest.raises(SettingsError):
            obj.settings.set("no-such-setting", value=1)
        with pytest.raises(SettingsError):
            obj.settings.get("anything", partition="Tarav.No.Such.Partition")
