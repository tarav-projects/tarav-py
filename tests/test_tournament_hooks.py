# $kw: ^test-tournament-hooks --from Tournament.Hook --note [DF] boundary tests for hook defaults, snapshot execution, return validation, and purity enforcement ^<anchor-on-landing>
from __future__ import annotations

from pathlib import Path

import pytest

from agentos.tournament import (
    HookPurityError,
    HookReturnError,
    TournamentStore,
    load_definition,
    open_definition,
)


DEFINITION = '''
def render_match(ctx):
    return f"{ctx.question}\\nA: {ctx.presented[0]}\\nB: {ctx.presented[1]}"


def match_identity(ctx):
    return "id-" + "-".join(sorted(ctx.players))
'''


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "definition.py"
    path.write_text(body, encoding="utf-8")
    return path


def _tournament(tmp_path: Path, path: Path):
    store = TournamentStore(tmp_path / "tournament")
    return store, store.create_tournament(
        definition_path=str(path),
        definition_digest="sha256:" + "0" * 64,
        players=("alpha", "beta"),
    )


def test_zero_hook_definition_runs_end_to_end(tmp_path: Path) -> None:
    path = _write(tmp_path, "question = 'which line better follows its type?'\n")
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")

    rendered = definition.render_match(players=("alpha", "beta"), presented=("beta", "alpha"))
    identity = definition.match_identity(
        players=("alpha", "beta"), presented=("beta", "alpha"), rendering=rendered
    )

    assert "alpha" in rendered and "beta" in rendered
    assert identity.startswith("sha256:")


def test_default_identity_is_a_hash_of_the_rendering(tmp_path: Path) -> None:
    path = _write(tmp_path, "question = 'q'\n")
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")

    first = definition.match_identity(
        players=("a", "b"), presented=("a", "b"), rendering="same text"
    )
    second = definition.match_identity(
        players=("b", "a"), presented=("b", "a"), rendering="same text"
    )
    third = definition.match_identity(
        players=("a", "b"), presented=("a", "b"), rendering="other text"
    )

    assert first == second
    assert first != third


def test_snapshot_is_executed_after_the_origin_changes(tmp_path: Path) -> None:
    path = _write(tmp_path, DEFINITION + "\nquestion = 'original'\n")
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")

    path.write_text(DEFINITION + "\nquestion = 'edited'\n", encoding="utf-8")

    rendered = definition.render_match(players=("alpha", "beta"), presented=("alpha", "beta"))
    assert "original" in rendered
    assert "edited" not in rendered


def test_snapshot_records_its_origin_and_digest(tmp_path: Path) -> None:
    path = _write(tmp_path, DEFINITION)
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")

    assert definition.origin_path == path.resolve()
    assert definition.digest.startswith("sha256:")
    assert definition.snapshot_path.is_file()


def test_hook_returning_the_wrong_type_is_rejected_at_the_boundary(tmp_path: Path) -> None:
    path = _write(tmp_path, "def render_match(ctx):\n    return 17\n")
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")

    with pytest.raises(HookReturnError) as excinfo:
        definition.render_match(players=("a", "b"), presented=("a", "b"))
    assert "render_match" in str(excinfo.value)


def test_hook_returning_an_empty_identity_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "def match_identity(ctx):\n    return '  '\n")
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")

    with pytest.raises(HookReturnError):
        definition.match_identity(
            players=("a", "b"), presented=("a", "b"), rendering="text"
        )


def test_hook_writing_a_guarded_file_raises_a_purity_violation(tmp_path: Path) -> None:
    guarded = tmp_path / "guarded.json"
    guarded.write_text("{}", encoding="utf-8")
    body = (
        "from pathlib import Path\n\n"
        "def render_match(ctx):\n"
        f"    Path({str(guarded)!r}).write_text('tampered', encoding='utf-8')\n"
        "    return 'text'\n"
    )
    path = _write(tmp_path, body)
    definition = load_definition(
        path, snapshot_dir=tmp_path / "snap", guarded_paths=(guarded,)
    )

    with pytest.raises(HookPurityError):
        definition.render_match(players=("a", "b"), presented=("a", "b"))


def test_hook_editing_its_own_snapshot_raises_a_purity_violation(tmp_path: Path) -> None:
    body = (
        "from pathlib import Path\n\n"
        "def render_match(ctx):\n"
        "    Path(ctx.snapshot_path).write_text('tampered', encoding='utf-8')\n"
        "    return 'text'\n"
    )
    path = _write(tmp_path, body)
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")

    with pytest.raises(HookPurityError):
        definition.render_match(players=("a", "b"), presented=("a", "b"))


def test_reopening_a_snapshot_verifies_it_instead_of_re_snapshotting(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, DEFINITION + "\nquestion = 'frozen'\n")
    created = load_definition(path, snapshot_dir=tmp_path / "snap")

    reopened = open_definition(created.snapshot_path, origin_path=path)

    assert reopened.digest == created.digest
    assert reopened.snapshot_path == created.snapshot_path
    assert "frozen" in reopened.render_match(
        players=("alpha", "beta"), presented=("alpha", "beta")
    )


def test_reopening_a_tampered_snapshot_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, DEFINITION)
    created = load_definition(path, snapshot_dir=tmp_path / "snap")
    created.snapshot_path.write_text("question = 'tampered'\n", encoding="utf-8")

    with pytest.raises(HookPurityError):
        open_definition(created.snapshot_path, origin_path=path)


def test_consumer_slot_hook_contributes_analysis_material(tmp_path: Path) -> None:
    body = (
        "def verdict_slot(ctx):\n"
        "    return {'rendering_length': len(ctx.rendering)}\n"
    )
    path = _write(tmp_path, body)
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")

    slot = definition.verdict_slot(
        players=("a", "b"), presented=("a", "b"), rendering="1234"
    )
    assert slot == {"rendering_length": 4}
