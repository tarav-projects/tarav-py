from __future__ import annotations

import os
from pathlib import Path

from agentos.cli import main


def _create_skill(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text("# skill\n", encoding="utf-8")


def test_skills_flatten_creates_symlink_for_nested_skill(tmp_path: Path, capsys) -> None:
    skills_root = tmp_path / "skills"
    nested_skill = skills_root / "group-one" / "alpha-skill"
    _create_skill(nested_skill)

    assert main(["skills", "flatten", str(skills_root)]) == 0
    capsys.readouterr()

    flattened_link = skills_root / "alpha-skill"
    assert flattened_link.is_symlink()
    assert flattened_link.resolve() == nested_skill.resolve()


def test_skills_flatten_defaults_to_current_directory(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    nested_skill = tmp_path / "group-one" / "alpha-skill"
    _create_skill(nested_skill)
    monkeypatch.chdir(tmp_path)

    assert main(["skills", "flatten"]) == 0
    capsys.readouterr()

    flattened_link = tmp_path / "alpha-skill"
    assert flattened_link.is_symlink()
    assert flattened_link.resolve() == nested_skill.resolve()


def test_skills_flatten_dry_run_does_not_create_symlink(tmp_path: Path, capsys) -> None:
    skills_root = tmp_path / "skills"
    nested_skill = skills_root / "group-one" / "alpha-skill"
    _create_skill(nested_skill)

    assert main(["skills", "flatten", str(skills_root), "--dry-run"]) == 0
    stdout = capsys.readouterr().out

    flattened_link = skills_root / "alpha-skill"
    assert not flattened_link.exists()
    assert "DRY-RUN would create:" in stdout
    assert "Dry run: no symlinks were created or replaced." in stdout


def test_skills_flatten_ignores_top_level_skills(tmp_path: Path, capsys) -> None:
    skills_root = tmp_path / "skills"
    top_level_skill = skills_root / "alpha-skill"
    _create_skill(top_level_skill)

    assert main(["skills", "flatten", str(skills_root), "--dry-run"]) == 0
    captured = capsys.readouterr()

    assert "No symlinks would be created." in captured.out
    assert "warn:" not in captured.err
    assert top_level_skill.is_dir()
    assert not top_level_skill.is_symlink()


def test_skills_flatten_noops_for_existing_matching_symlink(tmp_path: Path, capsys) -> None:
    skills_root = tmp_path / "skills"
    nested_skill = skills_root / "group-one" / "alpha-skill"
    _create_skill(nested_skill)

    flattened_link = skills_root / "alpha-skill"
    flattened_link.parent.mkdir(parents=True, exist_ok=True)
    flattened_link.symlink_to(Path("group-one") / "alpha-skill", target_is_directory=True)

    assert main(["skills", "flatten", str(skills_root)]) == 0
    stdout = capsys.readouterr().out

    assert "No new symlinks created." in stdout
    assert "info: skipping nested skill source" in stdout
    assert str(nested_skill.resolve()) in stdout
    assert str(flattened_link) in stdout
    assert "Skipped 1 existing matching symlink(s)." in stdout
    assert flattened_link.is_symlink()
    assert flattened_link.resolve() == nested_skill.resolve()


def test_skills_flatten_warns_and_skips_when_target_path_exists(tmp_path: Path, capsys) -> None:
    skills_root = tmp_path / "skills"
    nested_skill = skills_root / "group-one" / "alpha-skill"
    _create_skill(nested_skill)

    conflicting_path = skills_root / "alpha-skill"
    conflicting_path.parent.mkdir(parents=True, exist_ok=True)
    conflicting_path.mkdir()

    assert main(["skills", "flatten", str(skills_root)]) == 0
    captured = capsys.readouterr()
    assert "No new symlinks created." in captured.out
    assert "Skipped 1 conflicting existing path(s)." in captured.out
    assert "warn: skipping nested skill source" in captured.err
    assert str(nested_skill.resolve()) in captured.err
    assert str(conflicting_path.resolve()) in captured.err
    assert conflicting_path.is_dir()
    assert not conflicting_path.is_symlink()


def test_skills_flatten_dry_run_warns_and_skips_when_target_path_exists(
    tmp_path: Path,
    capsys,
) -> None:
    skills_root = tmp_path / "skills"
    nested_skill = skills_root / "group-one" / "alpha-skill"
    _create_skill(nested_skill)

    conflicting_path = skills_root / "alpha-skill"
    conflicting_path.parent.mkdir(parents=True, exist_ok=True)
    conflicting_path.mkdir()

    assert main(["skills", "flatten", str(skills_root), "--dry-run"]) == 0
    captured = capsys.readouterr()
    assert "No symlinks would be created." in captured.out
    assert "Skipped 1 conflicting existing path(s)." in captured.out
    assert "warn: skipping nested skill source" in captured.err
    assert str(nested_skill.resolve()) in captured.err
    assert str(conflicting_path.resolve()) in captured.err
    assert conflicting_path.is_dir()
    assert not conflicting_path.is_symlink()


def test_skills_flatten_errors_for_duplicate_nested_skill_names(tmp_path: Path, capsys) -> None:
    skills_root = tmp_path / "skills"
    _create_skill(skills_root / "group-one" / "alpha-skill")
    _create_skill(skills_root / "group-two" / "alpha-skill")

    assert main(["skills", "flatten", str(skills_root)]) == 1
    stderr = capsys.readouterr().err
    assert "duplicate nested skill names under" in stderr


def test_skills_flatten_creates_symlink_for_hidden_nested_skill(tmp_path: Path, capsys) -> None:
    skills_root = tmp_path / "skills"
    nested_skill = skills_root / ".system" / "alpha-skill"
    _create_skill(nested_skill)

    assert main(["skills", "flatten", str(skills_root)]) == 0
    capsys.readouterr()

    flattened_link = skills_root / "alpha-skill"
    assert flattened_link.is_symlink()
    assert os.readlink(flattened_link) == str(Path(".system") / "alpha-skill")
    assert flattened_link.resolve() == nested_skill.resolve()


def test_skills_flatten_creates_symlink_for_nested_skill_under_symlinked_dir(
    tmp_path: Path,
    capsys,
) -> None:
    skills_root = tmp_path / "skills"
    external_bundle = tmp_path / "bundle"
    nested_skill = external_bundle / "group-one" / "alpha-skill"
    _create_skill(nested_skill)

    skills_root.mkdir(parents=True, exist_ok=True)
    (skills_root / "linked-bundle").symlink_to(external_bundle, target_is_directory=True)

    assert main(["skills", "flatten", str(skills_root)]) == 0
    capsys.readouterr()

    flattened_link = skills_root / "alpha-skill"
    assert flattened_link.is_symlink()
    assert os.readlink(flattened_link) == str(Path("linked-bundle") / "group-one" / "alpha-skill")
    assert flattened_link.resolve() == nested_skill.resolve()


def test_skills_flatten_overwrite_replaces_conflicting_symlink(tmp_path: Path, capsys) -> None:
    skills_root = tmp_path / "skills"
    nested_skill = skills_root / "group-one" / "alpha-skill"
    wrong_target = skills_root / "group-two" / "beta-skill"
    _create_skill(nested_skill)
    _create_skill(wrong_target)

    flattened_link = skills_root / "alpha-skill"
    flattened_link.symlink_to(Path("group-two") / "beta-skill", target_is_directory=True)

    assert main(["skills", "flatten", str(skills_root), "--overwrite"]) == 0
    stdout = capsys.readouterr().out

    assert str(flattened_link) in stdout
    assert "Replaced 1 conflicting symlink(s)." in stdout
    assert flattened_link.is_symlink()
    assert flattened_link.resolve() == nested_skill.resolve()


def test_skills_flatten_overwrite_dry_run_does_not_replace_conflicting_symlink(
    tmp_path: Path,
    capsys,
) -> None:
    skills_root = tmp_path / "skills"
    nested_skill = skills_root / "group-one" / "alpha-skill"
    wrong_target = skills_root / "group-two" / "beta-skill"
    _create_skill(nested_skill)
    _create_skill(wrong_target)

    flattened_link = skills_root / "alpha-skill"
    flattened_link.symlink_to(Path("group-two") / "beta-skill", target_is_directory=True)

    assert main(["skills", "flatten", str(skills_root), "--overwrite", "--dry-run"]) == 0
    stdout = capsys.readouterr().out

    assert f"DRY-RUN would replace: {flattened_link}" in stdout
    assert "Would replace 1 conflicting symlink(s)." in stdout
    assert "Dry run: no symlinks were created or replaced." in stdout
    assert flattened_link.is_symlink()
    assert flattened_link.resolve() == wrong_target.resolve()


def test_skills_flatten_overwrite_still_warns_and_skips_non_symlink_conflicts(
    tmp_path: Path,
    capsys,
) -> None:
    skills_root = tmp_path / "skills"
    nested_skill = skills_root / "group-one" / "alpha-skill"
    _create_skill(nested_skill)

    conflicting_path = skills_root / "alpha-skill"
    conflicting_path.parent.mkdir(parents=True, exist_ok=True)
    conflicting_path.mkdir()

    assert main(["skills", "flatten", str(skills_root), "--overwrite"]) == 0
    captured = capsys.readouterr()

    assert "Skipped 1 conflicting existing path(s)." in captured.out
    assert "warn: skipping nested skill source" in captured.err
    assert conflicting_path.is_dir()
    assert not conflicting_path.is_symlink()


def test_skills_prune_removes_broken_symlink(tmp_path: Path, capsys) -> None:
    skills_root = tmp_path / "skills"
    broken_link = skills_root / "alpha-skill"
    broken_link.parent.mkdir(parents=True, exist_ok=True)
    broken_link.symlink_to(Path("missing-alpha-skill"), target_is_directory=True)

    assert main(["skills", "prune", str(skills_root)]) == 0
    stdout = capsys.readouterr().out

    assert str(broken_link) in stdout
    assert not broken_link.exists()
    assert not broken_link.is_symlink()


def test_skills_prune_defaults_to_current_directory(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    broken_link = tmp_path / "alpha-skill"
    broken_link.symlink_to(Path("missing-alpha-skill"), target_is_directory=True)
    monkeypatch.chdir(tmp_path)

    assert main(["skills", "prune"]) == 0
    stdout = capsys.readouterr().out

    assert str(broken_link) in stdout
    assert not broken_link.exists()
    assert not broken_link.is_symlink()


def test_skills_prune_dry_run_does_not_remove_broken_symlink(tmp_path: Path, capsys) -> None:
    skills_root = tmp_path / "skills"
    broken_link = skills_root / "alpha-skill"
    broken_link.parent.mkdir(parents=True, exist_ok=True)
    broken_link.symlink_to(Path("missing-alpha-skill"), target_is_directory=True)

    assert main(["skills", "prune", str(skills_root), "--dry-run"]) == 0
    stdout = capsys.readouterr().out

    assert f"DRY-RUN would remove: {broken_link}" in stdout
    assert "Dry run: no symlinks were removed." in stdout
    assert broken_link.is_symlink()
    assert not broken_link.exists()


def test_skills_prune_ignores_non_broken_entries(tmp_path: Path, capsys) -> None:
    skills_root = tmp_path / "skills"
    real_skill = skills_root / "group-one" / "alpha-skill"
    _create_skill(real_skill)

    working_link = skills_root / "alpha-skill"
    working_link.symlink_to(Path("group-one") / "alpha-skill", target_is_directory=True)

    assert main(["skills", "prune", str(skills_root), "--dry-run"]) == 0
    captured = capsys.readouterr()

    assert "No broken symlinks would be removed." in captured.out
    assert "warn:" not in captured.err
    assert working_link.is_symlink()
    assert working_link.resolve() == real_skill.resolve()


def test_skills_prune_removes_broken_symlink_in_hidden_nested_dir(tmp_path: Path, capsys) -> None:
    skills_root = tmp_path / "skills"
    broken_link = skills_root / ".system" / "alpha-skill"
    broken_link.parent.mkdir(parents=True, exist_ok=True)
    broken_link.symlink_to(Path("missing-alpha-skill"), target_is_directory=True)

    assert main(["skills", "prune", str(skills_root)]) == 0
    stdout = capsys.readouterr().out

    assert str(broken_link) in stdout
    assert not broken_link.exists()
    assert not broken_link.is_symlink()
