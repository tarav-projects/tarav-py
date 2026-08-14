from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tarav._core.errors import CliError
from tarav.testing import TaravTestEnvironment
from tarav.chatlas.tagger import auto_match, load_tagger_profile, render_session
from tarav.chatlas.time_interface import format_local_timestamp


def _test_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> TaravTestEnvironment:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    return environment


def test_load_profile_returns_tags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment = _test_environment(monkeypatch, tmp_path)
    environment.write_global_config(**{
        "chatlas": {
            "taggers": {
                "session-type": {"tags": ["hugentic-session", "agentic-session"]},
            },
        },
    })
    profile = load_tagger_profile("session-type")
    assert profile["name"] == "session-type"
    assert profile["tags"] == ["hugentic-session", "agentic-session"]
    assert profile["auto_test_rate"] == 0.1
    assert profile["compiled_auto"] == {}


def test_load_profile_missing_config_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _test_environment(monkeypatch, tmp_path)
    with pytest.raises(CliError, match="tarav config not found"):
        load_tagger_profile("session-type")


def test_load_profile_missing_taggers_section_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = _test_environment(monkeypatch, tmp_path)
    environment.write_global_config(**{"chatlas": {}})
    with pytest.raises(CliError, match="no `chatlas.taggers` section"):
        load_tagger_profile("session-type")


def test_load_profile_missing_profile_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = _test_environment(monkeypatch, tmp_path)
    environment.write_global_config(
        **{"chatlas": {"taggers": {"other": {"tags": ["x"]}}}}
    )
    with pytest.raises(CliError, match="no tagger profile"):
        load_tagger_profile("session-type")


def test_load_profile_empty_tags_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = _test_environment(monkeypatch, tmp_path)
    environment.write_global_config(**{"chatlas": {"taggers": {"x": {"tags": []}}}})
    with pytest.raises(CliError, match="non-empty list"):
        load_tagger_profile("x")


def test_load_profile_non_string_tag_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = _test_environment(monkeypatch, tmp_path)
    environment.write_global_config(
        **{"chatlas": {"taggers": {"x": {"tags": ["a", ""]}}}}
    )
    with pytest.raises(CliError, match="non-empty list"):
        load_tagger_profile("x")


def test_load_profile_too_many_tags_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = _test_environment(monkeypatch, tmp_path)
    tags = [f"t{i}" for i in range(10)]
    environment.write_global_config(**{"chatlas": {"taggers": {"x": {"tags": tags}}}})
    with pytest.raises(CliError, match="at most"):
        load_tagger_profile("x")


def test_render_session_includes_key_fields() -> None:
    row = {
        "identity_hash": "abcdef0123456789abcdef0123456789",
        "provider": "claude-code",
        "project_path": "/Users/x/work",
        "last_activity_at": "2026-05-30T01:23:45Z",
        "summary": {
            "visible_user_turn_count": 7,
            "visible_assistant_turn_count": 12,
            "first_user_text_excerpt": "Let's design the tagger",
        },
    }
    out = render_session(row)
    assert "abcdef012345" in out
    assert "claude-code" in out
    assert "/Users/x/work" in out
    assert format_local_timestamp("2026-05-30T01:23:45Z") in out
    assert "2026-05-30T01:23:45Z" not in out
    assert "user=7" in out
    assert "assistant=12" in out
    assert "Let's design the tagger" in out


def test_render_session_handles_missing_fields() -> None:
    out = render_session({"identity_hash": "abc"})
    assert "abc" in out
    assert "(no project)" in out
    assert "(no excerpt available)" in out


def test_load_profile_auto_block_round_trips(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment = _test_environment(monkeypatch, tmp_path)
    environment.write_global_config(**{
        "chatlas": {
            "taggers": {
                "session-type": {
                    "tags": ["hugentic-session", "agentic-session"],
                    "auto_test_rate": 0.25,
                    "auto": {
                        "agentic-session": {
                            "method": "regex",
                            "patterns": [
                                {"turn": 1, "regex": "^Use md-library-pkg"},
                                {"regex": "^Run: iterante execute"},
                            ],
                        },
                    },
                },
            },
        },
    })
    profile = load_tagger_profile("session-type")
    assert profile["auto_test_rate"] == 0.25
    auto = profile["compiled_auto"]
    assert set(auto.keys()) == {"agentic-session"}
    patterns = auto["agentic-session"]
    assert len(patterns) == 2
    assert patterns[0][0] == 1
    assert patterns[0][2] == "^Use md-library-pkg"
    assert patterns[1][0] == 1  # default turn
    assert patterns[1][2] == "^Run: iterante execute"


def test_load_profile_auto_unknown_tag_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment = _test_environment(monkeypatch, tmp_path)
    environment.write_global_config(**{
        "chatlas": {
            "taggers": {
                "x": {
                    "tags": ["a", "b"],
                    "auto": {"c": {"method": "regex", "patterns": [{"regex": "^z"}]}},
                },
            },
        },
    })
    with pytest.raises(CliError, match="unknown tag"):
        load_tagger_profile("x")


def test_load_profile_auto_invalid_regex_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment = _test_environment(monkeypatch, tmp_path)
    environment.write_global_config(**{
        "chatlas": {
            "taggers": {
                "x": {
                    "tags": ["a"],
                    "auto": {"a": {"method": "regex", "patterns": [{"regex": "["}]}},
                },
            },
        },
    })
    with pytest.raises(CliError, match="regex is invalid"):
        load_tagger_profile("x")


def test_load_profile_auto_non_regex_method_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment = _test_environment(monkeypatch, tmp_path)
    environment.write_global_config(**{
        "chatlas": {
            "taggers": {
                "x": {
                    "tags": ["a"],
                    "auto": {"a": {"method": "literal", "patterns": [{"regex": "z"}]}},
                },
            },
        },
    })
    with pytest.raises(CliError, match="method must be `regex`"):
        load_tagger_profile("x")


def test_load_profile_auto_empty_patterns_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment = _test_environment(monkeypatch, tmp_path)
    environment.write_global_config(**{
        "chatlas": {
            "taggers": {
                "x": {
                    "tags": ["a"],
                    "auto": {"a": {"method": "regex", "patterns": []}},
                },
            },
        },
    })
    with pytest.raises(CliError, match="non-empty list"):
        load_tagger_profile("x")


def test_load_profile_auto_bad_turn_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment = _test_environment(monkeypatch, tmp_path)
    environment.write_global_config(**{
        "chatlas": {
            "taggers": {
                "x": {
                    "tags": ["a"],
                    "auto": {"a": {"method": "regex", "patterns": [{"turn": 0, "regex": "z"}]}},
                },
            },
        },
    })
    with pytest.raises(CliError, match="positive integer"):
        load_tagger_profile("x")


@pytest.mark.parametrize("bad_rate", [-0.1, 1.5, "x", True])
def test_load_profile_bad_auto_test_rate_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_rate: object
) -> None:
    environment = _test_environment(monkeypatch, tmp_path)
    environment.write_global_config(**{
        "chatlas": {
            "taggers": {
                "x": {"tags": ["a"], "auto_test_rate": bad_rate},
            },
        },
    })
    with pytest.raises(CliError, match="auto_test_rate"):
        load_tagger_profile("x")


def _row_with_excerpt(excerpt: str | None) -> dict[str, Any]:
    row: dict[str, Any] = {"identity_hash": "ab12"}
    if excerpt is not None:
        row["summary"] = {"first_user_text_excerpt": excerpt}
    return row


def _compile_one_pattern(turn: int, regex: str) -> dict[str, Any]:
    import re as _re

    return {"agentic-session": [(turn, _re.compile(regex), regex)]}


def test_auto_match_turn1_hit() -> None:
    row = _row_with_excerpt(
        "Use md-library-pkg (including references/transcript-spec.md)"
    )
    compiled = _compile_one_pattern(
        1, r"^Use md-library-pkg \(including references/transcript-spec\.md\)"
    )
    result = auto_match(row, compiled, chatlas_root=None, session_model_cache={})
    assert result is not None
    tag, info = result
    assert tag == "agentic-session"
    assert info["turn"] == 1


def test_auto_match_turn1_miss() -> None:
    row = _row_with_excerpt("just some normal user prose")
    compiled = _compile_one_pattern(1, r"^Use md-library-pkg")
    assert auto_match(row, compiled, chatlas_root=None, session_model_cache={}) is None


def test_auto_match_empty_compiled_returns_none() -> None:
    row = _row_with_excerpt("anything")
    assert auto_match(row, {}, chatlas_root=None, session_model_cache={}) is None


def test_auto_match_missing_summary_returns_none() -> None:
    compiled = _compile_one_pattern(1, r"^anything")
    assert (
        auto_match(
            {"identity_hash": "ab12"},
            compiled,
            chatlas_root=None,
            session_model_cache={},
        )
        is None
    )


def test_auto_match_first_match_wins() -> None:
    row = _row_with_excerpt("Run: iterante execute --template foo")
    import re as _re

    compiled = {
        "agentic-session": [
            (1, _re.compile(r"^Use md-library-pkg"), "^Use md-library-pkg"),
            (1, _re.compile(r"^Run: iterante execute"), "^Run: iterante execute"),
        ],
    }
    result = auto_match(row, compiled, chatlas_root=None, session_model_cache={})
    assert result is not None
    _, info = result
    assert info["regex"] == "^Run: iterante execute"


def test_auto_match_turn2_loads_session_model(monkeypatch: pytest.MonkeyPatch) -> None:
    row = {"identity_hash": "ab12", "summary": {"first_user_text_excerpt": "hello"}}
    load_calls: list[dict[str, Any]] = []

    import tarav.chatlas.tagger as tagger_module

    def fake_load(r: dict[str, Any]) -> dict[str, Any]:
        load_calls.append(r)
        return {"fake": True}

    def fake_visible(model: dict[str, Any], *, normal_turn_kinds: set[str]) -> list[str]:
        assert normal_turn_kinds == {"user"}
        assert model == {"fake": True}
        return ["hello", "Run: iterante execute --template foo"]

    monkeypatch.setattr(tagger_module, "load_chatlas_session_model", fake_load)
    monkeypatch.setattr(tagger_module, "visible_message_texts", fake_visible)

    compiled = _compile_one_pattern(2, r"^Run: iterante execute")
    cache: dict[str, Any] = {}
    result = auto_match(row, compiled, chatlas_root=None, session_model_cache=cache)
    assert result is not None
    assert result[0] == "agentic-session"
    assert len(load_calls) == 1
    assert cache["user_turns"] == ["hello", "Run: iterante execute --template foo"]


def test_auto_match_caches_session_model_across_patterns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {"identity_hash": "ab12", "summary": {"first_user_text_excerpt": "hi"}}
    load_calls: list[dict[str, Any]] = []

    import tarav.chatlas.tagger as tagger_module

    def fake_load(r: dict[str, Any]) -> dict[str, Any]:
        load_calls.append(r)
        return {"x": 1}

    def fake_visible(model: dict[str, Any], *, normal_turn_kinds: set[str]) -> list[str]:
        assert normal_turn_kinds == {"user"}
        return ["hi", "second", "third"]

    monkeypatch.setattr(tagger_module, "load_chatlas_session_model", fake_load)
    monkeypatch.setattr(tagger_module, "visible_message_texts", fake_visible)

    import re as _re

    compiled = {
        "agentic-session": [
            (2, _re.compile(r"^nope$"), "^nope$"),
            (3, _re.compile(r"^third$"), "^third$"),
        ],
    }
    cache: dict[str, Any] = {}
    result = auto_match(row, compiled, chatlas_root=None, session_model_cache=cache)
    assert result is not None
    assert result[1]["turn"] == 3
    assert len(load_calls) == 1


def test_random_sampling_with_seed_is_deterministic() -> None:
    import random as _random

    rng_a = _random.Random(0)
    rng_b = _random.Random(0)
    draws_a = [rng_a.random() for _ in range(10)]
    draws_b = [rng_b.random() for _ in range(10)]
    assert draws_a == draws_b


def test_disagreement_record_shape() -> None:
    disagreement = {
        "identity_hash": "ab12",
        "auto_predicted": "agentic-session",
        "user_picked": "hugentic-session",
    }
    assert disagreement["auto_predicted"] != disagreement["user_picked"]
    assert set(disagreement.keys()) == {
        "identity_hash",
        "auto_predicted",
        "user_picked",
    }


def test_auto_match_load_failure_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    row = {"identity_hash": "ab12"}
    import tarav.chatlas.tagger as tagger_module

    def fake_load(r: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(tagger_module, "load_chatlas_session_model", fake_load)

    compiled = _compile_one_pattern(2, r"^anything")
    cache: dict[str, Any] = {}
    assert (
        auto_match(row, compiled, chatlas_root=None, session_model_cache=cache) is None
    )
    assert cache["user_turns"] == []
