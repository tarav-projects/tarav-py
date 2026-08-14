# $kw: --from Session.Identity
from __future__ import annotations

import json
import random
import re
import sys
import termios
import tty
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from tarav._core.errors import CliError
from tarav._core.project import global_config_path

from tarav.chatlas.annotations import add_session_tag, remove_session_tag
from tarav.chatlas.query import chatlas_query
from tarav.chatlas.normalization.session_model.messages import visible_message_texts
from tarav.chatlas.time_interface import format_local_timestamp
from tarav.chatlas.views import load_chatlas_session_model

_MORE_TURNS_BATCH = 3

_MAX_TAGS_PER_PROFILE = 9

_DEFAULT_AUTO_TEST_RATE = 0.1

CompiledAutoPatterns = dict[str, list[tuple[int, re.Pattern[str], str]]]


def load_tagger_profile(name: str, *, home_dir: Path | None = None) -> dict[str, Any]:
    config_path = global_config_path(home_dir=home_dir)
    if not config_path.is_file():
        raise CliError(f"tarav config not found at {config_path}")
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"tarav config at {config_path} is not valid JSON: {exc}")
    if not isinstance(payload, dict):
        raise CliError(f"tarav config at {config_path} is not a JSON object")
    taggers = payload.get("chatlas", {}).get("taggers") if isinstance(payload.get("chatlas"), dict) else None
    if not isinstance(taggers, dict):
        raise CliError(f"no `chatlas.taggers` section in {config_path}")
    profile = taggers.get(name)
    if not isinstance(profile, dict):
        raise CliError(f"no tagger profile `{name}` in {config_path}")
    tags = profile.get("tags")
    if not isinstance(tags, list) or not tags or not all(isinstance(t, str) and t for t in tags):
        raise CliError(f"profile `{name}` must define `tags` as a non-empty list of non-empty strings")
    if len(tags) > _MAX_TAGS_PER_PROFILE:
        raise CliError(
            f"profile `{name}` has {len(tags)} tags; v1 supports at most {_MAX_TAGS_PER_PROFILE} (digit keys 1-9)"
        )
    auto_test_rate = _validate_auto_test_rate(profile.get("auto_test_rate"), profile_name=name)
    compiled_auto = _compile_auto(profile.get("auto"), tags=list(tags), profile_name=name)
    return {
        "name": name,
        "tags": list(tags),
        "auto_test_rate": auto_test_rate,
        "compiled_auto": compiled_auto,
    }


def _validate_auto_test_rate(value: Any, *, profile_name: str) -> float:
    if value is None:
        return _DEFAULT_AUTO_TEST_RATE
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CliError(
            f"profile `{profile_name}`: auto_test_rate must be a number in [0.0, 1.0]"
        )
    rate = float(value)
    if not (0.0 <= rate <= 1.0):
        raise CliError(
            f"profile `{profile_name}`: auto_test_rate must be in [0.0, 1.0]; got {rate}"
        )
    return rate


def _compile_auto(
    auto: Any,
    *,
    tags: list[str],
    profile_name: str,
) -> CompiledAutoPatterns:
    if auto is None:
        return {}
    if not isinstance(auto, dict):
        raise CliError(f"profile `{profile_name}`: auto must be an object")
    compiled: CompiledAutoPatterns = {}
    for tag, spec in auto.items():
        if tag not in tags:
            raise CliError(
                f"profile `{profile_name}`: auto refers to unknown tag `{tag}`"
            )
        if not isinstance(spec, dict):
            raise CliError(f"profile `{profile_name}`: auto.`{tag}` must be an object")
        method = spec.get("method")
        if method != "regex":
            raise CliError(
                f"profile `{profile_name}`: auto.`{tag}`.method must be `regex` (v1)"
            )
        patterns = spec.get("patterns")
        if not isinstance(patterns, list) or not patterns:
            raise CliError(
                f"profile `{profile_name}`: auto.`{tag}`.patterns must be a non-empty list"
            )
        compiled_patterns: list[tuple[int, re.Pattern[str], str]] = []
        for i, pattern in enumerate(patterns):
            if not isinstance(pattern, dict):
                raise CliError(
                    f"profile `{profile_name}`: auto.`{tag}`.patterns[{i}] must be an object"
                )
            regex_str = pattern.get("regex")
            if not isinstance(regex_str, str) or not regex_str:
                raise CliError(
                    f"profile `{profile_name}`: auto.`{tag}`.patterns[{i}].regex must be a non-empty string"
                )
            turn = pattern.get("turn", 1)
            if isinstance(turn, bool) or not isinstance(turn, int) or turn < 1:
                raise CliError(
                    f"profile `{profile_name}`: auto.`{tag}`.patterns[{i}].turn must be a positive integer"
                )
            try:
                compiled_regex = re.compile(regex_str)
            except re.error as exc:
                raise CliError(
                    f"profile `{profile_name}`: auto.`{tag}`.patterns[{i}].regex is invalid: {exc}"
                )
            compiled_patterns.append((turn, compiled_regex, regex_str))
        compiled[tag] = compiled_patterns
    return compiled


def auto_match(
    row: dict[str, Any],
    compiled_auto: CompiledAutoPatterns,
    *,
    chatlas_root: Path | None,
    session_model_cache: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    if not compiled_auto:
        return None
    for tag, patterns in compiled_auto.items():
        for turn, regex, regex_str in patterns:
            text = _user_turn_text(
                row,
                turn,
                chatlas_root=chatlas_root,
                session_model_cache=session_model_cache,
            )
            if text is None:
                continue
            if regex.search(text):
                return tag, {"turn": turn, "regex": regex_str}
    return None


def _user_turn_text(
    row: dict[str, Any],
    turn: int,
    *,
    chatlas_root: Path | None,
    session_model_cache: dict[str, Any],
) -> str | None:
    if turn == 1:
        summary = row.get("summary")
        if isinstance(summary, dict):
            excerpt = summary.get("first_user_text_excerpt")
            if isinstance(excerpt, str):
                return excerpt
        return None
    if "user_turns" not in session_model_cache:
        try:
            session_model = load_chatlas_session_model(row)
        except Exception:
            session_model_cache["user_turns"] = []
            return None
        session_model_cache["user_turns"] = list(
            visible_message_texts(session_model, normal_turn_kinds={"user"})
        )
    user_turns: list[str] = session_model_cache["user_turns"]
    if 1 <= turn <= len(user_turns):
        return user_turns[turn - 1]
    return None


def iter_unreviewed(
    profile: dict[str, Any],
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
) -> Iterator[dict[str, Any]]:
    payload = chatlas_query(
        sort="newest",
        providers=providers,
        without_tags=tuple(profile["tags"]),
        chatlas_root=chatlas_root,
        row_shape="full",
        limit=10_000,
    )
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return
    for row in rows:
        if isinstance(row, dict):
            yield row


def render_session(row: dict[str, Any]) -> str:
    identity_hash = row.get("identity_hash") or ""
    short_id = identity_hash[:12] if isinstance(identity_hash, str) else ""
    provider = row.get("provider") or "?"
    project_path = row.get("project_path") or "(no project)"
    last_activity_at = row.get("last_activity_at")
    last_activity = (
        format_local_timestamp(last_activity_at) if last_activity_at else "?"
    )
    summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
    user_turns = summary.get("visible_user_turn_count") if isinstance(summary, dict) else None
    assistant_turns = summary.get("visible_assistant_turn_count") if isinstance(summary, dict) else None
    excerpt = summary.get("first_user_text_excerpt") if isinstance(summary, dict) else None
    lines = [
        f"identity_hash : {short_id}  ({identity_hash})",
        f"provider      : {provider}",
        f"project_path  : {project_path}",
        f"last_activity : {last_activity}",
        f"turns         : user={user_turns} assistant={assistant_turns}",
        "",
        "first user turn:",
        (excerpt or "(no excerpt available)"),
    ]
    return "\n".join(lines)


def run_tagger(
    *,
    profile_name: str,
    providers: tuple[str, ...] | None = None,
    limit: int | None = None,
    auto_test_rate: float | None = None,
    random_seed: int | None = None,
    chatlas_root: Path | None = None,
) -> int:
    profile = load_tagger_profile(profile_name)
    tags: list[str] = profile["tags"]
    compiled_auto = profile["compiled_auto"]
    effective_rate = auto_test_rate if auto_test_rate is not None else profile["auto_test_rate"]
    if not (0.0 <= effective_rate <= 1.0):
        raise CliError(f"auto_test_rate must be in [0.0, 1.0]; got {effective_rate}")
    rng = random.Random(random_seed) if random_seed is not None else random.Random()
    rows = list(iter_unreviewed(profile, providers=providers, chatlas_root=chatlas_root))
    tagged_ids: set[str] = set()
    skipped_ids: set[str] = set()
    auto_tagged = 0
    auto_test_count = 0
    auto_test_agreements = 0
    auto_test_disagreements: list[dict[str, str]] = []
    pending_test_predictions: dict[int, str] = {}
    extra_turns: dict[int, list[str]] = {}
    loaded_user_turns: dict[int, list[str]] = {}
    cursor = 0

    while cursor < len(rows):
        if limit is not None and len(tagged_ids) >= limit:
            break
        row = rows[cursor]
        identity_hash = row.get("identity_hash")
        if not isinstance(identity_hash, str) or not identity_hash:
            cursor += 1
            continue
        if cursor not in pending_test_predictions:
            auto_match_result = auto_match(
                row,
                compiled_auto,
                chatlas_root=chatlas_root,
                session_model_cache={},
            )
            if auto_match_result is not None:
                matched_tag, _ = auto_match_result
                if effective_rate > 0 and rng.random() < effective_rate:
                    pending_test_predictions[cursor] = matched_tag
                    auto_test_count += 1
                else:
                    add_session_tag(identity_hash, matched_tag, chatlas_root=chatlas_root)
                    auto_tagged += 1
                    cursor += 1
                    continue
        _print_session_prompt(row, tags, extra_turns.get(cursor, []))
        key = _read_single_key()
        if key in ("q", "\x03"):
            print()
            break
        if key.isdigit() and key != "0":
            idx = int(key) - 1
            if 0 <= idx < len(tags):
                chosen = tags[idx]
                for prior in tags:
                    if prior != chosen:
                        remove_session_tag(identity_hash, prior, chatlas_root=chatlas_root)
                add_session_tag(identity_hash, chosen, chatlas_root=chatlas_root)
                tagged_ids.add(identity_hash)
                skipped_ids.discard(identity_hash)
                if cursor in pending_test_predictions:
                    predicted = pending_test_predictions.pop(cursor)
                    if predicted == chosen:
                        auto_test_agreements += 1
                    else:
                        auto_test_disagreements.append({
                            "identity_hash": identity_hash,
                            "auto_predicted": predicted,
                            "user_picked": chosen,
                        })
                print(f"\n  → tagged: {chosen}\n")
                cursor += 1
                continue
        if key == "s":
            skipped_ids.add(identity_hash)
            print("\n  → skipped\n")
            cursor += 1
            continue
        if key == "m":
            _load_more_turns(cursor, row, extra_turns, loaded_user_turns)
            continue
        if key == "b":
            if cursor > 0:
                cursor -= 1
                print("\n  → back\n")
            else:
                print("\n  → already at first session\n")
            continue
        print(f"\n  → (unrecognized key {key!r}; press 1-{len(tags)} / m / s / b / q)\n")

    print(json.dumps({
        "status": "ok",
        "command": "chatlas utils tagger",
        "profile": profile["name"],
        "tagged": len(tagged_ids),
        "auto_tagged": auto_tagged,
        "auto_test_count": auto_test_count,
        "auto_test_agreements": auto_test_agreements,
        "auto_test_disagreements": auto_test_disagreements,
        "skipped": len(skipped_ids),
        "remaining_unreviewed": max(0, len(rows) - cursor),
    }))
    return 0


def _load_more_turns(
    cursor: int,
    row: dict[str, Any],
    extra_turns: dict[int, list[str]],
    loaded_user_turns: dict[int, list[str]],
) -> None:
    if cursor not in loaded_user_turns:
        try:
            session_model = load_chatlas_session_model(row)
        except Exception as exc:
            print(f"\n  → failed to load session model: {exc}\n")
            loaded_user_turns[cursor] = []
            return
        loaded_user_turns[cursor] = list(visible_message_texts(session_model, normal_turn_kinds={"user"}))
    all_turns = loaded_user_turns[cursor]
    shown = extra_turns.get(cursor, [])
    next_shown_count = min(len(all_turns), len(shown) + _MORE_TURNS_BATCH)
    if next_shown_count <= len(shown):
        print("\n  → no more user turns\n")
        return
    extra_turns[cursor] = all_turns[:next_shown_count]


def _print_session_prompt(row: dict[str, Any], tags: list[str], extra_user_turns: list[str]) -> None:
    print("=" * 72)
    print(render_session(row))
    if len(extra_user_turns) > 1:
        for i, turn in enumerate(extra_user_turns[1:], start=2):
            print()
            print(f"user turn {i}:")
            print(turn)
    print()
    options = "  ".join(f"[{i + 1}] {tag}" for i, tag in enumerate(tags))
    print(f"{options}  [m] more  [s] skip  [b] back  [q] quit")
    print("> ", end="", flush=True)


def _read_single_key() -> str:
    if not sys.stdin.isatty():
        raise CliError("chatlas tagger requires an interactive TTY for keyboard input")
    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
    return ch


__all__ = [
    "load_tagger_profile",
    "iter_unreviewed",
    "render_session",
    "run_tagger",
    "auto_match",
]
