from __future__ import annotations

from pathlib import Path

import pytest

from tarav.l0._core.errors import CliError
from tarav.testing import TaravTestEnvironment
from tarav.l1.chatlas.instance_selection import selected_provider_instances


def _isolate_chatlas(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> TaravTestEnvironment:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    return environment


def test_selected_provider_instances_uses_chatlas_sources_without_profiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _isolate_chatlas(monkeypatch, tmp_path)
    codex_home = tmp_path / "codex-home"
    environment.write_global_config(
        chatlas={
            "sources": [
                {
                    "provider": "codex",
                    "home": str(codex_home),
                },
            ],
        }
    )

    instances = selected_provider_instances(providers=None, start_path=tmp_path)

    assert len(instances) == 1
    instance = instances[0]
    assert instance.provider == "codex"
    assert instance.agent.home == codex_home.resolve()
    assert instance.agent.profile_id is None
    assert instance.source_home == str(codex_home.resolve())
    assert instance.fingerprint == instance.agent.fingerprint()


def test_selected_provider_instances_filters_sources_by_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _isolate_chatlas(monkeypatch, tmp_path)
    environment.write_global_config(
        chatlas={
            "sources": [
                {"provider": "codex", "home": str(tmp_path / "codex-home")},
                {"provider": "claude-code", "home": str(tmp_path / "claude-home")},
            ],
        }
    )

    instances = selected_provider_instances(providers=("claude-code",), start_path=tmp_path)

    assert [instance.provider for instance in instances] == ["claude-code"]
    assert instances[0].agent.home == (tmp_path / "claude-home").resolve()


def test_selected_provider_instances_skips_non_scannable_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _isolate_chatlas(monkeypatch, tmp_path)
    canonical_home = tmp_path / "codex-home"
    satellite_home = tmp_path / "codex-satellite"
    environment.write_global_config(
        chatlas={
            "sources": [
                {
                    "provider": "codex",
                    "home": str(canonical_home),
                    "scannable": True,
                },
                {
                    "provider": "codex",
                    "home": str(satellite_home),
                    "scannable": False,
                },
            ],
        }
    )

    instances = selected_provider_instances(providers=None, start_path=tmp_path)

    assert [instance.agent.home for instance in instances] == [
        canonical_home.resolve()
    ]


@pytest.mark.parametrize("value", [None, 0, 1, "false", [], {}])
def test_selected_provider_instances_rejects_non_boolean_scannable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    value: object,
) -> None:
    environment = _isolate_chatlas(monkeypatch, tmp_path)
    environment.write_global_config(
        chatlas={
            "sources": [
                {
                    "provider": "codex",
                    "home": str(tmp_path / "codex-home"),
                    "scannable": value,
                },
            ],
        }
    )

    with pytest.raises(
        CliError,
        match="chatlas.sources\\[0\\].scannable must be a boolean",
    ):
        selected_provider_instances(providers=None, start_path=tmp_path)


def test_selected_provider_instances_rejects_unknown_source_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _isolate_chatlas(monkeypatch, tmp_path)
    environment.write_global_config(
        chatlas={
            "sources": [
                {"provider": "unknown-provider", "home": str(tmp_path / "home")},
            ],
        }
    )

    with pytest.raises(CliError, match="unsupported Chatlas source provider"):
        selected_provider_instances(providers=None, start_path=tmp_path)


def test_selected_provider_instances_rejects_source_without_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _isolate_chatlas(monkeypatch, tmp_path)
    environment.write_global_config(
        chatlas={
            "sources": [
                {"provider": "codex"},
            ],
        }
    )

    with pytest.raises(CliError, match="chatlas.sources\\[0\\].home is required"):
        selected_provider_instances(providers=None, start_path=tmp_path)


def test_selected_provider_instances_rejects_agentos_system_homes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _isolate_chatlas(monkeypatch, tmp_path)
    system_home = environment.tarav_home / "agent" / "homes" / "codex" / "browser-br"
    environment.write_global_config(
        chatlas={
            "sources": [
                {"provider": "codex", "home": str(system_home)},
            ],
        }
    )

    with pytest.raises(CliError, match="must not use Agentos-managed system homes"):
        selected_provider_instances(providers=None, start_path=tmp_path)


def test_selected_provider_instances_rejects_home_with_symlink_component(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _isolate_chatlas(monkeypatch, tmp_path)
    real_home = tmp_path / "real-claude"
    real_home.mkdir()
    linked_parent = tmp_path / "linked-claude"
    linked_parent.symlink_to(real_home, target_is_directory=True)
    environment.write_global_config(
        chatlas={
            "sources": [
                {"provider": "claude-code", "home": str(linked_parent)},
            ],
        }
    )

    with pytest.raises(CliError, match="must not contain symlink components"):
        selected_provider_instances(providers=None, start_path=tmp_path)
